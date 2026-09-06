use rusqlite::{params, Connection};
use sha2::{Digest, Sha256};
use std::{env, fs, io::Read, path::Path};
use tempfile::TempDir;

#[path = "../../../src-tauri/src/bootstrap.rs"]
mod bootstrap;
#[path = "../../../src-tauri/src/db.rs"]
mod db;
#[path = "../../../src-tauri/src/legacy_data.rs"]
mod legacy_data;
#[path = "../../../src-tauri/src/migrations.rs"]
mod migrations;
#[path = "../../../src-tauri/src/storage_contract.rs"]
mod storage_contract;
#[path = "../../../src-tauri/src/app_state.rs"]
mod app_state;

mod security {
    pub fn hash_password(password: &str) -> Result<String, String> {
        if password.is_empty() {
            return Err("Senha de teste vazia.".to_string());
        }
        Ok(format!("$migration-harness${password}"))
    }
}

fn create_legacy_database(path: &Path) -> Result<(), String> {
    let conn = Connection::open(path).map_err(|error| error.to_string())?;
    conn.execute_batch(
        "CREATE TABLE usuarios (id INTEGER PRIMARY KEY, login TEXT NOT NULL, senha_hash TEXT NOT NULL);
         CREATE TABLE empresas (id INTEGER PRIMARY KEY, nome TEXT NOT NULL);
         CREATE TABLE clientes (id INTEGER PRIMARY KEY, nome TEXT NOT NULL);
         INSERT INTO usuarios VALUES (1, 'admin', 'hash-legado');
         INSERT INTO empresas VALUES (1, 'Empresa teste');
         INSERT INTO clientes VALUES (1, 'Cliente teste');",
    )
    .map_err(|error| error.to_string())
}

fn scalar_count(path: &Path, table: &str) -> Result<i64, String> {
    Connection::open(path)
        .and_then(|conn| conn.query_row(&format!("SELECT COUNT(*) FROM {table}"), [], |row| row.get(0)))
        .map_err(|error| error.to_string())
}

fn table_has_column(path: &Path, table: &str, column: &str) -> Result<bool, String> {
    let conn = Connection::open(path).map_err(|error| error.to_string())?;
    let mut statement = conn
        .prepare(&format!("PRAGMA table_info({table})"))
        .map_err(|error| error.to_string())?;
    let columns = statement
        .query_map([], |row| row.get::<_, String>(1))
        .map_err(|error| error.to_string())?;
    for item in columns {
        if item.map_err(|error| error.to_string())? == column {
            return Ok(true);
        }
    }
    Ok(false)
}

fn create_legacy_credential_database(
    path: &Path,
    password_hash: &str,
    temporary_password: i64,
) -> Result<(), String> {
    let conn = Connection::open(path).map_err(|error| error.to_string())?;
    conn.execute_batch(
        "CREATE TABLE usuarios (
            id INTEGER PRIMARY KEY,
            login TEXT NOT NULL,
            senha_hash TEXT NOT NULL,
            senha_provisoria INTEGER NOT NULL DEFAULT 0
         );",
    )
    .map_err(|error| error.to_string())?;
    conn.execute(
        "INSERT INTO usuarios (id, login, senha_hash, senha_provisoria)
         VALUES (1, 'admin', ?1, ?2)",
        params![password_hash, temporary_password],
    )
    .map_err(|error| error.to_string())?;
    Ok(())
}

