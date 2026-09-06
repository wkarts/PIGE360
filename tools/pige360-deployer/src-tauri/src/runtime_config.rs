use std::{
    collections::{BTreeMap, HashSet},
    env,
    fs::{self, OpenOptions},
    io::Write,
    net::{SocketAddr, TcpListener},
    path::{Path, PathBuf},
};

use chrono::Utc;
use rusqlite::{params, OptionalExtension};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

use crate::{app_state::SharedState, db::open_connection};

pub const ENV_FILE_NAME: &str = ".env";
pub const INTERNAL_API_DEFAULT_PORT: u16 = 61001;
pub const LOCAL_WEB_DEFAULT_PORT: u16 = 61002;
pub const AUXILIARY_DEFAULT_PORT: u16 = 61003;
pub const BRIDGE_CORE_DEFAULT_PORT: u16 = 61004;

struct RuntimePortDefinition {
    key: &'static str,
    label: &'static str,
    env_host_key: &'static str,
    env_port_key: &'static str,
    default_port: u16,
    description: &'static str,
}

const INTERNAL_API_PORT_DEFINITION: RuntimePortDefinition = RuntimePortDefinition {
    key: "internal_api",
    label: "API interna",
    env_host_key: "PIGE360_DEPLOYER_API_HOST",
    env_port_key: "PIGE360_DEPLOYER_API_PORT",
    default_port: INTERNAL_API_DEFAULT_PORT,
    description: "API local Axum usada pelo template em modo desktop/headless.",
};

const LOCAL_WEB_PORT_DEFINITION: RuntimePortDefinition = RuntimePortDefinition {
    key: "local_web",
    label: "Servidor web local",
    env_host_key: "PIGE360_DEPLOYER_WEB_HOST",
    env_port_key: "PIGE360_DEPLOYER_WEB_PORT",
    default_port: LOCAL_WEB_DEFAULT_PORT,
    description: "Servidor web/preview usado em desenvolvimento ou distribuição web local.",
};

const AUXILIARY_PORT_DEFINITION: RuntimePortDefinition = RuntimePortDefinition {
    key: "auxiliary",
    label: "Webhook Service",
    env_host_key: "PIGE360_DEPLOYER_WEBHOOK_HOST",
    env_port_key: "PIGE360_DEPLOYER_WEBHOOK_PORT",
    default_port: AUXILIARY_DEFAULT_PORT,
    description: "Serviço nativo genérico para receber webhooks HTTP por módulo/provedor.",
};

