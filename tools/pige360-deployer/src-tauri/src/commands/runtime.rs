use base64::{engine::general_purpose, Engine as _};
use serde_json::{json, Value};
use tauri::{AppHandle, Manager, State, WebviewUrl, WebviewWindowBuilder};

use crate::{
    app_state::SharedState,
    internal_api::{config::InternalApiConfig, server, web_server},
    runtime_config::{self, RuntimeSettings},
};

#[tauri::command]
pub fn internal_api_status(state: State<'_, SharedState>) -> Result<Value, String> {
    let status = server::status()?;
    let web_status = web_server::status().ok();
    let settings_payload = runtime_config::load_settings(state.inner())?;
    let settings = settings_payload.settings;
    let docs_url = status
        .docs_url
        .clone()
        .unwrap_or_else(|| settings.internal_api_docs_url.clone());
    Ok(json!({
        "running": status.running,
        "host": if status.running { status.host.clone() } else { settings.internal_api_host.clone() },
        "port": if status.running { status.port } else { settings.internal_api_port },
        "url": status.url.clone().unwrap_or_else(|| settings.internal_api_base_url.clone()),
        "docs_url": docs_url,
        "started_at": status.started_at.clone(),
        "token_required": settings.internal_api_require_token,
        "token_configured": !settings.internal_api_token.trim().is_empty(),
        "auto_start": settings.internal_api_auto_start,
        "docs_public_local": settings.internal_api_docs_public_local,
        "docs_enabled": settings.internal_api_docs_enabled,
        "docs_path": settings.internal_api_docs_path.clone(),
        "timeout_ms": settings.internal_api_timeout_ms,
        "log_mode": settings.internal_api_log_mode.clone(),
        "settings": settings,
        "ports": settings_payload.ports,
        "warnings": settings_payload.warnings,
        "web_server": web_status,
        "recent_logs": recent_internal_api_logs(state.inner()).unwrap_or_default(),
    }))
}

#[tauri::command]
pub fn internal_api_start(
    state: State<'_, SharedState>,
    host: Option<String>,
    port: Option<u16>,
) -> Result<Value, String> {
    let config = if host.is_some() || port.is_some() {
        let loaded = runtime_config::load_settings(state.inner())?.settings;
        let mut loaded = loaded;
        if let Some(host) = host {
            loaded.internal_api_host = host;
        }
        if let Some(port) = port {
            loaded.internal_api_port = port;
        }
        InternalApiConfig::from_runtime_settings(&loaded)
    } else {
        runtime_config::resolve_internal_api_config(state.inner())?
    };
    let status = server::start_background(state.inner().clone(), config)?;
    serde_json::to_value(status).map_err(|err| err.to_string())
}

#[tauri::command]
pub fn internal_api_stop() -> Result<Value, String> {
    let status = server::stop_background()?;
    serde_json::to_value(status).map_err(|err| err.to_string())
}

#[tauri::command]
pub fn internal_api_restart(
    state: State<'_, SharedState>,
    host: Option<String>,
    port: Option<u16>,
) -> Result<Value, String> {
    let _ = server::stop_background();
    internal_api_start(state, host, port)
}

#[tauri::command]
pub fn runtime_settings_load(state: State<'_, SharedState>) -> Result<Value, String> {
    serde_json::to_value(runtime_config::load_settings(state.inner())?)
        .map_err(|err| err.to_string())
}

#[tauri::command]
pub fn runtime_settings_save(
    state: State<'_, SharedState>,
    settings: RuntimeSettings,
) -> Result<Value, String> {
    let api_was_running = server::status()?.running;
    let web_was_running = web_server::status()?.running;
    let webhook_was_running = crate::native_webhook::server::status()
        .map(|status| status.running)
        .unwrap_or(false);
    let websocket_was_running = crate::native_websocket::server::status()
        .map(|status| status.running)
        .unwrap_or(false);
    let should_restart_api = settings.internal_api_restart_on_config_change && api_was_running;

    let saved = runtime_config::save_settings(state.inner(), settings)?;

    if should_restart_api {
        let _ = server::stop_background();
        let config = runtime_config::resolve_internal_api_config(state.inner())?;
        let _ = server::start_background(state.inner().clone(), config)?;
    }

    if web_was_running || saved.settings.local_web_auto_start {
        let _ = web_server::stop_background();
        if saved.settings.local_web_enabled && saved.settings.local_web_auto_start {
            let _ = web_server::start_background(state.inner().clone());
        }
    }

    if webhook_was_running || saved.settings.webhook_auto_start {
        let _ = crate::native_webhook::server::stop_background();
        if saved.settings.webhook_enabled && saved.settings.webhook_auto_start {
            let _ = crate::native_webhook::server::start_background(state.inner().clone());
        }
    }

    if websocket_was_running || saved.settings.websocket_auto_start {
        let _ = crate::native_websocket::server::stop_background();
        if saved.settings.websocket_enabled && saved.settings.websocket_auto_start {
            let _ = crate::native_websocket::server::start_background(state.inner().clone());
        }
    }

    Ok(json!({
        "env_path": saved.env_path,
        "settings": saved.settings,
        "ports": saved.ports,
        "warnings": saved.warnings,
        "restarted": should_restart_api,
    }))
}