fn create_affected_target_database(
    path: &Path,
    password_hash: &str,
    last_login: Option<&str>,
) -> Result<(), String> {
    let conn = Connection::open(path).map_err(|error| error.to_string())?;
    conn.execute_batch(
        "CREATE TABLE usuarios (
            id INTEGER PRIMARY KEY,
            login TEXT NOT NULL,
            senha_hash TEXT NOT NULL,
            senha_provisoria INTEGER NOT NULL DEFAULT 0,
            ultimo_login_em TEXT,
            updated_at TEXT NOT NULL
         );
         CREATE TABLE app_settings (
            chave TEXT PRIMARY KEY,
            valor TEXT,
            updated_at TEXT NOT NULL
         );
         INSERT INTO app_settings (chave, valor, updated_at)
         VALUES ('security_bootstrap_credential_rotation_v1', 'completed', '2026-08-01T00:00:00Z');",
    )
    .map_err(|error| error.to_string())?;
    conn.execute(
        "INSERT INTO usuarios (
            id, login, senha_hash, senha_provisoria, ultimo_login_em, updated_at
         ) VALUES (1, 'admin', ?1, 1, ?2, '2026-08-01T00:00:00Z')",
        params![password_hash, last_login],
    )
    .map_err(|error| error.to_string())?;
    Ok(())
}

fn sha256_file(path: &Path) -> Result<String, String> {
    let mut file = fs::File::open(path).map_err(|error| error.to_string())?;
    let mut hasher = Sha256::new();
    let mut buffer = [0_u8; 8192];
    loop {
        let count = file.read(&mut buffer).map_err(|error| error.to_string())?;
        if count == 0 {
            break;
        }
        hasher.update(&buffer[..count]);
    }
    Ok(format!("{:x}", hasher.finalize()))
}

fn write_legacy_migration_marker(
    data_dir: &Path,
    legacy: &Path,
    target: &Path,
) -> Result<(), String> {
    fs::create_dir_all(data_dir).map_err(|error| error.to_string())?;
    let marker = serde_json::json!({
        "schema_version": 1,
        "application_version": "1.5.0",
        "source_path": legacy.to_string_lossy(),
        "source_checksum_sha256": sha256_file(legacy)?,
        "target_path": target.to_string_lossy(),
        "backup_path": data_dir.join("backups/original.db").to_string_lossy(),
        "completed_at": "2026-08-01T00:00:00Z"
    });
    fs::write(
        data_dir.join("legacy-database-migration-v1.json"),
        serde_json::to_vec_pretty(&marker).map_err(|error| error.to_string())?,
    )
    .map_err(|error| error.to_string())?;
    Ok(())
}

fn test_new_install() -> Result<(), String> {
    let temp = TempDir::new().map_err(|error| error.to_string())?;
    let data_dir = temp.path().join(storage_contract::CURRENT_LOCAL_DATA_DIR);
    let target = storage_contract::sqlite_database_path(&data_dir);
    env::set_var("PIGE360_DEPLOYER_LEGACY_DB_PATH", temp.path().join("inexistente.db"));
    let state = app_state::SharedState::new();
    state.init_with_data_dir(data_dir.clone())?;

    if state.db_path()? != target || state.data_dir()? != data_dir || !target.is_file() {
        return Err("Instalação nova não criou o SQLite no caminho canônico.".to_string());
    }
    if !storage_contract::LEGACY_LOCAL_DATA_DIRS.is_empty()
        || !storage_contract::LEGACY_SQLITE_DATABASE_FILE_NAMES.is_empty()
    {
        return Err("Aplicação nova recebeu aliases legados não solicitados.".to_string());
    }
    if scalar_count(&target, "usuarios")? < 1 || scalar_count(&target, "empresas")? < 1 {
        return Err("Seeds iniciais não foram aplicados na instalação nova.".to_string());
    }
    if !table_has_column(&target, "usuarios", "senha_provisoria")?
        || !table_has_column(&target, "usuarios", "ultimo_login_em")?
        || !data_dir
            .join(format!("schema-backup-{}.ok", env!("CARGO_PKG_VERSION")))
            .is_file()
    {
        return Err("Migrations atuais não foram concluídas no SQLite canônico.".to_string());
    }
    Ok(())
}

