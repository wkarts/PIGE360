use crate::deployer::error::{DeployError, Result};
use crate::deployer::github::GitHubSource;
use crate::deployer::protocol::{
    AgentEvent, DeployRequest, DeploymentPlatform, DistributionDescriptor, EventKind,
    ServerPreflight, PROTOCOL_VERSION,
};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::ffi::{OsStr, OsString};
use std::fs;
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use tauri::{AppHandle, Emitter};
use uuid::Uuid;
use zeroize::{Zeroize, Zeroizing};

include!(concat!(env!("OUT_DIR"), "/pige360_embedded_agents.rs"));

#[derive(Clone, Copy, Debug, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AuthMethod { Key, Agent }

#[derive(Clone, Serialize, Deserialize)]
pub struct ConnectionInput {
    pub host: String,
    #[serde(default = "default_port")]
    pub port: u16,
    pub user: String,
    pub auth_method: AuthMethod,
    #[serde(default)]
    pub key_file: Option<String>,
    #[serde(default)]
    pub known_hosts_file: Option<String>,
    #[serde(default)]
    pub accept_new_host_key: bool,
    #[serde(default)]
    pub sudo: bool,
    #[serde(default = "default_timeout")]
    pub connect_timeout_seconds: u64,
}

impl std::fmt::Debug for ConnectionInput {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.debug_struct("ConnectionInput")
            .field("host", &self.host).field("port", &self.port).field("user", &self.user)
            .field("auth_method", &self.auth_method).field("key_file", &self.key_file)
            .field("known_hosts_file", &self.known_hosts_file).field("accept_new_host_key", &self.accept_new_host_key)
            .field("sudo", &self.sudo).field("connect_timeout_seconds", &self.connect_timeout_seconds).finish()
    }
}