#[tauri::command]
pub fn internal_api_test_port(host: String, port: u16) -> Result<Value, String> {
    let available = runtime_config::is_port_available(&host, port);
    let suggested_port = port;
    Ok(json!({
        "host": host,
        "port": port,
        "available": available,
        "suggested_port": suggested_port,
    }))
}

#[tauri::command]
pub fn internal_api_test(base_url: String, timeout_ms: Option<u64>) -> Result<Value, String> {
    let safe_base_url = normalize_client_base_url(&base_url);
    let url = format!("{}/health", safe_base_url.trim_end_matches('/'));
    let timeout = std::time::Duration::from_millis(timeout_ms.unwrap_or(8000).max(1000));
    let client = reqwest::blocking::Client::builder()
        .timeout(timeout)
        .build()
        .map_err(|err| format!("Falha ao preparar teste da API: {err}"))?;
    let response = client
        .get(&url)
        .send()
        .map_err(|err| format!("Falha ao conectar na API interna em {url}: {err}"))?;
    let status = response.status().as_u16();
    let body = response.text().unwrap_or_default();
    Ok(json!({ "url": url, "status": status, "ok": (200..300).contains(&status), "body": body }))
}

#[tauri::command]
pub fn web_proxy_status() -> Result<Value, String> {
    serde_json::to_value(web_server::status()?).map_err(|err| err.to_string())
}

#[tauri::command]
pub fn web_proxy_start(state: State<'_, SharedState>) -> Result<Value, String> {
    serde_json::to_value(web_server::start_background(state.inner().clone())?)
        .map_err(|err| err.to_string())
}

#[tauri::command]
pub fn web_proxy_stop() -> Result<Value, String> {
    serde_json::to_value(web_server::stop_background()?).map_err(|err| err.to_string())
}

#[tauri::command]
pub fn web_proxy_restart(state: State<'_, SharedState>) -> Result<Value, String> {
    let _ = web_server::stop_background();
    web_proxy_start(state)
}

#[tauri::command]
pub fn runtime_env_example() -> Result<String, String> {
    Ok(runtime_config::default_env_template())
}

#[tauri::command]
pub fn startup_with_windows_set(enabled: bool) -> Result<Value, String> {
    Ok(json!({
        "action": if enabled { "startup-enable" } else { "startup-disable" },
        "implemented": false,
        "status": "managed-by-installer",
        "message": "Inicialização com o sistema não executa cmd, PowerShell, reg.exe, sc.exe ou shell dentro da aplicação. A preferência deve ser aplicada pelo instalador/serviço nativo do aplicativo derivado.",
        "requested": enabled
    }))
}
#[tauri::command]
pub fn app_service_install() -> Result<Value, String> {
    service_action("install")
}
#[tauri::command]
pub fn app_service_uninstall() -> Result<Value, String> {
    service_action("uninstall")
}
#[tauri::command]
pub fn app_service_start() -> Result<Value, String> {
    service_action("start")
}
#[tauri::command]
pub fn app_service_stop() -> Result<Value, String> {
    service_action("stop")
}
#[tauri::command]
pub fn app_service_restart() -> Result<Value, String> {
    let stop = service_action("stop").unwrap_or_else(|err| json!({"stop_error": err}));
    let start = service_action("start")?;
    Ok(json!({"action": "restart", "stop": stop, "start": start}))
}
#[tauri::command]
pub fn app_service_status() -> Result<Value, String> {
    service_action("status")
}

fn service_action(action: &str) -> Result<Value, String> {
    Ok(json!({
        "action": action,
        "implemented": false,
        "status": "managed-by-installer",
        "message": "A aplicação não executa comandos externos para instalar/iniciar/parar serviços. Use o instalador, um helper nativo dedicado ou o serviço do app derivado. Isso remove dependência de cmd, PowerShell, sc.exe e systemctl em tempo de execução."
    }))
}
fn normalize_client_base_url(base_url: &str) -> String {
    let trimmed = base_url.trim();
    if trimmed.is_empty() {
        return "http://127.0.0.1:61001".to_string();
    }
    trimmed
        .replace("http://0.0.0.0:", "http://127.0.0.1:")
        .replace("https://0.0.0.0:", "https://127.0.0.1:")
        .replace("http://[::]:", "http://127.0.0.1:")
        .replace("https://[::]:", "https://127.0.0.1:")
}

