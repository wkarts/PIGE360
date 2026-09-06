use chrono::Utc;
use rusqlite::{params, Connection, OpenFlags, OptionalExtension};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    path::{Path, PathBuf},
};

use crate::storage_contract;

const MIGRATION_MARKER: &str = "legacy-database-migration-v1.json";
const LEGACY_ROTATION_KEY: &str = "security_bootstrap_credential_rotation_v1";
const LEGACY_CREDENTIAL_REPAIR_KEY: &str = "legacy_credentials_preserved_v1";

#[derive(Debug, Clone)]
pub struct DatabaseRecovery {
    backup_path: PathBuf,
    source_backup_path: PathBuf,
    target_existed: bool,
    copied_from_legacy: bool,
    source_path: PathBuf,
    source_checksum: String,
}

impl DatabaseRecovery {
    pub fn copied_from_legacy(&self) -> bool {
        self.copied_from_legacy
    }

    pub fn preserved_user_credentials(&self) -> Result<bool, String> {
        if !self.copied_from_legacy() || !self.source_path.is_file() {
            return Ok(false);
        }
        let source =
            Connection::open_with_flags(&self.source_path, OpenFlags::SQLITE_OPEN_READ_ONLY)
                .map_err(|err| format!("Falha ao validar credenciais da origem legada: {err}"))?;
        if !table_exists(&source, "usuarios")?
            || !table_has_column(&source, "usuarios", "senha_hash")?
        {
            return Ok(false);
        }
        let count: i64 = source
            .query_row(
                "SELECT COUNT(*) FROM usuarios WHERE TRIM(COALESCE(senha_hash, '')) <> ''",
                [],
                |row| row.get(0),
            )
            .map_err(|err| format!("Falha ao contar credenciais legadas: {err}"))?;
        Ok(count > 0)
    }
}

#[derive(Debug, Serialize, Deserialize)]
struct MigrationMarker {
    schema_version: u32,
    application_version: String,
    source_path: String,
    source_checksum_sha256: String,
    target_path: String,
    backup_path: String,
    completed_at: String,
}

#[derive(Debug, Deserialize)]
struct LegacyBootstrapConfig {
    data_dir_override: Option<String>,
}

#[derive(Debug)]
struct LegacyCredentialRepair {
    target_user_id: i64,
    source_password_hash: String,
    source_temporary_password: i64,
}

pub fn prepare(data_dir: &Path, target_db: &Path) -> Result<Option<DatabaseRecovery>, String> {
    fs::create_dir_all(data_dir)
        .map_err(|err| format!("Falha ao preparar diretório de dados: {err}"))?;

    if target_db.is_file() {
        validate_integrity(target_db)?;
        if !data_dir.join(MIGRATION_MARKER).is_file() && target_is_unused_bootstrap(target_db)? {
            if let Some(legacy_db) = resolve_legacy_database(target_db)? {
                return replace_unused_target_with_legacy(data_dir, target_db, &legacy_db)
                    .map(Some);
            }
        }
        let credential_repair_pending =
            pending_rotated_legacy_credential(data_dir, target_db)?.is_some();
        let marker = data_dir.join(format!("schema-backup-{}.ok", env!("CARGO_PKG_VERSION")));
        if marker.is_file() && !credential_repair_pending {
            return Ok(None);
        }
        return backup_database(data_dir, target_db, true, false).map(Some);
    }

    let Some(legacy_db) = resolve_legacy_database(target_db)? else {
        return Ok(None);
    };
    validate_integrity(&legacy_db)?;
    let recovery = backup_database(data_dir, &legacy_db, false, true)?;
    let temporary = target_db.with_extension("db.migrating");
    if temporary.exists() {
        fs::remove_file(&temporary)
            .map_err(|err| format!("Falha ao limpar cópia temporária anterior: {err}"))?;
    }
    copy_synced(&legacy_db, &temporary)?;
    validate_integrity(&temporary)?;
    validate_critical_counts(&legacy_db, &temporary)?;
    fs::rename(&temporary, target_db)
        .map_err(|err| format!("Falha ao ativar cópia migrada do banco legado: {err}"))?;
    Ok(Some(recovery))
}

