use crate::deployer::catalog::{
    allowed_env_keys, allowed_secret_keys, deployment_prefix, normalize_tag, safe_directory,
    validate_channel, validate_relative_path,
};
use crate::deployer::error::{DeployError, Result};
use crate::deployer::github::GitHubSource;
use crate::deployer::protocol::{
    AgentEvent, DeployReceipt, DeployRequest, DeploymentAction, DeploymentEnvironment,
    DeploymentPlatform, PROTOCOL_VERSION,
};
use chrono::Utc;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};
use uuid::Uuid;
use zeroize::{Zeroize, Zeroizing};

const INSTALLER_VERSION: &str = env!("CARGO_PKG_VERSION");
const MAX_ENV_BYTES: usize = 2 * 1024 * 1024;

pub fn execute(mut request: DeployRequest) -> Result<DeployReceipt> {
    let result = execute_inner(&mut request);
    request.github_token.zeroize();
    request.registry_token.zeroize();
    request.env_input.zeroize();
    for value in request.secret_inputs.values_mut() {
        value.zeroize();
    }
    result
}

fn execute_inner(request: &mut DeployRequest) -> Result<DeployReceipt> {
    validate_request(request)?;
    ensure_linux()?;
    if request.action == DeploymentAction::Rollback {
        return execute_rollback(request);
    }

    emit(AgentEvent::info("request", "Solicitação PIGE360 validada.", Some(3)));
    let directory = safe_directory(&request.directory)?;
    let prefix = deployment_prefix(request.platform, request.environment);
    let mut source = GitHubSource::new(&request.repository, request.github_token.take())?;
    emit(AgentEvent::info("source", "Resolvendo revisão imutável no GitHub…", Some(8)));
    let resolved = source.resolve(request.channel, request.environment, &request.requested_version)?;
    emit(AgentEvent::info(
        "source",
        format!("Revisão {} resolvida para {}.", resolved.reference, &resolved.commit[..12]),
        Some(14),
    ));
    let tree = source.fetch_tree(&prefix, &resolved.commit)?;
    verify_distribution(&tree, request.environment.as_str(), request.platform)?;
    emit(AgentEvent::info(
        "integrity",
        format!("{} arquivos do deployment validados por manifesto.", tree.len()),
        Some(24),
    ));

    let stage_parent = if request.action == DeploymentAction::Plan {
        PathBuf::from("/tmp")
    } else {
        directory.parent().ok_or_else(|| DeployError::msg("Diretório da stack sem pai."))?.to_path_buf()
    };
    fs::create_dir_all(&stage_parent)?;
    let stage = create_unique_directory(&stage_parent, ".pige360-deployer-stage-")?;
    let operation = (|| -> Result<DeployReceipt> {
        write_distribution_tree(&stage, &tree)?;
        let env_text = prepare_environment(&request, &directory, &tree, &resolved.image_tag, &resolved.version)?;
        write_atomic(&stage.join(".env"), env_text.as_bytes(), 0o600)?;
        emit(AgentEvent::info("configuration", "Ambiente preparado sem expor segredos.", Some(34)));

        if request.action == DeploymentAction::Plan {
            run_compose(
                &stage,
                "config",
                &command_args(&["config", "--quiet"]),
                request.wait_seconds,
                None,
                None,
            )?;
            return Ok(DeployReceipt {
                schema_version: 1,
                installer_version: INSTALLER_VERSION.into(),
                repository: source.repository().into(),
                channel: resolved.channel.as_str().into(),
                commit: resolved.commit.clone(),
                environment: request.environment.as_str().into(),
                version: resolved.version.clone(),
                image_tag: resolved.image_tag.clone(),
                platform: request.platform.as_str().into(),
                directory: directory.to_string_lossy().into_owned(),
                status: "PLANNED".into(),
                managed_files: tree.keys().cloned().collect(),
                source_proofs: source.proofs.clone(),
                backup_directory: None,
                result: Some(json!({
                    "deployment_prefix": prefix,
                    "files": tree.len(),
                    "immutable": true,
                    "deployment_mode": "service-native-image-only",
                    "compose_validated": true
                })),
            });
        }

        let _lock = OperationLock::acquire(&directory)?;
        let existed = directory.join(".pige360-deployer.json").is_file()
            || directory.join("compose.yaml").is_file()
            || directory.join("stack.yaml").is_file();
        if existed && request.action == DeploymentAction::Apply {
            emit(AgentEvent::info(
                "backup",
                "Criando backup service-native antes da atualização…",
                Some(42),
            ));
            let backup_name = format!("pre-deployer-{}", Utc::now().format("%Y%m%dT%H%M%SZ"));
            run_compose(
                &directory,
                "backup",
                &vec![
                    "--profile".into(),
                    "operations".into(),
                    "run".into(),
                    "--rm".into(),
                    "pige360-backup".into(),
                    "backup".into(),
                    "--name".into(),
                    backup_name,
                ],
                request.wait_seconds,
                None,
                None,
            )?;
        }
        let sync = synchronize_distribution(&stage, &directory, tree.keys().cloned().collect())?;
        let mut rollback_guard = SyncRollbackGuard::new(
            directory.clone(),
            sync.backup_directory.as_deref(),
            sync.incoming.clone(),
        );
        merge_environment_for_action(&stage, &directory, request.action, existed)?;
        emit(AgentEvent::info("storage", "Arquivos gerenciados sincronizados com backup transacional.", Some(48)));

        let registry_token = request.registry_token.take().map(Zeroizing::new);
        let docker_config = prepare_registry_login(
            &directory,
            request.registry_user.as_deref(),
            registry_token.as_ref().map(|value| value.as_str()),
            request.wait_seconds,
        )?;
        let docker_config_path = docker_config.as_ref().map(TemporaryDirectory::path);
        emit(AgentEvent::info(
            "validate",
            "Validando o Compose service-native e a política de distribuição…",
            Some(56),
        ));
        run_compose(
            &directory,
            "config",
            &command_args(&["config", "--quiet"]),
            request.wait_seconds,
            docker_config_path,
            None,
        )?;
        run_compose(
            &directory,
            "init-secrets",
            &command_args(&[
                "run",
                "--rm",
                "--no-deps",
                "pige360-secrets-init",
                "init-secrets",
            ]),
            request.wait_seconds,
            docker_config_path,
            None,
        )?;
        apply_secret_inputs(
            &directory,
            &request.secret_inputs,
            request.wait_seconds,
            docker_config_path,
        )?;
        run_compose(
            &directory,
            "validate-config",
            &command_args(&[
                "run",
                "--rm",
                "pige360-config-validate",
                "validate",
            ]),
            request.wait_seconds,
            docker_config_path,
            None,
        )?;

        let status = match request.action {
            DeploymentAction::Prepare => "PREPARED",
            DeploymentAction::Apply => {
                emit(AgentEvent::info(
                    if existed { "update" } else { "install" },
                    "Baixando imagens e iniciando os serviços PIGE360…",
                    Some(68),
                ));
                if let Err(apply_error) =
                    apply_stack(&directory, request.wait_seconds, docker_config_path)
                {
                    emit(AgentEvent::warning(
                        "rollback",
                        "A aplicação falhou; restaurando arquivos, ambiente e stack anterior.",
                    ));
                    if let Err(restore_error) = rollback_guard.rollback_now() {
                        return Err(DeployError::msg(format!(
                            "Falha ao aplicar a nova distribuição ({apply_error}) e ao restaurar os arquivos ({restore_error})."
                        )));
                    }
                    if existed {
                        if let Err(runtime_error) =
                            apply_stack(&directory, request.wait_seconds, docker_config_path)
                        {
                            return Err(DeployError::msg(format!(
                                "Falha ao aplicar a nova distribuição ({apply_error}); os arquivos anteriores foram restaurados, mas a stack anterior não reiniciou ({runtime_error})."
                            )));
                        }
                    }
                    return Err(apply_error);
                }
                "SERVICES_READY"
            }
            _ => return Err(DeployError::msg("Ação não suportada neste estágio.")),
        };
        let mut managed_files = tree.keys().cloned().collect::<Vec<_>>();
        managed_files.push(".env".into());
        managed_files.sort();
        managed_files.dedup();
        let receipt = DeployReceipt {
            schema_version: 1,
            installer_version: INSTALLER_VERSION.into(),
            repository: source.repository().into(),
            channel: resolved.channel.as_str().into(),
            commit: resolved.commit.clone(),
            environment: request.environment.as_str().into(),
            version: resolved.version.clone(),
            image_tag: resolved.image_tag.clone(),
            platform: request.platform.as_str().into(),
            directory: directory.to_string_lossy().into_owned(),
            status: status.into(),
            managed_files,
            source_proofs: source.proofs.clone(),
            backup_directory: sync.backup_directory,
            result: Some(json!({
                "operation": if request.action == DeploymentAction::Prepare {"prepare"} else if existed {"update"} else {"install"},
                "immutable_image_tag": resolved.image_tag,
                "deployment_mode": "service-native-image-only"
            })),
        };
        write_atomic(&directory.join(".pige360-deployer.json"), serde_json::to_vec_pretty(&receipt)?.as_slice(), 0o600)?;
        rollback_guard.commit();
        Ok(receipt)
    })();
    let _ = fs::remove_dir_all(&stage);
    operation
}