fn recent_internal_api_logs(state: &SharedState) -> Result<Vec<Value>, String> {
    let db_path = state.db_path()?;
    let conn = crate::db::open_connection(&db_path)?;
    let mut stmt = conn
        .prepare("SELECT level, message, created_at, details_json FROM app_logs WHERE category='internal-api' ORDER BY id DESC LIMIT 50")
        .map_err(|err| err.to_string())?;
    let rows = stmt
        .query_map([], |row| {
            Ok(json!({
                "level": row.get::<_, String>(0)?,
                "message": row.get::<_, String>(1)?,
                "created_at": row.get::<_, String>(2)?,
                "details_json": row.get::<_, Option<String>>(3)?,
            }))
        })
        .map_err(|err| err.to_string())?;
    let mut logs = Vec::new();
    for row in rows {
        logs.push(row.map_err(|err| err.to_string())?);
    }
    Ok(logs)
}

#[tauri::command]
pub fn open_print_preview(
    app: AppHandle,
    html: Option<String>,
    title: Option<String>,
) -> Result<bool, String> {
    let label = format!("print-preview-{}", chrono::Utc::now().timestamp_millis());
    let safe_title = title.unwrap_or_else(|| "Pré-visualização de impressão".to_string());
    let document = build_print_document(html.unwrap_or_default(), &safe_title);
    let encoded = general_purpose::STANDARD.encode(document.as_bytes());
    let url = url::Url::parse(&format!("data:text/html;base64,{encoded}"))
        .map_err(|err| format!("Falha ao montar preview de impressão: {err}"))?;
    let window = WebviewWindowBuilder::new(&app, label, WebviewUrl::External(url))
        .title(safe_title)
        .inner_size(1100.0, 760.0)
        .resizable(true)
        .center()
        .build()
        .map_err(|err| format!("Falha ao abrir janela de impressão: {err}"))?;
    let _ = window.set_focus();
    Ok(true)
}

fn build_print_document(html: String, title: &str) -> String {
    let body = if html.trim().is_empty() {
        "<main class=\"empty\">Nenhum conteúdo informado para impressão.</main>".to_string()
    } else {
        html
    };
    format!(
        r#"<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <style>
    :root {{ color-scheme: light only; }}
    body {{ margin: 0; background: #eef2f7; color: #172033; font-family: Inter, Arial, sans-serif; }}
    .shell {{ max-width: 980px; margin: 24px auto; background: #fff; border-radius: 16px; box-shadow: 0 18px 50px rgba(15,23,42,.14); overflow: hidden; }}
    header {{ padding: 20px 28px; border-bottom: 1px solid #e2e8f0; display: flex; justify-content: space-between; gap: 16px; }}
    h1 {{ margin: 0; font-size: 18px; }}
    .meta {{ color: #64748b; font-size: 12px; }}
    .content {{ padding: 28px; }}
    .content table {{ width: 100%; border-collapse: collapse; }}
    .content th, .content td {{ border-bottom: 1px solid #e5e7eb; padding: 8px 10px; text-align: left; }}
    .actions {{ position: sticky; bottom: 0; display: flex; justify-content: flex-end; padding: 12px 28px; background: #f8fafc; border-top: 1px solid #e2e8f0; }}
    button {{ border: 0; border-radius: 10px; padding: 10px 16px; background: #2563eb; color: #fff; font-weight: 700; cursor: pointer; }}
    .empty {{ padding: 48px; text-align: center; color: #64748b; border: 1px dashed #cbd5e1; border-radius: 14px; }}
    @media print {{ body {{ background: #fff; }} .shell {{ margin: 0; max-width: none; box-shadow: none; border-radius: 0; }} .actions {{ display: none; }} }}
  </style>
</head>
<body>
  <section class="shell">
    <header>
      <div><h1>{title}</h1><div class="meta">PIGE360 Deployer · Preview de impressão</div></div>
      <div class="meta">Gerado em <span id="now"></span></div>
    </header>
    <div class="content">{body}</div>
    <div class="actions"><button onclick="window.print()">Imprimir</button></div>
  </section>
  <script>document.getElementById('now').textContent = new Date().toLocaleString('pt-BR');</script>
</body>
</html>"#
    )
}

#[tauri::command]
pub fn tray_status() -> Result<Value, String> {
    let enabled = std::env::var("PIGE360_DEPLOYER_TRAY_ENABLED")
        .ok()
        .map(|value| {
            matches!(
                value.trim().to_ascii_lowercase().as_str(),
                "1" | "true" | "yes" | "on"
            )
        })
        .unwrap_or(true);
    let api_status = server::status()?;
    Ok(json!({
        "enabled": enabled,
        "api": api_status,
        "main_window": if enabled { "managed" } else { "tray-disabled" }
    }))
}

#[tauri::command]
pub fn tray_restore_window(app: AppHandle) -> Result<bool, String> {
    if let Some(window) = app.get_webview_window("main") {
        window.show().map_err(|err| err.to_string())?;
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
    Ok(true)
}

#[tauri::command]
pub fn tray_exit_app(app: AppHandle) -> Result<bool, String> {
    app.exit(0);
    Ok(true)
}
