use std::{
    net::{SocketAddr, TcpListener as StdTcpListener},
    sync::{Mutex, OnceLock},
    thread::JoinHandle,
    time::Duration,
};

use axum::{
    body::{to_bytes, Body},
    extract::State,
    http::{header, HeaderMap, HeaderValue, Method, StatusCode, Uri},
    response::{IntoResponse, Response},
    routing::{any, get, post},
    Json, Router,
};
use serde::Serialize;
use tokio::{net::TcpListener, sync::oneshot};
use tower_http::cors::{Any, CorsLayer};

use crate::{
    app_state::SharedState,
    db::{open_connection, write_app_log, AppLogInput},
    internal_api::{app_commands, state::InternalApiState, web_app},
    runtime_config::{self, RuntimeSettings},
};

struct WebRuntimeHandle {
    host: String,
    port: u16,
    started_at: String,
    shutdown: Option<oneshot::Sender<()>>,
    thread: Option<JoinHandle<()>>,
    url: String,
    loopback: Option<AuxiliaryWebRuntimeHandle>,
}

struct AuxiliaryWebRuntimeHandle {
    shutdown: Option<oneshot::Sender<()>>,
    thread: Option<JoinHandle<()>>,
}

#[derive(Clone)]
struct WebProxyState {
    api_base_url: String,
    api_token_header: String,
    api_token: String,
    http_client: reqwest::Client,
    command_state: InternalApiState,
}

static WEB_RUNTIME: OnceLock<Mutex<Option<WebRuntimeHandle>>> = OnceLock::new();
static WEB_START_LOCK: OnceLock<Mutex<()>> = OnceLock::new();

fn runtime_slot() -> &'static Mutex<Option<WebRuntimeHandle>> {
    WEB_RUNTIME.get_or_init(|| Mutex::new(None))
}

fn start_lock() -> &'static Mutex<()> {
    WEB_START_LOCK.get_or_init(|| Mutex::new(()))
}

#[derive(Debug, Clone, Serialize)]
pub struct WebRuntimeStatus {
    pub running: bool,
    pub host: String,
    pub port: u16,
    pub url: Option<String>,
    pub started_at: Option<String>,
    pub external: bool,
    pub message: Option<String>,
}

enum WebBindResult {
    Bound {
        host: String,
        port: u16,
        url: String,
        listener: StdTcpListener,
    },
    External(WebRuntimeStatus),
}

struct WebServerThreadConfig {
    name: String,
    state: SharedState,
    host: String,
    port: u16,
    std_listener: StdTcpListener,
    proxy_state: WebProxyState,
    started_at: String,
    rx: oneshot::Receiver<()>,
}

