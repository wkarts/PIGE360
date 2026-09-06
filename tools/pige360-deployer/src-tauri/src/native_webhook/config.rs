use std::net::SocketAddr;

use serde::{Deserialize, Serialize};

use crate::runtime_config::RuntimeSettings;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WebhookConfig {
    pub enabled: bool,
    pub host: String,
    pub port: u16,
    pub base_path: String,
    pub token_required: bool,
    pub token_header: String,
    pub token: String,
    pub allow_lan: bool,
    pub allow_external: bool,
}

impl Default for WebhookConfig {
    fn default() -> Self {
        Self {
            enabled: false,
            host: "0.0.0.0".to_string(),
            port: 61003,
            base_path: "/webhooks".to_string(),
            token_required: true,
            token_header: "X-Webhook-Token".to_string(),
            token: String::new(),
            allow_lan: true,
            allow_external: false,
        }
    }
}

impl WebhookConfig {
    pub fn from_runtime_settings(settings: &RuntimeSettings) -> Self {
        Self {
            enabled: settings.webhook_enabled,
            host: settings.webhook_host.clone(),
            port: settings.webhook_port,
            base_path: normalize_path(&settings.webhook_base_path),
            token_required: settings.webhook_token_required,
            token_header: settings.webhook_token_header.clone(),
            token: settings.webhook_token.clone(),
            allow_lan: settings.webhook_allow_lan,
            allow_external: settings.webhook_allow_external,
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
            return Err("Host do Webhook Service não pode ficar vazio.".to_string());
        }
        if self.port == 0 {
            return Err("Porta do Webhook Service deve estar entre 1 e 65535.".to_string());
        }
        format!("{host}:{}", self.port)
            .parse::<SocketAddr>()
            .map(|_| ())
            .map_err(|err| format!("Endereço do Webhook Service inválido: {err}"))
    }

    pub fn public_host(&self) -> String {
        match self.host.as_str() {
            "0.0.0.0" | "::" | "[::]" => "127.0.0.1".to_string(),
            value => value.to_string(),
        }
    }

    pub fn url(&self) -> String {
        format!("http://{}:{}", self.public_host(), self.port)
    }
}

pub fn normalize_path(path: &str) -> String {
    let trimmed = path.trim();
    if trimmed.is_empty() {
        return "/webhooks".to_string();
    }
    if trimmed.starts_with('/') {
        trimmed.trim_end_matches('/').to_string()
    } else {
        format!("/{}", trimmed.trim_end_matches('/'))
    }
}
