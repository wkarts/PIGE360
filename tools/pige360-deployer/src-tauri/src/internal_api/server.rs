use std::{
    net::{SocketAddr, TcpListener as StdTcpListener},
    sync::{Mutex, OnceLock},
    thread::JoinHandle,
    time::Duration,
};

use tokio::{net::TcpListener, sync::oneshot};

use crate::{
    app_state::SharedState,
    db::{open_connection, write_app_log, AppLogInput},
    internal_api::{config::InternalApiConfig, routes, state::InternalApiState},
};

struct ApiRuntimeHandle {
    bind_host: String,
    public_host: String,
    port: u16,
    started_at: String,
    shutdown: Option<oneshot::Sender<()>>,
    thread: Option<JoinHandle<()>>,
    docs_url: String,
}

static API_RUNTIME: OnceLock<Mutex<Option<ApiRuntimeHandle>>> = OnceLock::new();
static API_START_LOCK: OnceLock<Mutex<()>> = OnceLock::new();

fn runtime_slot() -> &'static Mutex<Option<ApiRuntimeHandle>> {
    API_RUNTIME.get_or_init(|| Mutex::new(None))
}

fn start_lock() -> &'static Mutex<()> {
    API_START_LOCK.get_or_init(|| Mutex::new(()))
}

#[derive(Debug, Clone, serde::Serialize)]
pub struct ApiRuntimeStatus {
    pub running: bool,
    pub host: String,
    pub port: u16,
    pub url: Option<String>,
    pub docs_url: Option<String>,
    pub started_at: Option<String>,
    pub external: bool,
    pub message: Option<String>,
}

pub fn run_blocking(state: &SharedState, host: &str, port: u16) -> Result<(), String> {
    let config = InternalApiConfig::default().with_host_port(host.to_string(), port);
    run_blocking_with_config(state, config)
}

pub fn run_blocking_with_config(
    state: &SharedState,
    config: InternalApiConfig,
) -> Result<(), String> {
    let rt = tokio::runtime::Runtime::new()
        .map_err(|err| format!("Falha ao criar runtime Tokio: {err}"))?;
    rt.block_on(run_with_config(state, config))
}

pub async fn run(state: &SharedState, host: &str, port: u16) -> Result<(), String> {
    let config = InternalApiConfig::default().with_host_port(host.to_string(), port);
    run_with_config(state, config).await
}

pub async fn run_with_config(state: &SharedState, config: InternalApiConfig) -> Result<(), String> {
    config.validate_bind()?;

    let api_state = build_api_state(state, &config)?;
    let addr = socket_addr(&config)?;
    let public_host = crate::internal_api::config::public_url_host(&config.host);
    std::env::set_var("PIGE360_DEPLOYER_API_HOST", config.host.clone());
    std::env::set_var("PIGE360_DEPLOYER_API_PORT", config.port.to_string());
    std::env::set_var(
        "PIGE360_DEPLOYER_API_BASE_URL",
        format!("http://{public_host}:{}", config.port),
    );
    let listener = TcpListener::bind(addr)
        .await
        .map_err(|err| format!("Falha ao iniciar API interna em {addr}: {err}"))?;

    // O servidor web/proxy não é iniciado aqui.
    // A inicialização dos serviços é centralizada no orquestrador do Tauri/CLI
    // para evitar dupla tentativa de bind na mesma porta durante o startup.
    println!("API interna ativa em http://{addr}");
    axum::serve(listener, routes::router(api_state))
        .await
        .map_err(|err| format!("Falha no servidor da API interna: {err}"))
}

