use std::env;

use crate::runtime_config::RuntimeSettings;

#[derive(Debug, Clone)]
pub struct InternalApiSecurityConfig {
    pub bind_host: String,
    pub allow_public_network: bool,
    pub require_token: bool,
    pub token_header: String,
    pub token: Option<String>,
    pub cors_enabled: bool,
    pub docs_public: bool,
    pub docs_public_local: bool,
}

#[derive(Debug, Clone)]
pub struct InternalApiDocsConfig {
    pub enabled: bool,
    pub path: String,
    pub public_url: Option<String>,
}

#[derive(Debug, Clone)]
pub struct InternalApiConfig {
    pub enabled: bool,
    pub auto_start: bool,
    pub host: String,
    pub port: u16,
    pub base_url: String,
    pub timeout_ms: u64,
    pub log_mode: String,
    pub open_scalar_after_start: bool,
    pub restart_on_config_change: bool,
    pub expose_docs: bool,
    pub docs: InternalApiDocsConfig,
    pub security: InternalApiSecurityConfig,
}

impl Default for InternalApiConfig {
    fn default() -> Self {
        let host = env::var("PIGE360_DEPLOYER_API_HOST").unwrap_or_else(|_| "127.0.0.1".to_string());
        let port = env::var("PIGE360_DEPLOYER_API_PORT")
            .ok()
            .and_then(|value| value.parse::<u16>().ok())
            .unwrap_or(61001);
        let docs_path = normalize_docs_path(
            &env::var("PIGE360_DEPLOYER_API_DOCS_PATH").unwrap_or_else(|_| "/docs".to_string()),
        );
        let expose_docs = env_bool("PIGE360_DEPLOYER_API_SCALAR_ENABLED", true)
            && env_bool("PIGE360_DEPLOYER_API_EXPOSE_DOCS", true);
        let require_token = env_bool("PIGE360_DEPLOYER_API_REQUIRE_TOKEN", false);
        let allow_public_network = env_bool("PIGE360_DEPLOYER_API_ALLOW_PUBLIC_NETWORK", false);
        let cors_enabled = env_bool("PIGE360_DEPLOYER_API_CORS", false);
        let docs_public = env_bool("PIGE360_DEPLOYER_API_DOCS_PUBLIC", false);
        let docs_public_local = env_bool("PIGE360_DEPLOYER_API_DOCS_PUBLIC_LOCAL", true);
        let token_header =
            env::var("PIGE360_DEPLOYER_API_TOKEN_HEADER").unwrap_or_else(|_| "X-App-Token".to_string());
        let token = env::var("PIGE360_DEPLOYER_API_TOKEN")
            .ok()
            .filter(|value| !value.trim().is_empty());
        let base_url = env::var("PIGE360_DEPLOYER_API_BASE_URL")
            .ok()
            .filter(|value| !value.trim().is_empty())
            .unwrap_or_else(|| format!("http://{host}:{port}"));
        let docs_url = env::var("PIGE360_DEPLOYER_API_SCALAR_URL")
            .ok()
            .filter(|value| !value.trim().is_empty())
            .filter(|value| !value.contains("127.0.0.1:61001"));

        Self {
            enabled: true,
            auto_start: env_bool("PIGE360_DEPLOYER_API_AUTO_START", false),
            host: host.clone(),
            port,
            base_url: base_url.clone(),
            timeout_ms: env_u64("PIGE360_DEPLOYER_API_TIMEOUT_MS", 8000),
            log_mode: env::var("PIGE360_DEPLOYER_API_LOG_MODE")
                .unwrap_or_else(|_| "normal".to_string()),
            open_scalar_after_start: env_bool("PIGE360_DEPLOYER_API_OPEN_SCALAR_AFTER_START", false),
            restart_on_config_change: env_bool("PIGE360_DEPLOYER_API_RESTART_ON_CONFIG_CHANGE", true),
            expose_docs,
            docs: InternalApiDocsConfig {
                enabled: expose_docs,
                path: docs_path.clone(),
                public_url: docs_url
                    .filter(|url| normalize_url(url) != derived_docs_url(&base_url, &docs_path)),
            },
            security: InternalApiSecurityConfig {
                bind_host: host,
                allow_public_network,
                require_token,
                token_header,
                token,
                cors_enabled,
                docs_public,
                docs_public_local,
            },
        }
    }
}