#[derive(Clone, Serialize, Deserialize)]
pub struct DesktopDeployRequest {
    pub connection: ConnectionInput,
    pub deploy: DeployRequest,
    #[serde(default)]
    pub env_input_path: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ConnectionTestResult {
    pub known_host_status: String,
    pub fingerprint_sha256: Option<String>,
    pub host_key_type: Option<String>,
    pub server: ServerPreflight,
}

fn default_port() -> u16 { 22 }
fn default_timeout() -> u64 { 20 }

#[tauri::command]
pub async fn pige360_embedded_agent_status() -> serde_json::Value {
    serde_json::json!({
        "amd64": agent_descriptor(AGENT_LINUX_AMD64),
        "supported_architectures": ["x86_64", "amd64"],
    })
}

#[tauri::command]
pub async fn pige360_distribution_list(repository: String, github_token: Option<String>) -> std::result::Result<Vec<DistributionDescriptor>, String> {
    tauri::async_runtime::spawn_blocking(move || GitHubSource::new(&repository, github_token)?.list_distributions())
        .await.map_err(|_| "Falha interna ao consultar distribuições.".to_string())?.map_err(|error| error.to_string())
}

#[tauri::command]
pub async fn pige360_test_connection(input: ConnectionInput) -> std::result::Result<ConnectionTestResult, String> {
    tauri::async_runtime::spawn_blocking(move || test_connection_blocking(&input))
        .await.map_err(|_| "Falha interna ao testar SSH.".to_string())?.map_err(|error| error.to_string())
}

#[tauri::command]
pub async fn pige360_deploy(app: AppHandle, input: DesktopDeployRequest) -> std::result::Result<serde_json::Value, String> {
    tauri::async_runtime::spawn_blocking(move || deploy_blocking(&app, input))
        .await.map_err(|_| "Falha interna durante a implantação.".to_string())?.map_err(|error| error.to_string())
}

fn test_connection_blocking(input: &ConnectionInput) -> Result<ConnectionTestResult> {
    validate_connection(input)?;
    let (fingerprint_sha256, host_key_type) = scan_host_key(input).unwrap_or((None, None));
    let probe = "printf 'os='; uname -s; printf 'arch='; uname -m; printf 'kernel='; uname -r; printf 'user='; id -un; printf 'docker='; if command -v docker >/dev/null 2>&1; then docker --version | tr '\\n' ' '; fi; printf '\\ncompose='; if docker compose version >/dev/null 2>&1; then docker compose version | tr '\\n' ' '; fi; printf '\\ncloudpanel='; if command -v clpctl >/dev/null 2>&1 || test -d /home/clp; then printf true; else printf false; fi; printf '\\ndisk_kb='; df -Pk /opt 2>/dev/null | awk 'NR==2 {print $4}'; printf '\\n'";
    let output = ssh_output(input, probe).map_err(|error| {
        if let Some(fingerprint) = &fingerprint_sha256 {
            DeployError::msg(format!(
                "{error} Fingerprint detectado: {fingerprint}. Compare-o no console do servidor antes de aceitar o host novo."
            ))
        } else {
            error
        }
    })?;
    let values = parse_probe(&output)?;
    if input.sudo {
        let status = ssh_status(input, "sudo -n true")?;
        if !status.success() { return Err(DeployError::msg("O usuário não possui sudo não interativo (`sudo -n`).")); }
    }
    let docker_version = nonempty(values.get("docker"));
    let compose_version = nonempty(values.get("compose"));
    Ok(ConnectionTestResult {
        known_host_status: if input.accept_new_host_key { "known-or-accepted".into() } else { "known".into() },
        fingerprint_sha256,
        host_key_type,
        server: ServerPreflight {
            os: values.get("os").cloned().unwrap_or_default(),
            architecture: values.get("arch").cloned().unwrap_or_default(),
            kernel: values.get("kernel").cloned().unwrap_or_default(),
            docker_available: docker_version.is_some(),
            docker_version,
            compose_available: compose_version.is_some(),
            compose_version,
            cloudpanel_available: values.get("cloudpanel").is_some_and(|value| value == "true"),
            disk_available_bytes: values.get("disk_kb").and_then(|value| value.parse::<u64>().ok()).map(|kb| kb.saturating_mul(1024)),
            effective_user: values.get("user").cloned().unwrap_or_default(),
        },
    })
}

fn scan_host_key(input: &ConnectionInput) -> Result<(Option<String>, Option<String>)> {
    let timeout = input.connect_timeout_seconds.clamp(1, 120).to_string();
    let port = input.port.to_string();
    let output = Command::new("ssh-keyscan")
        .args(["-T", &timeout, "-p", &port, &input.host])
        .stdin(Stdio::null())
        .stderr(Stdio::null())
        .output()
        .map_err(|_| DeployError::msg("ssh-keyscan não está disponível."))?;
    if !output.status.success() || output.stdout.is_empty() {
        return Ok((None, None));
    }
    let mut child = Command::new("ssh-keygen")
        .args(["-lf", "-", "-E", "sha256"])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|_| DeployError::msg("ssh-keygen não está disponível."))?;
    if let Some(mut stdin) = child.stdin.take() {
        stdin.write_all(&output.stdout)?;
    }
    let fingerprints = child.wait_with_output()?;
    if !fingerprints.status.success() {
        return Ok((None, None));
    }
    let rendered = String::from_utf8(fingerprints.stdout)
        .map_err(|_| DeployError::msg("Fingerprint SSH não está em UTF-8."))?;
    let pieces = rendered
        .lines()
        .next()
        .unwrap_or_default()
        .split_whitespace()
        .collect::<Vec<_>>();
    Ok((
        pieces.get(1).map(|value| (*value).to_string()),
        pieces
            .last()
            .map(|value| value.trim_matches(|character| matches!(character, '(' | ')')).to_string()),
    ))
}