pub fn start_background(
    state: SharedState,
    config: InternalApiConfig,
) -> Result<ApiRuntimeStatus, String> {
    config.validate_bind()?;
    let _start_guard = start_lock()
        .lock()
        .map_err(|_| "Falha ao bloquear inicialização da API interna.".to_string())?;

    {
        let guard = runtime_slot()
            .lock()
            .map_err(|_| "Falha ao bloquear runtime da API interna.".to_string())?;
        if let Some(handle) = guard.as_ref() {
            return Ok(ApiRuntimeStatus {
                running: true,
                host: handle.public_host.clone(),
                port: handle.port,
                url: Some(format!("http://{}:{}", handle.public_host, handle.port)),
                docs_url: Some(handle.docs_url.clone()),
                started_at: Some(handle.started_at.clone()),
                external: false,
                message: None,
            });
        }
    }

    log_runtime_event(
        &state,
        "info",
        "API iniciando",
        serde_json::json!({ "host": config.host.clone(), "port": config.port }),
    );
    let mut config = config;
    let host = config.host.clone();
    let public_host = crate::internal_api::config::public_url_host(&host);
    let port = config.port;
    let addr = socket_addr(&config)?;
    std::env::set_var("PIGE360_DEPLOYER_API_HOST", host.clone());
    std::env::set_var("PIGE360_DEPLOYER_API_PORT", port.to_string());
    std::env::set_var(
        "PIGE360_DEPLOYER_API_BASE_URL",
        format!("http://{public_host}:{port}"),
    );
    let std_listener = match StdTcpListener::bind(addr) {
        Ok(listener) => listener,
        Err(err) => {
            if err.kind() == std::io::ErrorKind::AddrInUse {
                if let Some(status) = adopt_existing_api_runtime(&public_host, port) {
                    log_runtime_event(
                        &state,
                        "warning",
                        "API interna já estava ativa; reutilizando instância existente",
                        serde_json::json!({
                            "configured": addr.to_string(),
                            "port": port,
                            "error": err.to_string(),
                            "external": true,
                            "url": status.url.clone()
                        }),
                    );
                    return Ok(status);
                }
            }

            let message = format!(
                "Porta da API interna {addr} indisponível: {err}. A porta está ocupada por outro processo que não respondeu como PIGE360 Deployer API. Altere PIGE360_DEPLOYER_API_PORT ou encerre o processo externo que está usando esta porta."
            );
            log_runtime_event(
                &state,
                "error",
                "Porta da API interna indisponível",
                serde_json::json!({ "configured": addr.to_string(), "port": port, "error": err.to_string(), "adopted_existing_instance": false }),
            );
            return Err(message);
        }
    };
    std_listener
        .set_nonblocking(true)
        .map_err(|err| format!("Falha ao configurar listener da API interna: {err}"))?;
    config.base_url = format!("http://{public_host}:{port}");
    let started_at = chrono::Utc::now().to_rfc3339();
    let docs_url = config.docs_url();
    let (tx, rx) = oneshot::channel::<()>();
    let thread_started_at = started_at.clone();
    let thread_state = state.clone();

    let thread = std::thread::Builder::new()
        .name("pige360-deployer-internal-api".to_string())
        .spawn(move || {
            let rt = match tokio::runtime::Runtime::new() {
                Ok(rt) => rt,
                Err(err) => {
                    eprintln!("Falha ao criar runtime da API interna: {err}");
                    return;
                }
            };
            let result = rt.block_on(async move {
                let addr = socket_addr(&config)?;
                let listener = TcpListener::from_std(std_listener).map_err(|err| {
                    format!("Falha ao anexar listener da API interna em {addr}: {err}")
                })?;
                let api_state = build_api_state(&thread_state, &config)?;
                println!("API interna desktop ativa em http://{addr} desde {thread_started_at}");
                axum::serve(listener, routes::router(api_state))
                    .with_graceful_shutdown(async move {
                        let _ = rx.await;
                    })
                    .await
                    .map_err(|err| format!("Falha no servidor da API interna: {err}"))
            });
            if let Err(err) = result {
                eprintln!("{err}");
            }
        })
        .map_err(|err| format!("Falha ao iniciar thread da API interna: {err}"))?;

    let mut guard = runtime_slot()
        .lock()
        .map_err(|_| "Falha ao bloquear runtime da API interna.".to_string())?;
    *guard = Some(ApiRuntimeHandle {
        bind_host: host.clone(),
        public_host: public_host.clone(),
        port,
        docs_url: docs_url.clone(),
        started_at: started_at.clone(),
        shutdown: Some(tx),
        thread: Some(thread),
    });

    log_runtime_event(
        &state,
        "info",
        "API iniciada com sucesso",
        serde_json::json!({
            "bind_url": format!("http://{host}:{port}"),
            "url": format!("http://{public_host}:{port}"),
            "docs_url": docs_url,
            "web_url": crate::internal_api::web_server::status().ok().and_then(|status| status.url)
        }),
    );

    Ok(ApiRuntimeStatus {
        running: true,
        host: public_host.clone(),
        port,
        url: Some(format!("http://{public_host}:{port}")),
        docs_url: Some(docs_url),
        started_at: Some(started_at),
        external: false,
        message: None,
    })
}