fn execute_rollback(request: &mut DeployRequest) -> Result<DeployReceipt> {
    let directory = safe_directory(&request.directory)?;
    let tag = request.rollback_tag.take().filter(|value| !value.trim().is_empty()).ok_or_else(|| DeployError::msg("Informe a tag imutável de rollback."))?;
    validate_rollback_tag(request.environment, &tag)?;
    let _lock = OperationLock::acquire(&directory)?;
    let receipt_path = directory.join(".pige360-deployer.json");
    if !receipt_path.is_file()
        || (!directory.join("compose.yaml").is_file() && !directory.join("stack.yaml").is_file())
    {
        return Err(DeployError::msg(
            "A stack não possui recibo e Compose service-native gerenciado pelo PIGE360 Deployer.",
        ));
    }
    let previous: DeployReceipt = serde_json::from_slice(&fs::read(&receipt_path)?)?;
    emit(AgentEvent::warning("rollback", format!("Revertendo {} para a tag imutável {tag}.", request.directory)));
    let backup_name = format!("pre-rollback-{}", Utc::now().format("%Y%m%dT%H%M%SZ"));
    run_compose(
        &directory,
        "backup",
        &vec![
            "--profile".into(),
            "operations".into(),
            "run".into(),
            "--rm".into(),
            "pige360-backup".into(),
            "backup".into(),
            "--name".into(),
            backup_name,
        ],
        request.wait_seconds,
        None,
        None,
    )?;
    let current_env = fs::read_to_string(directory.join(".env"))?;
    let previous_tag = env_value(&current_env, "PIGE360_IMAGE_TAG")
        .ok_or_else(|| DeployError::msg("O .env não contém PIGE360_IMAGE_TAG."))?;
    let mut rolled_env = set_env_value(&current_env, "PIGE360_IMAGE_TAG", normalize_tag(&tag))?;
    if crate::deployer::catalog::is_stable(&tag) {
        rolled_env = set_env_value(&rolled_env, "APP_VERSION", normalize_tag(&tag))?;
    }
    write_atomic(&directory.join(".env"), rolled_env.as_bytes(), 0o600)?;
    if let Err(error) = apply_stack(&directory, request.wait_seconds, None) {
        let restored = set_env_value(&current_env, "PIGE360_IMAGE_TAG", &previous_tag)?;
        write_atomic(&directory.join(".env"), restored.as_bytes(), 0o600)?;
        let _ = apply_stack(&directory, request.wait_seconds, None);
        return Err(error);
    }
    let mut receipt = previous;
    receipt.image_tag = normalize_tag(&tag).to_string();
    receipt.status = "ROLLED_BACK".into();
    receipt.result = Some(json!({"rollback_tag": tag, "completed": true}));
    write_atomic(&receipt_path, serde_json::to_vec_pretty(&receipt)?.as_slice(), 0o600)?;
    Ok(receipt)
}

