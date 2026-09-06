use crate::deployer::catalog::{
    is_develop_prerelease, is_stable, normalize_tag, validate_channel,
    validate_relative_path,
};
use crate::deployer::error::{DeployError, Result};
use crate::deployer::protocol::{
    DeploymentEnvironment, DistributionChannel, DistributionDescriptor, ResolvedDistribution,
};
use base64::Engine;
use reqwest::blocking::Client;
use reqwest::header::{ACCEPT, AUTHORIZATION, USER_AGENT};
use serde_json::Value;
use sha1::{Digest, Sha1};
use std::collections::BTreeMap;
use std::time::Duration;
use zeroize::Zeroizing;

const MAX_API_BYTES: usize = 16 * 1024 * 1024;
const MAX_FILE_BYTES: u64 = 4 * 1024 * 1024;
const MAX_TREE_BYTES: u64 = 64 * 1024 * 1024;
const MAX_TREE_FILES: usize = 512;

pub struct GitHubSource {
    repository: String,
    token: Option<Zeroizing<String>>,
    client: Client,
    pub proofs: BTreeMap<String, String>,
}

impl GitHubSource {
    pub fn new(repository: &str, token: Option<String>) -> Result<Self> {
        let repository = normalize_repository(repository)?;
        let client = Client::builder()
            .timeout(Duration::from_secs(45))
            .redirect(reqwest::redirect::Policy::none())
            .build()?;
        Ok(Self {
            repository,
            token: token
                .filter(|value| !value.trim().is_empty())
                .map(Zeroizing::new),
            client,
            proofs: BTreeMap::new(),
        })
    }

    pub fn repository(&self) -> &str {
        &self.repository
    }

    pub fn resolve(
        &self,
        channel: DistributionChannel,
        environment: DeploymentEnvironment,
        requested: &str,
    ) -> Result<ResolvedDistribution> {
        validate_channel(channel, environment, requested)?;
        let (reference, version, prerelease) = match channel {
            DistributionChannel::Develop => ("develop".to_string(), "develop".to_string(), true),
            DistributionChannel::Prerelease => {
                let tag = normalize_tag(requested);
                let reference = if is_develop_prerelease(tag) {
                    tag.to_string()
                } else {
                    format!("v{tag}")
                };
                let release = self.get_json(&format!("releases/tags/{}", encode_segment(&reference)))?;
                ensure_release(&release, true)?;
                (reference, tag.to_string(), true)
            }
            DistributionChannel::Stable => {
                let reference = if requested == "latest" {
                    let release = self.get_json("releases/latest")?;
                    ensure_release(&release, false)?;
                    release.get("tag_name").and_then(Value::as_str).ok_or_else(|| DeployError::msg("Release latest sem tag."))?.to_string()
                } else {
                    let tag = format!("v{}", normalize_tag(requested));
                    let release = self.get_json(&format!("releases/tags/{}", encode_segment(&tag)))?;
                    ensure_release(&release, false)?;
                    tag
                };
                (reference.clone(), normalize_tag(&reference).to_string(), false)
            }
        };
        let commit = self.commit_sha(&reference)?;
        let image_tag = if channel == DistributionChannel::Develop {
            format!("develop-{}", &commit[..12])
        } else {
            version.clone()
        };
        Ok(ResolvedDistribution { channel, version, reference, commit, image_tag, prerelease })
    }

    pub fn list_distributions(&self) -> Result<Vec<DistributionDescriptor>> {
        let mut result = Vec::new();
        if let Ok(commit) = self.commit_sha("develop") {
            result.push(DistributionDescriptor {
                channel: DistributionChannel::Develop,
                version: format!("develop-{}", &commit[..12]),
                reference: "develop".into(),
                commit,
                prerelease: true,
                published_at: None,
            });
        }
        let releases = self.get_json("releases?per_page=30")?;
        let items = releases.as_array().ok_or_else(|| DeployError::msg("Catálogo de releases GitHub inválido."))?;
        for item in items {
            if item.get("draft").and_then(Value::as_bool).unwrap_or(false) {
                continue;
            }
            let Some(reference) = item.get("tag_name").and_then(Value::as_str) else { continue };
            let version = normalize_tag(reference);
            let prerelease = item.get("prerelease").and_then(Value::as_bool).unwrap_or(false);
            let channel = if prerelease && is_develop_prerelease(version) {
                DistributionChannel::Prerelease
            } else if !prerelease && is_stable(version) {
                DistributionChannel::Stable
            } else {
                continue;
            };
            let Ok(commit) = self.commit_sha(reference) else { continue };
            result.push(DistributionDescriptor {
                channel,
                version: version.to_string(),
                reference: reference.to_string(),
                commit,
                prerelease,
                published_at: item.get("published_at").and_then(Value::as_str).map(str::to_string),
            });
            if result.len() >= 16 {
                break;
            }
        }
        Ok(result)
    }