fn test_upgrade_repeat_and_completed_start() -> Result<(), String> {
    let temp = TempDir::new().map_err(|error| error.to_string())?;
    let legacy = temp.path().join("app-legacy.db");
    let data_dir = temp.path().join("novo");
    let target = storage_contract::sqlite_database_path(&data_dir);
    create_legacy_database(&legacy)?;
    env::set_var("PIGE360_DEPLOYER_LEGACY_DB_PATH", &legacy);

    let recovery = legacy_data::prepare(&data_dir, &target)?
        .ok_or_else(|| "Banco legado não foi detectado.".to_string())?;
    if scalar_count(&target, "clientes")? != 1 || scalar_count(&legacy, "clientes")? != 1 {
        return Err("Contagens críticas divergiram durante a cópia.".to_string());
    }
    legacy_data::finalize(&data_dir, &target, Some(&recovery))?;
    if !data_dir.join("legacy-database-migration-v1.json").is_file() {
        return Err("Marcador idempotente não foi criado.".to_string());
    }
    if legacy_data::prepare(&data_dir, &target)?.is_some() {
        return Err("Execução repetida não deveria migrar novamente.".to_string());
    }
    Ok(())
}

fn test_corrupt_legacy() -> Result<(), String> {
    let temp = TempDir::new().map_err(|error| error.to_string())?;
    let legacy = temp.path().join("app-legacy.db");
    fs::write(&legacy, b"sqlite corrompido").map_err(|error| error.to_string())?;
    env::set_var("PIGE360_DEPLOYER_LEGACY_DB_PATH", &legacy);
    let target = storage_contract::sqlite_database_path(&temp.path().join("novo"));
    if legacy_data::prepare(target.parent().unwrap_or(temp.path()), &target).is_ok() {
        return Err("Banco legado corrompido foi aceito.".to_string());
    }
    if fs::read(&legacy).map_err(|error| error.to_string())? != b"sqlite corrompido" {
        return Err("Banco legado corrompido foi modificado.".to_string());
    }
    Ok(())
}

fn test_copy_failure_preserves_source() -> Result<(), String> {
    let temp = TempDir::new().map_err(|error| error.to_string())?;
    let source = temp.path().join("origem.db");
    create_legacy_database(&source)?;
    let destination = temp.path().join("destino-como-diretorio");
    fs::create_dir(&destination).map_err(|error| error.to_string())?;
    let before = scalar_count(&source, "usuarios")?;
    let error = legacy_data::copy_synced(&source, &destination)
        .expect_err("Destino inválido deveria simular falha de espaço/permissão.");
    if !error.contains("espaço") || scalar_count(&source, "usuarios")? != before {
        return Err("Falha de cópia não preservou origem ou não orientou sobre espaço.".to_string());
    }
    Ok(())
}

fn test_failed_migration_rollback() -> Result<(), String> {
    let temp = TempDir::new().map_err(|error| error.to_string())?;
    let legacy = temp.path().join("app-legacy.db");
    let data_dir = temp.path().join("novo");
    let target = storage_contract::sqlite_database_path(&data_dir);
    create_legacy_database(&legacy)?;
    env::set_var("PIGE360_DEPLOYER_LEGACY_DB_PATH", &legacy);
    let recovery = legacy_data::prepare(&data_dir, &target)?;
    Connection::open(&target)
        .and_then(|conn| conn.execute("DELETE FROM usuarios", params![]))
        .map_err(|error| error.to_string())?;
    legacy_data::rollback(&target, recovery.as_ref())?;
    if target.exists() || scalar_count(&legacy, "usuarios")? != 1 {
        return Err("Rollback da migração inicial não preservou o banco legado.".to_string());
    }
    Ok(())
}

fn test_existing_database_rollback() -> Result<(), String> {
    let temp = TempDir::new().map_err(|error| error.to_string())?;
    let target = storage_contract::sqlite_database_path(temp.path());
    create_legacy_database(&target)?;
    env::set_var("PIGE360_DEPLOYER_LEGACY_DB_PATH", temp.path().join("inexistente.db"));
    let recovery = legacy_data::prepare(temp.path(), &target)?;
    Connection::open(&target)
        .and_then(|conn| conn.execute("DELETE FROM usuarios", params![]))
        .map_err(|error| error.to_string())?;
    legacy_data::rollback(&target, recovery.as_ref())?;
    if scalar_count(&target, "usuarios")? != 1 {
        return Err("Rollback não restaurou banco existente a partir do backup.".to_string());
    }
    Ok(())
}

