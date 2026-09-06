use std::{
    net::{SocketAddr, TcpListener as StdTcpListener},
    sync::{Mutex, OnceLock},
    thread::JoinHandle,
};

use serde::Serialize;
use tokio::{net::TcpListener, sync::oneshot};

use crate::{
    app_state::SharedState,
    native_webhook::{
        config::WebhookConfig,
        routes::{self, WebhookState},
    },
};

struct WebhookRuntimeHandle {
    bind_host: String,
    public_host: String,
    port: u16,
    base_path: String,
    started_at: String,
    shutdown: Option<oneshot::Sender<()>>,
    thread: Option<JoinHandle<()>>,
    loopback: Option<AuxiliaryWebhookRuntimeHandle>,
}

struct AuxiliaryWebhookRuntimeHandle {
    shutdown: Option<oneshot::Sender<()>>,
    thread: Option<JoinHandle<()>>,
}

struct WebhookServerThreadConfig {
    name: String,
    state: SharedState,
    std_listener: StdTcpListener,
    config: WebhookConfig,
    rx: oneshot::Receiver<()>,
}

static WEBHOOK_RUNTIME: OnceLock<Mutex<Option<WebhookRuntimeHandle>>> = OnceLock::new();
static WEBHOOK_START_LOCK: OnceLock<Mutex<()>> = OnceLock::new();

fn runtime_slot() -> &'static Mutex<Option<WebhookRuntimeHandle>> {
    WEBHOOK_RUNTIME.get_or_init(|| Mutex::new(None))
}

fn start_lock() -> &'static Mutex<()> {
    WEBHOOK_START_LOCK.get_or_init(|| Mutex::new(()))
}

#[derive(Debug, Clone, Serialize)]
pub struct WebhookRuntimeStatus {
    pub running: bool,
    pub host: String,
    pub port: u16,
    pub url: Option<String>,
    pub base_path: String,
    pub events_count: usize,
    pub started_at: Option<String>,
}

pub fn start_background(state: SharedState) -> Result<WebhookRuntimeStatus, String> {
    let config = crate::runtime_config::resolve_webhook_config(&state)?;
    start_background_with_config(state, config)
}