/// Servidor Web local no padrão do School:
/// - pré-bind síncrono com StdTcpListener antes de criar a thread;
/// - handle global único e idempotente;
/// - sem depender de configuração persistida antiga do banco;
/// - publica a mesma interface gerada pelo Vite em /;
/// - expõe proxy /__internal_api/* para a API interna.
pub fn start_background(state: SharedState) -> Result<WebRuntimeStatus, String> {
    let _start_guard = start_lock()
        .lock()
        .map_err(|_| "Falha ao bloquear inicialização do runtime web.".to_string())?;

    let settings = runtime_config::load_settings(&state)
        .map(|payload| payload.settings)
        .unwrap_or_else(|_| RuntimeSettings::default());
    if !settings.local_web_enabled {
        return Ok(WebRuntimeStatus {
            running: false,
            host: settings.local_web_host.clone(),
            port: settings.local_web_port,
            url: None,
            started_at: None,
            external: false,
            message: Some("Webport/proxy está desabilitado nos parâmetros runtime.".to_string()),
        });
    }
    let configured_host = web_bind_host(&settings);
    let port = settings.local_web_port;

    // O status em memória só pode ser reaproveitado quando corresponde exatamente
    // ao host/porta atuais. Isso permite trocar Local -> Rede local/remoto sem
    // manter um listener antigo em 127.0.0.1 segurando a porta fixa.
    if let Some(status) = current_status()? {
        if web_status_matches_config(&status.host, &configured_host) && status.port == port {
            return Ok(status);
        }
        drop(status);
        let _ = stop_background();
        std::thread::sleep(Duration::from_millis(350));
    }
    let (host, bound_port, url, std_listener) =
        match bind_web_listener(&state, &configured_host, port)? {
            WebBindResult::Bound {
                host,
                port: bound_port,
                url,
                listener,
            } => (host, bound_port, url, listener),
            WebBindResult::External(status) => return Ok(status),
        };

    let internal_config = runtime_config::resolve_internal_api_config(&state).map_err(|err| {
        format!("Falha ao resolver configuração da API interna para o proxy web: {err}")
    })?;
    let api_base_url = resolve_proxy_api_base_url(&settings, bound_port, &internal_config);
    let http_client = reqwest::Client::builder()
        .timeout(Duration::from_secs(30))
        .pool_idle_timeout(Duration::from_secs(90))
        .build()
        .map_err(|err| format!("Falha ao preparar cliente HTTP do proxy web: {err}"))?;
    let command_state = InternalApiState {
        db_path: state.db_path()?,
        data_dir: state.data_dir()?,
        started_at: chrono::Utc::now().to_rfc3339(),
        host: internal_config.host.clone(),
        port: internal_config.port,
        config: internal_config.clone(),
    };

    let proxy_state = WebProxyState {
        api_base_url,
        api_token_header: settings.internal_api_token_header.clone(),
        api_token: settings.internal_api_token.clone(),
        http_client,
        command_state,
    };

    let started_at = chrono::Utc::now().to_rfc3339();
    let (tx, rx) = oneshot::channel::<()>();
    let loopback = prepare_loopback_mirror(
        &state,
        &configured_host,
        &host,
        bound_port,
        &started_at,
        &proxy_state,
    );
    let thread = spawn_web_server_thread(WebServerThreadConfig {
        name: "pige360-deployer-web-proxy".to_string(),
        state: state.clone(),
        host: host.clone(),
        port: bound_port,
        std_listener,
        proxy_state: proxy_state.clone(),
        started_at: started_at.clone(),
        rx,
    })?;

    let mut guard = runtime_slot()
        .lock()
        .map_err(|_| "Falha ao bloquear runtime web.".to_string())?;
    *guard = Some(WebRuntimeHandle {
        host: host.clone(),
        port: bound_port,
        url: url.clone(),
        started_at: started_at.clone(),
        shutdown: Some(tx),
        thread: Some(thread),
        loopback,
    });

    log_runtime_event(
        &state,
        "info",
        "Servidor web iniciado com sucesso",
        serde_json::json!({
            "bind": format!("{host}:{bound_port}"),
            "url": url.clone(),
            "loopback_url": loopback_url_for(&host, bound_port),
            "api_proxy": proxy_state.api_base_url
        }),
    );

    Ok(WebRuntimeStatus {
        running: true,
        host,
        port: bound_port,
        url: Some(url),
        started_at: Some(started_at),
        external: false,
        message: None,
    })
}

pub fn status() -> Result<WebRuntimeStatus, String> {
    if let Some(status) = current_status()? {
        return Ok(status);
    }

    let host = web_bind_host_from_env();
    let port = web_port_from_env();
    if let Some(status) = adopt_existing_web_runtime(&host, port) {
        return Ok(status);
    }

    Ok(WebRuntimeStatus {
        running: false,
        host: client_host_for_bind(&host),
        port,
        url: None,
        started_at: None,
        external: false,
        message: None,
    })
}

pub fn stop_background() -> Result<WebRuntimeStatus, String> {
    let mut handle = {
        let mut guard = runtime_slot()
            .lock()
            .map_err(|_| "Falha ao bloquear runtime web.".to_string())?;
        guard.take()
    };

    if let Some(handle) = handle.as_mut() {
        if let Some(loopback) = handle.loopback.as_mut() {
            if let Some(shutdown) = loopback.shutdown.take() {
                let _ = shutdown.send(());
            }
            if let Some(thread) = loopback.thread.take() {
                let _ = thread.join();
            }
        }
        if let Some(shutdown) = handle.shutdown.take() {
            let _ = shutdown.send(());
        }
        if let Some(thread) = handle.thread.take() {
            let _ = thread.join();
        }
    }
    status()
}