fn validate_request(request: &DeployRequest) -> Result<()> {
    if request.protocol_version != PROTOCOL_VERSION {
        return Err(DeployError::msg(format!("Protocolo incompatível: desktop={}, agente={PROTOCOL_VERSION}.", request.protocol_version)));
    }
    if request.wait_seconds == 0 || request.wait_seconds > 3600 {
        return Err(DeployError::msg("wait_seconds deve estar entre 1 e 3600."));
    }
    if request.repository.trim().is_empty() || request.directory.trim().is_empty() {
        return Err(DeployError::msg("Repositório e diretório são obrigatórios."));
    }
    if request.action != DeploymentAction::Rollback {
        validate_channel(request.channel, request.environment, &request.requested_version)?;
    }
    let allowed_env = allowed_env_keys();
    if let Some(key) = request.env_overrides.keys().find(|key| !allowed_env.contains(key.as_str())) {
        return Err(DeployError::msg(format!("Override de ambiente não permitido: {key}.")));
    }
    let allowed_secrets = allowed_secret_keys();
    if let Some(key) = request.secret_inputs.keys().find(|key| !allowed_secrets.contains(key.as_str())) {
        return Err(DeployError::msg(format!("Secret não permitido: {key}.")));
    }
    if request.registry_user.as_ref().is_some_and(|value| !value.trim().is_empty())
        != request.registry_token.as_ref().is_some_and(|value| !value.is_empty())
    {
        return Err(DeployError::msg("Usuário e token GHCR devem ser informados em conjunto."));
    }
    Ok(())
}

fn ensure_linux() -> Result<()> {
    if std::env::consts::OS != "linux" {
        return Err(DeployError::msg("O agente remoto deve executar em um servidor Linux."));
    }
    Ok(())
}