const BRIDGE_CORE_PORT_DEFINITION: RuntimePortDefinition = RuntimePortDefinition {
    key: "bridge_core",
    label: "WebSocket Service",
    env_host_key: "PIGE360_DEPLOYER_WEBSOCKET_HOST",
    env_port_key: "PIGE360_DEPLOYER_WEBSOCKET_PORT",
    default_port: BRIDGE_CORE_DEFAULT_PORT,
    description: "Serviço nativo genérico de WebSocket/eventos em tempo real.",
};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct RuntimeSettings {
    pub internal_api_host: String,
    pub internal_api_port: u16,
    pub internal_api_base_url: String,
    pub internal_api_docs_url: String,
    pub internal_api_auto_start: bool,
    pub internal_api_restart_on_config_change: bool,
    pub internal_api_require_token: bool,
    pub internal_api_allow_public_network: bool,
    pub internal_api_cors_enabled: bool,
    pub internal_api_token_header: String,
    pub internal_api_token: String,
    pub internal_api_docs_public_local: bool,
    pub internal_api_open_scalar_after_start: bool,
    pub internal_api_timeout_ms: u64,
    pub internal_api_log_mode: String,
    pub internal_api_docs_enabled: bool,
    pub internal_api_docs_path: String,
    pub local_web_enabled: bool,
    pub local_web_auto_start: bool,
    pub local_web_host: String,
    pub local_web_port: u16,
    pub auxiliary_host: String,
    pub auxiliary_port: u16,
    pub bridge_core_host: String,
    pub bridge_core_port: u16,
    pub webhook_enabled: bool,
    pub webhook_auto_start: bool,
    pub webhook_host: String,
    pub webhook_port: u16,
    pub webhook_base_path: String,
    pub webhook_token_required: bool,
    pub webhook_token_header: String,
    pub webhook_token: String,
    pub webhook_allow_lan: bool,
    pub webhook_allow_external: bool,
    pub websocket_enabled: bool,
    pub websocket_auto_start: bool,
    pub websocket_host: String,
    pub websocket_port: u16,
    pub websocket_path: String,
    pub websocket_token_required: bool,
    pub websocket_token_query: String,
    pub websocket_token_header: String,
    pub websocket_token: String,
    pub websocket_allow_lan: bool,
    pub websocket_allow_external: bool,
    pub websocket_heartbeat_seconds: u64,
    pub tray_enabled: bool,
    pub minimize_to_tray: bool,
    pub close_to_tray: bool,
    pub start_with_windows: bool,
    pub services_auto_start: bool,
    pub app_service_name: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct RuntimeServicePort {
    pub key: String,
    pub label: String,
    pub env_host_key: String,
    pub env_port_key: String,
    pub default_port: u16,
    pub host: String,
    pub configured_port: u16,
    pub effective_port: u16,
    pub available: bool,
    pub fallback_applied: bool,
    pub description: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct RuntimeSettingsPayload {
    pub env_path: String,
    pub settings: RuntimeSettings,
    pub ports: Vec<RuntimeServicePort>,
    pub warnings: Vec<String>,
}

impl Default for RuntimeSettings {
    fn default() -> Self {
        Self {
            internal_api_host: env_string("PIGE360_DEPLOYER_API_HOST", "127.0.0.1"),
            internal_api_port: env_u16("PIGE360_DEPLOYER_API_PORT", INTERNAL_API_DEFAULT_PORT),
            internal_api_base_url: env_string(
                "PIGE360_DEPLOYER_API_BASE_URL",
                "http://127.0.0.1:61001",
            ),
            internal_api_docs_url: env_string(
                "PIGE360_DEPLOYER_API_SCALAR_URL",
                "http://127.0.0.1:61001/docs",
            ),
            internal_api_auto_start: env_bool("PIGE360_DEPLOYER_API_AUTO_START", true),
            internal_api_restart_on_config_change: env_bool(
                "PIGE360_DEPLOYER_API_RESTART_ON_CONFIG_CHANGE",
                true,
            ),
            internal_api_require_token: env_bool("PIGE360_DEPLOYER_API_REQUIRE_TOKEN", false),
            internal_api_allow_public_network: env_bool(
                "PIGE360_DEPLOYER_API_ALLOW_PUBLIC_NETWORK",
                false,
            ),
            internal_api_cors_enabled: env_bool("PIGE360_DEPLOYER_API_CORS", false),
            internal_api_token_header: env_string("PIGE360_DEPLOYER_API_TOKEN_HEADER", "X-App-Token"),
            internal_api_token: env_string("PIGE360_DEPLOYER_API_TOKEN", ""),
            internal_api_docs_public_local: env_bool("PIGE360_DEPLOYER_API_DOCS_PUBLIC_LOCAL", true),
            internal_api_open_scalar_after_start: env_bool(
                "PIGE360_DEPLOYER_API_OPEN_SCALAR_AFTER_START",
                false,
            ),
            internal_api_timeout_ms: env_u64("PIGE360_DEPLOYER_API_TIMEOUT_MS", 8000),
            internal_api_log_mode: env_string("PIGE360_DEPLOYER_API_LOG_MODE", "normal"),
            internal_api_docs_enabled: env_bool("PIGE360_DEPLOYER_API_SCALAR_ENABLED", true),
            internal_api_docs_path: env_string("PIGE360_DEPLOYER_API_DOCS_PATH", "/docs"),
            local_web_enabled: env_bool(
                "PIGE360_DEPLOYER_WEB_ENABLED",
                !env_bool("PIGE360_DEPLOYER_WEB_DISABLED", false),
            ),
            local_web_auto_start: env_bool("PIGE360_DEPLOYER_WEB_AUTO_START", true),
            local_web_host: env_string("PIGE360_DEPLOYER_WEB_HOST", "127.0.0.1"),
            local_web_port: env_u16("PIGE360_DEPLOYER_WEB_PORT", LOCAL_WEB_DEFAULT_PORT),
            auxiliary_host: env_string("PIGE360_DEPLOYER_WEBHOOK_HOST", "127.0.0.1"),
            auxiliary_port: env_u16("PIGE360_DEPLOYER_WEBHOOK_PORT", AUXILIARY_DEFAULT_PORT),
            bridge_core_host: env_string("PIGE360_DEPLOYER_WEBSOCKET_HOST", "127.0.0.1"),
            bridge_core_port: env_u16("PIGE360_DEPLOYER_WEBSOCKET_PORT", BRIDGE_CORE_DEFAULT_PORT),
            webhook_enabled: env_bool("PIGE360_DEPLOYER_WEBHOOK_ENABLED", false),
            webhook_auto_start: env_bool("PIGE360_DEPLOYER_WEBHOOK_AUTO_START", false),
            webhook_host: env_string("PIGE360_DEPLOYER_WEBHOOK_HOST", "127.0.0.1"),
            webhook_port: env_u16("PIGE360_DEPLOYER_WEBHOOK_PORT", AUXILIARY_DEFAULT_PORT),
            webhook_base_path: env_string("PIGE360_DEPLOYER_WEBHOOK_BASE_PATH", "/webhooks"),
            webhook_token_required: env_bool("PIGE360_DEPLOYER_WEBHOOK_TOKEN_REQUIRED", true),
            webhook_token_header: env_string(
                "PIGE360_DEPLOYER_WEBHOOK_TOKEN_HEADER",
                "X-Webhook-Token",
            ),
            webhook_token: env_string("PIGE360_DEPLOYER_WEBHOOK_TOKEN", ""),
            webhook_allow_lan: env_bool("PIGE360_DEPLOYER_WEBHOOK_ALLOW_LAN", false),
            webhook_allow_external: env_bool("PIGE360_DEPLOYER_WEBHOOK_ALLOW_EXTERNAL", false),
            websocket_enabled: env_bool("PIGE360_DEPLOYER_WEBSOCKET_ENABLED", false),
            websocket_auto_start: env_bool("PIGE360_DEPLOYER_WEBSOCKET_AUTO_START", false),
            websocket_host: env_string("PIGE360_DEPLOYER_WEBSOCKET_HOST", "127.0.0.1"),
            websocket_port: env_u16("PIGE360_DEPLOYER_WEBSOCKET_PORT", BRIDGE_CORE_DEFAULT_PORT),
            websocket_path: env_string("PIGE360_DEPLOYER_WEBSOCKET_PATH", "/ws"),
            websocket_token_required: env_bool("PIGE360_DEPLOYER_WEBSOCKET_TOKEN_REQUIRED", true),
            websocket_token_query: env_string("PIGE360_DEPLOYER_WEBSOCKET_TOKEN_QUERY", "token"),
            websocket_token_header: env_string(
                "PIGE360_DEPLOYER_WEBSOCKET_TOKEN_HEADER",
                "X-WebSocket-Token",
            ),
            websocket_token: env_string("PIGE360_DEPLOYER_WEBSOCKET_TOKEN", ""),
            websocket_allow_lan: env_bool("PIGE360_DEPLOYER_WEBSOCKET_ALLOW_LAN", false),
            websocket_allow_external: env_bool("PIGE360_DEPLOYER_WEBSOCKET_ALLOW_EXTERNAL", false),
            websocket_heartbeat_seconds: env_u64("PIGE360_DEPLOYER_WEBSOCKET_HEARTBEAT_SECONDS", 30),
            tray_enabled: env_bool("PIGE360_DEPLOYER_TRAY_ENABLED", true),
            minimize_to_tray: env_bool("PIGE360_DEPLOYER_TRAY_MINIMIZE_TO_TRAY", true),
            close_to_tray: env_bool("PIGE360_DEPLOYER_TRAY_CLOSE_TO_TRAY", false),
            start_with_windows: env_bool("PIGE360_DEPLOYER_START_WITH_WINDOWS", false),
            services_auto_start: env_bool("PIGE360_DEPLOYER_SERVICES_AUTO_START", false),
            app_service_name: env_string("PIGE360_DEPLOYER_SERVICE_NAME", "Pige360DeployerServer"),
        }
    }
}

pub fn init_env_file(state: Option<&SharedState>) -> Result<PathBuf, String> {
    let path = env_file_path(state)?;
    if !path.exists() {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)
                .map_err(|err| format!("Falha ao criar diretório do .env: {err}"))?;
        }
        fs::write(&path, default_env_template())
            .map_err(|err| format!("Falha ao criar .env padrão em {}: {err}", path.display()))?;
    }
    load_env_file(&path)?;
    Ok(path)
}