fn test_bootstrap_credential_lifecycle() -> Result<(), String> {
    let temp = TempDir::new().map_err(|error| error.to_string())?;
    let db_path = storage_contract::sqlite_database_path(temp.path());
    let credential_file = temp.path().join(".bootstrap-admin.local");
    let first = bootstrap::load_or_create(&db_path)?;
    let second = bootstrap::load_or_create(&db_path)?;
    if first.password.len() != 32 || first.password != second.password || !credential_file.is_file() {
        return Err("Credencial bootstrap não é forte ou idempotente.".to_string());
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        if fs::metadata(&credential_file)
            .map_err(|error| error.to_string())?
            .permissions()
            .mode()
            & 0o777
            != 0o600
        {
            return Err("Credencial bootstrap não possui permissão 0600.".to_string());
        }
    }
    bootstrap::remove_after_password_change(&db_path)?;
    if credential_file.exists() {
        return Err("Credencial bootstrap não foi removida após troca de senha.".to_string());
    }
    Ok(())
}

fn test_rotated_legacy_credential_is_restored() -> Result<(), String> {
    let temp = TempDir::new().map_err(|error| error.to_string())?;
    let legacy = temp.path().join("app-legacy.db");
    let data_dir = temp.path().join("novo");
    let target = storage_contract::sqlite_database_path(&data_dir);
    fs::create_dir_all(&data_dir).map_err(|error| error.to_string())?;
    create_legacy_credential_database(&legacy, "hash-legado-preservado", 0)?;
    create_affected_target_database(&target, "hash-bootstrap-rotacionado", None)?;
    write_legacy_migration_marker(&data_dir, &legacy, &target)?;
    fs::write(
        data_dir.join(format!("schema-backup-{}.ok", env!("CARGO_PKG_VERSION"))),
        b"ok\n",
    )
    .map_err(|error| error.to_string())?;

    let recovery = legacy_data::prepare(&data_dir, &target)?
        .ok_or_else(|| "Reparo de credencial deveria forçar backup do destino.".to_string())?;
    if !legacy_data::restore_rotated_legacy_credential(&data_dir, &target)? {
        return Err("Credencial legada afetada não foi restaurada.".to_string());
    }
    legacy_data::finalize(&data_dir, &target, Some(&recovery))?;

    let restored: (String, i64) = Connection::open(&target)
        .and_then(|conn| {
            conn.query_row(
                "SELECT senha_hash, senha_provisoria FROM usuarios WHERE login = 'admin'",
                [],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )
        })
        .map_err(|error| error.to_string())?;
    if restored != ("hash-legado-preservado".to_string(), 0) {
        return Err("Hash ou estado provisório da credencial legada foi alterado.".to_string());
    }
    if legacy_data::restore_rotated_legacy_credential(&data_dir, &target)? {
        return Err("Reparo de credencial não foi idempotente.".to_string());
    }
    let source_hash: String = Connection::open(&legacy)
        .and_then(|conn| {
            conn.query_row(
                "SELECT senha_hash FROM usuarios WHERE login = 'admin'",
                [],
                |row| row.get(0),
            )
        })
        .map_err(|error| error.to_string())?;
    if source_hash != "hash-legado-preservado" {
        return Err("Banco legado original foi modificado durante o reparo.".to_string());
    }
    Ok(())
}