fn verify_distribution(
    tree: &BTreeMap<String, Vec<u8>>,
    expected_environment: &str,
    platform: DeploymentPlatform,
) -> Result<()> {
    let compose_name = if platform == DeploymentPlatform::Portainer {
        "stack.yaml"
    } else {
        "compose.yaml"
    };
    for required in [
        compose_name,
        ".env.example",
        "README.md",
        "GENERATED-MANIFEST.json",
        "SHA256SUMS",
    ] {
        if !tree.contains_key(required) {
            return Err(DeployError::msg(format!("Deployment incompleto: falta {required}.")));
        }
    }
    let manifest: Value = serde_json::from_slice(tree.get("GENERATED-MANIFEST.json").unwrap())?;
    if manifest.get("environment").and_then(Value::as_str) != Some(expected_environment) {
        return Err(DeployError::msg("Ambiente do manifesto diverge da solicitação."));
    }
    if manifest.get("schema_version").and_then(Value::as_u64) != Some(2)
        || manifest.get("mode").and_then(Value::as_str) != Some("service-native-image-only")
    {
        return Err(DeployError::msg(
            "O Deployer exige deployment schema 2 service-native-image-only.",
        ));
    }
    let expected_platform = if platform == DeploymentPlatform::Compose {
        None
    } else {
        Some(platform.as_str())
    };
    if manifest.get("platform").and_then(Value::as_str) != expected_platform {
        return Err(DeployError::msg("Plataforma do manifesto diverge da solicitação."));
    }
    let files = manifest.get("files").and_then(Value::as_object).ok_or_else(|| DeployError::msg("Manifesto sem hashes de arquivos."))?;
    for (path, expected) in files {
        validate_relative_path(path)?;
        let expected = expected.as_str().ok_or_else(|| DeployError::msg("Hash inválido no manifesto."))?;
        let bytes = tree.get(path).ok_or_else(|| DeployError::msg(format!("Arquivo do manifesto ausente: {path}.")))?;
        let actual = hex_bytes(&Sha256::digest(bytes));
        if actual != expected {
            return Err(DeployError::msg(format!("SHA-256 divergente em {path}.")));
        }
    }
    let sums = std::str::from_utf8(tree.get("SHA256SUMS").unwrap())
        .map_err(|_| DeployError::msg("SHA256SUMS não está em UTF-8."))?;
    let mut covered = BTreeSet::new();
    for line in sums.lines() {
        let (expected, path) = line
            .split_once("  ")
            .ok_or_else(|| DeployError::msg("Linha inválida em SHA256SUMS."))?;
        if expected.len() != 64
            || !expected
                .bytes()
                .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
        {
            return Err(DeployError::msg("Hash inválido em SHA256SUMS."));
        }
        validate_relative_path(path)?;
        let bytes = tree
            .get(path)
            .ok_or_else(|| DeployError::msg(format!("Arquivo de SHA256SUMS ausente: {path}.")))?;
        if hex_bytes(&Sha256::digest(bytes)) != expected {
            return Err(DeployError::msg(format!("SHA256SUMS diverge em {path}.")));
        }
        if !covered.insert(path.to_string()) {
            return Err(DeployError::msg(format!("Arquivo duplicado em SHA256SUMS: {path}.")));
        }
    }
    let expected_coverage = tree
        .keys()
        .filter(|path| path.as_str() != "SHA256SUMS")
        .cloned()
        .collect::<BTreeSet<_>>();
    if covered != expected_coverage {
        return Err(DeployError::msg("SHA256SUMS não cobre exatamente o deployment."));
    }
    Ok(())
}

fn prepare_environment(request: &DeployRequest, directory: &Path, tree: &BTreeMap<String, Vec<u8>>, image_tag: &str, version: &str) -> Result<String> {
    let existing_path = directory.join(".env");
    let existing = existing_path.is_file();
    if existing && request.env_input.is_some() {
        return Err(DeployError::msg("Um .env local não pode substituir o .env já existente no servidor."));
    }
    let mut text = if existing {
        fs::read_to_string(existing_path)?
    } else if let Some(input) = &request.env_input {
        if input.len() > MAX_ENV_BYTES { return Err(DeployError::msg("O .env inicial excede 2 MB.")); }
        input.clone()
    } else {
        String::from_utf8(tree.get(".env.example").unwrap().clone()).map_err(|_| DeployError::msg(".env.example não está em UTF-8."))?
    };
    text = set_env_value(&text, "PIGE360_ENVIRONMENT", request.environment.as_str())?;
    text = set_env_value(&text, "APP_ENV", if request.environment == DeploymentEnvironment::Production { "production" } else { "staging" })?;
    text = set_env_value(&text, "PIGE360_IMAGE_TAG", image_tag)?;
    if crate::deployer::catalog::is_stable(version) {
        text = set_env_value(&text, "APP_VERSION", normalize_tag(version))?;
    }
    for (key, value) in &request.env_overrides {
        text = set_env_value(&text, key, value)?;
    }
    Ok(text)
}