pub fn start_background_with_config(
    state: SharedState,
    mut config: WebhookConfig,
) -> Result<WebhookRuntimeStatus, String> {
    let _start_guard = start_lock()
        .lock()
        .map_err(|_| "Falha ao bloquear inicialização do Webhook Service.".to_string())?;
    if !config.enabled {
        return Ok(WebhookRuntimeStatus {
            running: false,
            host: config.public_host(),
            port: config.port,
            url: None,
            base_path: config.base_path.clone(),
            events_count: routes::list_events_snapshot().len(),
            started_at: None,
        });
    }
    config.validate_bind()?;
    {
        let guard = runtime_slot()
            .lock()
            .map_err(|_| "Falha ao bloquear runtime do Webhook Service.".to_string())?;
        if let Some(handle) = guard.as_ref() {
            if handle.bind_host == config.host
                && handle.port == config.port
                && handle.base_path == config.base_path
            {
                return Ok(status_from_handle(handle));
            }
        }
    }
    let _ = stop_background();
    std::thread::sleep(std::time::Duration::from_millis(250));

    let public_host = config.public_host();
    if !crate::net_bind::is_wildcard_host(&config.host)
        && existing_webhook_service_responds(&public_host, config.port)
    {
        let started_at = chrono::Utc::now().to_rfc3339();
        let handle = WebhookRuntimeHandle {
            bind_host: config.host.clone(),
            public_host: public_host.clone(),
            port: config.port,
            base_path: config.base_path.clone(),
            started_at,
            shutdown: None,
            thread: None,
            loopback: None,
        };
        let status = status_from_handle(&handle);
        let mut guard = runtime_slot()
            .lock()
            .map_err(|_| "Falha ao bloquear runtime do Webhook Service.".to_string())?;
        *guard = Some(handle);
        return Ok(status);
    }
    let bound = match bind_listener_with_safe_fallback(&config) {
        Ok(bound) => bound,
        Err(err) => {
            let public_host = config.public_host();
            if existing_webhook_service_responds(&public_host, config.port) {
                let started_at = chrono::Utc::now().to_rfc3339();
                let handle = WebhookRuntimeHandle {
                    bind_host: config.host.clone(),
                    public_host: public_host.clone(),
                    port: config.port,
                    base_path: config.base_path.clone(),
                    started_at,
                    shutdown: None,
                    thread: None,
                    loopback: None,
                };
                let status = status_from_handle(&handle);
                let mut guard = runtime_slot()
                    .lock()
                    .map_err(|_| "Falha ao bloquear runtime do Webhook Service.".to_string())?;
                *guard = Some(handle);
                return Ok(status);
            }
            return Err(err);
        }
    };
    let requested_host = config.host.clone();
    let std_listener = bound.listener;
    let public_host = bound.public_host;
    let port = bound.port;
    config.host = bound.bind_host;

    let (tx, rx) = oneshot::channel::<()>();
    let started_at = chrono::Utc::now().to_rfc3339();
    let base_path = config.base_path.clone();
    let thread = spawn_webhook_server_thread(WebhookServerThreadConfig {
        name: "pige360-deployer-webhook-service".to_string(),
        state: state.clone(),
        std_listener,
        config: config.clone(),
        rx,
    })?;
    let loopback = prepare_loopback_mirror(&requested_host, &state, &config, port);

    let handle = WebhookRuntimeHandle {
        bind_host: config.host.clone(),
        public_host: public_host.clone(),
        port,
        base_path,
        started_at,
        shutdown: Some(tx),
        thread: Some(thread),
        loopback,
    };
    let status = status_from_handle(&handle);
    let mut guard = runtime_slot()
        .lock()
        .map_err(|_| "Falha ao bloquear runtime do Webhook Service.".to_string())?;
    *guard = Some(handle);
    Ok(status)
}