pub fn load_env_file(path: &Path) -> Result<(), String> {
    if !path.exists() {
        return Ok(());
    }
    let raw = fs::read_to_string(path).map_err(|err| format!("Falha ao ler .env: {err}"))?;
    for line in raw.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') || !trimmed.contains('=') {
            continue;
        }
        let mut parts = trimmed.splitn(2, '=');
        let key = parts.next().unwrap_or_default().trim();
        let value = parts
            .next()
            .unwrap_or_default()
            .trim()
            .trim_matches('"')
            .trim_matches('\'');
        if !key.is_empty() && env::var(key).is_err() {
            env::set_var(key, value);
        }
    }
    Ok(())
}

pub fn env_file_path(state: Option<&SharedState>) -> Result<PathBuf, String> {
    if let Ok(path) = env::var("PIGE360_DEPLOYER_ENV_FILE") {
        let trimmed = path.trim();
        if !trimmed.is_empty() {
            return Ok(PathBuf::from(trimmed));
        }
    }
    if let Some(state) = state {
        if let Ok(data_dir) = state.data_dir() {
            return Ok(data_dir.join(ENV_FILE_NAME));
        }
    }
    let config_dir = dirs::config_local_dir()
        .or_else(|| env::current_dir().ok())
        .ok_or_else(|| "Não foi possível resolver diretório para .env.".to_string())?;
    Ok(config_dir.join("pige360_deployer").join(ENV_FILE_NAME))
}

pub fn load_settings(state: &SharedState) -> Result<RuntimeSettingsPayload, String> {
    let env_path = init_env_file(Some(state))?;
    let mut settings = RuntimeSettings::default();
    let db_path = state.db_path()?;
    let conn = open_connection(&db_path)?;
    if let Some(raw) = conn
        .query_row(
            "SELECT valor FROM app_settings WHERE chave = 'runtime.settings' LIMIT 1",
            [],
            |row| row.get::<_, String>(0),
        )
        .optional()
        .map_err(|err| format!("Falha ao ler configurações runtime: {err}"))?
    {
        if !raw.trim().is_empty() {
            settings = serde_json::from_str(&raw)
                .map_err(|err| format!("Configuração runtime inválida no banco: {err}"))?;
        }
    }
    normalize_runtime_settings(&mut settings);
    let (ports, warnings) = build_ports(&settings);
    Ok(RuntimeSettingsPayload {
        env_path: env_path.to_string_lossy().to_string(),
        settings,
        ports,
        warnings,
    })
}