fn set_env_value(text: &str, key: &str, value: &str) -> Result<String> {
    if value
        .chars()
        .any(|character| matches!(character, '\r' | '\n' | '\0' | '\''))
    {
        return Err(DeployError::msg(format!("Valor inválido para {key}.")));
    }
    let literal = if value.bytes().all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'.' | b'/' | b':' | b'@' | b',' | b'?' | b'=' | b'+' | b'*' | b'-' | b'{' | b'}')) {
        value.to_string()
    } else {
        format!("'{value}'")
    };
    let mut output = String::new();
    let mut found = false;
    for line in text.lines() {
        let candidate = line.trim_start().strip_prefix("export ").unwrap_or(line.trim_start());
        if candidate.split_once('=').is_some_and(|(name, _)| name == key) {
            if found { return Err(DeployError::msg(format!("Variável duplicada no .env: {key}."))); }
            output.push_str(&format!("{key}={literal}\n"));
            found = true;
        } else {
            output.push_str(line);
            output.push('\n');
        }
    }
    if !found { output.push_str(&format!("{key}={literal}\n")); }
    Ok(output)
}

fn write_distribution_tree(root: &Path, tree: &BTreeMap<String, Vec<u8>>) -> Result<()> {
    for (relative, bytes) in tree {
        validate_relative_path(relative)?;
        let mode = if relative.ends_with(".sh") || relative.ends_with(".py") { 0o700 } else { 0o600 };
        write_atomic(&root.join(relative), bytes, mode)?;
    }
    Ok(())
}

struct SyncResult {
    backup_directory: Option<String>,
    incoming: Vec<String>,
}

fn synchronize_distribution(stage: &Path, destination: &Path, incoming: Vec<String>) -> Result<SyncResult> {
    fs::create_dir_all(destination)?;
    let previous_receipt = destination.join(".pige360-deployer.json");
    let previous_files = if previous_receipt.is_file() {
        serde_json::from_slice::<DeployReceipt>(&fs::read(&previous_receipt)?).map(|receipt| receipt.managed_files).unwrap_or_default()
    } else { Vec::new() };
    let incoming_set = incoming.iter().cloned().collect::<BTreeSet<_>>();
    let timestamp = format!(
        "{}-{}",
        Utc::now().format("%Y%m%dT%H%M%SZ"),
        Uuid::new_v4().simple()
    );
    let backup = destination.join(".state").join("deployer-backups").join(timestamp);
    fs::create_dir_all(&backup)?;
    fs::set_permissions(&backup, fs::Permissions::from_mode(0o700))?;
    if destination.join(".env").is_file() {
        write_atomic(&backup.join(".env"), &fs::read(destination.join(".env"))?, 0o600)?;
    }
    let mut touched = BTreeSet::new();
    for relative in previous_files.iter().chain(incoming.iter()) {
        if relative == ".env" || relative.starts_with("volumes/") || relative.starts_with("secrets/") || relative.starts_with(".state/") { continue; }
        validate_relative_path(relative)?;
        if !touched.insert(relative.clone()) { continue; }
        let current = destination.join(relative);
        if current.is_file() {
            let target = backup.join(relative);
            if let Some(parent) = target.parent() { fs::create_dir_all(parent)?; }
            let mode = if relative.ends_with(".sh") || relative.ends_with(".py") {
                0o700
            } else {
                0o600
            };
            write_atomic(&target, &fs::read(&current)?, mode)?;
        }
    }
    for relative in &incoming {
        if relative == ".env" { continue; }
        let source = stage.join(relative);
        let mode = if relative.ends_with(".sh") || relative.ends_with(".py") { 0o700 } else { 0o600 };
        write_atomic(&destination.join(relative), &fs::read(source)?, mode)?;
    }
    for relative in previous_files {
        if relative == ".env" || incoming_set.contains(&relative) || relative.starts_with("volumes/") || relative.starts_with("secrets/") || relative.starts_with(".state/") { continue; }
        let path = destination.join(relative);
        if path.is_file() { fs::remove_file(path)?; }
    }
    if !destination.join(".env").is_file() {
        write_atomic(&destination.join(".env"), &fs::read(stage.join(".env"))?, 0o600)?;
    }
    write_atomic(&backup.join("manifest.json"), serde_json::to_vec_pretty(&json!({"incoming": incoming, "previous": touched}))?.as_slice(), 0o600)?;
    Ok(SyncResult {
        backup_directory: Some(backup.to_string_lossy().into_owned()),
        incoming,
    })
}

fn merge_environment_for_action(stage: &Path, destination: &Path, action: DeploymentAction, existed: bool) -> Result<()> {
    if !existed {
        return Ok(());
    }
    let desired = fs::read_to_string(stage.join(".env"))?;
    let output = match action {
        DeploymentAction::Prepare => {
            let current = fs::read_to_string(destination.join(".env"))?;
            let current_tag = env_value(&current, "PIGE360_IMAGE_TAG")
                .ok_or_else(|| DeployError::msg("O .env existente não possui PIGE360_IMAGE_TAG para rollback seguro."))?;
            let with_current_tag = set_env_value(&desired, "PIGE360_IMAGE_TAG", &current_tag)?;
            if let Some(current_version) = env_value(&current, "APP_VERSION") {
                return write_atomic(
                    &destination.join(".env"),
                    set_env_value(&with_current_tag, "APP_VERSION", &current_version)?.as_bytes(),
                    0o600,
                );
            }
            with_current_tag
        }
        DeploymentAction::Apply => desired,
        _ => return Ok(()),
    };
    write_atomic(&destination.join(".env"), output.as_bytes(), 0o600)
}