fn deploy_blocking(app: &AppHandle, mut input: DesktopDeployRequest) -> Result<serde_json::Value> {
    validate_connection(&input.connection)?;
    if let Some(path) = input.env_input_path.take().filter(|value| !value.trim().is_empty()) {
        let path = expand_home(&path)?;
        let metadata = fs::metadata(&path)?;
        if !metadata.is_file() || metadata.len() > 2 * 1024 * 1024 { return Err(DeployError::msg("O .env inicial deve ser arquivo regular com até 2 MB.")); }
        input.deploy.env_input = Some(fs::read_to_string(path)?);
    }
    emit_local(app, "ssh", "Conectando ao VPS e validando known_hosts…", Some(3));
    let preflight = test_connection_blocking(&input.connection)?;
    if !preflight.server.os.eq_ignore_ascii_case("linux") || !preflight.server.docker_available || !preflight.server.compose_available {
        return Err(DeployError::msg("O destino precisa ser Linux com Docker e Docker Compose v2."));
    }
    if input.deploy.platform == DeploymentPlatform::Cloudpanel && !preflight.server.cloudpanel_available {
        return Err(DeployError::msg("O target CloudPanel exige uma instalação CloudPanel detectável no servidor."));
    }
    if preflight.server.disk_available_bytes.is_some_and(|bytes| bytes < 10 * 1024 * 1024 * 1024) {
        return Err(DeployError::msg("O servidor precisa de pelo menos 10 GB livres em /opt para preparar o PIGE360."));
    }
    let embedded = embedded_agent(&preflight.server.architecture)?;
    emit_local(app, "agent", format!("Agente Rust {} selecionado.", embedded.architecture), Some(12));

    let suffix = Uuid::new_v4().simple().to_string();
    let remote_dir = format!("/tmp/pige360-deployer-{suffix}");
    let remote_agent = format!("{remote_dir}/pige360-deploy-agent");
    let local_agent = std::env::temp_dir().join(format!("pige360-deploy-agent-{suffix}"));
    fs::write(&local_agent, embedded.bytes)?;
    let operation = (|| -> Result<serde_json::Value> {
        let mkdir_command = format!("umask 077 && mkdir -- {remote_dir}");
        if !ssh_status(&input.connection, &mkdir_command)?.success() { return Err(DeployError::msg("Não foi possível criar o diretório temporário remoto.")); }
        scp_upload(&input.connection, &local_agent, &remote_agent)?;
        let verify = format!("chmod 700 -- {remote_agent} && sha256sum -- {remote_agent}");
        let output = ssh_output(&input.connection, &verify)?;
        let actual = output.split_whitespace().next().unwrap_or_default();
        if actual != embedded.sha256 { return Err(DeployError::msg("SHA-256 do agente remoto divergiu após upload.")); }
        let self_test = if input.connection.sudo { format!("sudo -n {remote_agent} self-test") } else { format!("{remote_agent} self-test") };
        let value: serde_json::Value = serde_json::from_str(ssh_output(&input.connection, &self_test)?.trim())?;
        if value.get("ok").and_then(serde_json::Value::as_bool) != Some(true)
            || value.get("protocol").and_then(serde_json::Value::as_u64) != Some(PROTOCOL_VERSION as u64)
        { return Err(DeployError::msg("Self-test do agente remoto é incompatível.")); }
        emit_local(app, "agent", "Agente enviado, verificado e aprovado no self-test.", Some(22));
        let command = if input.connection.sudo { format!("sudo -n {remote_agent} execute") } else { format!("{remote_agent} execute") };
        let request_json = Zeroizing::new(serde_json::to_string(&input.deploy)?);
        run_agent_stream(app, &input.connection, &command, request_json.as_str())
    })();
    let _ = fs::remove_file(&local_agent);
    let cleanup = format!("rm -f -- {remote_agent}; rmdir -- {remote_dir} 2>/dev/null || true");
    if ssh_status(&input.connection, &cleanup).is_err() {
        let _ = app.emit("pige360-deploy-event", AgentEvent::warning("cleanup", "Não foi possível confirmar a remoção do temporário remoto."));
    }
    input.deploy.github_token.zeroize();
    input.deploy.registry_token.zeroize();
    input.deploy.env_input.zeroize();
    for value in input.deploy.secret_inputs.values_mut() {
        value.zeroize();
    }
    operation
}