fn test_used_target_credential_is_not_overwritten() -> Result<(), String> {
    let temp = TempDir::new().map_err(|error| error.to_string())?;
    let legacy = temp.path().join("app-legacy.db");
    let data_dir = temp.path().join("novo");
    let target = storage_contract::sqlite_database_path(&data_dir);
    fs::create_dir_all(&data_dir).map_err(|error| error.to_string())?;
    create_legacy_credential_database(&legacy, "hash-legado-antigo", 0)?;
    create_affected_target_database(
        &target,
        "hash-atual-em-uso",
        Some("2026-08-01T12:00:00Z"),
    )?;
    write_legacy_migration_marker(&data_dir, &legacy, &target)?;

    if legacy_data::restore_rotated_legacy_credential(&data_dir, &target)? {
        return Err("Credencial já utilizada não deveria ser sobrescrita.".to_string());
    }
    let target_hash: String = Connection::open(&target)
        .and_then(|conn| {
            conn.query_row(
                "SELECT senha_hash FROM usuarios WHERE login = 'admin'",
                [],
                |row| row.get(0),
            )
        })
        .map_err(|error| error.to_string())?;
    if target_hash != "hash-atual-em-uso" {
        return Err("Credencial atual foi alterada indevidamente.".to_string());
    }
    Ok(())
}

fn create_seeded_database(path: &Path) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    migrations::migrate(path)
}

fn admin_hash(path: &Path) -> Result<String, String> {
    Connection::open(path)
        .and_then(|conn| {
            conn.query_row(
                "SELECT senha_hash FROM usuarios WHERE LOWER(login) = 'admin' LIMIT 1",
                [],
                |row| row.get(0),
            )
        })
        .map_err(|error| error.to_string())
}

fn test_unused_124_bootstrap_is_replaced_by_legacy_database() -> Result<(), String> {
    let temp = TempDir::new().map_err(|error| error.to_string())?;
    let current_dir = temp.path().join(storage_contract::CURRENT_LOCAL_DATA_DIR);
    let current_db = storage_contract::sqlite_database_path(&current_dir);
    let legacy_dir = temp.path().join("pige360_deployer_legacy");
    let legacy_db = legacy_dir.join("app-legacy.db");

    env::set_var(
        "PIGE360_DEPLOYER_LEGACY_DB_PATH",
        temp.path().join("legado-ainda-inexistente.db"),
    );
    let initial_state = app_state::SharedState::new();
    initial_state.init_with_data_dir(current_dir.clone())?;
    if !current_db.is_file() {
        return Err("Bootstrap 1.5.x de teste não foi criado.".to_string());
    }

    create_seeded_database(&legacy_db)?;
    Connection::open(&legacy_db)
        .and_then(|conn| {
            conn.execute(
                "UPDATE usuarios
                    SET senha_hash = 'hash-legado-preservado',
                        senha_provisoria = 0,
                        ultimo_login_em = '2026-07-31T12:00:00Z'
                  WHERE LOWER(login) = 'admin'",
                [],
            )
        })
        .map_err(|error| error.to_string())?;
    env::set_var("PIGE360_DEPLOYER_LEGACY_DB_PATH", &legacy_db);

    let migrated_state = app_state::SharedState::new();
    migrated_state.init_with_data_dir(current_dir.clone())?;
    if admin_hash(&current_db)? != "hash-legado-preservado" {
        return Err("Base bootstrap 1.5.x não foi substituída pelo banco legado.".to_string());
    }
    if admin_hash(&legacy_db)? != "hash-legado-preservado" {
        return Err("Credencial do banco legado original foi modificada.".to_string());
    }
    if !current_dir
        .join("legacy-database-migration-v1.json")
        .is_file()
        || current_dir.join(".bootstrap-admin.local").exists()
    {
        return Err(
            "Migração não registrou conclusão ou manteve bootstrap obsoleto.".to_string(),
        );
    }
    Ok(())
}