pub fn restore_rotated_legacy_credential(
    data_dir: &Path,
    target_db: &Path,
) -> Result<bool, String> {
    let Some(repair) = pending_rotated_legacy_credential(data_dir, target_db)? else {
        return Ok(false);
    };

    let mut conn = Connection::open(target_db)
        .map_err(|err| format!("Falha ao abrir banco para preservar credencial legada: {err}"))?;
    conn.pragma_update(None, "foreign_keys", "ON")
        .map_err(|err| format!("Falha ao ativar foreign_keys na preservação legada: {err}"))?;
    let transaction = conn
        .transaction()
        .map_err(|err| format!("Falha ao iniciar preservação da credencial legada: {err}"))?;
    let now = Utc::now().to_rfc3339();

    transaction
        .execute(
            "UPDATE usuarios
                SET senha_hash = ?1, senha_provisoria = ?2, updated_at = ?3
              WHERE id = ?4",
            params![
                repair.source_password_hash,
                repair.source_temporary_password,
                now,
                repair.target_user_id
            ],
        )
        .map_err(|err| format!("Falha ao restaurar hash da credencial legada: {err}"))?;

    transaction
        .execute(
            "INSERT OR REPLACE INTO app_settings (chave, valor, updated_at)
             VALUES (?1, 'completed', ?2)",
            params![LEGACY_CREDENTIAL_REPAIR_KEY, now],
        )
        .map_err(|err| format!("Falha ao registrar preservação da credencial legada: {err}"))?;

    transaction
        .commit()
        .map_err(|err| format!("Falha ao confirmar preservação da credencial legada: {err}"))?;
    Ok(true)
}

pub fn finalize(
    data_dir: &Path,
    target_db: &Path,
    recovery: Option<&DatabaseRecovery>,
) -> Result<(), String> {
    validate_integrity(target_db)?;
    let version_marker = data_dir.join(format!("schema-backup-{}.ok", env!("CARGO_PKG_VERSION")));
    write_private_file(&version_marker, b"ok\n")?;

    let Some(recovery) = recovery else {
        return Ok(());
    };
    if !recovery.copied_from_legacy {
        return Ok(());
    }
    let marker = MigrationMarker {
        schema_version: 1,
        application_version: env!("CARGO_PKG_VERSION").to_string(),
        source_path: recovery.source_path.to_string_lossy().to_string(),
        source_checksum_sha256: recovery.source_checksum.clone(),
        target_path: target_db.to_string_lossy().to_string(),
        backup_path: recovery.source_backup_path.to_string_lossy().to_string(),
        completed_at: Utc::now().to_rfc3339(),
    };
    let payload = serde_json::to_vec_pretty(&marker)
        .map_err(|err| format!("Falha ao serializar marcador da migração: {err}"))?;
    write_private_file(&data_dir.join(MIGRATION_MARKER), &payload)
}

pub fn rollback(target_db: &Path, recovery: Option<&DatabaseRecovery>) -> Result<(), String> {
    let Some(recovery) = recovery else {
        return Ok(());
    };
    if recovery.target_existed {
        let temporary = target_db.with_extension("db.rollback");
        copy_synced(&recovery.backup_path, &temporary)?;
        validate_integrity(&temporary)?;
        if target_db.exists() {
            fs::remove_file(target_db)
                .map_err(|err| format!("Falha ao remover banco com migration reprovada: {err}"))?;
        }
        fs::rename(&temporary, target_db)
            .map_err(|err| format!("Falha ao restaurar banco anterior: {err}"))?;
    } else if target_db.exists() {
        fs::remove_file(target_db)
            .map_err(|err| format!("Falha ao remover cópia migrada reprovada: {err}"))?;
    }
    Ok(())
}