pub fn stop_background() -> Result<ApiRuntimeStatus, String> {
    // O webport/proxy é independente da API interna. Parar/reiniciar a API
    // não deve derrubar http://127.0.0.1:61002 nem gerar ERR_CONNECTION_REFUSED.
    let mut handle = {
        let mut guard = runtime_slot()
            .lock()
            .map_err(|_| "Falha ao bloquear runtime da API interna.".to_string())?;
        guard.take()
    };

    if let Some(handle) = handle.as_mut() {
        let stopped_host = handle.bind_host.clone();
        let stopped_port = handle.port;
        if let Some(shutdown) = handle.shutdown.take() {
            let _ = shutdown.send(());
        }
        if let Some(thread) = handle.thread.take() {
            let _ = thread.join();
        }
        eprintln!("API interna parada em {stopped_host}:{stopped_port}");
    }

    status()
}

pub fn status() -> Result<ApiRuntimeStatus, String> {
    let guard = runtime_slot()
        .lock()
        .map_err(|_| "Falha ao bloquear runtime da API interna.".to_string())?;
    if let Some(handle) = guard.as_ref() {
        Ok(ApiRuntimeStatus {
            running: true,
            host: handle.public_host.clone(),
            port: handle.port,
            url: Some(format!("http://{}:{}", handle.public_host, handle.port)),
            docs_url: Some(handle.docs_url.clone()),
            started_at: Some(handle.started_at.clone()),
            external: false,
            message: None,
        })
    } else {
        let host =
            std::env::var("PIGE360_DEPLOYER_API_HOST").unwrap_or_else(|_| "127.0.0.1".to_string());
        let public_host = crate::internal_api::config::public_url_host(&host);
        let port = std::env::var("PIGE360_DEPLOYER_API_PORT")
            .ok()
            .and_then(|value| value.parse::<u16>().ok())
            .unwrap_or(61001);
        if let Some(status) = adopt_existing_api_runtime(&public_host, port) {
            return Ok(status);
        }

        Ok(ApiRuntimeStatus {
            running: false,
            host,
            port,
            url: None,
            docs_url: None,
            started_at: None,
            external: false,
            message: None,
        })
    }
}

fn adopt_existing_api_runtime(public_host: &str, port: u16) -> Option<ApiRuntimeStatus> {
    let local_url = format!("http://127.0.0.1:{port}");
    let health_url = format!("{local_url}/health");
    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_millis(900))
        .build()
        .ok()?;
    let response = client.get(&health_url).send().ok()?;
    if !response.status().is_success() {
        return None;
    }
    let value = response.json::<serde_json::Value>().ok()?;
    let version_matches = value
        .get("version")
        .and_then(|version| version.as_str())
        .map(|version| version == env!("CARGO_PKG_VERSION"))
        .unwrap_or(false);
    if !version_matches {
        return None;
    }

    Some(ApiRuntimeStatus {
        running: true,
        host: public_host.to_string(),
        port,
        url: Some(local_url),
        docs_url: Some(format!("http://127.0.0.1:{port}/docs")),
        started_at: None,
        external: true,
        message: Some("API interna já estava ativa em outra instância do PIGE360 Deployer; esta janela reutilizou a instância existente sem tentar abrir uma segunda porta.".to_string()),
    })
}

fn socket_addr(config: &InternalApiConfig) -> Result<SocketAddr, String> {
    format!("{}:{}", config.host, config.port)
        .parse()
        .map_err(|err| format!("Endereço da API interna inválido: {err}"))
}

fn log_runtime_event(state: &SharedState, level: &str, message: &str, details: serde_json::Value) {
    if let (Ok(db_path), Ok(data_dir)) = (state.db_path(), state.data_dir()) {
        if let Ok(conn) = open_connection(&db_path) {
            let _ = write_app_log(
                &conn,
                &data_dir,
                AppLogInput {
                    level,
                    category: "internal-api",
                    message,
                    source: Some("internal_api::server"),
                    route: None,
                    details: Some(&details),
                },
            );
        }
    }
}

fn build_api_state(
    state: &SharedState,
    config: &InternalApiConfig,
) -> Result<InternalApiState, String> {
    Ok(InternalApiState {
        db_path: state.db_path()?,
        data_dir: state.data_dir()?,
        started_at: chrono::Utc::now().to_rfc3339(),
        host: config.host.clone(),
        port: config.port,
        config: config.clone(),
    })
}