pub fn save_settings(
    state: &SharedState,
    mut settings: RuntimeSettings,
) -> Result<RuntimeSettingsPayload, String> {
    normalize_runtime_settings(&mut settings);
    validate_port_range(&settings)?;
    let env_path = init_env_file(Some(state))?;
    let (ports, warnings) = build_ports(&settings);
    if has_duplicate_configured_ports(&settings, &ports) {
        return Err(
            "Há portas configuradas em conflito entre serviços ativos. Ajuste antes de salvar."
                .to_string(),
        );
    }
    let now = Utc::now().to_rfc3339();
    let db_path = state.db_path()?;
    let conn = open_connection(&db_path)?;
    let serialized = serde_json::to_string(&settings).map_err(|err| err.to_string())?;
    conn.execute(
        "INSERT OR REPLACE INTO app_settings (chave, valor, created_at, updated_at) VALUES ('runtime.settings', ?1, COALESCE((SELECT created_at FROM app_settings WHERE chave='runtime.settings'), ?2), ?2)",
        params![serialized, now],
    )
    .map_err(|err| format!("Falha ao persistir configurações runtime: {err}"))?;
    write_env_file(&env_path, &settings)?;
    apply_env_from_settings(&settings);
    normalize_runtime_settings(&mut settings);
    Ok(RuntimeSettingsPayload {
        env_path: env_path.to_string_lossy().to_string(),
        settings,
        ports,
        warnings,
    })
}

pub fn default_env_template() -> String {
    r#"# PIGE360 Deployer - configuração local
# A porta padrão do Tauri (devUrl 1420) não é alterada por este arquivo.
PIGE360_DEPLOYER_API_HOST=127.0.0.1
PIGE360_DEPLOYER_API_PORT=61001
PIGE360_DEPLOYER_API_AUTO_START=true
PIGE360_DEPLOYER_API_BASE_URL=http://127.0.0.1:61001
PIGE360_DEPLOYER_API_SCALAR_ENABLED=true
PIGE360_DEPLOYER_API_SCALAR_URL=http://127.0.0.1:61001/docs
PIGE360_DEPLOYER_API_DOCS_PATH=/docs
PIGE360_DEPLOYER_API_DOCS_PUBLIC_LOCAL=true
PIGE360_DEPLOYER_API_RESTART_ON_CONFIG_CHANGE=true
PIGE360_DEPLOYER_API_OPEN_SCALAR_AFTER_START=false
PIGE360_DEPLOYER_API_TIMEOUT_MS=8000
PIGE360_DEPLOYER_API_LOG_MODE=normal
PIGE360_DEPLOYER_WEB_ENABLED=true
PIGE360_DEPLOYER_WEB_HOST=127.0.0.1
PIGE360_DEPLOYER_WEB_PORT=61002
PIGE360_DEPLOYER_WEB_AUTO_START=true
PIGE360_DEPLOYER_WEB_BIND_LAN=false
PIGE360_DEPLOYER_WEBHOOK_AUTO_START=false
PIGE360_DEPLOYER_WEBHOOK_ENABLED=false
PIGE360_DEPLOYER_WEBHOOK_HOST=127.0.0.1
PIGE360_DEPLOYER_WEBHOOK_PORT=61003
PIGE360_DEPLOYER_WEBHOOK_BASE_PATH=/webhooks
PIGE360_DEPLOYER_WEBHOOK_TOKEN_REQUIRED=true
PIGE360_DEPLOYER_WEBHOOK_TOKEN_HEADER=X-Webhook-Token
PIGE360_DEPLOYER_WEBHOOK_TOKEN=
PIGE360_DEPLOYER_WEBHOOK_ALLOW_LAN=false
PIGE360_DEPLOYER_WEBHOOK_ALLOW_EXTERNAL=false
PIGE360_DEPLOYER_WEBSOCKET_ENABLED=false
PIGE360_DEPLOYER_WEBSOCKET_AUTO_START=false
PIGE360_DEPLOYER_WEBSOCKET_HOST=127.0.0.1
PIGE360_DEPLOYER_WEBSOCKET_PORT=61004
PIGE360_DEPLOYER_WEBSOCKET_PATH=/ws
PIGE360_DEPLOYER_WEBSOCKET_TOKEN_REQUIRED=true
PIGE360_DEPLOYER_WEBSOCKET_TOKEN_QUERY=token
PIGE360_DEPLOYER_WEBSOCKET_TOKEN_HEADER=X-WebSocket-Token
PIGE360_DEPLOYER_WEBSOCKET_TOKEN=
PIGE360_DEPLOYER_WEBSOCKET_ALLOW_LAN=false
PIGE360_DEPLOYER_WEBSOCKET_ALLOW_EXTERNAL=false
PIGE360_DEPLOYER_WEBSOCKET_HEARTBEAT_SECONDS=30
PIGE360_DEPLOYER_TRAY_ENABLED=true
PIGE360_DEPLOYER_TRAY_MINIMIZE_TO_TRAY=true
PIGE360_DEPLOYER_TRAY_CLOSE_TO_TRAY=false
PIGE360_DEPLOYER_START_WITH_WINDOWS=false
PIGE360_DEPLOYER_SERVICES_AUTO_START=false
PIGE360_DEPLOYER_SERVICE_NAME=Pige360DeployerServer
PIGE360_DEPLOYER_API_REQUIRE_TOKEN=false
PIGE360_DEPLOYER_API_ALLOW_PUBLIC_NETWORK=false
PIGE360_DEPLOYER_API_CORS=false
PIGE360_DEPLOYER_API_TOKEN=
PIGE360_DEPLOYER_API_TOKEN_HEADER=X-App-Token
# Informe PIGE360_DEPLOYER_API_TOKEN via secret/env real em produção; não commite tokens.
"#
    .to_string()
}