    pub fn fetch_tree(&mut self, prefix: &str, commit: &str) -> Result<BTreeMap<String, Vec<u8>>> {
        validate_relative_path(prefix)?;
        if !valid_sha(commit) {
            return Err(DeployError::msg("Commit Git inválido."));
        }
        let mut entries = Vec::new();
        self.walk_contents(prefix, commit, 0, &mut entries)?;
        if entries.is_empty() {
            return Err(DeployError::msg(format!("A distribuição não contém arquivos em {prefix}.")));
        }
        if entries.len() > MAX_TREE_FILES {
            return Err(DeployError::msg("A distribuição excede o limite de arquivos do instalador."));
        }
        let mut total = 0u64;
        let mut output = BTreeMap::new();
        for entry in entries {
            total = total.saturating_add(entry.size);
            if entry.size > MAX_FILE_BYTES || total > MAX_TREE_BYTES {
                return Err(DeployError::msg("A distribuição excede os limites de tamanho do instalador."));
            }
            let bytes = self.fetch_blob(&entry.sha)?;
            if bytes.len() as u64 != entry.size {
                return Err(DeployError::msg(format!("Tamanho Git divergente em {}.", entry.path)));
            }
            let relative = entry.path.strip_prefix(prefix).unwrap_or(&entry.path).trim_start_matches('/').to_string();
            validate_relative_path(&relative)?;
            self.proofs.insert(relative.clone(), entry.sha);
            output.insert(relative, bytes);
        }
        Ok(output)
    }

    fn walk_contents(&self, path: &str, commit: &str, depth: usize, output: &mut Vec<TreeEntry>) -> Result<()> {
        if depth > 12 || output.len() > MAX_TREE_FILES {
            return Err(DeployError::msg("Árvore de deployment excede os limites permitidos."));
        }
        let encoded = path.split('/').map(encode_segment).collect::<Vec<_>>().join("/");
        let value = self.get_json(&format!("contents/{encoded}?ref={commit}"))?;
        let items = value.as_array().ok_or_else(|| DeployError::msg("Diretório GitHub inválido."))?;
        for item in items {
            let kind = item.get("type").and_then(Value::as_str).unwrap_or_default();
            let item_path = item.get("path").and_then(Value::as_str).ok_or_else(|| DeployError::msg("Item GitHub sem caminho."))?;
            validate_relative_path(item_path)?;
            match kind {
                "dir" => self.walk_contents(item_path, commit, depth + 1, output)?,
                "file" => {
                    let sha = item.get("sha").and_then(Value::as_str).unwrap_or_default();
                    let size = item.get("size").and_then(Value::as_u64).unwrap_or(MAX_FILE_BYTES + 1);
                    if !valid_sha(sha) {
                        return Err(DeployError::msg("Blob Git com SHA inválido."));
                    }
                    output.push(TreeEntry { path: item_path.to_string(), sha: sha.to_string(), size });
                }
                "symlink" | "submodule" => return Err(DeployError::msg("Links e submódulos não são aceitos no deployment.")),
                _ => return Err(DeployError::msg("Tipo de item GitHub não suportado.")),
            }
        }
        Ok(())
    }

    fn fetch_blob(&self, sha: &str) -> Result<Vec<u8>> {
        let value = self.get_json(&format!("git/blobs/{sha}"))?;
        if value.get("encoding").and_then(Value::as_str) != Some("base64") {
            return Err(DeployError::msg("Blob Git não usa Base64."));
        }
        let content = value
            .get("content")
            .and_then(Value::as_str)
            .ok_or_else(|| DeployError::msg("Blob Git sem conteúdo."))?
            .replace('\r', "")
            .replace('\n', "");
        let bytes = base64::engine::general_purpose::STANDARD.decode(content).map_err(|_| DeployError::msg("Blob Git Base64 inválido."))?;
        let mut hasher = Sha1::new();
        hasher.update(format!("blob {}\0", bytes.len()).as_bytes());
        hasher.update(&bytes);
        let digest = hex_bytes(&hasher.finalize());
        if digest != sha {
            return Err(DeployError::msg("Integridade SHA-1 do blob Git divergente."));
        }
        Ok(bytes)
    }

