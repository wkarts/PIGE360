use crate::deployer::error::{DeployError, Result};
use crate::deployer::protocol::{DeploymentEnvironment, DeploymentPlatform, DistributionChannel};
use std::collections::BTreeSet;
use std::path::{Component, Path, PathBuf};

pub fn deployment_prefix(platform: DeploymentPlatform, environment: DeploymentEnvironment) -> String {
    match platform {
        DeploymentPlatform::Compose => format!("deployments/{}", environment.as_str()),
        _ => format!("deployments/{}/{}", platform.as_str(), environment.as_str()),
    }
}

pub fn validate_channel(channel: DistributionChannel, environment: DeploymentEnvironment, requested: &str) -> Result<()> {
    match (channel, environment) {
        (DistributionChannel::Develop, DeploymentEnvironment::Develop) if requested == "develop" => Ok(()),
        (DistributionChannel::Prerelease, DeploymentEnvironment::Develop)
            if is_develop_prerelease(requested) => Ok(()),
        (DistributionChannel::Stable, DeploymentEnvironment::Production) if requested == "latest" || is_stable(requested) => Ok(()),
        (DistributionChannel::Stable, DeploymentEnvironment::Develop) if requested == "latest" || is_stable(requested) => Ok(()),
        (DistributionChannel::Develop, DeploymentEnvironment::Production) => Err(DeployError::msg("Produção não aceita o canal develop.")),
        (DistributionChannel::Prerelease, DeploymentEnvironment::Production) => Err(DeployError::msg("Produção não aceita prerelease.")),
        _ => Err(DeployError::msg("Canal, ambiente e versão não formam uma distribuição PIGE360 válida.")),
    }
}

pub fn normalize_tag(value: &str) -> &str {
    value.strip_prefix('v').unwrap_or(value)
}

pub fn is_stable(value: &str) -> bool {
    semver_parts(normalize_tag(value), false)
}

pub fn is_prerelease(value: &str) -> bool {
    semver_parts(normalize_tag(value), true)
}

pub fn is_develop_prerelease(value: &str) -> bool {
    let value = normalize_tag(value);
    value.len() == 20
        && value.starts_with("develop-")
        && value[8..]
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}

fn semver_parts(value: &str, prerelease: bool) -> bool {
    let (core, suffix) = match value.split_once('-') {
        Some((core, suffix)) if !suffix.is_empty() => (core, Some(suffix)),
        None => (value, None),
        _ => return false,
    };
    if prerelease != suffix.is_some() || suffix.is_some_and(|part| !valid_semver_suffix(part)) {
        return false;
    }
    let pieces = core.split('.').collect::<Vec<_>>();
    pieces.len() == 3 && pieces.iter().all(|piece| valid_numeric_identifier(piece))
}

fn valid_numeric_identifier(value: &str) -> bool {
    !value.is_empty()
        && value.bytes().all(|byte| byte.is_ascii_digit())
        && (value.len() == 1 || !value.starts_with('0'))
}

fn valid_semver_suffix(value: &str) -> bool {
    value.split('.').all(|part| !part.is_empty() && part.bytes().all(|byte| byte.is_ascii_alphanumeric() || byte == b'-'))
}

pub fn safe_directory(value: &str) -> Result<PathBuf> {
    let path = PathBuf::from(value);
    if !path.is_absolute() || path.components().any(|part| matches!(part, Component::ParentDir | Component::CurDir)) {
        return Err(DeployError::msg("O diretório da stack precisa ser absoluto e não pode conter . ou ..."));
    }
    for forbidden in ["/", "/opt", "/home", "/root", "/etc", "/var", "/tmp"] {
        if path == Path::new(forbidden) {
            return Err(DeployError::msg("Escolha um subdiretório exclusivo para a stack PIGE360."));
        }
    }
    for forbidden_prefix in [
        "/bin", "/boot", "/dev", "/etc", "/lib", "/lib64", "/proc", "/root",
        "/run", "/sbin", "/sys", "/usr",
    ] {
        if path.starts_with(forbidden_prefix) {
            return Err(DeployError::msg("O diretório da stack não pode ficar em uma árvore sensível do sistema."));
        }
    }
    let mut cursor = Some(path.as_path());
    while let Some(current) = cursor {
        if std::fs::symlink_metadata(current).ok().is_some_and(|meta| meta.file_type().is_symlink()) {
            return Err(DeployError::msg("A stack não pode atravessar links simbólicos."));
        }
        cursor = current.parent();
    }
    Ok(path)
}