fn current_status() -> Result<Option<WebRuntimeStatus>, String> {
    let guard = runtime_slot()
        .lock()
        .map_err(|_| "Falha ao bloquear runtime web.".to_string())?;
    Ok(guard.as_ref().map(|handle| WebRuntimeStatus {
        running: true,
        host: handle.host.clone(),
        port: handle.port,
        url: Some(handle.url.clone()),
        started_at: Some(handle.started_at.clone()),
        external: false,
        message: None,
    }))
}

fn web_status_matches_config(running_host: &str, configured_host: &str) -> bool {
    running_host == configured_host
        || (crate::net_bind::is_wildcard_host(configured_host)
            && !matches!(
                running_host.trim(),
                "127.0.0.1" | "localhost" | "::1" | "[::1]"
            ))
}

fn spawn_web_server_thread(config: WebServerThreadConfig) -> Result<JoinHandle<()>, String> {
    let WebServerThreadConfig {
        name,
        state,
        host,
        port,
        std_listener,
        proxy_state,
        started_at,
        rx,
    } = config;

    std_listener
        .set_nonblocking(true)
        .map_err(|err| format!("Falha ao configurar listener web em {host}:{port}: {err}"))?;

    let thread_name = name;
    let error_source = thread_name.clone();

    std::thread::Builder::new()
        .name(thread_name)
        .spawn(move || {
            let rt = match tokio::runtime::Runtime::new() {
                Ok(rt) => rt,
                Err(err) => {
                    eprintln!("Falha ao criar runtime web: {err}");
                    log_runtime_event(
                        &state,
                        "error",
                        "Falha ao criar runtime web",
                        serde_json::json!({"error": err.to_string(), "listener": error_source.clone()}),
                    );
                    return;
                }
            };

            let result = rt.block_on(async move {
                let addr = socket_addr(&host, port)?;
                let listener = TcpListener::from_std(std_listener)
                    .map_err(|err| format!("Falha ao anexar listener web em {addr}: {err}"))?;
                println!("Servidor web PIGE360 Deployer ativo em http://{addr} desde {started_at}");
                axum::serve(listener, router(proxy_state))
                    .with_graceful_shutdown(async move {
                        let _ = rx.await;
                    })
                    .await
                    .map_err(|err| format!("Falha no servidor web local: {err}"))
            });

            if let Err(err) = result {
                eprintln!("{err}");
                log_runtime_event(
                    &state,
                    "error",
                    "Falha no servidor web",
                    serde_json::json!({"error": err, "listener": error_source.clone()}),
                );
            }
        })
        .map_err(|err| format!("Falha ao iniciar thread do servidor web: {err}"))
}

fn prepare_loopback_mirror(
    state: &SharedState,
    configured_host: &str,
    effective_host: &str,
    port: u16,
    started_at: &str,
    proxy_state: &WebProxyState,
) -> Option<AuxiliaryWebRuntimeHandle> {
    if !should_bind_loopback_mirror(configured_host, effective_host) {
        return None;
    }

    let loopback_host = "127.0.0.1";
    let listener = match crate::net_bind::bind_fixed_service_listener(loopback_host, port) {
        Ok(bound) => bound.listener,
        Err(err) => {
            log_runtime_event(
                state,
                "warning",
                "Webport/proxy ativo na rede local, mas loopback está indisponível",
                serde_json::json!({
                    "lan_bind": format!("{effective_host}:{port}"),
                    "loopback_bind": format!("{loopback_host}:{port}"),
                    "error": err.to_string(),
                    "localhost_available": false,
                    "hint": "Outro processo pode estar usando 127.0.0.1 nesta porta. Acesse pelo IP local ou libere a porta para habilitar localhost."
                }),
            );
            return None;
        }
    };

    let (tx, rx) = oneshot::channel::<()>();
    match spawn_web_server_thread(WebServerThreadConfig {
        name: "pige360-deployer-web-proxy-loopback".to_string(),
        state: state.clone(),
        host: loopback_host.to_string(),
        port,
        std_listener: listener,
        proxy_state: proxy_state.clone(),
        started_at: started_at.to_string(),
        rx,
    }) {
        Ok(thread) => {
            log_runtime_event(
                state,
                "info",
                "Webport/proxy também publicado no loopback local",
                serde_json::json!({
                    "lan_bind": format!("{effective_host}:{port}"),
                    "loopback_bind": format!("{loopback_host}:{port}"),
                    "url": format!("http://{loopback_host}:{port}"),
                    "localhost_available": true
                }),
            );
            Some(AuxiliaryWebRuntimeHandle {
                shutdown: Some(tx),
                thread: Some(thread),
            })
        }
        Err(err) => {
            log_runtime_event(
                state,
                "warning",
                "Falha ao iniciar listener loopback auxiliar do Webport/proxy",
                serde_json::json!({
                    "lan_bind": format!("{effective_host}:{port}"),
                    "loopback_bind": format!("{loopback_host}:{port}"),
                    "error": err,
                    "localhost_available": false
                }),
            );
            None
        }
    }
}

