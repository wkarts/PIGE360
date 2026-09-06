use std::{env, path::PathBuf};

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RuntimeMode {
    Desktop,
    HeadlessApi,
    WebProxy,
    Cli,
    Worker,
}

#[derive(Debug, Clone)]
pub struct CliArgs {
    pub mode: RuntimeMode,
    pub host: String,
    pub port: u16,
    pub database_driver: String,
    pub data_dir: Option<PathBuf>,
    pub start_web_proxy: bool,
    pub start_webhook: bool,
    pub start_websocket: bool,
    pub start_services: bool,
}

impl Default for CliArgs {
    fn default() -> Self {
        Self {
            mode: RuntimeMode::Desktop,
            host: env::var("PIGE360_DEPLOYER_API_HOST").unwrap_or_else(|_| "127.0.0.1".to_string()),
            port: env::var("PIGE360_DEPLOYER_API_PORT")
                .ok()
                .and_then(|value| value.parse::<u16>().ok())
                .unwrap_or(61001),
            database_driver: "sqlite".to_string(),
            data_dir: None,
            start_web_proxy: false,
            start_webhook: false,
            start_websocket: false,
            start_services: false,
        }
    }
}

impl CliArgs {
    pub fn parse() -> Self {
        let mut parsed = Self::default();
        let args: Vec<String> = env::args().skip(1).collect();
        let mut index = 0usize;
        while index < args.len() {
            let arg = &args[index];
            if let Some(value) = arg.strip_prefix("--mode=") {
                parsed.mode = parse_mode(value);
            } else if arg == "--mode" {
                if let Some(value) = args.get(index + 1) {
                    parsed.mode = parse_mode(value);
                    index += 1;
                }
            } else if let Some(value) = arg.strip_prefix("--host=") {
                if !value.trim().is_empty() {
                    parsed.host = value.trim().to_string();
                }
            } else if arg == "--host" {
                if let Some(value) = args.get(index + 1) {
                    if !value.trim().is_empty() {
                        parsed.host = value.trim().to_string();
                    }
                    index += 1;
                }
            } else if let Some(value) = arg.strip_prefix("--port=") {
                if let Ok(port) = value.parse::<u16>() {
                    parsed.port = port;
                }
            } else if arg == "--port" {
                if let Some(value) = args.get(index + 1) {
                    if let Ok(port) = value.parse::<u16>() {
                        parsed.port = port;
                    }
                    index += 1;
                }
            } else if let Some(value) = arg.strip_prefix("--database-driver=") {
                parsed.database_driver = value.to_ascii_lowercase();
            } else if arg == "--database-driver" {
                if let Some(value) = args.get(index + 1) {
                    parsed.database_driver = value.to_ascii_lowercase();
                    index += 1;
                }
            } else if let Some(value) = arg.strip_prefix("--data-dir=") {
                if !value.trim().is_empty() {
                    parsed.data_dir = Some(PathBuf::from(value));
                }
            } else if arg == "--data-dir" {
                if let Some(value) = args.get(index + 1) {
                    if !value.trim().is_empty() {
                        parsed.data_dir = Some(PathBuf::from(value));
                    }
                    index += 1;
                }
            } else if matches!(
                arg.as_str(),
                "--start-web-proxy"
                    | "--web-proxy-auto-start"
                    | "--start-webport"
                    | "--webport-auto-start"
            ) {
                parsed.start_web_proxy = true;
            } else if matches!(
                arg.as_str(),
                "--start-webhook" | "--webhook-auto-start" | "--webhook"
            ) {
                parsed.start_webhook = true;
            } else if matches!(
                arg.as_str(),
                "--start-websocket" | "--websocket-auto-start" | "--websocket"
            ) {
                parsed.start_websocket = true;
            } else if matches!(
                arg.as_str(),
                "--start-services" | "--services-auto-start" | "--auto-start-services"
            ) {
                parsed.start_services = true;
            }
            index += 1;
        }
        parsed
    }
}

fn parse_mode(value: &str) -> RuntimeMode {
    match value.trim().to_ascii_lowercase().as_str() {
        "headless-api" | "server" | "api" => RuntimeMode::HeadlessApi,
        "web-proxy" | "webport" | "web" | "proxy" => RuntimeMode::WebProxy,
        "cli" => RuntimeMode::Cli,
        "worker" => RuntimeMode::Worker,
        _ => RuntimeMode::Desktop,
    }
}