fn resolve_legacy_database(target_db: &Path) -> Result<Option<PathBuf>, String> {
    let mut candidates = Vec::new();
    if let Ok(configured) = std::env::var("PIGE360_DEPLOYER_LEGACY_DB_PATH") {
        let trimmed = configured.trim();
        if !trimmed.is_empty() {
            candidates.push(PathBuf::from(trimmed));
        }
    }
    if let Ok(configured) = std::env::var("PIGE360_DEPLOYER_LEGACY_DB_PATHS") {
        candidates.extend(
            configured
                .split([';', ','])
                .map(str::trim)
                .filter(|value| !value.is_empty())
                .map(PathBuf::from),
        );
    }
    if let Some(config_base) = dirs::config_local_dir() {
        for slug in storage_contract::LEGACY_LOCAL_DATA_DIRS {
            append_configured_legacy_database(
                &mut candidates,
                &config_base.join(slug).join("bootstrap.json"),
            )?;
        }
    }
    if let Some(base) = dirs::data_local_dir() {
        candidates.extend(storage_contract::known_legacy_database_candidates(&base));
    }
    let mut unique: Vec<PathBuf> = Vec::new();
    for candidate in candidates {
        if candidate.is_file()
            && !same_file(&candidate, target_db)
            && !unique.iter().any(|known| same_file(known, &candidate))
        {
            unique.push(candidate);
        }
    }
    match unique.as_slice() {
        [] => Ok(None),
        [candidate] => Ok(Some(candidate.clone())),
        _ => Err(format!(
            "Mais de um banco legado foi encontrado. Defina PIGE360_DEPLOYER_LEGACY_DB_PATH com uma única origem confirmada: {}",
            unique
                .iter()
                .map(|path| path.display().to_string())
                .collect::<Vec<_>>()
                .join(", ")
        )),
    }
}

fn same_file(left: &Path, right: &Path) -> bool {
    if left == right {
        return true;
    }
    match (fs::canonicalize(left), fs::canonicalize(right)) {
        (Ok(left), Ok(right)) => left == right,
        _ => false,
    }
}

fn append_configured_legacy_database(
    candidates: &mut Vec<PathBuf>,
    config_path: &Path,
) -> Result<(), String> {
    if !config_path.is_file() {
        return Ok(());
    }
    let raw = fs::read_to_string(config_path).map_err(|err| {
        format!(
            "Falha ao ler configuração legada {}: {err}",
            config_path.display()
        )
    })?;
    let config = serde_json::from_str::<LegacyBootstrapConfig>(&raw).map_err(|err| {
        format!(
            "Falha ao interpretar configuração legada {}: {err}",
            config_path.display()
        )
    })?;
    let Some(configured) = config
        .data_dir_override
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
    else {
        return Ok(());
    };
    let configured_path = PathBuf::from(configured);
    if configured_path.is_file() {
        candidates.push(configured_path);
    } else {
        candidates.extend(storage_contract::legacy_database_candidates_in(
            &configured_path,
        ));
    }
    Ok(())
}