fn run_agent_stream(app: &AppHandle, input: &ConnectionInput, remote_command: &str, request_json: &str) -> Result<serde_json::Value> {
    let mut command = Command::new("ssh");
    command.args(ssh_arguments(input)?).arg(remote_target(input)).arg(remote_command)
        .stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::null());
    let mut child = command.spawn().map_err(|_| DeployError::msg("OpenSSH Client (`ssh`) não foi encontrado."))?;
    if let Some(mut stdin) = child.stdin.take() { stdin.write_all(request_json.as_bytes())?; stdin.flush()?; }
    let stdout = child.stdout.take().ok_or_else(|| DeployError::msg("Falha ao capturar eventos do agente."))?;
    let mut final_result = None;
    for line in BufReader::new(stdout).lines() {
        let line = line?;
        if line.trim().is_empty() { continue; }
        match serde_json::from_str::<AgentEvent>(&line) {
            Ok(event) => {
                if matches!(event.kind, EventKind::Result) { final_result = event.data.clone(); }
                let _ = app.emit("pige360-deploy-event", &event);
            }
            Err(_) => { let _ = app.emit("pige360-deploy-event", AgentEvent::warning("agent-output", "Linha não estruturada omitida.")); }
        }
    }
    let status = child.wait()?;
    if !status.success() { return Err(DeployError::msg(format!("Agente remoto encerrou com código {}. Saída sensível foi omitida.", status.code().unwrap_or(-1)))); }
    final_result.ok_or_else(|| DeployError::msg("O agente remoto não retornou recibo final."))
}

fn ssh_arguments(input: &ConnectionInput) -> Result<Vec<OsString>> {
    validate_connection(input)?;
    let mut args = vec![
        OsString::from("-p"), OsString::from(input.port.to_string()),
        OsString::from("-o"), OsString::from("BatchMode=yes"),
        OsString::from("-o"), OsString::from(format!("ConnectTimeout={}", input.connect_timeout_seconds.clamp(1, 120))),
        OsString::from("-o"), OsString::from(if input.accept_new_host_key { "StrictHostKeyChecking=accept-new" } else { "StrictHostKeyChecking=yes" }),
    ];
    if let Some(path) = input.known_hosts_file.as_deref().filter(|value| !value.trim().is_empty()) {
        args.extend([OsString::from("-o"), OsString::from(format!("UserKnownHostsFile={}", expand_home(path)?.display()))]);
    }
    if matches!(input.auth_method, AuthMethod::Key) {
        let key = input.key_file.as_deref().filter(|value| !value.trim().is_empty()).ok_or_else(|| DeployError::msg("Informe a chave SSH privada."))?;
        args.extend([OsString::from("-i"), expand_home(key)?.into_os_string()]);
    }
    Ok(args)
}

fn ssh_output(input: &ConnectionInput, remote_command: &str) -> Result<String> {
    let output = Command::new("ssh").args(ssh_arguments(input)?).arg(remote_target(input)).arg(remote_command)
        .stdin(Stdio::null()).stderr(Stdio::null()).output().map_err(|_| DeployError::msg("OpenSSH Client (`ssh`) não foi encontrado."))?;
    if !output.status.success() { return Err(DeployError::msg("Comando SSH falhou. Verifique autenticação, known_hosts e permissões.")); }
    String::from_utf8(output.stdout).map_err(|_| DeployError::msg("Resposta SSH não está em UTF-8."))
}

fn ssh_status(input: &ConnectionInput, remote_command: &str) -> Result<std::process::ExitStatus> {
    Command::new("ssh").args(ssh_arguments(input)?).arg(remote_target(input)).arg(remote_command)
        .stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null()).status().map_err(|_| DeployError::msg("OpenSSH Client (`ssh`) não foi encontrado."))
}

fn scp_upload(input: &ConnectionInput, source: &Path, remote_path: &str) -> Result<()> {
    let mut args = ssh_arguments(input)?;
    if let Some(position) = args.iter().position(|value| value == OsStr::new("-p")) { args[position] = OsString::from("-P"); }
    let target = format!("{}:{}", remote_target(input), remote_path);
    let status = Command::new("scp").args(args).arg(source).arg(target).stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null())
        .status().map_err(|_| DeployError::msg("OpenSSH Client (`scp`) não foi encontrado."))?;
    if !status.success() { return Err(DeployError::msg("Falha ao enviar agente por SCP.")); }
    Ok(())
}

