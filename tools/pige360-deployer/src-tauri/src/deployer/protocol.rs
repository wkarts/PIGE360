use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

pub const PROTOCOL_VERSION: u32 = 1;

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum DistributionChannel {
    Develop,
    Prerelease,
    Stable,
}

impl DistributionChannel {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Develop => "develop",
            Self::Prerelease => "prerelease",
            Self::Stable => "stable",
        }
    }
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum DeploymentEnvironment {
    Develop,
    Production,
}

impl DeploymentEnvironment {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Develop => "develop",
            Self::Production => "production",
        }
    }
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum DeploymentPlatform {
    Compose,
    Dockge,
    Cloudpanel,
    Portainer,
}

impl DeploymentPlatform {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Compose => "compose",
            Self::Dockge => "dockge",
            Self::Cloudpanel => "cloudpanel",
            Self::Portainer => "portainer",
        }
    }
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum DeploymentAction {
    Plan,
    Prepare,
    Apply,
    Rollback,
}

#[derive(Clone, Serialize, Deserialize)]
pub struct DeployRequest {
    pub protocol_version: u32,
    pub repository: String,
    pub channel: DistributionChannel,
    pub environment: DeploymentEnvironment,
    pub requested_version: String,
    pub platform: DeploymentPlatform,
    pub directory: String,
    pub action: DeploymentAction,
    #[serde(default)]
    pub rollback_tag: Option<String>,
    #[serde(default)]
    pub github_token: Option<String>,
    #[serde(default)]
    pub registry_user: Option<String>,
    #[serde(default)]
    pub registry_token: Option<String>,
    #[serde(default)]
    pub env_input: Option<String>,
    #[serde(default)]
    pub env_overrides: BTreeMap<String, String>,
    #[serde(default)]
    pub secret_inputs: BTreeMap<String, String>,
    #[serde(default = "default_wait_seconds")]
    pub wait_seconds: u64,
}

fn default_wait_seconds() -> u64 {
    600
}

impl std::fmt::Debug for DeployRequest {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter
            .debug_struct("DeployRequest")
            .field("protocol_version", &self.protocol_version)
            .field("repository", &self.repository)
            .field("channel", &self.channel)
            .field("environment", &self.environment)
            .field("requested_version", &self.requested_version)
            .field("platform", &self.platform)
            .field("directory", &self.directory)
            .field("action", &self.action)
            .field("rollback_tag", &self.rollback_tag)
            .field("github_token", &self.github_token.as_ref().map(|_| "[REDACTED]"))
            .field("registry_user", &self.registry_user)
            .field("registry_token", &self.registry_token.as_ref().map(|_| "[REDACTED]"))
            .field("env_input", &self.env_input.as_ref().map(|_| "[REDACTED]"))
            .field("env_overrides", &self.env_overrides.keys().collect::<Vec<_>>())
            .field("secret_inputs", &self.secret_inputs.keys().collect::<Vec<_>>())
            .field("wait_seconds", &self.wait_seconds)
            .finish()
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct DistributionDescriptor {
    pub channel: DistributionChannel,
    pub version: String,
    pub reference: String,
    pub commit: String,
    pub prerelease: bool,
    pub published_at: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ResolvedDistribution {
    pub channel: DistributionChannel,
    pub version: String,
    pub reference: String,
    pub commit: String,
    pub image_tag: String,
    pub prerelease: bool,
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum EventKind {
    Info,
    Warning,
    Error,
    Result,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct AgentEvent {
    pub protocol_version: u32,
    pub kind: EventKind,
    pub step: String,
    pub message: String,
    pub progress: Option<u8>,
    pub data: Option<serde_json::Value>,
}

impl AgentEvent {
    pub fn info(step: impl Into<String>, message: impl Into<String>, progress: Option<u8>) -> Self {
        Self { protocol_version: PROTOCOL_VERSION, kind: EventKind::Info, step: step.into(), message: message.into(), progress, data: None }
    }

    pub fn warning(step: impl Into<String>, message: impl Into<String>) -> Self {
        Self { protocol_version: PROTOCOL_VERSION, kind: EventKind::Warning, step: step.into(), message: message.into(), progress: None, data: None }
    }

    pub fn error(step: impl Into<String>, message: impl Into<String>) -> Self {
        Self { protocol_version: PROTOCOL_VERSION, kind: EventKind::Error, step: step.into(), message: message.into(), progress: None, data: None }
    }

    pub fn result(step: impl Into<String>, message: impl Into<String>, data: serde_json::Value) -> Self {
        Self { protocol_version: PROTOCOL_VERSION, kind: EventKind::Result, step: step.into(), message: message.into(), progress: Some(100), data: Some(data) }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ServerPreflight {
    pub os: String,
    pub architecture: String,
    pub kernel: String,
    pub docker_available: bool,
    pub docker_version: Option<String>,
    pub compose_available: bool,
    pub compose_version: Option<String>,
    pub cloudpanel_available: bool,
    pub disk_available_bytes: Option<u64>,
    pub effective_user: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct DeployReceipt {
    pub schema_version: u32,
    pub installer_version: String,
    pub repository: String,
    pub channel: String,
    pub commit: String,
    pub environment: String,
    pub version: String,
    pub image_tag: String,
    pub platform: String,
    pub directory: String,
    pub status: String,
    pub managed_files: Vec<String>,
    pub source_proofs: BTreeMap<String, String>,
    pub backup_directory: Option<String>,
    pub result: Option<serde_json::Value>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn debug_redacts_all_sensitive_fields() {
        let request = DeployRequest {
            protocol_version: PROTOCOL_VERSION,
            repository: "organization/PIGE360".into(),
            channel: DistributionChannel::Develop,
            environment: DeploymentEnvironment::Develop,
            requested_version: "develop".into(),
            platform: DeploymentPlatform::Compose,
            directory: "/opt/stacks/pige360-develop".into(),
            action: DeploymentAction::Plan,
            rollback_tag: None,
            github_token: Some("github-secret".into()),
            registry_user: None,
            registry_token: Some("registry-secret".into()),
            env_input: Some("APP_JWT_SECRET=env-secret".into()),
            env_overrides: BTreeMap::new(),
            secret_inputs: BTreeMap::from([("cloudflare_api_token".into(), "cloudflare-secret".into())]),
            wait_seconds: 600,
        };
        let rendered = format!("{request:?}");
        for forbidden in ["github-secret", "registry-secret", "env-secret", "cloudflare-secret"] {
            assert!(!rendered.contains(forbidden));
        }
    }
}