fn pending_rotated_legacy_credential(
    data_dir: &Path,
    target_db: &Path,
) -> Result<Option<LegacyCredentialRepair>, String> {
    let Some(marker) = read_migration_marker(data_dir)? else {
        return Ok(None);
    };
    let source_path = PathBuf::from(&marker.source_path);
    if !source_path.is_file() || !target_db.is_file() {
        return Ok(None);
    }
    validate_integrity(&source_path)?;

    let target = Connection::open_with_flags(target_db, OpenFlags::SQLITE_OPEN_READ_ONLY)
        .map_err(|err| format!("Falha ao abrir banco migrado para validar credencial: {err}"))?;
    if !table_exists(&target, "app_settings")? || !table_exists(&target, "usuarios")? {
        return Ok(None);
    }

    let repair_status: Option<String> = target
        .query_row(
            "SELECT valor FROM app_settings WHERE chave = ?1 LIMIT 1",
            [LEGACY_CREDENTIAL_REPAIR_KEY],
            |row| row.get(0),
        )
        .optional()
        .map_err(|err| format!("Falha ao consultar reparo de credencial legada: {err}"))?;
    if repair_status.as_deref() == Some("completed") {
        return Ok(None);
    }

    let rotation_status: Option<String> = target
        .query_row(
            "SELECT valor FROM app_settings WHERE chave = ?1 LIMIT 1",
            [LEGACY_ROTATION_KEY],
            |row| row.get(0),
        )
        .optional()
        .map_err(|err| format!("Falha ao consultar rotação de credencial legada: {err}"))?;
    if rotation_status.as_deref() != Some("completed") {
        return Ok(None);
    }

    let current_source_checksum = sha256_file(&source_path)?;
    if current_source_checksum != marker.source_checksum_sha256 {
        return Err(format!(
            "O banco legado mudou depois da migração; o hash anterior não será restaurado automaticamente: {}",
            source_path.display()
        ));
    }

    let target_admin: Option<(i64, String, i64, Option<String>)> = target
        .query_row(
            "SELECT id, senha_hash, senha_provisoria, ultimo_login_em
               FROM usuarios
              WHERE LOWER(login) = 'admin'
              LIMIT 1",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
        )
        .optional()
        .map_err(|err| format!("Falha ao consultar administrador migrado: {err}"))?;
    let Some((target_user_id, target_hash, temporary_password, last_login)) = target_admin else {
        return Ok(None);
    };
    if temporary_password != 1
        || last_login
            .as_deref()
            .is_some_and(|value| !value.trim().is_empty())
    {
        return Ok(None);
    }

    let source = Connection::open_with_flags(&source_path, OpenFlags::SQLITE_OPEN_READ_ONLY)
        .map_err(|err| format!("Falha ao abrir banco legado para preservar credencial: {err}"))?;
    if !table_exists(&source, "usuarios")? {
        return Ok(None);
    }
    let has_temporary_password = table_has_column(&source, "usuarios", "senha_provisoria")?;
    let source_sql = if has_temporary_password {
        "SELECT senha_hash, senha_provisoria FROM usuarios WHERE LOWER(login) = 'admin' LIMIT 1"
    } else {
        "SELECT senha_hash, 0 FROM usuarios WHERE LOWER(login) = 'admin' LIMIT 1"
    };
    let source_admin: Option<(String, i64)> = source
        .query_row(source_sql, [], |row| Ok((row.get(0)?, row.get(1)?)))
        .optional()
        .map_err(|err| format!("Falha ao consultar credencial no banco legado: {err}"))?;
    let Some((source_password_hash, source_temporary_password)) = source_admin else {
        return Ok(None);
    };
    if source_password_hash.trim().is_empty() || source_password_hash == target_hash {
        return Ok(None);
    }

    Ok(Some(LegacyCredentialRepair {
        target_user_id,
        source_password_hash,
        source_temporary_password,
    }))
}

fn read_migration_marker(data_dir: &Path) -> Result<Option<MigrationMarker>, String> {
    let path = data_dir.join(MIGRATION_MARKER);
    if !path.is_file() {
        return Ok(None);
    }
    let raw = fs::read(&path).map_err(|err| {
        format!(
            "Falha ao ler marcador de migração {}: {err}",
            path.display()
        )
    })?;
    serde_json::from_slice::<MigrationMarker>(&raw)
        .map(Some)
        .map_err(|err| {
            format!(
                "Falha ao interpretar marcador de migração {}: {err}",
                path.display()
            )
        })
}