impl InternalApiConfig {
    pub fn from_runtime_settings(settings: &RuntimeSettings) -> Self {
        let mut config = Self::default().with_host_port(
            settings.internal_api_host.clone(),
            settings.internal_api_port,
        );
        config.auto_start = settings.internal_api_auto_start;
        config.base_url = settings.internal_api_base_url.clone();
        config.timeout_ms = settings.internal_api_timeout_ms;
        config.log_mode = settings.internal_api_log_mode.clone();
        config.open_scalar_after_start = settings.internal_api_open_scalar_after_start;
        config.restart_on_config_change = settings.internal_api_restart_on_config_change;
        config.expose_docs = settings.internal_api_docs_enabled;
        config.docs.enabled = settings.internal_api_docs_enabled;
        config.docs.path = normalize_docs_path(&settings.internal_api_docs_path);
        config.docs.public_url = (!settings.internal_api_docs_url.trim().is_empty()
            && normalize_url(&settings.internal_api_docs_url)
                != derived_docs_url(&settings.internal_api_base_url, &config.docs.path))
        .then(|| settings.internal_api_docs_url.trim().to_string());
        config.security.require_token = settings.internal_api_require_token;
        config.security.allow_public_network = settings.internal_api_allow_public_network;
        config.security.cors_enabled = settings.internal_api_cors_enabled;
        config.security.token_header = settings.internal_api_token_header.clone();
        config.security.token = (!settings.internal_api_token.trim().is_empty())
            .then(|| settings.internal_api_token.clone());
        config.security.docs_public_local = settings.internal_api_docs_public_local;
        config
    }

    pub fn with_host_port(mut self, host: String, port: u16) -> Self {
        let public_host = public_url_host(&host);
        self.host = host.clone();
        self.port = port;
        self.base_url = format!("http://{public_host}:{port}");
        self.security.bind_host = host;
        self
    }

    pub fn docs_url(&self) -> String {
        self.docs
            .public_url
            .clone()
            .unwrap_or_else(|| derived_docs_url(&self.base_url, &self.docs.path))
    }

    pub fn docs_are_public_for_current_bind(&self) -> bool {
        self.security.docs_public
            || (self.security.docs_public_local && is_local_access_host(&self.host))
    }

    pub fn validate_bind(&self) -> Result<(), String> {
        let host = self.host.trim();
        let is_public = matches!(host, "0.0.0.0" | "::" | "[::]");
        if is_public && !self.security.allow_public_network {
            return Err("API interna bloqueada: bind público exige PIGE360_DEPLOYER_API_ALLOW_PUBLIC_NETWORK=true.".to_string());
        }
        Ok(())
    }
}

pub fn public_url_host(host: &str) -> String {
    match host.trim() {
        "0.0.0.0" | "::" | "[::]" => "127.0.0.1".to_string(),
        "" => "127.0.0.1".to_string(),
        other => other.to_string(),
    }
}

fn derived_docs_url(base_url: &str, docs_path: &str) -> String {
    format!(
        "{}{}",
        base_url.trim_end_matches('/'),
        normalize_docs_path(docs_path)
    )
}

fn normalize_url(url: &str) -> String {
    url.trim().trim_end_matches('/').to_string()
}

fn normalize_docs_path(path: &str) -> String {
    let trimmed = path.trim();
    if trimmed.is_empty() {
        return "/docs".to_string();
    }
    if trimmed.starts_with('/') {
        trimmed.to_string()
    } else {
        format!("/{trimmed}")
    }
}

fn is_local_access_host(host: &str) -> bool {
    matches!(
        host.trim(),
        "127.0.0.1" | "localhost" | "::1" | "[::1]" | "0.0.0.0" | "::" | "[::]"
    )
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