fn apply_env_from_settings(settings: &RuntimeSettings) {
    env::set_var("PIGE360_DEPLOYER_API_HOST", &settings.internal_api_host);
    env::set_var(
        "PIGE360_DEPLOYER_API_PORT",
        settings.internal_api_port.to_string(),
    );
    env::set_var("PIGE360_DEPLOYER_API_BASE_URL", &settings.internal_api_base_url);
    env::set_var(
        "PIGE360_DEPLOYER_API_SCALAR_URL",
        &settings.internal_api_docs_url,
    );
    env::set_var(
        "PIGE360_DEPLOYER_API_AUTO_START",
        settings.internal_api_auto_start.to_string(),
    );
    env::set_var(
        "PIGE360_DEPLOYER_API_ALLOW_PUBLIC_NETWORK",
        settings.internal_api_allow_public_network.to_string(),
    );
    env::set_var(
        "PIGE360_DEPLOYER_API_CORS",
        settings.internal_api_cors_enabled.to_string(),
    );
    env::set_var(
        "PIGE360_DEPLOYER_WEB_ENABLED",
        settings.local_web_enabled.to_string(),
    );
    env::set_var("PIGE360_DEPLOYER_WEB_HOST", &settings.local_web_host);
    env::set_var("PIGE360_DEPLOYER_WEB_PORT", settings.local_web_port.to_string());
    env::set_var(
        "PIGE360_DEPLOYER_WEB_AUTO_START",
        settings.local_web_auto_start.to_string(),
    );
    env::set_var(
        "PIGE360_DEPLOYER_WEB_BIND_LAN",
        (settings.local_web_host == "0.0.0.0").to_string(),
    );
    env::set_var(
        "PIGE360_DEPLOYER_WEBHOOK_ENABLED",
        settings.webhook_enabled.to_string(),
    );
    env::set_var(
        "PIGE360_DEPLOYER_WEBHOOK_AUTO_START",
        settings.webhook_auto_start.to_string(),
    );
    env::set_var("PIGE360_DEPLOYER_WEBHOOK_HOST", &settings.webhook_host);
    env::set_var(
        "PIGE360_DEPLOYER_WEBHOOK_PORT",
        settings.webhook_port.to_string(),
    );
    env::set_var(
        "PIGE360_DEPLOYER_WEBHOOK_ALLOW_LAN",
        settings.webhook_allow_lan.to_string(),
    );
    env::set_var(
        "PIGE360_DEPLOYER_WEBSOCKET_ENABLED",
        settings.websocket_enabled.to_string(),
    );
    env::set_var(
        "PIGE360_DEPLOYER_WEBSOCKET_AUTO_START",
        settings.websocket_auto_start.to_string(),
    );
    env::set_var("PIGE360_DEPLOYER_WEBSOCKET_HOST", &settings.websocket_host);
    env::set_var(
        "PIGE360_DEPLOYER_WEBSOCKET_PORT",
        settings.websocket_port.to_string(),
    );
    env::set_var(
        "PIGE360_DEPLOYER_WEBSOCKET_ALLOW_LAN",
        settings.websocket_allow_lan.to_string(),
    );
}