fn table_has_column(conn: &Connection, table: &str, column: &str) -> Result<bool, String> {
    let pragma = format!("PRAGMA table_info({table})");
    let mut stmt = conn
        .prepare(&pragma)
        .map_err(|err| format!("Falha ao inspecionar colunas de {table}: {err}"))?;
    let columns = stmt
        .query_map([], |row| row.get::<_, String>(1))
        .map_err(|err| format!("Falha ao consultar colunas de {table}: {err}"))?;
    for item in columns {
        if item.map_err(|err| format!("Falha ao mapear coluna de {table}: {err}"))? == column {
            return Ok(true);
        }
    }
    Ok(false)
}

fn target_is_unused_bootstrap(target_db: &Path) -> Result<bool, String> {
    let target = Connection::open_with_flags(target_db, OpenFlags::SQLITE_OPEN_READ_ONLY)
        .map_err(|err| format!("Falha ao inspecionar banco atual antes da migração: {err}"))?;
    if !table_exists(&target, "usuarios")? {
        return Ok(false);
    }
    if !table_exists(&target, "app_settings")?
        || !table_has_column(&target, "usuarios", "senha_provisoria")?
        || !table_has_column(&target, "usuarios", "ultimo_login_em")?
    {
        return Ok(false);
    }

    let bootstrap_status: Option<String> = target
        .query_row(
            "SELECT valor FROM app_settings WHERE chave = 'bootstrap_seed_status' LIMIT 1",
            [],
            |row| row.get(0),
        )
        .optional()
        .map_err(|err| format!("Falha ao verificar bootstrap do banco atual: {err}"))?;
    if !matches!(bootstrap_status.as_deref(), Some("applied" | "ok")) {
        return Ok(false);
    }

    let users: i64 = target
        .query_row("SELECT COUNT(*) FROM usuarios", [], |row| row.get(0))
        .map_err(|err| format!("Falha ao contar usuários do banco atual: {err}"))?;
    let untouched_admin: i64 = target
        .query_row(
            "SELECT COUNT(*)
               FROM usuarios
              WHERE LOWER(login) = 'admin'
                AND senha_provisoria = 1
                AND (ultimo_login_em IS NULL OR TRIM(ultimo_login_em) = '')",
            [],
            |row| row.get(0),
        )
        .map_err(|err| format!("Falha ao validar administrador bootstrap: {err}"))?;
    if users != 1 || untouched_admin != 1 {
        return Ok(false);
    }

    if !has_only_expected_demo_row(&target, "empresas", "nome", "Empresa Demonstração")?
        || !has_only_expected_demo_row(&target, "departamentos", "descricao", "Administrativo")?
        || !has_only_expected_demo_row(&target, "funcoes", "descricao", "Administrador")?
        || !has_only_expected_demo_row(&target, "centro_custos", "descricao", "Administrativo")?
    {
        return Ok(false);
    }

    for table in [
        "user_sessions",
        "clientes",
        "fornecedores",
        "produtos",
        "sync_queue",
        "audit_logs",
        "integration_configs",
        "integration_logs",
        "api_tokens",
    ] {
        if table_exists(&target, table)? && table_count(&target, table)? > 0 {
            return Ok(false);
        }
    }

    Ok(true)
}

fn has_only_expected_demo_row(
    conn: &Connection,
    table: &str,
    field: &str,
    expected: &str,
) -> Result<bool, String> {
    if !table_exists(conn, table)? {
        return Ok(false);
    }
    let total = table_count(conn, table)?;
    let sql = format!("SELECT COUNT(*) FROM {table} WHERE {field} = ?1");
    let expected_count: i64 = conn
        .query_row(&sql, [expected], |row| row.get(0))
        .map_err(|err| format!("Falha ao validar seed em {table}: {err}"))?;
    Ok(total == 1 && expected_count == 1)
}

fn table_count(conn: &Connection, table: &str) -> Result<i64, String> {
    let sql = format!("SELECT COUNT(*) FROM {table}");
    conn.query_row(&sql, [], |row| row.get(0))
        .map_err(|err| format!("Falha ao contar registros de {table}: {err}"))
}

