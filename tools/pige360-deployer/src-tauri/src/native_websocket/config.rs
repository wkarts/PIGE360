use std::net::SocketAddr;

use serde::{Deserialize, Serialize};

use crate::runtime_config::RuntimeSettings;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WebSocketConfig {
    pub enabled: bool,
    pub host: String,
    pub port: u16,
    pub path: String,
    pub token_required: bool,
    pub token_query: String,
    pub token_header: String,
    pub token: String,
    pub allow_lan: bool,
    pub allow_external: bool,
    pub heartbeat_seconds: u64,
}

impl Default for WebSocketConfig {
    fn default() -> Self {
        Self {
            enabled: false,
            host: "0.0.0.0".to_string(),
            port: 61004,
            path: "/ws".to_string(),
            token_required: true,
            token_query: "token".to_string(),
            token_header: "X-WebSocket-Token".to_string(),
            token: String::new(),
            allow_lan: true,
            allow_external: false,
            heartbeat_seconds: 30,
        }
    }
}

impl WebSocketConfig {
    pub fn from_runtime_settings(settings: &RuntimeSettings) -> Self {
        Self {
            enabled: settings.websocket_enabled,
            host: settings.websocket_host.clone(),
            port: settings.websocket_port,
            path: normalize_path(&settings.websocket_path),
            token_required: settings.websocket_token_required,
            token_query: settings.websocket_token_query.clone(),
            token_header: settings.websocket_token_header.clone(),
            token: settings.websocket_token.clone(),
            allow_lan: settings.websocket_allow_lan,
            allow_external: settings.websocket_allow_external,
            heartbeat_seconds: settings.websocket_heartbeat_seconds,
        }
    }

    pub fn with_host_port(mut self, host: String, port: u16) -> Self {
        self.host = host;
        self.port = port;
        self
    }

    pub fn validate_bind(&self) -> Result<(), String> {
        let host = self.host.trim();
        if host.is_empty() {
            return Err("Host do WebSocket Service não pode ficar vazio.".to_string());
        }
        if self.port == 0 {
            return Err("Porta do WebSocket Service deve estar entre 1 e 65535.".to_string());
        }
        format!("{host}:{}", self.port)
            .parse::<SocketAddr>()
            .map(|_| ())
            .map_err(|err| format!("Endereço do WebSocket Service inválido: {err}"))
    }

    pub fn public_host(&self) -> String {
        match self.host.as_str() {
            "0.0.0.0" | "::" | "[::]" => "127.0.0.1".to_string(),
            value => value.to_string(),
        }
    }

    pub fn url(&self) -> String {
        format!("ws://{}:{}{}", self.public_host(), self.port, self.path)
    }
}

pub fn normalize_path(path: &str) -> String {
    let trimmed = path.trim();
    if trimmed.is_empty() {
        return "/ws".to_string();
    }
    if trimmed.starts_with('/') {
        trimmed.trim_end_matches('/').to_string()
    } else {
        format!("/{}", trimmed.trim_end_matches('/'))
    }
}