fn test_used_124_database_is_never_overwritten() -> Result<(), String> {
    let temp = TempDir::new().map_err(|error| error.to_string())?;
    let current_dir = temp.path().join(storage_contract::CURRENT_LOCAL_DATA_DIR);
    let current_db = storage_contract::sqlite_database_path(&current_dir);
    let legacy_dir = temp.path().join("pige360_deployer_legacy");
    let legacy_db = legacy_dir.join("app-legacy.db");

    env::set_var(
        "PIGE360_DEPLOYER_LEGACY_DB_PATH",
        temp.path().join("legado-ainda-inexistente.db"),
    );
    let initial_state = app_state::SharedState::new();
    initial_state.init_with_data_dir(current_dir.clone())?;
    Connection::open(&current_db)
        .and_then(|conn| {
            conn.execute(
                "UPDATE usuarios
                    SET senha_hash = 'hash-novo-em-uso',
                        senha_provisoria = 0,
                        ultimo_login_em = '2026-08-01T12:00:00Z'
                  WHERE LOWER(login) = 'admin'",
                [],
            )
        })
        .map_err(|error| error.to_string())?;

    create_seeded_database(&legacy_db)?;
    Connection::open(&legacy_db)
        .and_then(|conn| {
            conn.execute(
                "UPDATE usuarios SET senha_hash = 'hash-legado' WHERE LOWER(login) = 'admin'",
                [],
            )
        })
        .map_err(|error| error.to_string())?;
    env::set_var("PIGE360_DEPLOYER_LEGACY_DB_PATH", &legacy_db);

    let retained_state = app_state::SharedState::new();
    retained_state.init_with_data_dir(current_dir.clone())?;
    if admin_hash(&current_db)? != "hash-novo-em-uso"
        || current_dir
            .join("legacy-database-migration-v1.json")
            .exists()
    {
        return Err("Base 1.5.x já utilizada foi sobrescrita pelo legado.".to_string());
    }
    Ok(())
}

fn test_explicit_legacy_database_is_migrated_to_current_contract() -> Result<(), String> {
    let temp = TempDir::new().map_err(|error| error.to_string())?;
    let legacy_dir = temp.path().join("pige360_deployer_legacy");
    let legacy_db = legacy_dir.join("app-legacy.db");
    let current_dir = temp.path().join(storage_contract::CURRENT_LOCAL_DATA_DIR);
    let current_db = storage_contract::sqlite_database_path(&current_dir);
    fs::create_dir_all(&legacy_dir).map_err(|error| error.to_string())?;
    create_legacy_database(&legacy_db)?;

    env::set_var("PIGE360_DEPLOYER_LEGACY_DB_PATH", &legacy_db);
    let recovery = legacy_data::prepare(&current_dir, &current_db)?
        .ok_or_else(|| "Base anterior à 1.5 não foi detectada.".to_string())?;
    legacy_data::finalize(&current_dir, &current_db, Some(&recovery))?;
    if scalar_count(&current_db, "clientes")? != 1 || scalar_count(&legacy_db, "clientes")? != 1
    {
        return Err("Migração explícita não preservou origem e contagens.".to_string());
    }
    Ok(())
}

fn test_bootstrap_is_unique_per_installation() -> Result<(), String> {
    let first = TempDir::new().map_err(|error| error.to_string())?;
    let second = TempDir::new().map_err(|error| error.to_string())?;
    let first_credential = bootstrap::load_or_create(&first.path().join("app.db"))?;
    let second_credential = bootstrap::load_or_create(&second.path().join("app.db"))?;
    if first_credential.password == second_credential.password {
        return Err("Instalações distintas receberam a mesma credencial bootstrap.".to_string());
    }
    Ok(())
}

fn test_bootstrap_ignores_working_directory() -> Result<(), String> {
    let temp = TempDir::new().map_err(|error| error.to_string())?;
    let working = temp.path().join("working");
    let data = temp.path().join("data");
    fs::create_dir_all(&working).map_err(|error| error.to_string())?;
    fs::create_dir_all(&data).map_err(|error| error.to_string())?;
    let foreign = working.join(".bootstrap-admin.local");
    fs::write(
        &foreign,
        "Usuario bootstrap: admin\nSenha bootstrap: AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\n",
    )
    .map_err(|error| error.to_string())?;
    let previous = env::current_dir().map_err(|error| error.to_string())?;
    env::set_current_dir(&working).map_err(|error| error.to_string())?;
    let result = bootstrap::load_or_create(&data.join("app.db"));
    env::set_current_dir(previous).map_err(|error| error.to_string())?;
    let credential = result?;
    if credential.password == "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        || !foreign.is_file()
        || !data.join(".bootstrap-admin.local").is_file()
    {
        return Err("Bootstrap leu ou removeu credencial fora do diretório canônico.".to_string());
    }
    Ok(())
}