fn replace_unused_target_with_legacy(
    data_dir: &Path,
    target_db: &Path,
    legacy_db: &Path,
) -> Result<DatabaseRecovery, String> {
    validate_integrity(legacy_db)?;
    let target_recovery = backup_database(data_dir, target_db, true, false)?;
    let source_recovery = backup_database(data_dir, legacy_db, false, true)?;
    let temporary = target_db.with_extension("db.migrating");
    if temporary.exists() {
        fs::remove_file(&temporary)
            .map_err(|err| format!("Falha ao limpar cópia temporária anterior: {err}"))?;
    }
    copy_synced(legacy_db, &temporary)?;
    validate_integrity(&temporary)?;
    validate_critical_counts(legacy_db, &temporary)?;

    let displaced = target_db.with_extension("db.bootstrap-unused");
    if displaced.exists() {
        fs::remove_file(&displaced)
            .map_err(|err| format!("Falha ao limpar banco bootstrap temporário: {err}"))?;
    }
    fs::rename(target_db, &displaced)
        .map_err(|err| format!("Falha ao preservar banco bootstrap antes da migração: {err}"))?;
    if let Err(error) = fs::rename(&temporary, target_db) {
        let restore_error = fs::rename(&displaced, target_db).err();
        return Err(match restore_error {
            Some(restore_error) => format!(
                "Falha ao ativar banco legado: {error}. A restauração do bootstrap também falhou: {restore_error}"
            ),
            None => format!(
                "Falha ao ativar banco legado: {error}. O banco bootstrap anterior foi restaurado."
            ),
        });
    }
    if let Err(error) = fs::remove_file(&displaced) {
        eprintln!(
            "Aviso: o banco bootstrap substituído permaneceu em {}: {error}",
            displaced.display()
        );
    }

    Ok(DatabaseRecovery {
        backup_path: target_recovery.backup_path,
        source_backup_path: source_recovery.source_backup_path,
        target_existed: true,
        copied_from_legacy: true,
        source_path: legacy_db.to_path_buf(),
        source_checksum: source_recovery.source_checksum,
    })
}

fn backup_database(
    data_dir: &Path,
    source: &Path,
    target_existed: bool,
    copied_from_legacy: bool,
) -> Result<DatabaseRecovery, String> {
    let checksum = sha256_file(source)?;
    let backups = data_dir.join("backups");
    fs::create_dir_all(&backups)
        .map_err(|err| format!("Falha ao criar diretório de backups: {err}"))?;
    let stamp = Utc::now().format("%Y%m%dT%H%M%S%fZ");
    let backup_path = backups.join(format!(
        "pige360-deployer-{}-{}-{}.db",
        env!("CARGO_PKG_VERSION"),
        stamp,
        &checksum[..16]
    ));
    copy_synced(source, &backup_path)?;
    validate_integrity(&backup_path)?;
    Ok(DatabaseRecovery {
        source_backup_path: backup_path.clone(),
        backup_path,
        target_existed,
        copied_from_legacy,
        source_path: source.to_path_buf(),
        source_checksum: checksum,
    })
}

pub(crate) fn copy_synced(source: &Path, destination: &Path) -> Result<(), String> {
    let mut wal_name = source.as_os_str().to_os_string();
    wal_name.push("-wal");
    let wal_path = PathBuf::from(wal_name);
    if wal_path.is_file()
        && fs::metadata(&wal_path)
            .map_err(|err| format!("Falha ao inspecionar WAL legado: {err}"))?
            .len()
            > 0
    {
        return Err(format!(
            "O banco {} possui WAL pendente em {}. Encerre a aplicação antiga e execute um checkpoint SQLite antes da migração para evitar perda de dados.",
            source.display(),
            wal_path.display()
        ));
    }
    let mut input = File::open(source)
        .map_err(|err| format!("Falha ao abrir banco de origem {}: {err}", source.display()))?;
    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut output = options.open(destination).map_err(|err| {
        format!(
            "Falha ao criar cópia do banco em {} (verifique espaço e permissões): {err}",
            destination.display()
        )
    })?;
    std::io::copy(&mut input, &mut output)
        .map_err(|err| format!("Falha durante cópia segura do banco: {err}"))?;
    output
        .sync_all()
        .map_err(|err| format!("Falha ao sincronizar cópia do banco: {err}"))?;
    Ok(())
}