struct SyncRollbackGuard {
    destination: PathBuf,
    backup: Option<PathBuf>,
    incoming: Vec<String>,
    committed: bool,
}

impl SyncRollbackGuard {
    fn new(destination: PathBuf, backup: Option<&str>, mut incoming: Vec<String>) -> Self {
        incoming.push(".env".into());
        incoming.sort();
        incoming.dedup();
        Self {
            destination,
            backup: backup.map(PathBuf::from),
            incoming,
            committed: false,
        }
    }

    fn commit(&mut self) {
        self.committed = true;
    }

    fn rollback_now(&mut self) -> Result<()> {
        if self.committed {
            return Ok(());
        }
        restore_synchronized_files(
            &self.destination,
            self.backup.as_deref(),
            &self.incoming,
        )?;
        self.committed = true;
        Ok(())
    }
}

impl Drop for SyncRollbackGuard {
    fn drop(&mut self) {
        if !self.committed {
            let _ = restore_synchronized_files(
                &self.destination,
                self.backup.as_deref(),
                &self.incoming,
            );
        }
    }
}

fn restore_synchronized_files(
    destination: &Path,
    backup: Option<&Path>,
    incoming: &[String],
) -> Result<()> {
    let backup = backup.ok_or_else(|| DeployError::msg("Backup transacional ausente."))?;
    for relative in incoming {
        validate_relative_path(relative)?;
        if !backup.join(relative).is_file() {
            let current = destination.join(relative);
            if current.is_file() {
                fs::remove_file(current)?;
            }
        }
    }
    restore_backup_tree(backup, backup, destination)
}

fn restore_backup_tree(root: &Path, current: &Path, destination: &Path) -> Result<()> {
    for entry in fs::read_dir(current)? {
        let entry = entry?;
        let file_type = entry.file_type()?;
        if file_type.is_symlink() {
            return Err(DeployError::msg("Backup transacional contém link simbólico."));
        }
        if file_type.is_dir() {
            restore_backup_tree(root, &entry.path(), destination)?;
            continue;
        }
        let relative = entry
            .path()
            .strip_prefix(root)
            .map_err(|_| DeployError::msg("Arquivo de backup fora do diretório transacional."))?
            .to_string_lossy()
            .replace('\\', "/");
        if relative == "manifest.json" {
            continue;
        }
        validate_relative_path(&relative)?;
        let mode = if relative.ends_with(".sh") || relative.ends_with(".py") {
            0o700
        } else {
            0o600
        };
        write_atomic(
            &destination.join(&relative),
            &fs::read(entry.path())?,
            mode,
        )?;
    }
    Ok(())
}

fn env_value(text: &str, key: &str) -> Option<String> {
    text.lines().find_map(|line| {
        let candidate = line.trim_start().strip_prefix("export ").unwrap_or(line.trim_start());
        let (name, value) = candidate.split_once('=')?;
        if name != key {
            return None;
        }
        Some(value.trim().trim_matches('\'').to_string())
    })
}

fn apply_secret_inputs(
    root: &Path,
    secrets: &BTreeMap<String, String>,
    timeout: u64,
    docker_config: Option<&Path>,
) -> Result<()> {
    for (name, value) in secrets {
        if !allowed_secret_keys().contains(name.as_str()) { return Err(DeployError::msg("Secret fora da allowlist.")); }
        run_compose(
            root,
            "secret-set",
            &vec![
                "--profile".into(),
                "operations".into(),
                "run".into(),
                "--rm".into(),
                "--no-deps".into(),
                "-T".into(),
                "pige360-secret-set".into(),
                "secret-set".into(),
                name.clone(),
            ],
            timeout,
            docker_config,
            Some(value.as_bytes()),
        )?;
    }
    Ok(())
}

