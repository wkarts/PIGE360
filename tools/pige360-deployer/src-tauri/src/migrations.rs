use chrono::Utc;
use rusqlite::{params, OptionalExtension};
use std::path::Path;

use crate::{bootstrap, db::open_connection, security::hash_password};

const BOOTSTRAP_SEED_KEY: &str = "bootstrap_seed_version";
const BOOTSTRAP_SEED_STATUS_KEY: &str = "bootstrap_seed_status";
const BOOTSTRAP_SEED_VERSION: i64 = 1;

pub fn migrate(db_path: &Path) -> Result<(), String> {
    let conn = open_connection(db_path)?;

    conn.execute_batch(
        r#"
        CREATE TABLE IF NOT EXISTS empresas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            nome_fantasia TEXT,
            documento TEXT,
            inscricao_estadual TEXT,
            inscricao_municipal TEXT,
            telefone TEXT,
            email TEXT,
            responsavel_nome TEXT,
            responsavel_telefone TEXT,
            cep TEXT,
            endereco TEXT,
            numero TEXT,
            complemento TEXT,
            bairro TEXT,
            cidade TEXT,
            estado TEXT,
            observacoes TEXT,
            ativo INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            login TEXT NOT NULL UNIQUE,
            email TEXT,
            telefone TEXT,
            cargo TEXT,
            observacoes TEXT,
            photo_url TEXT,
            senha_hash TEXT NOT NULL,
            master_user INTEGER NOT NULL DEFAULT 0,
            administrador INTEGER NOT NULL DEFAULT 0,
            senha_provisoria INTEGER NOT NULL DEFAULT 0,
            ultimo_login_em TEXT,
            ativo INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS perfis_acesso (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE,
            descricao TEXT,
            perfil_master INTEGER NOT NULL DEFAULT 0,
            ativo INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS perfis_permissoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            perfil_id INTEGER NOT NULL,
            permissao_chave TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (perfil_id) REFERENCES perfis_acesso(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS usuarios_perfis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            perfil_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
            FOREIGN KEY (perfil_id) REFERENCES perfis_acesso(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS usuarios_empresas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            empresa_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
            FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS user_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            session_token TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            last_activity_at TEXT NOT NULL,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS departamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            descricao TEXT NOT NULL,
            ativo INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS funcoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            descricao TEXT NOT NULL,
            ativo INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS centro_custos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT,
            descricao TEXT NOT NULL,
            ativo INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            documento TEXT,
            telefone TEXT,
            email TEXT,
            endereco TEXT,
            cidade TEXT,
            estado TEXT,
            observacoes TEXT,
            ativo INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS fornecedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            documento TEXT,
            telefone TEXT,
            email TEXT,
            endereco TEXT,
            cidade TEXT,
            estado TEXT,
            observacoes TEXT,
            ativo INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT,
            descricao TEXT NOT NULL,
            tipo TEXT,
            unidade TEXT,
            valor REAL NOT NULL DEFAULT 0,
            ativo INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_name TEXT NOT NULL,
            action_name TEXT NOT NULL,
            record_id INTEGER,
            payload_json TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sync_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_name TEXT NOT NULL,
            action_name TEXT NOT NULL,
            record_id INTEGER,
            payload_json TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS app_settings (
            chave TEXT PRIMARY KEY,
            valor TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS app_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            level TEXT NOT NULL,
            category TEXT NOT NULL,
            message TEXT NOT NULL,
            source TEXT,
            route TEXT,
            details_json TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS admin_guard (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            support_secret_hash TEXT,
            totp_secret_encrypted TEXT,
            totp_enabled INTEGER NOT NULL DEFAULT 0,
            recovery_codes_encrypted TEXT,
            licensing_protected INTEGER NOT NULL DEFAULT 1,
            white_label_protected INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_rotated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS admin_unlock_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            scope TEXT NOT NULL,
            unlock_token TEXT NOT NULL UNIQUE,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_used_at TEXT,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS local_licenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER NOT NULL,
            cnpj TEXT NOT NULL,
            license_kind TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            issued_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            fingerprint TEXT,
            payload_encrypted TEXT,
            integrity_hash TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (empresa_id) REFERENCES empresas(id)
        );

        CREATE TABLE IF NOT EXISTS feature_flags (
            chave TEXT PRIMARY KEY,
            ativo INTEGER NOT NULL DEFAULT 1,
            descricao TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS integration_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            tipo TEXT NOT NULL DEFAULT 'rest',
            base_url TEXT NOT NULL,
            metodo_padrao TEXT NOT NULL DEFAULT 'GET',
            headers_json TEXT,
            token_encrypted TEXT,
            ambiente TEXT NOT NULL DEFAULT 'production',
            status TEXT NOT NULL DEFAULT 'inactive',
            timeout_seconds INTEGER NOT NULL DEFAULT 30,
            retry_attempts INTEGER NOT NULL DEFAULT 0,
            ultimo_erro TEXT,
            ultima_execucao_em TEXT,
            ativo INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS integration_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            integration_id INTEGER,
            method TEXT,
            url TEXT,
            request_headers_json TEXT,
            status_code INTEGER,
            success INTEGER NOT NULL DEFAULT 0,
            duration_ms INTEGER,
            error_message TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (integration_id) REFERENCES integration_configs(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS api_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            token_hash TEXT NOT NULL,
            escopo TEXT,
            ativo INTEGER NOT NULL DEFAULT 1,
            expires_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS configuracoes (
            nome TEXT PRIMARY KEY,
            valor TEXT,
            updated_at TEXT NOT NULL
        );
        "#,
    )
    .map_err(|err| format!("Falha ao executar migrations: {err}"))?;

    migrate_existing_schema(&conn)?;
    ensure_optional_columns(&conn)?;
    ensure_indexes(&conn)?;
    seed_data(&conn, db_path)
}

fn migrate_existing_schema(conn: &rusqlite::Connection) -> Result<(), String> {
    for (table, column, definition) in [
        ("empresas", "nome_fantasia", "TEXT"),
        ("empresas", "inscricao_estadual", "TEXT"),
        ("empresas", "inscricao_municipal", "TEXT"),
        ("empresas", "responsavel_nome", "TEXT"),
        ("empresas", "responsavel_telefone", "TEXT"),
        ("empresas", "cep", "TEXT"),
        ("empresas", "numero", "TEXT"),
        ("empresas", "complemento", "TEXT"),
        ("empresas", "observacoes", "TEXT"),
        ("usuarios", "email", "TEXT"),
        ("usuarios", "telefone", "TEXT"),
        ("usuarios", "cargo", "TEXT"),
        ("usuarios", "observacoes", "TEXT"),
        ("usuarios", "photo_url", "TEXT"),
        ("usuarios", "master_user", "INTEGER NOT NULL DEFAULT 0"),
        ("usuarios", "senha_provisoria", "INTEGER NOT NULL DEFAULT 0"),
        ("usuarios", "ultimo_login_em", "TEXT"),
    ] {
        add_column_if_missing(conn, table, column, definition)?;
    }

    conn.execute_batch(
        r#"
        UPDATE empresas
           SET documento = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(documento, ''), '.', ''), '-', ''), '/', ''), '(', ''), ')', ''), ' ', '');
        UPDATE empresas
           SET telefone = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(telefone, ''), '(', ''), ')', ''), '-', ''), ' ', ''), '.', '');
        UPDATE empresas
           SET responsavel_telefone = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(responsavel_telefone, ''), '(', ''), ')', ''), '-', ''), ' ', ''), '.', '');
        UPDATE empresas
           SET cep = REPLACE(REPLACE(REPLACE(COALESCE(cep, ''), '.', ''), '-', ''), ' ', '');
        UPDATE usuarios
           SET login = LOWER(TRIM(COALESCE(login, '')));
        UPDATE usuarios
           SET telefone = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(telefone, ''), '(', ''), ')', ''), '-', ''), ' ', ''), '.', '');
        "#,
    )
    .map_err(|err| format!("Falha ao normalizar dados existentes: {err}"))?;

    Ok(())
}