fn should_bind_loopback_mirror(configured_host: &str, effective_host: &str) -> bool {
    crate::net_bind::is_wildcard_host(configured_host)
        && !crate::net_bind::is_wildcard_host(effective_host)
        && !matches!(
            effective_host.trim(),
            "127.0.0.1" | "localhost" | "::1" | "[::1]"
        )
}

fn loopback_url_for(host: &str, port: u16) -> Option<String> {
    if !crate::net_bind::is_wildcard_host(host)
        && !matches!(host.trim(), "127.0.0.1" | "localhost" | "::1" | "[::1]")
    {
        Some(format!("http://127.0.0.1:{port}"))
    } else {
        None
    }
}

fn router(proxy_state: WebProxyState) -> Router {
    Router::new()
        .route("/", get(web_app::web_index))
        .route("/index.html", get(web_app::web_index))
        .route("/__web_health", get(web_health))
        .route("/__internal_api/health", get(web_internal_health))
        .route("/__internal_api/api/command", post(web_command))
        .route("/__internal_api", any(proxy_internal_api))
        .route("/__internal_api/", any(proxy_internal_api))
        .route("/__internal_api/*path", any(proxy_internal_api))
        .route("/assets/*path", get(web_app::root_assets))
        .route("/branding/*path", get(web_app::root_branding))
        .route("/icons/*path", get(web_app::root_icons))
        .route("/manifest.webmanifest", get(web_app::manifest))
        .route("/sw.js", get(web_app::disabled_service_worker))
        .route("/*path", get(web_app::web_asset))
        .with_state(proxy_state)
        .layer(
            CorsLayer::new()
                .allow_origin(Any)
                .allow_methods(Any)
                .allow_headers(Any),
        )
}

async fn web_health() -> Response {
    let body = serde_json::json!({
        "ok": true,
        "service": "pige360-deployer-web-proxy",
        "version": env!("CARGO_PKG_VERSION"),
        "web_port": web_port_from_env(),
        "api_base_url": normalize_client_base_url(
            &std::env::var("PIGE360_DEPLOYER_API_BASE_URL")
                .unwrap_or_else(|_| "http://127.0.0.1:61001".to_string()),
        ),
        "bind_host": web_bind_host_from_env(),
        "lan_expected": true,
    })
    .to_string();
    let mut response = body.into_response();
    response.headers_mut().insert(
        header::CONTENT_TYPE,
        HeaderValue::from_static("application/json; charset=utf-8"),
    );
    response.headers_mut().insert(
        header::CACHE_CONTROL,
        HeaderValue::from_static("no-store, no-cache, must-revalidate"),
    );
    response
}

async fn web_internal_health(State(proxy): State<WebProxyState>) -> Response {
    let body = serde_json::json!({
        "ok": true,
        "service": "internal-api-via-webport",
        "version": env!("CARGO_PKG_VERSION"),
        "host": proxy.command_state.host.clone(),
        "port": proxy.command_state.port,
        "started_at": proxy.command_state.started_at.clone(),
        "transport": "in-process",
    })
    .to_string();
    let mut response = body.into_response();
    response.headers_mut().insert(
        header::CONTENT_TYPE,
        HeaderValue::from_static("application/json; charset=utf-8"),
    );
    response.headers_mut().insert(
        header::CACHE_CONTROL,
        HeaderValue::from_static("no-store, no-cache, must-revalidate"),
    );
    response
}