fn write_env_file(path: &Path, settings: &RuntimeSettings) -> Result<(), String> {
    let content = format!(
        "# PIGE360 Deployer - gerado pela tela Sistema e parâmetros\n\
PIGE360_DEPLOYER_API_HOST={}\n\
PIGE360_DEPLOYER_API_PORT={}\n\
PIGE360_DEPLOYER_API_BASE_URL={}\n\
PIGE360_DEPLOYER_API_AUTO_START={}\n\
PIGE360_DEPLOYER_API_RESTART_ON_CONFIG_CHANGE={}\n\
PIGE360_DEPLOYER_API_REQUIRE_TOKEN={}\n\
PIGE360_DEPLOYER_API_ALLOW_PUBLIC_NETWORK={}\n\
PIGE360_DEPLOYER_API_CORS={}\n\
PIGE360_DEPLOYER_API_TOKEN_HEADER={}\n\
PIGE360_DEPLOYER_API_TOKEN={}\n\
PIGE360_DEPLOYER_API_DOCS_PUBLIC_LOCAL={}\n\
PIGE360_DEPLOYER_API_OPEN_SCALAR_AFTER_START={}\n\
PIGE360_DEPLOYER_API_TIMEOUT_MS={}\n\
PIGE360_DEPLOYER_API_LOG_MODE={}\n\
PIGE360_DEPLOYER_API_SCALAR_ENABLED={}\n\
PIGE360_DEPLOYER_API_SCALAR_URL={}\n\
PIGE360_DEPLOYER_API_DOCS_PATH={}\n\
PIGE360_DEPLOYER_WEB_ENABLED={}\n\
PIGE360_DEPLOYER_WEB_HOST={}\n\
PIGE360_DEPLOYER_WEB_PORT={}\n\
PIGE360_DEPLOYER_WEB_AUTO_START={}\n\
PIGE360_DEPLOYER_WEB_BIND_LAN={}\n\
PIGE360_DEPLOYER_AUX_HOST={}\n\
PIGE360_DEPLOYER_AUX_PORT={}\n\
PIGE360_DEPLOYER_BRIDGE_HOST={}\n\
PIGE360_DEPLOYER_BRIDGE_PORT={}\n\
PIGE360_DEPLOYER_WEBHOOK_ENABLED={}\n\
PIGE360_DEPLOYER_WEBHOOK_AUTO_START={}\n\
PIGE360_DEPLOYER_WEBHOOK_HOST={}\n\
PIGE360_DEPLOYER_WEBHOOK_PORT={}\n\
PIGE360_DEPLOYER_WEBHOOK_BASE_PATH={}\n\
PIGE360_DEPLOYER_WEBHOOK_TOKEN_REQUIRED={}\n\
PIGE360_DEPLOYER_WEBHOOK_TOKEN_HEADER={}\n\
PIGE360_DEPLOYER_WEBHOOK_TOKEN={}\n\
PIGE360_DEPLOYER_WEBHOOK_ALLOW_LAN={}\n\
PIGE360_DEPLOYER_WEBHOOK_ALLOW_EXTERNAL={}\n\
PIGE360_DEPLOYER_WEBSOCKET_ENABLED={}\n\
PIGE360_DEPLOYER_WEBSOCKET_AUTO_START={}\n\
PIGE360_DEPLOYER_WEBSOCKET_HOST={}\n\
PIGE360_DEPLOYER_WEBSOCKET_PORT={}\n\
PIGE360_DEPLOYER_WEBSOCKET_PATH={}\n\
PIGE360_DEPLOYER_WEBSOCKET_TOKEN_REQUIRED={}\n\
PIGE360_DEPLOYER_WEBSOCKET_TOKEN_QUERY={}\n\
PIGE360_DEPLOYER_WEBSOCKET_TOKEN_HEADER={}\n\
PIGE360_DEPLOYER_WEBSOCKET_TOKEN={}\n\
PIGE360_DEPLOYER_WEBSOCKET_ALLOW_LAN={}\n\
PIGE360_DEPLOYER_WEBSOCKET_ALLOW_EXTERNAL={}\n\
PIGE360_DEPLOYER_WEBSOCKET_HEARTBEAT_SECONDS={}\n\
PIGE360_DEPLOYER_TRAY_ENABLED={}\n\
PIGE360_DEPLOYER_TRAY_MINIMIZE_TO_TRAY={}\n\
PIGE360_DEPLOYER_TRAY_CLOSE_TO_TRAY={}\n\
PIGE360_DEPLOYER_START_WITH_WINDOWS={}\n\
PIGE360_DEPLOYER_SERVICES_AUTO_START={}\n\
PIGE360_DEPLOYER_SERVICE_NAME={}\n\
# Informe PIGE360_DEPLOYER_API_TOKEN via secret/env real em produção; não commite tokens.\n",
        settings.internal_api_host,
        settings.internal_api_port,
        settings.internal_api_base_url,
        settings.internal_api_auto_start,
        settings.internal_api_restart_on_config_change,
        settings.internal_api_require_token,
        settings.internal_api_allow_public_network,
        settings.internal_api_cors_enabled,
        settings.internal_api_token_header,
        settings.internal_api_token,
        settings.internal_api_docs_public_local,
        settings.internal_api_open_scalar_after_start,
        settings.internal_api_timeout_ms,
        settings.internal_api_log_mode,
        settings.internal_api_docs_enabled,
        settings.internal_api_docs_url,
        settings.internal_api_docs_path,
        settings.local_web_enabled,
        settings.local_web_host,
        settings.local_web_port,
        settings.local_web_auto_start,
        is_public_bind_host(&settings.local_web_host),
        settings.auxiliary_host,
        settings.auxiliary_port,
        settings.bridge_core_host,
        settings.bridge_core_port,
        settings.webhook_enabled,
        settings.webhook_auto_start,
        settings.webhook_host,
        settings.webhook_port,
        settings.webhook_base_path,
        settings.webhook_token_required,
        settings.webhook_token_header,
        settings.webhook_token,
        settings.webhook_allow_lan,
        settings.webhook_allow_external,
        settings.websocket_enabled,
        settings.websocket_auto_start,
        settings.websocket_host,
        settings.websocket_port,
        settings.websocket_path,
        settings.websocket_token_required,
        settings.websocket_token_query,
        settings.websocket_token_header,
        settings.websocket_token,
        settings.websocket_allow_lan,
        settings.websocket_allow_external,
        settings.websocket_heartbeat_seconds,
        settings.tray_enabled,
        settings.minimize_to_tray,
        settings.close_to_tray,
        settings.start_with_windows,
        settings.services_auto_start,
        settings.app_service_name
    );
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .map_err(|err| format!("Falha ao criar diretório do .env: {err}"))?;
    }
    let mut file = OpenOptions::new()
        .create(true)
        .write(true)
        .truncate(true)
        .open(path)
        .map_err(|err| format!("Falha ao abrir .env para escrita: {err}"))?;
    file.write_all(content.as_bytes())
        .map_err(|err| format!("Falha ao escrever .env: {err}"))
}