pub fn stop_background() -> Result<WebhookRuntimeStatus, String> {
    let mut handle = {
        let mut guard = runtime_slot()
            .lock()
            .map_err(|_| "Falha ao bloquear runtime do Webhook Service.".to_string())?;
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

pub fn status() -> Result<WebhookRuntimeStatus, String> {
    let guard = runtime_slot()
        .lock()
        .map_err(|_| "Falha ao bloquear runtime do Webhook Service.".to_string())?;
    if let Some(handle) = guard.as_ref() {
        Ok(status_from_handle(handle))
    } else {
        Ok(WebhookRuntimeStatus {
            running: false,
            host: std::env::var("PIGE360_DEPLOYER_WEBHOOK_HOST")
                .unwrap_or_else(|_| "0.0.0.0".to_string()),
            port: std::env::var("PIGE360_DEPLOYER_WEBHOOK_PORT")
                .ok()
                .and_then(|value| value.parse::<u16>().ok())
                .unwrap_or(61003),
            url: None,
            base_path: std::env::var("PIGE360_DEPLOYER_WEBHOOK_BASE_PATH")
                .unwrap_or_else(|_| "/webhooks".to_string()),
            events_count: routes::list_events_snapshot().len(),
            started_at: None,
        })
    }
}

fn status_from_handle(handle: &WebhookRuntimeHandle) -> WebhookRuntimeStatus {
    WebhookRuntimeStatus {
        running: true,
        host: handle.public_host.clone(),
        port: handle.port,
        url: Some(format!("http://{}:{}", handle.public_host, handle.port)),
        base_path: handle.base_path.clone(),
        events_count: routes::list_events_snapshot().len(),
        started_at: Some(handle.started_at.clone()),
    }
}

fn spawn_webhook_server_thread(
    config: WebhookServerThreadConfig,
) -> Result<JoinHandle<()>, String> {
    let WebhookServerThreadConfig {
        name,
        state,
        std_listener,
        config,
        rx,
    } = config;

    std_listener
        .set_nonblocking(true)
        .map_err(|err| format!("Falha ao configurar listener do Webhook Service: {err}"))?;

    std::thread::Builder::new()
        .name(name)
        .spawn(move || {
            let rt = match tokio::runtime::Runtime::new() {
                Ok(rt) => rt,
                Err(err) => {
                    eprintln!("Falha ao criar runtime do Webhook Service: {err}");
                    return;
                }
            };
            let result = rt.block_on(async move {
                let listener = TcpListener::from_std(std_listener)
                    .map_err(|err| format!("Falha ao anexar listener do Webhook Service: {err}"))?;
                let state = WebhookState {
                    app_state: state,
                    config,
                };
                axum::serve(listener, routes::router(state))
                    .with_graceful_shutdown(async move {
                        let _ = rx.await;
                    })
                    .await
                    .map_err(|err| format!("Falha no Webhook Service: {err}"))
            });
            if let Err(err) = result {
                eprintln!("{err}");
            }
        })
        .map_err(|err| format!("Falha ao iniciar thread do Webhook Service: {err}"))
}

fn prepare_loopback_mirror(
    configured_host: &str,
    state: &SharedState,
    effective_config: &WebhookConfig,
    port: u16,
) -> Option<AuxiliaryWebhookRuntimeHandle> {
    if !should_bind_loopback_mirror(configured_host, &effective_config.host) {
        return None;
    }

    let loopback_host = "127.0.0.1";
    let listener = match crate::net_bind::bind_fixed_service_listener(loopback_host, port) {
        Ok(bound) => bound.listener,
        Err(err) => {
            eprintln!(
                "Webhook Service ativo em {}:{port}, mas loopback {loopback_host}:{port} está indisponível: {err}",
                effective_config.host
            );
            return None;
        }
    };

    let mut loopback_config = effective_config.clone();
    loopback_config.host = loopback_host.to_string();
    let (tx, rx) = oneshot::channel::<()>();
    match spawn_webhook_server_thread(WebhookServerThreadConfig {
        name: "pige360-deployer-webhook-service-loopback".to_string(),
        state: state.clone(),
        std_listener: listener,
        config: loopback_config,
        rx,
    }) {
        Ok(thread) => Some(AuxiliaryWebhookRuntimeHandle {
            shutdown: Some(tx),
            thread: Some(thread),
        }),
        Err(err) => {
            eprintln!(
                "Falha ao iniciar listener loopback auxiliar do Webhook Service em {loopback_host}:{port}: {err}"
            );
            None
        }
    }
}

fn should_bind_loopback_mirror(configured_host: &str, effective_host: &str) -> bool {
    !crate::net_bind::is_wildcard_host(effective_host)
        && !is_loopback_host(effective_host)
        && !is_loopback_host(configured_host)
}

fn is_loopback_host(host: &str) -> bool {
    matches!(host.trim(), "127.0.0.1" | "localhost" | "::1" | "[::1]")
}

fn bind_listener_with_safe_fallback(
    config: &WebhookConfig,
) -> Result<crate::net_bind::PreparedListener, String> {
    let requested_addr = socket_addr(config)?;
    crate::net_bind::bind_fixed_service_listener(&config.host, config.port).map_err(|err| {
        format!(
            "Porta fixa do Webhook Service {requested_addr} indisponível: {err}. Ajuste PIGE360_DEPLOYER_WEBHOOK_PORT/parâmetros ou encerre o processo que está usando esta porta."
        )
    })
}

fn existing_webhook_service_responds(host: &str, port: u16) -> bool {
    let url = format!("http://{host}:{port}/health");
    reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_millis(750))
        .build()
        .and_then(|client| client.get(url).send())
        .and_then(|response| response.error_for_status())
        .map(|response| {
            response
                .text()
                .map(|body| body.contains("\"service\":\"webhook\"") || body.contains("webhook"))
                .unwrap_or(false)
        })
        .unwrap_or(false)
}

fn socket_addr(config: &WebhookConfig) -> Result<SocketAddr, String> {
    format!("{}:{}", config.host, config.port)
        .parse()
        .map_err(|err| format!("Endereço do Webhook Service inválido: {err}"))
}