async fn web_command(
    State(proxy): State<WebProxyState>,
    Json(request): Json<app_commands::CommandRequest>,
) -> Result<Json<app_commands::CommandResponse>, (StatusCode, Json<app_commands::CommandResponse>)>
{
    match app_commands::execute_command(&proxy.command_state, &request.command, request.args) {
        Ok(result) => Ok(Json(app_commands::CommandResponse {
            ok: true,
            result: Some(result),
            error: None,
        })),
        Err(error) => Err((
            StatusCode::BAD_REQUEST,
            Json(app_commands::CommandResponse {
                ok: false,
                result: None,
                error: Some(error),
            }),
        )),
    }
}

async fn proxy_internal_api(
    State(proxy): State<WebProxyState>,
    method: Method,
    uri: Uri,
    headers: HeaderMap,
    body: Body,
) -> Response {
    let upstream_url = upstream_url(&proxy.api_base_url, &uri);
    let body_bytes = match to_bytes(body, 10 * 1024 * 1024).await {
        Ok(bytes) => bytes,
        Err(err) => {
            return (
                StatusCode::BAD_REQUEST,
                format!("Falha ao ler corpo da requisição do proxy: {err}"),
            )
                .into_response();
        }
    };

    let reqwest_method = match reqwest::Method::from_bytes(method.as_str().as_bytes()) {
        Ok(value) => value,
        Err(err) => {
            return (
                StatusCode::METHOD_NOT_ALLOWED,
                format!("Método HTTP inválido no proxy: {err}"),
            )
                .into_response();
        }
    };

    let mut request = proxy
        .http_client
        .request(reqwest_method, &upstream_url)
        .body(body_bytes.to_vec());
    if let Some(value) = headers
        .get(header::ACCEPT)
        .and_then(|value| value.to_str().ok())
    {
        request = request.header(reqwest::header::ACCEPT, value);
    }
    if let Some(value) = headers
        .get(header::CONTENT_TYPE)
        .and_then(|value| value.to_str().ok())
    {
        request = request.header(reqwest::header::CONTENT_TYPE, value);
    }
    if !proxy.api_token.trim().is_empty() && !proxy.api_token_header.trim().is_empty() {
        request = request.header(proxy.api_token_header.trim(), proxy.api_token.trim());
    }

    let response = match request.send().await {
        Ok(response) => response,
        Err(err) => {
            return (
                StatusCode::BAD_GATEWAY,
                format!("Falha ao acessar API interna pelo proxy em {upstream_url}: {err}"),
            )
                .into_response();
        }
    };

    let status =
        StatusCode::from_u16(response.status().as_u16()).unwrap_or(StatusCode::BAD_GATEWAY);
    let content_type = response
        .headers()
        .get(reqwest::header::CONTENT_TYPE)
        .cloned();
    let response_bytes = match response.bytes().await {
        Ok(bytes) => bytes,
        Err(err) => {
            return (
                StatusCode::BAD_GATEWAY,
                format!("Falha ao ler resposta da API interna pelo proxy: {err}"),
            )
                .into_response();
        }
    };

    let mut builder = Response::builder().status(status);
    if let Some(content_type) =
        content_type.and_then(|value| HeaderValue::from_bytes(value.as_bytes()).ok())
    {
        builder = builder.header(header::CONTENT_TYPE, content_type);
    }
    builder
        .header(header::CACHE_CONTROL, "no-store, no-cache, must-revalidate")
        .body(Body::from(response_bytes.to_vec()))
        .unwrap_or_else(|err| {
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                format!("Falha ao montar resposta do proxy: {err}"),
            )
                .into_response()
        })
}

fn upstream_url(api_base_url: &str, uri: &Uri) -> String {
    let raw_path = uri.path();
    let mut path = raw_path
        .strip_prefix("/__internal_api")
        .unwrap_or(raw_path)
        .to_string();
    if path.is_empty() {
        path = "/".to_string();
    }
    let query = uri
        .query()
        .map(|query| format!("?{query}"))
        .unwrap_or_default();
    format!("{}{}{}", api_base_url.trim_end_matches('/'), path, query)
}

fn resolve_proxy_api_base_url(
    settings: &RuntimeSettings,
    web_port: u16,
    internal_config: &crate::internal_api::config::InternalApiConfig,
) -> String {
    let derived = format!(
        "http://{}:{}",
        crate::internal_api::config::public_url_host(&internal_config.host),
        internal_config.port
    );
    let configured = normalize_client_base_url(&settings.internal_api_base_url);

    if configured.trim().is_empty()
        || configured.contains(&format!(":{web_port}"))
        || configured.ends_with("/__internal_api")
        || configured.ends_with("/__internal_api/")
    {
        return derived;
    }

    configured
}