pub fn build_ports(settings: &RuntimeSettings) -> (Vec<RuntimeServicePort>, Vec<String>) {
    let mut ports = vec![
        port_item(
            &INTERNAL_API_PORT_DEFINITION,
            &settings.internal_api_host,
            settings.internal_api_port,
        ),
        port_item(
            &LOCAL_WEB_PORT_DEFINITION,
            &settings.local_web_host,
            settings.local_web_port,
        ),
        port_item(
            &AUXILIARY_PORT_DEFINITION,
            &settings.webhook_host,
            settings.webhook_port,
        ),
        port_item(
            &BRIDGE_CORE_PORT_DEFINITION,
            &settings.websocket_host,
            settings.websocket_port,
        ),
    ];
    let mut warnings = Vec::new();
    let mut seen: HashSet<u16> = HashSet::new();
    for item in &mut ports {
        item.effective_port = item.configured_port;
        item.fallback_applied = false;
        let service_enabled = match item.key.as_str() {
            "local_web" => settings.local_web_enabled,
            "auxiliary" => settings.webhook_enabled,
            "bridge_core" => settings.websocket_enabled,
            _ => true,
        };
        if service_enabled && !seen.insert(item.configured_port) {
            item.available = false;
            warnings.push(format!(
                "Porta {} está configurada em mais de um serviço ativo. Ajuste as portas para evitar conflito entre API/Web/Webhook/WebSocket.",
                item.configured_port
            ));
        }
        if service_enabled && !is_port_available(&item.host, item.configured_port) {
            // Porta em uso não é necessariamente erro: pode ser o próprio serviço já rodando.
            // A tela exibe o estado como "em uso" sem transformar isso em alerta global.
            item.available = false;
        }
    }
    (ports, warnings)
}

fn port_item(
    definition: &RuntimePortDefinition,
    host: &str,
    configured_port: u16,
) -> RuntimeServicePort {
    RuntimeServicePort {
        key: definition.key.to_string(),
        label: definition.label.to_string(),
        env_host_key: definition.env_host_key.to_string(),
        env_port_key: definition.env_port_key.to_string(),
        default_port: definition.default_port,
        host: host.to_string(),
        configured_port,
        effective_port: configured_port,
        available: true,
        fallback_applied: false,
        description: definition.description.to_string(),
    }
}

pub fn resolve_internal_api_config(
    state: &SharedState,
) -> Result<crate::internal_api::config::InternalApiConfig, String> {
    let payload = load_settings(state)?;
    let port = payload
        .ports
        .iter()
        .find(|item| item.key == "internal_api")
        .map(|item| item.effective_port)
        .unwrap_or(payload.settings.internal_api_port);
    Ok(
        crate::internal_api::config::InternalApiConfig::from_runtime_settings(&payload.settings)
            .with_host_port(payload.settings.internal_api_host, port),
    )
}

pub fn resolve_webhook_config(
    state: &SharedState,
) -> Result<crate::native_webhook::config::WebhookConfig, String> {
    let payload = load_settings(state)?;
    let port = payload
        .ports
        .iter()
        .find(|item| item.key == "auxiliary")
        .map(|item| item.effective_port)
        .unwrap_or(payload.settings.webhook_port);
    Ok(
        crate::native_webhook::config::WebhookConfig::from_runtime_settings(&payload.settings)
            .with_host_port(payload.settings.webhook_host, port),
    )
}

pub fn resolve_websocket_config(
    state: &SharedState,
) -> Result<crate::native_websocket::config::WebSocketConfig, String> {
    let payload = load_settings(state)?;
    let port = payload
        .ports
        .iter()
        .find(|item| item.key == "bridge_core")
        .map(|item| item.effective_port)
        .unwrap_or(payload.settings.websocket_port);
    Ok(
        crate::native_websocket::config::WebSocketConfig::from_runtime_settings(&payload.settings)
            .with_host_port(payload.settings.websocket_host, port),
    )
}

fn validate_port_range(settings: &RuntimeSettings) -> Result<(), String> {
    let values = BTreeMap::from([
        ("API interna", settings.internal_api_port),
        ("Servidor web local", settings.local_web_port),
        ("Webhook Service", settings.webhook_port),
        ("WebSocket Service", settings.websocket_port),
    ]);
    for (label, port) in values {
        if port == 0 {
            return Err(format!("{label}: porta deve estar entre 1 e 65535."));
        }
    }
    Ok(())
}

fn has_duplicate_configured_ports(
    settings: &RuntimeSettings,
    ports: &[RuntimeServicePort],
) -> bool {
    let mut seen = HashSet::new();
    ports
        .iter()
        .filter(|item| match item.key.as_str() {
            "local_web" => settings.local_web_enabled,
            "auxiliary" => settings.webhook_enabled,
            "bridge_core" => settings.websocket_enabled,
            _ => true,
        })
        .any(|item| !seen.insert(item.configured_port))
}

pub fn is_port_available(host: &str, port: u16) -> bool {
    let bind_host = if host.trim().is_empty() {
        "127.0.0.1"
    } else {
        host.trim()
    };
    format!("{bind_host}:{port}")
        .parse::<SocketAddr>()
        .ok()
        .and_then(|addr| TcpListener::bind(addr).ok())
        .is_some()
}

fn env_string(key: &str, default: &str) -> String {
    env::var(key)
        .ok()
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| default.to_string())
}

fn is_public_bind_host(host: &str) -> bool {
    matches!(host.trim(), "0.0.0.0" | "::" | "[::]")
}