fn add_column_if_missing(
    conn: &rusqlite::Connection,
    table: &str,
    column: &str,
    definition: &str,
) -> Result<(), String> {
    let pragma = format!("PRAGMA table_info({table})");
    let mut stmt = conn
        .prepare(&pragma)
        .map_err(|err| format!("Falha ao inspecionar tabela {table}: {err}"))?;

    let columns = stmt
        .query_map([], |row| row.get::<_, String>(1))
        .map_err(|err| format!("Falha ao ler colunas de {table}: {err}"))?;

    let mut exists = false;
    for item in columns {
        if item.map_err(|err| format!("Falha ao mapear coluna de {table}: {err}"))? == column {
            exists = true;
            break;
        }
    }

    if !exists {
        let sql = format!("ALTER TABLE {table} ADD COLUMN {column} {definition}");
        conn.execute(&sql, [])
            .map_err(|err| format!("Falha ao adicionar coluna {column} em {table}: {err}"))?;
    }

    Ok(())
}

fn ensure_indexes(conn: &rusqlite::Connection) -> Result<(), String> {
    conn.execute_batch(
        r#"
        CREATE INDEX IF NOT EXISTS idx_empresas_nome ON empresas(nome);
        CREATE INDEX IF NOT EXISTS idx_empresas_documento ON empresas(documento);
        CREATE INDEX IF NOT EXISTS idx_usuarios_login ON usuarios(login);
        CREATE INDEX IF NOT EXISTS idx_usuarios_master ON usuarios(master_user, ativo);
        CREATE UNIQUE INDEX IF NOT EXISTS ux_perfis_nome ON perfis_acesso(nome);
        CREATE UNIQUE INDEX IF NOT EXISTS ux_perfis_permissao ON perfis_permissoes(perfil_id, permissao_chave);
        CREATE UNIQUE INDEX IF NOT EXISTS ux_usuarios_perfis ON usuarios_perfis(usuario_id, perfil_id);
        CREATE UNIQUE INDEX IF NOT EXISTS ux_usuarios_empresas ON usuarios_empresas(usuario_id, empresa_id);
        CREATE UNIQUE INDEX IF NOT EXISTS ux_user_sessions_token ON user_sessions(session_token);
        CREATE UNIQUE INDEX IF NOT EXISTS ux_local_licenses_empresa ON local_licenses(empresa_id);
        CREATE INDEX IF NOT EXISTS idx_app_logs_created_at ON app_logs(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_app_logs_category ON app_logs(category);
        CREATE INDEX IF NOT EXISTS idx_admin_unlock_sessions_usuario ON admin_unlock_sessions(usuario_id);
        CREATE INDEX IF NOT EXISTS idx_admin_unlock_sessions_token ON admin_unlock_sessions(unlock_token);
        CREATE INDEX IF NOT EXISTS idx_local_licenses_cnpj ON local_licenses(cnpj);
        CREATE INDEX IF NOT EXISTS idx_app_settings_chave ON app_settings(chave);
        CREATE INDEX IF NOT EXISTS idx_clientes_nome ON clientes(nome);
        CREATE INDEX IF NOT EXISTS idx_fornecedores_nome ON fornecedores(nome);
        CREATE INDEX IF NOT EXISTS idx_produtos_descricao ON produtos(descricao);
        CREATE INDEX IF NOT EXISTS idx_sync_queue_status ON sync_queue(status);
        "#,
    )
    .map_err(|err| format!("Falha ao criar índices: {err}"))?;
    Ok(())
}

fn seed_data(conn: &rusqlite::Connection, db_path: &Path) -> Result<(), String> {
    let now = Utc::now().to_rfc3339();

    ensure_company_seed(conn, &now)?;
    ensure_access_seed(conn, db_path, &now)?;
    ensure_simple_seed(conn, "departamentos", "descricao", "Administrativo", &now)?;
    ensure_simple_seed(conn, "funcoes", "descricao", "Administrador", &now)?;
    ensure_center_cost_seed(conn, &now)?;
    ensure_app_settings(conn, &now)?;

    Ok(())
}

fn ensure_company_seed(conn: &rusqlite::Connection, now: &str) -> Result<(), String> {
    let exists: Option<i64> = conn
        .query_row("SELECT id FROM empresas LIMIT 1", [], |row| row.get(0))
        .optional()
        .map_err(|err| format!("Falha ao verificar empresa inicial: {err}"))?;

    if exists.is_none() {
        conn.execute(
            "INSERT INTO empresas (nome, nome_fantasia, documento, email, telefone, cidade, estado, ativo, created_at, updated_at)
             VALUES ('Empresa Demonstração', 'Empresa Demo', '00000000000000', 'contato@empresa.local', '0000000000', 'Cidade', 'UF', 1, ?1, ?1)",
            params![now],
        )
        .map_err(|err| format!("Falha ao criar empresa inicial: {err}"))?;
    }

    Ok(())
}

fn ensure_access_seed(
    conn: &rusqlite::Connection,
    db_path: &Path,
    now: &str,
) -> Result<(), String> {
    let admin_id: i64 = match conn
        .query_row(
            "SELECT id FROM usuarios WHERE login = 'admin' LIMIT 1",
            [],
            |row| row.get(0),
        )
        .optional()
        .map_err(|err| format!("Falha ao verificar usuário admin: {err}"))?
    {
        Some(id) => id,
        None => {
            let credential = bootstrap::load_or_create(db_path)?;
            let password_hash = hash_password(&credential.password)?;
            conn.execute(
                "INSERT INTO usuarios (nome, login, email, senha_hash, master_user, administrador, senha_provisoria, ativo, created_at, updated_at)
                 VALUES ('Administrador', ?1, 'admin@local', ?2, 1, 1, 1, 1, ?3, ?3)",
                params![credential.username, password_hash, now],
            )
            .map_err(|err| format!("Falha ao criar usuário admin: {err}"))?;
            conn.last_insert_rowid()
        }
    };

    conn.execute(
        "UPDATE usuarios SET master_user = 1, administrador = 1, ativo = 1, updated_at = ?1 WHERE id = ?2",
        params![now, admin_id],
    )
    .map_err(|err| format!("Falha ao atualizar usuário admin: {err}"))?;

    let perfil_master_id: i64 = match conn
        .query_row(
            "SELECT id FROM perfis_acesso WHERE nome = 'Master' LIMIT 1",
            [],
            |row| row.get(0),
        )
        .optional()
        .map_err(|err| format!("Falha ao verificar perfil master: {err}"))?
    {
        Some(id) => id,
        None => {
            conn.execute(
                "INSERT INTO perfis_acesso (nome, descricao, perfil_master, ativo, created_at, updated_at)
                 VALUES ('Master', 'Perfil com acesso total ao sistema.', 1, 1, ?1, ?1)",
                params![now],
            )
            .map_err(|err| format!("Falha ao criar perfil master: {err}"))?;
            conn.last_insert_rowid()
        }
    };

    conn.execute(
        "UPDATE perfis_acesso SET descricao = ?1, perfil_master = 1, ativo = 1, updated_at = ?2 WHERE id = ?3",
        params!["Perfil com acesso total ao sistema.", now, perfil_master_id],
    )
    .map_err(|err| format!("Falha ao atualizar perfil master: {err}"))?;

    conn.execute(
        "DELETE FROM perfis_permissoes WHERE perfil_id = ?1",
        [perfil_master_id],
    )
    .map_err(|err| format!("Falha ao limpar permissões do perfil master: {err}"))?;

    for key in access_permission_keys() {
        conn.execute(
            "INSERT OR IGNORE INTO perfis_permissoes (perfil_id, permissao_chave, created_at) VALUES (?1, ?2, ?3)",
            params![perfil_master_id, key, now],
        )
        .map_err(|err| format!("Falha ao gravar permissão do perfil master: {err}"))?;
    }

    conn.execute(
        "INSERT OR IGNORE INTO usuarios_perfis (usuario_id, perfil_id, created_at) VALUES (?1, ?2, ?3)",
        params![admin_id, perfil_master_id, now],
    )
    .map_err(|err| format!("Falha ao vincular perfil master ao admin: {err}"))?;

    let mut stmt = conn
        .prepare("SELECT id FROM empresas ORDER BY id ASC")
        .map_err(|err| format!("Falha ao preparar vínculo de empresas do admin: {err}"))?;
    let empresa_ids = stmt
        .query_map([], |row| row.get::<_, i64>(0))
        .map_err(|err| format!("Falha ao consultar empresas para o admin: {err}"))?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|err| format!("Falha ao mapear empresas do admin: {err}"))?;

    for empresa_id in empresa_ids {
        conn.execute(
            "INSERT OR IGNORE INTO usuarios_empresas (usuario_id, empresa_id, created_at) VALUES (?1, ?2, ?3)",
            params![admin_id, empresa_id, now],
        )
        .map_err(|err| format!("Falha ao vincular empresa ao usuário admin: {err}"))?;
    }

    Ok(())
}