fn prepare_registry_login(root: &Path, user: Option<&str>, token: Option<&str>, timeout: u64) -> Result<Option<TemporaryDirectory>> {
    match (user.filter(|value| !value.trim().is_empty()), token.filter(|value| !value.is_empty())) {
        (None, None) => Ok(None),
        (Some(user), Some(token)) => {
            let path = create_unique_directory(&root.join(".state"), "docker-auth-")?;
            fs::set_permissions(&path, fs::Permissions::from_mode(0o700))?;
            let mut child = Command::new("docker")
                .args(["login", "ghcr.io", "--username", user, "--password-stdin"])
                .env("DOCKER_CONFIG", &path)
                .stdin(Stdio::piped()).stdout(Stdio::null()).stderr(Stdio::null())
                .spawn().map_err(|_| DeployError::msg("Docker não foi encontrado."))?;
            if let Some(mut stdin) = child.stdin.take() { stdin.write_all(token.as_bytes())?; stdin.write_all(b"\n")?; }
            let status = wait_child(&mut child, Duration::from_secs(timeout.min(120)), "docker login")?;
            if !status.success() { let _ = fs::remove_dir_all(&path); return Err(DeployError::msg("Falha no login temporário GHCR.")); }
            Ok(Some(TemporaryDirectory(path)))
        }
        _ => Err(DeployError::msg("Usuário e token GHCR devem ser informados em conjunto.")),
    }
}

struct TemporaryDirectory(PathBuf);

impl TemporaryDirectory {
    fn path(&self) -> &Path {
        &self.0
    }
}

impl Drop for TemporaryDirectory {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn command_args(values: &[&str]) -> Vec<String> {
    values.iter().map(|value| (*value).to_string()).collect()
}

fn compose_file(root: &Path) -> Result<&'static str> {
    if root.join("compose.yaml").is_file() {
        Ok("compose.yaml")
    } else if root.join("stack.yaml").is_file() {
        Ok("stack.yaml")
    } else {
        Err(DeployError::msg("Deployment sem compose.yaml ou stack.yaml."))
    }
}

fn run_compose(
    root: &Path,
    operation: &str,
    arguments: &[String],
    timeout: u64,
    docker_config: Option<&Path>,
    stdin_data: Option<&[u8]>,
) -> Result<()> {
    let compose = compose_file(root)?;
    let env_file = root.join(".env");
    if !env_file.is_file() {
        return Err(DeployError::msg("Deployment sem arquivo .env."));
    }
    let log_directory = root.join(".state").join("deployer-logs");
    fs::create_dir_all(&log_directory)?;
    fs::set_permissions(&log_directory, fs::Permissions::from_mode(0o700))?;
    let log_path = log_directory.join(format!(
        "{}-{}-{}.log",
        Utc::now().format("%Y%m%dT%H%M%SZ"),
        operation,
        Uuid::new_v4().simple()
    ));
    let log = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(&log_path)?;
    let log_stderr = log.try_clone()?;
    let mut command = Command::new("docker");
    command
        .args(["compose", "--project-directory"])
        .arg(root)
        .arg("--env-file")
        .arg(&env_file)
        .args(["-f", compose])
        .args(arguments)
        .current_dir(root)
        .stdin(if stdin_data.is_some() { Stdio::piped() } else { Stdio::null() })
        .stdout(Stdio::from(log))
        .stderr(Stdio::from(log_stderr));
    if let Some(config) = docker_config { command.env("DOCKER_CONFIG", config); }
    let mut child = command
        .spawn()
        .map_err(|_| DeployError::msg("Docker Compose v2 não foi encontrado."))?;
    if let (Some(data), Some(mut stdin)) = (stdin_data, child.stdin.take()) {
        stdin.write_all(data)?;
        stdin.write_all(b"\n")?;
    }
    let status = wait_child(
        &mut child,
        Duration::from_secs(timeout.saturating_add(120).min(3720)),
        operation,
    )?;
    if !status.success() {
        return Err(DeployError::msg(format!(
            "Operação Compose {operation} falhou com código {}. O log restrito está em {} no servidor.",
            status.code().unwrap_or(-1),
            log_path.display()
        )));
    }
    Ok(())
}

fn apply_stack(root: &Path, timeout: u64, docker_config: Option<&Path>) -> Result<()> {
    run_compose(
        root,
        "config",
        &command_args(&["config", "--quiet"]),
        timeout,
        docker_config,
        None,
    )?;
    run_compose(
        root,
        "pull",
        &command_args(&["pull"]),
        timeout,
        docker_config,
        None,
    )?;
    let up = vec![
        "up".into(),
        "-d".into(),
        "--remove-orphans".into(),
        "--wait".into(),
        "--wait-timeout".into(),
        timeout.to_string(),
    ];
    run_compose(root, "up", &up, timeout, docker_config, None)?;
    run_compose(
        root,
        "readiness",
        &command_args(&[
            "--profile",
            "operations",
            "run",
            "--rm",
            "--no-deps",
            "pige360-readiness",
            "readiness",
        ]),
        timeout,
        docker_config,
        None,
    )
}

fn wait_child(child: &mut std::process::Child, timeout: Duration, operation: &str) -> Result<std::process::ExitStatus> {
    let deadline = Instant::now() + timeout;
    loop {
        if let Some(status) = child.try_wait()? { return Ok(status); }
        if Instant::now() >= deadline {
            let _ = child.kill();
            let _ = child.wait();
            return Err(DeployError::msg(format!("Tempo limite excedido em {operation}.")));
        }
        std::thread::sleep(Duration::from_millis(250));
    }
}