fn validate_integrity(path: &Path) -> Result<(), String> {
    let flags = OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NO_MUTEX;
    let conn = Connection::open_with_flags(path, flags).map_err(|err| {
        format!(
            "Falha ao abrir SQLite para validação {}: {err}",
            path.display()
        )
    })?;
    let result: String = conn
        .query_row("PRAGMA integrity_check", [], |row| row.get(0))
        .map_err(|err| {
            format!(
                "Falha ao executar integrity_check em {}: {err}",
                path.display()
            )
        })?;
    if result.eq_ignore_ascii_case("ok") {
        Ok(())
    } else {
        Err(format!(
            "Banco SQLite inválido em {}: {result}",
            path.display()
        ))
    }
}

fn validate_critical_counts(source: &Path, target: &Path) -> Result<(), String> {
    let source_conn = Connection::open_with_flags(source, OpenFlags::SQLITE_OPEN_READ_ONLY)
        .map_err(|err| format!("Falha ao abrir banco legado para contagem: {err}"))?;
    let target_conn = Connection::open_with_flags(target, OpenFlags::SQLITE_OPEN_READ_ONLY)
        .map_err(|err| format!("Falha ao abrir cópia para contagem: {err}"))?;
    for table in storage_contract::CRITICAL_MIGRATION_TABLES {
        if !table_exists(&source_conn, table)? {
            continue;
        }
        let sql = format!("SELECT COUNT(*) FROM {table}");
        let source_count: i64 = source_conn
            .query_row(&sql, [], |row| row.get(0))
            .map_err(|err| format!("Falha ao contar {table} na origem: {err}"))?;
        let target_count: i64 = target_conn
            .query_row(&sql, [], |row| row.get(0))
            .map_err(|err| format!("Falha ao contar {table} na cópia: {err}"))?;
        if source_count != target_count {
            return Err(format!(
                "Contagem divergente na cópia de {table}: origem={source_count}, destino={target_count}"
            ));
        }
    }
    Ok(())
}

fn table_exists(conn: &Connection, table: &str) -> Result<bool, String> {
    conn.query_row(
        "SELECT EXISTS(SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?1)",
        [table],
        |row| row.get::<_, i64>(0),
    )
    .map(|value| value == 1)
    .map_err(|err| format!("Falha ao inspecionar tabela {table}: {err}"))
}

fn sha256_file(path: &Path) -> Result<String, String> {
    let mut file =
        File::open(path).map_err(|err| format!("Falha ao abrir arquivo para checksum: {err}"))?;
    let mut hasher = Sha256::new();
    let mut buffer = [0_u8; 64 * 1024];
    loop {
        let count = file
            .read(&mut buffer)
            .map_err(|err| format!("Falha ao calcular checksum: {err}"))?;
        if count == 0 {
            break;
        }
        hasher.update(&buffer[..count]);
    }
    Ok(format!("{:x}", hasher.finalize()))
}

fn write_private_file(path: &Path, payload: &[u8]) -> Result<(), String> {
    let mut options = OpenOptions::new();
    options.write(true).create(true).truncate(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options
        .open(path)
        .map_err(|err| format!("Falha ao gravar marcador {}: {err}", path.display()))?;
    file.write_all(payload)
        .and_then(|_| file.sync_all())
        .map_err(|err| format!("Falha ao sincronizar marcador {}: {err}", path.display()))
}