fn validate_connection(input: &ConnectionInput) -> Result<()> {
    let valid_host = !input.host.is_empty() && input.host.bytes().all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'-' | b':' | b'_' | b'[' | b']'));
    let valid_user = !input.user.is_empty() && input.user.bytes().all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'-' | b'_'));
    if !valid_host || !valid_user || input.port == 0 { return Err(DeployError::msg("Host, porta ou usuário SSH inválido.")); }
    Ok(())
}

fn remote_target(input: &ConnectionInput) -> String {
    let host = if input.host.contains(':') && !input.host.starts_with('[') { format!("[{}]", input.host) } else { input.host.clone() };
    format!("{}@{host}", input.user)
}

fn expand_home(value: &str) -> Result<PathBuf> {
    if value == "~" { return dirs::home_dir().ok_or_else(|| DeployError::msg("HOME não localizado.")); }
    if let Some(rest) = value.strip_prefix("~/") {
        return Ok(dirs::home_dir().ok_or_else(|| DeployError::msg("HOME não localizado."))?.join(rest));
    }
    Ok(PathBuf::from(value))
}

fn parse_probe(output: &str) -> Result<BTreeMap<String, String>> {
    let mut result = BTreeMap::new();
    for line in output.lines() {
        if let Some((key, value)) = line.split_once('=') { result.insert(key.to_string(), value.trim().to_string()); }
    }
    for key in ["os", "arch", "kernel", "user"] {
        if result.get(key).is_none_or(String::is_empty) { return Err(DeployError::msg("Preflight SSH retornou dados incompletos.")); }
    }
    Ok(result)
}

fn nonempty(value: Option<&String>) -> Option<String> { value.filter(|text| !text.trim().is_empty()).cloned() }

struct EmbeddedAgent { bytes: &'static [u8], architecture: &'static str, sha256: String }

fn embedded_agent(machine: &str) -> Result<EmbeddedAgent> {
    let normalized = machine.trim().to_ascii_lowercase();
    let (bytes, architecture) = match normalized.as_str() {
        "x86_64" | "amd64" => (AGENT_LINUX_AMD64, "amd64"),
        other => return Err(DeployError::msg(format!(
            "Arquitetura Linux não suportada pelo implantador integrado: {other}. Use um VPS x86_64/amd64."
        ))),
    };
    if bytes.is_empty() { return Err(DeployError::msg(format!("Agente Linux {architecture} não foi embutido neste build. Use o artefato completo do workflow."))); }
    Ok(EmbeddedAgent { bytes, architecture, sha256: hex_bytes(&Sha256::digest(bytes)) })
}

fn agent_descriptor(bytes: &[u8]) -> serde_json::Value {
    serde_json::json!({"embedded": !bytes.is_empty(), "bytes": bytes.len(), "sha256": if bytes.is_empty() { None } else { Some(hex_bytes(&Sha256::digest(bytes))) }})
}

fn emit_local(app: &AppHandle, step: &str, message: impl Into<String>, progress: Option<u8>) {
    let _ = app.emit("pige360-deploy-event", AgentEvent::info(step, message, progress));
}

fn hex_bytes(bytes: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut output = String::with_capacity(bytes.len() * 2);
    for byte in bytes { output.push(HEX[(byte >> 4) as usize] as char); output.push(HEX[(byte & 0x0f) as usize] as char); }
    output
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_shell_metacharacters_in_host_and_user() {
        let mut input = ConnectionInput { host: "server.example".into(), port: 22, user: "deploy".into(), auth_method: AuthMethod::Agent, key_file: None, known_hosts_file: None, accept_new_host_key: false, sudo: false, connect_timeout_seconds: 20 };
        assert!(validate_connection(&input).is_ok());
        input.host = "server;touch /tmp/pwned".into();
        assert!(validate_connection(&input).is_err());
        input.host = "server.example".into(); input.user = "root$(id)".into();
        assert!(validate_connection(&input).is_err());
    }

    #[test]
    fn parses_preflight_without_executing_output() {
        let parsed = parse_probe("os=Linux\narch=x86_64\nkernel=6.8\nuser=deploy\ndocker=Docker 28\ncompose=Docker Compose 2\ncloudpanel=true\ndisk_kb=1024\n").unwrap();
        assert_eq!(parsed.get("arch").map(String::as_str), Some("x86_64"));
    }
}