fn validate_rollback_tag(environment: DeploymentEnvironment, value: &str) -> Result<()> {
    let tag = normalize_tag(value);
    let immutable_develop = tag.starts_with("develop-") && tag.len() == 20 && tag[8..].bytes().all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase());
    let stable = crate::deployer::catalog::is_stable(tag);
    let prerelease = crate::deployer::catalog::is_prerelease(tag);
    if environment == DeploymentEnvironment::Production && !stable { return Err(DeployError::msg("Rollback de produção exige SemVer estável.")); }
    if environment == DeploymentEnvironment::Develop && !(immutable_develop || stable || prerelease) { return Err(DeployError::msg("Rollback develop exige develop-<sha12> ou SemVer imutável.")); }
    Ok(())
}

fn create_unique_directory(parent: &Path, prefix: &str) -> Result<PathBuf> {
    fs::create_dir_all(parent)?;
    for _ in 0..8 {
        let path = parent.join(format!("{prefix}{}", Uuid::new_v4().simple()));
        match fs::create_dir(&path) {
            Ok(()) => { fs::set_permissions(&path, fs::Permissions::from_mode(0o700))?; return Ok(path); }
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(error) => return Err(error.into()),
        }
    }
    Err(DeployError::msg("Não foi possível reservar diretório temporário exclusivo."))
}

fn write_atomic(path: &Path, bytes: &[u8], mode: u32) -> Result<()> {
    if fs::symlink_metadata(path).ok().is_some_and(|meta| meta.file_type().is_symlink()) { return Err(DeployError::msg("Recusando sobrescrever link simbólico.")); }
    let parent = path.parent().ok_or_else(|| DeployError::msg("Arquivo sem diretório pai."))?;
    fs::create_dir_all(parent)?;
    let temporary = parent.join(format!(".pige360-write-{}", Uuid::new_v4().simple()));
    let mut file = OpenOptions::new().write(true).create_new(true).mode(mode).custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC).open(&temporary)?;
    file.write_all(bytes)?;
    file.flush()?;
    file.sync_all()?;
    fs::rename(&temporary, path)?;
    fs::set_permissions(path, fs::Permissions::from_mode(mode))?;
    Ok(())
}

struct OperationLock { path: PathBuf, _marker: File }

impl OperationLock {
    fn acquire(directory: &Path) -> Result<Self> {
        let parent = directory.parent().ok_or_else(|| DeployError::msg("Stack sem diretório pai."))?;
        fs::create_dir_all(parent)?;
        let name = directory.file_name().and_then(|value| value.to_str()).ok_or_else(|| DeployError::msg("Nome de stack inválido."))?;
        let path = parent.join(format!(".pige360-deployer-{name}.lock"));
        fs::create_dir(&path).map_err(|error| if error.kind() == std::io::ErrorKind::AlreadyExists { DeployError::msg("Outra operação já está ativa para esta stack.") } else { error.into() })?;
        fs::set_permissions(&path, fs::Permissions::from_mode(0o700))?;
        let mut marker = OpenOptions::new().write(true).create_new(true).mode(0o600).open(path.join("pid"))?;
        writeln!(marker, "{}", std::process::id())?;
        marker.sync_all()?;
        Ok(Self { path, _marker: marker })
    }
}

impl Drop for OperationLock {
    fn drop(&mut self) { let _ = fs::remove_file(self.path.join("pid")); let _ = fs::remove_dir(&self.path); }
}

fn emit(event: AgentEvent) {
    if let Ok(line) = serde_json::to_string(&event) { println!("{line}"); let _ = std::io::stdout().flush(); }
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
    fn environment_updates_are_idempotent() {
        let once = set_env_value("A=1\nPIGE360_IMAGE_TAG=develop\n", "PIGE360_IMAGE_TAG", "develop-0123456789ab").unwrap();
        let twice = set_env_value(&once, "PIGE360_IMAGE_TAG", "develop-0123456789ab").unwrap();
        assert_eq!(once, twice);
        assert_eq!(twice.matches("PIGE360_IMAGE_TAG=").count(), 1);
    }

    #[test]
    fn rollback_policy_rejects_moving_develop_tag() {
        assert!(validate_rollback_tag(DeploymentEnvironment::Develop, "develop").is_err());
        assert!(validate_rollback_tag(DeploymentEnvironment::Develop, "develop-0123456789ab").is_ok());
        assert!(validate_rollback_tag(DeploymentEnvironment::Production, "1.2.3").is_ok());
        assert!(validate_rollback_tag(DeploymentEnvironment::Production, "1.2.3-rc.1").is_err());
    }
}