fn access_permission_keys() -> Vec<&'static str> {
    vec![
        "dashboard:view",
        "empresas:view",
        "empresas:manage",
        "cadastros:view",
        "cadastros:manage",
        "usuarios:view",
        "usuarios:manage",
        "perfis:view",
        "perfis:manage",
        "config:view",
        "config:manage",
        "licenciamento:view",
        "licenciamento:manage",
        "logs:view",
        "logs:manage",
        "sync:view",
        "relatorios:export",
    ]
}

fn ensure_simple_seed(
    conn: &rusqlite::Connection,
    table: &str,
    field: &str,
    value: &str,
    now: &str,
) -> Result<(), String> {
    let sql_check = format!("SELECT id FROM {} WHERE {} = ?1 LIMIT 1", table, field);
    let exists: Option<i64> = conn
        .query_row(&sql_check, params![value], |row| row.get(0))
        .optional()
        .map_err(|err| format!("Falha ao verificar seed de {table}: {err}"))?;

    if exists.is_none() {
        let sql_insert = format!(
            "INSERT INTO {} ({}, ativo, created_at, updated_at) VALUES (?1, 1, ?2, ?2)",
            table, field
        );
        conn.execute(&sql_insert, params![value, now])
            .map_err(|err| format!("Falha ao inserir seed em {table}: {err}"))?;
    }

    Ok(())
}