fn test_arbitrary_target_is_never_replaced() -> Result<(), String> {
    let temp = TempDir::new().map_err(|error| error.to_string())?;
    let data = temp.path().join("current");
    let target = storage_contract::sqlite_database_path(&data);
    let legacy = temp.path().join("legacy.db");
    fs::create_dir_all(&data).map_err(|error| error.to_string())?;
    Connection::open(&target)
        .and_then(|conn| conn.execute_batch("CREATE TABLE dados_reais (id INTEGER PRIMARY KEY); INSERT INTO dados_reais VALUES (1);"))
        .map_err(|error| error.to_string())?;
    create_legacy_database(&legacy)?;
    env::set_var("PIGE360_DEPLOYER_LEGACY_DB_PATH", &legacy);
    let _ = legacy_data::prepare(&data, &target)?;
    if scalar_count(&target, "dados_reais")? != 1 {
        return Err("Banco canônico arbitrário foi classificado como bootstrap substituível.".to_string());
    }
    Ok(())
}

fn test_changed_legacy_source_blocks_credential_repair() -> Result<(), String> {
    let temp = TempDir::new().map_err(|error| error.to_string())?;
    let legacy = temp.path().join("legacy.db");
    let data = temp.path().join("current");
    let target = storage_contract::sqlite_database_path(&data);
    fs::create_dir_all(&data).map_err(|error| error.to_string())?;
    create_legacy_credential_database(&legacy, "hash-original", 0)?;
    create_affected_target_database(&target, "hash-rotacionado", None)?;
    write_legacy_migration_marker(&data, &legacy, &target)?;
    Connection::open(&legacy)
        .and_then(|conn| conn.execute("UPDATE usuarios SET senha_hash = 'hash-alterado'", []))
        .map_err(|error| error.to_string())?;
    let error = legacy_data::restore_rotated_legacy_credential(&data, &target)
        .expect_err("Origem alterada deveria invalidar o reparo de credencial.");
    if !error.contains("mudou depois da migração") {
        return Err("Checksum divergente não bloqueou o reparo da credencial.".to_string());
    }
    Ok(())
}

fn test_pending_wal_blocks_raw_copy() -> Result<(), String> {
    let temp = TempDir::new().map_err(|error| error.to_string())?;
    let source = temp.path().join("legacy.db");
    let destination = temp.path().join("copy.db");
    create_legacy_database(&source)?;
    fs::write(temp.path().join("legacy.db-wal"), b"pending")
        .map_err(|error| error.to_string())?;
    let error = legacy_data::copy_synced(&source, &destination)
        .expect_err("WAL pendente deveria bloquear cópia de arquivo bruto.");
    if !error.contains("checkpoint SQLite") {
        return Err("WAL pendente não produziu orientação segura.".to_string());
    }
    Ok(())
}

fn main() -> Result<(), String> {
    test_new_install()?;
    test_upgrade_repeat_and_completed_start()?;
    test_corrupt_legacy()?;
    test_copy_failure_preserves_source()?;
    test_failed_migration_rollback()?;
    test_existing_database_rollback()?;
    test_bootstrap_credential_lifecycle()?;
    test_bootstrap_is_unique_per_installation()?;
    test_bootstrap_ignores_working_directory()?;
    test_rotated_legacy_credential_is_restored()?;
    test_used_target_credential_is_not_overwritten()?;
    test_unused_124_bootstrap_is_replaced_by_legacy_database()?;
    test_used_124_database_is_never_overwritten()?;
    test_explicit_legacy_database_is_migrated_to_current_contract()?;
    test_arbitrary_target_is_never_replaced()?;
    test_changed_legacy_source_blocks_credential_repair()?;
    test_pending_wal_blocks_raw_copy()?;
    env::remove_var("PIGE360_DEPLOYER_LEGACY_DB_PATH");
    println!("17 cenários de migração/segurança aprovados.");
    Ok(())
}