fn normalize_runtime_settings(settings: &mut RuntimeSettings) {
    if settings.internal_api_host.trim().is_empty() {
        settings.internal_api_host = "127.0.0.1".to_string();
    }
    if is_public_bind_host(&settings.internal_api_host) {
        settings.internal_api_allow_public_network = true;
        settings.internal_api_cors_enabled = true;
    }
    if settings.internal_api_port == 0 {
        settings.internal_api_port = INTERNAL_API_DEFAULT_PORT;
    }
    let public_host =
        crate::internal_api::config::public_url_host(settings.internal_api_host.trim());
    let base_url = format!("http://{}:{}", public_host, settings.internal_api_port);
    if settings.internal_api_base_url.trim().is_empty()
        || settings.internal_api_base_url.contains("127.0.0.1:61001")
        || settings.internal_api_base_url.contains("0.0.0.0")
        || settings.internal_api_base_url.contains("[::]")
    {
        settings.internal_api_base_url = base_url.clone();
    }
    if settings.internal_api_docs_path.trim().is_empty() {
        settings.internal_api_docs_path = "/docs".to_string();
    }
    if !settings.internal_api_docs_path.starts_with('/') {
        settings.internal_api_docs_path = format!("/{}", settings.internal_api_docs_path.trim());
    }
    if settings.internal_api_docs_url.trim().is_empty()
        || settings.internal_api_docs_url.contains("127.0.0.1:61001")
        || settings.internal_api_docs_url.contains("0.0.0.0")
        || settings.internal_api_docs_url.contains("[::]")
    {
        settings.internal_api_docs_url = format!("{}{}", base_url, settings.internal_api_docs_path);
    }
    if settings.internal_api_timeout_ms < 1000 {
        settings.internal_api_timeout_ms = 1000;
    }

    // Webport/proxy usa porta fixa definida pelo operador. Não há troca automática
    // para 61003/61004 nem fallback silencioso para localhost. Se a porta estiver
    // ocupada, a aplicação desktop continua abrindo e o usuário ajusta a porta nos
    // parâmetros ou encerra a instância anterior.
    if settings.local_web_host.trim().is_empty() {
        settings.local_web_host = "127.0.0.1".to_string();
    }
    if settings.local_web_port == 0 {
        settings.local_web_port = LOCAL_WEB_DEFAULT_PORT;
    }

    if settings.internal_api_log_mode.trim().is_empty() {
        settings.internal_api_log_mode = "normal".to_string();
    }
    if settings.internal_api_token_header.trim().is_empty() {
        settings.internal_api_token_header = "X-App-Token".to_string();
    }
    if settings.webhook_host.trim().is_empty() {
        settings.webhook_host = "127.0.0.1".to_string();
    }
    if is_public_bind_host(&settings.webhook_host) {
        settings.webhook_allow_lan = true;
    }
    if settings.webhook_port == 0 {
        settings.webhook_port = AUXILIARY_DEFAULT_PORT;
    }
    if settings.webhook_base_path.trim().is_empty() {
        settings.webhook_base_path = "/webhooks".to_string();
    }
    if !settings.webhook_base_path.starts_with('/') {
        settings.webhook_base_path = format!("/{}", settings.webhook_base_path.trim());
    }
    if settings.webhook_token_header.trim().is_empty() {
        settings.webhook_token_header = "X-Webhook-Token".to_string();
    }
    settings.auxiliary_host = settings.webhook_host.clone();
    settings.auxiliary_port = settings.webhook_port;

    if settings.websocket_host.trim().is_empty() {
        settings.websocket_host = "127.0.0.1".to_string();
    }
    if is_public_bind_host(&settings.websocket_host) {
        settings.websocket_allow_lan = true;
    }
    if settings.websocket_port == 0 {
        settings.websocket_port = BRIDGE_CORE_DEFAULT_PORT;
    }
    if settings.websocket_path.trim().is_empty() {
        settings.websocket_path = "/ws".to_string();
    }
    if !settings.websocket_path.starts_with('/') {
        settings.websocket_path = format!("/{}", settings.websocket_path.trim());
    }
    if settings.websocket_token_query.trim().is_empty() {
        settings.websocket_token_query = "token".to_string();
    }
    if settings.websocket_token_header.trim().is_empty() {
        settings.websocket_token_header = "X-WebSocket-Token".to_string();
    }
    if settings.websocket_heartbeat_seconds == 0 {
        settings.websocket_heartbeat_seconds = 30;
    }
    settings.bridge_core_host = settings.websocket_host.clone();
    settings.bridge_core_port = settings.websocket_port;

    if settings.app_service_name.trim().is_empty() {
        settings.app_service_name = "Pige360DeployerServer".to_string();
    }
}

fn env_u16(key: &str, default: u16) -> u16 {
    env::var(key)
        .ok()
        .and_then(|value| value.parse::<u16>().ok())
        .filter(|port| *port > 0)
        .unwrap_or(default)
}

fn env_u64(key: &str, default: u64) -> u64 {
    env::var(key)
        .ok()
        .and_then(|value| value.parse::<u64>().ok())
        .filter(|value| *value > 0)
        .unwrap_or(default)
}

fn env_bool(key: &str, default: bool) -> bool {
    env::var(key)
        .ok()
        .map(|value| {
            matches!(
                value.trim().to_ascii_lowercase().as_str(),
                "1" | "true" | "yes" | "on"
            )
        })
        .unwrap_or(default)
}

#[allow(dead_code)]
pub fn payload_to_json(payload: RuntimeSettingsPayload) -> Value {
    json!(payload)
}