fn web_bind_host(settings: &RuntimeSettings) -> String {
    // Fonte única de verdade: configuração salva pela interface/runtime.
    // 0.0.0.0 é bind de rede; 127.0.0.1 é bind local. Não há fallback implícito.
    normalize_web_bind_host(settings.local_web_host.trim())
}

fn normalize_web_bind_host(host: &str) -> String {
    crate::net_bind::normalize_bind_host(host)
}

fn bind_web_listener(
    state: &SharedState,
    configured_host: &str,
    port: u16,
) -> Result<WebBindResult, String> {
    let primary_host = normalize_web_bind_host(configured_host);
    let addr = socket_addr(&primary_host, port)?;

    match crate::net_bind::bind_fixed_service_listener(&primary_host, port) {
        Ok(bound) => {
            let url = format!("http://{}:{}", bound.public_host, bound.port);
            if let Some(note) = &bound.note {
                log_runtime_event(
                    state,
                    "warning",
                    "Webport/proxy publicado em interface LAN alternativa",
                    serde_json::json!({
                        "configured_host": configured_host,
                        "requested_host": primary_host,
                        "effective_host": bound.bind_host.clone(),
                        "configured_port": port,
                        "effective_port": bound.port,
                        "url": url.clone(),
                        "note": note,
                        "fixed_port_policy": true,
                        "port_fallback": false
                    }),
                );
            }
            Ok(WebBindResult::Bound {
                host: bound.bind_host,
                port: bound.port,
                url,
                listener: bound.listener,
            })
        }
        Err(err) if err.kind() == std::io::ErrorKind::AddrInUse => {
            if let Some(status) = adopt_existing_web_runtime_with_retry(&primary_host, port) {
                log_runtime_event(
                    state,
                    "warning",
                    "Servidor web/proxy já estava ativo; reutilizando instância existente",
                    serde_json::json!({
                        "configured_host": configured_host,
                        "effective_host": primary_host,
                        "configured_port": port,
                        "effective_port": port,
                        "addr": addr.to_string(),
                        "error": err.to_string(),
                        "external": true,
                        "url": status.url.clone(),
                        "fixed_port_policy": true
                    }),
                );
                Ok(WebBindResult::External(status))
            } else {
                let message = format!(
                    "Webport/proxy não foi iniciado em {addr}: {err}. A aplicação desktop continuará funcionando. Ajuste a porta nos parâmetros ou encerre o processo que está usando esta porta."
                );
                log_runtime_event(
                    state,
                    "warning",
                    "Webport/proxy não iniciado porque a porta configurada está ocupada",
                    serde_json::json!({
                        "configured_host": configured_host,
                        "effective_host": primary_host,
                        "configured_port": port,
                        "effective_port": port,
                        "addr": addr.to_string(),
                        "error": err.to_string(),
                        "auto_port": false,
                        "fallback_to_localhost": false,
                        "desktop_startup_blocked": false
                    }),
                );
                Ok(WebBindResult::External(WebRuntimeStatus {
                    running: false,
                    host: primary_host,
                    port,
                    url: None,
                    started_at: None,
                    external: false,
                    message: Some(message),
                }))
            }
        }
        Err(err) => {
            let message = format!(
                "Webport/proxy não foi iniciado em {addr}: {err}. A aplicação desktop continuará funcionando."
            );
            log_runtime_event(
                state,
                "warning",
                "Webport/proxy indisponível sem bloquear a aplicação",
                serde_json::json!({
                    "configured_host": configured_host,
                    "effective_host": primary_host,
                    "configured_port": port,
                    "effective_port": port,
                    "addr": addr.to_string(),
                    "error": err.to_string(),
                    "auto_port": false,
                    "fallback_to_localhost": false,
                    "desktop_startup_blocked": false
                }),
            );
            Ok(WebBindResult::External(WebRuntimeStatus {
                running: false,
                host: primary_host,
                port,
                url: None,
                started_at: None,
                external: false,
                message: Some(message),
            }))
        }
    }
}