    fn commit_sha(&self, reference: &str) -> Result<String> {
        let value = self.get_json(&format!("commits/{}", encode_segment(reference)))?;
        let sha = value.get("sha").and_then(Value::as_str).unwrap_or_default();
        if !valid_sha(sha) {
            return Err(DeployError::msg("Referência GitHub não resolveu para commit SHA-1."));
        }
        Ok(sha.to_string())
    }

    fn get_json(&self, suffix: &str) -> Result<Value> {
        let url = format!("https://api.github.com/repos/{}/{}", self.repository, suffix);
        let mut request = self.client.get(url)
            .header(ACCEPT, "application/vnd.github+json")
            .header(USER_AGENT, format!("PIGE360-Deployer/{}", env!("CARGO_PKG_VERSION")))
            .header("X-GitHub-Api-Version", "2022-11-28");
        if let Some(token) = &self.token {
            request = request.header(AUTHORIZATION, format!("Bearer {}", token.as_str()));
        }
        let response = request.send()?;
        let status = response.status();
        let bytes = response.bytes()?;
        if bytes.len() > MAX_API_BYTES {
            return Err(DeployError::msg("Resposta GitHub excede o limite do Deployer."));
        }
        if !status.is_success() {
            return Err(DeployError::msg(format!("GitHub HTTP {}. Confira repositório, versão e token.", status.as_u16())));
        }
        Ok(serde_json::from_slice(&bytes)?)
    }
}

#[derive(Debug)]
struct TreeEntry {
    path: String,
    sha: String,
    size: u64,
}

fn ensure_release(value: &Value, prerelease: bool) -> Result<()> {
    if value.get("draft").and_then(Value::as_bool).unwrap_or(true) {
        return Err(DeployError::msg("Draft não pode ser instalado."));
    }
    if value.get("prerelease").and_then(Value::as_bool).unwrap_or(false) != prerelease {
        return Err(DeployError::msg(if prerelease { "A tag não é uma prerelease publicada." } else { "Produção exige uma release estável publicada." }));
    }
    Ok(())
}

fn normalize_repository(value: &str) -> Result<String> {
    let mut repository = value.trim().trim_end_matches('/').trim_end_matches(".git").to_string();
    if let Some(path) = repository.strip_prefix("https://github.com/") {
        repository = path.to_string();
    }
    let pieces = repository.split('/').collect::<Vec<_>>();
    if pieces.len() != 2 || pieces.iter().any(|piece| piece.is_empty() || !piece.bytes().all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'-' | b'.'))) || repository.contains("..") {
        return Err(DeployError::msg("Repositório inválido; use owner/repo ou HTTPS github.com sem credenciais."));
    }
    Ok(repository)
}

fn valid_sha(value: &str) -> bool {
    value.len() == 40 && value.bytes().all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}

fn encode_segment(value: &str) -> String {
    let mut output = String::new();
    for byte in value.bytes() {
        if byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.' | b'~') {
            output.push(byte as char);
        } else {
            output.push('%');
            output.push_str(&format!("{byte:02X}"));
        }
    }
    output
}

fn hex_bytes(bytes: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut output = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        output.push(HEX[(byte >> 4) as usize] as char);
        output.push(HEX[(byte & 0x0f) as usize] as char);
    }
    output
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn repository_validation_is_strict() {
        assert_eq!(normalize_repository("organization/PIGE360").unwrap(), "organization/PIGE360");
        assert_eq!(
            normalize_repository("https://github.com/organization/PIGE360.git").unwrap(),
            "organization/PIGE360"
        );
        assert!(normalize_repository("https://user:token@github.com/organization/PIGE360").is_err());
        assert!(normalize_repository("organization/../PIGE360").is_err());
    }

    #[test]
    fn encoder_never_preserves_path_separators() {
        assert_eq!(encode_segment("v1.2.3-rc.1"), "v1.2.3-rc.1");
        assert_eq!(encode_segment("a/b"), "a%2Fb");
    }
}