pub fn validate_relative_path(value: &str) -> Result<()> {
    let path = Path::new(value);
    if value.is_empty()
        || value.contains('\\')
        || value.chars().any(char::is_control)
        || path.is_absolute()
        || path.components().any(|part| !matches!(part, Component::Normal(_)))
    {
        return Err(DeployError::msg("A distribuição contém um caminho inseguro."));
    }
    Ok(())
}

pub fn allowed_env_keys() -> BTreeSet<&'static str> {
    BTreeSet::from([
        "ACME_EMAIL", "CLOUDFLARE_CONTROL_ZONE_ID", "CLOUDFLARE_TENANT_ZONE_ID",
        "PIGE360_BASE_DOMAIN", "PLATFORM_CONTROL_BASE_DOMAIN", "PLATFORM_CONSOLE_HOST",
        "PLATFORM_API_HOST", "PLATFORM_OPS_HOST", "PLATFORM_BRANDING_HOST",
        "PLATFORM_DOWNLOADS_HOST", "TENANT_DEFAULT_BASE_DOMAIN", "TENANT_WILDCARD_HOST",
        "TENANT_CANONICAL_HOST_TEMPLATE", "TENANT_CUSTOM_DOMAIN_CNAME_TARGET",
    ])
}

pub fn allowed_secret_keys() -> BTreeSet<&'static str> {
    BTreeSet::from([
        "cloudflare_api_token",
        "cloudflare_control_tunnel_token",
        "cloudflare_tenant_tunnel_token",
        "connect_api_key",
    ])
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn maps_all_supported_targets() {
        assert_eq!(deployment_prefix(DeploymentPlatform::Compose, DeploymentEnvironment::Develop), "deployments/develop");
        assert_eq!(deployment_prefix(DeploymentPlatform::Dockge, DeploymentEnvironment::Production), "deployments/dockge/production");
        assert_eq!(deployment_prefix(DeploymentPlatform::Cloudpanel, DeploymentEnvironment::Develop), "deployments/cloudpanel/develop");
        assert_eq!(deployment_prefix(DeploymentPlatform::Portainer, DeploymentEnvironment::Production), "deployments/portainer/production");
    }

    #[test]
    fn production_is_stable_only() {
        assert!(validate_channel(DistributionChannel::Stable, DeploymentEnvironment::Production, "v1.2.3").is_ok());
        assert!(validate_channel(DistributionChannel::Develop, DeploymentEnvironment::Production, "develop").is_err());
        assert!(validate_channel(DistributionChannel::Prerelease, DeploymentEnvironment::Production, "v1.2.3-rc.1").is_err());
        assert!(validate_channel(DistributionChannel::Prerelease, DeploymentEnvironment::Develop, "develop-0123456789ab").is_ok());
    }

    #[test]
    fn blocks_broad_and_traversal_paths() {
        assert!(safe_directory("/opt").is_err());
        assert!(safe_directory("/opt/stacks/../pige360").is_err());
        assert!(safe_directory("/etc/systemd/pige360").is_err());
        assert!(safe_directory("/opt/stacks/pige360-develop").is_ok());
        assert!(validate_relative_path("../../etc/passwd").is_err());
        assert!(validate_relative_path("config\\..\\secret").is_err());
    }
}