fn web_bind_host_from_env() -> String {
    std::env::var("PIGE360_DEPLOYER_WEB_HOST")
        .or_else(|_| std::env::var("APP_WEB_HOST"))
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| "0.0.0.0".to_string())
}

fn web_port_from_env() -> u16 {
    std::env::var("PIGE360_DEPLOYER_WEB_PORT")
        .or_else(|_| std::env::var("APP_WEB_PORT"))
        .ok()
        .and_then(|value| value.trim().parse::<u16>().ok())
        .unwrap_or(61002)
}

fn socket_addr(host: &str, port: u16) -> Result<SocketAddr, String> {
    format!("{host}:{port}")
        .parse()
        .map_err(|err| format!("Endereço do servidor web inválido: {err}"))
}

fn client_host_for_bind(host: &str) -> String {
    crate::net_bind::public_host_for_bind(host)
}

fn normalize_client_base_url(value: &str) -> String {
    let trimmed = value.trim();
    let normalized = if trimmed.is_empty() {
        "http://127.0.0.1:61001".to_string()
    } else {
        trimmed.to_string()
    };
    normalized
        .replace("http://0.0.0.0:", "http://127.0.0.1:")
        .replace("http://[::]:", "http://127.0.0.1:")
        .replace("http://:::", "http://127.0.0.1:")
        .trim_end_matches('/')
        .trim_end_matches("/__internal_api")
        .to_string()
}

fn adopt_existing_web_runtime_with_retry(bind_host: &str, port: u16) -> Option<WebRuntimeStatus> {
    // Em Windows, quando duas rotas de inicialização ou duas instâncias sobem quase juntas,
    // uma delas pode fazer o bind antes do servidor HTTP aceitar conexões. Nesse intervalo,
    // o segundo bind recebe WSAEADDRINUSE/os error 10048, mas o probe imediato ainda falha.
    // Aguardar alguns ciclos evita tratar a própria aplicação em aquecimento como processo externo.
    for _ in 0..12 {
        if let Some(status) = adopt_existing_web_runtime(bind_host, port) {
            return Some(status);
        }
        std::thread::sleep(Duration::from_millis(250));
    }
    None
}

fn adopt_existing_web_runtime(bind_host: &str, port: u16) -> Option<WebRuntimeStatus> {
    let local_url = format!("http://127.0.0.1:{port}");
    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_millis(900))
        .build()
        .ok()?;

    if !probe_template_webport(&client, &format!("{local_url}/__web_health"))
        && !probe_template_webport(&client, &local_url)
    {
        return None;
    }

    Some(WebRuntimeStatus {
        running: true,
        host: bind_host.to_string(),
        port,
        url: Some(local_url),
        started_at: None,
        external: true,
        message: Some("Webport já estava ativo em outra instância do PIGE360 Deployer; esta janela reutilizou a instância existente sem tentar abrir uma segunda porta.".to_string()),
    })
}

fn probe_template_webport(client: &reqwest::blocking::Client, url: &str) -> bool {
    let response = match client.get(url).send() {
        Ok(response) => response,
        Err(_) => return false,
    };
    if !response.status().is_success() {
        return false;
    }
    let body = match response.text() {
        Ok(body) => body,
        Err(_) => return false,
    };
    if let Ok(value) = serde_json::from_str::<serde_json::Value>(&body) {
        if value
            .get("service")
            .and_then(|service| service.as_str())
            .map(|value| value == "pige360-deployer-web-proxy" || value == "internal-api-via-webport")
            .unwrap_or(false)
        {
            return true;
        }
    }
    let normalized = body.to_ascii_lowercase();
    normalized.contains("pige360 deployer")
        || normalized.contains("pige360-deployer-web-proxy")
        || normalized.contains("pige360_deployer_web_runtime")
}

fn log_runtime_event(state: &SharedState, level: &str, message: &str, details: serde_json::Value) {
    if let (Ok(db_path), Ok(data_dir)) = (state.db_path(), state.data_dir()) {
        if let Ok(conn) = open_connection(&db_path) {
            let _ = write_app_log(
                &conn,
                &data_dir,
                AppLogInput {
                    level,
                    category: "web-server",
                    message,
                    source: Some("internal_api::web_server"),
                    route: None,
                    details: Some(&details),
                },
            );
        }
    }
}