fn ensure_center_cost_seed(conn: &rusqlite::Connection, now: &str) -> Result<(), String> {
    let exists: Option<i64> = conn
        .query_row(
            "SELECT id FROM centro_custos WHERE codigo = 'ADM' LIMIT 1",
            [],
            |row| row.get(0),
        )
        .optional()
        .map_err(|err| format!("Falha ao verificar centro de custo inicial: {err}"))?;
    if exists.is_none() {
        conn.execute(
            "INSERT INTO centro_custos (codigo, descricao, ativo, created_at, updated_at) VALUES ('ADM', 'Administrativo', 1, ?1, ?1)",
            params![now],
        )
        .map_err(|err| format!("Falha ao inserir centro de custo inicial: {err}"))?;
    }
    Ok(())
}

fn ensure_app_settings(conn: &rusqlite::Connection, now: &str) -> Result<(), String> {
    let settings = [
        (BOOTSTRAP_SEED_KEY, BOOTSTRAP_SEED_VERSION.to_string()),
        (BOOTSTRAP_SEED_STATUS_KEY, "applied".to_string()),
        (
            "app_template_version",
            env!("CARGO_PKG_VERSION").to_string(),
        ),
        ("runtime_license_mode", "local".to_string()),
        ("login_session_days", "7".to_string()),
    ];

    for (key, value) in settings {
        conn.execute(
            "INSERT OR REPLACE INTO app_settings (chave, valor, created_at, updated_at) VALUES (?1, ?2, ?3, ?3)",
            params![key, value, now],
        )
        .map_err(|err| format!("Falha ao gravar configuração {key}: {err}"))?;

        conn.execute(
            "INSERT OR REPLACE INTO configuracoes (nome, valor, updated_at) VALUES (?1, ?2, ?3)",
            params![key, value, now],
        )
        .map_err(|err| format!("Falha ao gravar parâmetro {key}: {err}"))?;
    }

    Ok(())
}

fn ensure_optional_columns(conn: &rusqlite::Connection) -> Result<(), String> {
    let has_photo = conn
        .prepare("PRAGMA table_info(usuarios)")
        .and_then(|mut stmt| {
            let rows = stmt.query_map([], |row| row.get::<_, String>(1))?;
            let mut found = false;
            for row in rows {
                if row? == "photo_url" {
                    found = true;
                    break;
                }
            }
            Ok(found)
        })
        .map_err(|err| format!("Falha ao verificar colunas de usuários: {err}"))?;
    if !has_photo {
        conn.execute("ALTER TABLE usuarios ADD COLUMN photo_url TEXT", [])
            .map_err(|err| format!("Falha ao adicionar coluna photo_url em usuarios: {err}"))?;
    }
    Ok(())
}
