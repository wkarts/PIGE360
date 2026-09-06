use super::{
    config::{DatabaseConfig, DatabaseDriver},
    provider::types::{DbRow, DbValue},
};

#[derive(Debug, Clone)]
pub struct PostgresConnectionInfo {
    pub host: String,
    pub port: u16,
    pub database: String,
    pub username: String,
    pub password_configured: bool,
}

pub fn build_connection_info(config: &DatabaseConfig) -> Result<PostgresConnectionInfo, String> {
    if config.driver != DatabaseDriver::Postgres {
        return Err("Driver informado não é PostgreSQL.".to_string());
    }

    Ok(PostgresConnectionInfo {
        host: config
            .host
            .clone()
            .unwrap_or_else(|| "127.0.0.1".to_string()),
        port: config.port.unwrap_or(5432),
        database: config
            .database
            .clone()
            .ok_or_else(|| "Banco PostgreSQL não informado.".to_string())?,
        username: config
            .username
            .clone()
            .unwrap_or_else(|| "postgres".to_string()),
        password_configured: config
            .password
            .as_ref()
            .is_some_and(|value| !value.is_empty()),
    })
}

fn connection_string(config: &DatabaseConfig) -> Result<String, String> {
    let info = build_connection_info(config)?;
    let mut parts = vec![
        format!("host={}", info.host),
        format!("port={}", info.port),
        format!("dbname={}", info.database),
        format!("user={}", info.username),
    ];
    if let Some(password) = config.password.as_ref().filter(|value| !value.is_empty()) {
        parts.push(format!("password={password}"));
    }
    Ok(parts.join(" "))
}

#[cfg(feature = "postgres-db")]
fn client(config: &DatabaseConfig) -> Result<postgres::Client, String> {
    postgres::Client::connect(&connection_string(config)?, postgres::NoTls)
        .map_err(|err| format!("Falha ao conectar PostgreSQL: {err}"))
}

#[cfg(feature = "postgres-db")]
pub fn health(config: &DatabaseConfig) -> Result<bool, String> {
    let mut client = client(config)?;
    client
        .simple_query("SELECT 1")
        .map_err(|err| format!("Falha no health check PostgreSQL: {err}"))?;
    Ok(true)
}

#[cfg(not(feature = "postgres-db"))]
pub fn health(config: &DatabaseConfig) -> Result<bool, String> {
    let _ = build_connection_info(config)?;
    Err("PostgreSQL configurado, mas a feature Rust 'postgres-db' não está habilitada. Compile com --features postgres-db para conexão real.".to_string())
}

#[cfg(feature = "postgres-db")]
pub fn migrate(config: &DatabaseConfig) -> Result<(), String> {
    let mut client = client(config)?;
    for sql in postgres_schema() {
        client
            .batch_execute(sql)
            .map_err(|err| format!("Falha ao migrar PostgreSQL: {err}; SQL: {sql}"))?;
    }
    Ok(())
}

#[cfg(not(feature = "postgres-db"))]
pub fn migrate(config: &DatabaseConfig) -> Result<(), String> {
    let _ = build_connection_info(config)?;
    Err("Migrations PostgreSQL exigem compilação com --features postgres-db.".to_string())
}

#[cfg(feature = "postgres-db")]
fn postgres_value_to_json(row: &postgres::Row, index: usize) -> serde_json::Value {
    if let Ok(value) = row.try_get::<usize, Option<String>>(index) {
        return value
            .map(serde_json::Value::String)
            .unwrap_or(serde_json::Value::Null);
    }
    if let Ok(value) = row.try_get::<usize, Option<i64>>(index) {
        return value
            .map(serde_json::Value::from)
            .unwrap_or(serde_json::Value::Null);
    }
    if let Ok(value) = row.try_get::<usize, Option<i32>>(index) {
        return value
            .map(serde_json::Value::from)
            .unwrap_or(serde_json::Value::Null);
    }
    if let Ok(value) = row.try_get::<usize, Option<f64>>(index) {
        return value
            .map(serde_json::Value::from)
            .unwrap_or(serde_json::Value::Null);
    }
    if let Ok(value) = row.try_get::<usize, Option<bool>>(index) {
        return value
            .map(serde_json::Value::from)
            .unwrap_or(serde_json::Value::Null);
    }
    serde_json::Value::Null
}

#[cfg(feature = "postgres-db")]
fn postgres_row_to_json(row: postgres::Row) -> DbRow {
    let mut out = DbRow::new();
    for (index, column) in row.columns().iter().enumerate() {
        out.insert(
            column.name().to_string(),
            postgres_value_to_json(&row, index),
        );
    }
    out
}

#[cfg(feature = "postgres-db")]
fn execute_postgres(config: &DatabaseConfig, sql: &str, params: &[DbValue]) -> Result<u64, String> {
    use postgres::types::ToSql;

    let mut client = client(config)?;
    let owned = params.iter().map(to_postgres_value).collect::<Vec<_>>();
    let refs = owned
        .iter()
        .map(|value| value.as_ref() as &(dyn ToSql + Sync))
        .collect::<Vec<_>>();
    client
        .execute(sql, &refs)
        .map_err(|err| format!("Falha ao executar SQL PostgreSQL: {err}"))
}

#[cfg(feature = "postgres-db")]
fn query_postgres(
    config: &DatabaseConfig,
    sql: &str,
    params: &[DbValue],
) -> Result<Vec<DbRow>, String> {
    use postgres::types::ToSql;

    let mut client = client(config)?;
    let owned = params.iter().map(to_postgres_value).collect::<Vec<_>>();
    let refs = owned
        .iter()
        .map(|value| value.as_ref() as &(dyn ToSql + Sync))
        .collect::<Vec<_>>();
    let rows = client
        .query(sql, &refs)
        .map_err(|err| format!("Falha ao consultar PostgreSQL: {err}"))?;
    Ok(rows.into_iter().map(postgres_row_to_json).collect())
}

#[cfg(feature = "postgres-db")]
fn to_postgres_value(value: &DbValue) -> Box<dyn postgres::types::ToSql + Sync> {
    match value {
        DbValue::Null => Box::new(None::<String>),
        DbValue::Bool(value) => Box::new(*value),
        DbValue::Integer(value) => Box::new(*value),
        DbValue::Real(value) => Box::new(*value),
        DbValue::Text(value) => Box::new(value.clone()),
        DbValue::Json(value) => Box::new(value.to_string()),
    }
}

pub fn postgres_schema() -> Vec<&'static str> {
    vec![
        "CREATE TABLE IF NOT EXISTS empresas (id BIGSERIAL PRIMARY KEY, nome VARCHAR(255) NOT NULL, nome_fantasia VARCHAR(255), documento VARCHAR(32), inscricao_estadual VARCHAR(64), inscricao_municipal VARCHAR(64), telefone VARCHAR(64), email VARCHAR(255), responsavel_nome VARCHAR(255), responsavel_telefone VARCHAR(64), cep VARCHAR(32), endereco TEXT, numero VARCHAR(32), complemento VARCHAR(255), bairro VARCHAR(120), cidade VARCHAR(120), estado VARCHAR(32), observacoes TEXT, ativo BOOLEAN NOT NULL DEFAULT TRUE, created_at VARCHAR(40) NOT NULL, updated_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS usuarios (id BIGSERIAL PRIMARY KEY, nome VARCHAR(255) NOT NULL, login VARCHAR(120) NOT NULL UNIQUE, email VARCHAR(255), telefone VARCHAR(64), cargo VARCHAR(120), observacoes TEXT, senha_hash TEXT NOT NULL, master_user BOOLEAN NOT NULL DEFAULT FALSE, administrador BOOLEAN NOT NULL DEFAULT FALSE, senha_provisoria BOOLEAN NOT NULL DEFAULT FALSE, ultimo_login_em VARCHAR(40), ativo BOOLEAN NOT NULL DEFAULT TRUE, created_at VARCHAR(40) NOT NULL, updated_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS perfis_acesso (id BIGSERIAL PRIMARY KEY, nome VARCHAR(160) NOT NULL UNIQUE, descricao TEXT, perfil_master BOOLEAN NOT NULL DEFAULT FALSE, ativo BOOLEAN NOT NULL DEFAULT TRUE, created_at VARCHAR(40) NOT NULL, updated_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS perfis_permissoes (id BIGSERIAL PRIMARY KEY, perfil_id BIGINT NOT NULL, permissao_chave VARCHAR(190) NOT NULL, created_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS usuarios_perfis (id BIGSERIAL PRIMARY KEY, usuario_id BIGINT NOT NULL, perfil_id BIGINT NOT NULL, created_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS usuarios_empresas (id BIGSERIAL PRIMARY KEY, usuario_id BIGINT NOT NULL, empresa_id BIGINT NOT NULL, created_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS user_sessions (id BIGSERIAL PRIMARY KEY, usuario_id BIGINT NOT NULL, session_token VARCHAR(190) NOT NULL UNIQUE, created_at VARCHAR(40) NOT NULL, expires_at VARCHAR(40) NOT NULL, last_activity_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS departamentos (id BIGSERIAL PRIMARY KEY, descricao VARCHAR(255) NOT NULL, ativo BOOLEAN NOT NULL DEFAULT TRUE, created_at VARCHAR(40) NOT NULL, updated_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS funcoes (id BIGSERIAL PRIMARY KEY, descricao VARCHAR(255) NOT NULL, ativo BOOLEAN NOT NULL DEFAULT TRUE, created_at VARCHAR(40) NOT NULL, updated_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS centro_custos (id BIGSERIAL PRIMARY KEY, codigo VARCHAR(80), descricao VARCHAR(255) NOT NULL, ativo BOOLEAN NOT NULL DEFAULT TRUE, created_at VARCHAR(40) NOT NULL, updated_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS clientes (id BIGSERIAL PRIMARY KEY, nome VARCHAR(255) NOT NULL, documento VARCHAR(32), telefone VARCHAR(64), email VARCHAR(255), endereco TEXT, cidade VARCHAR(120), estado VARCHAR(32), observacoes TEXT, ativo BOOLEAN NOT NULL DEFAULT TRUE, created_at VARCHAR(40) NOT NULL, updated_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS fornecedores (id BIGSERIAL PRIMARY KEY, nome VARCHAR(255) NOT NULL, documento VARCHAR(32), telefone VARCHAR(64), email VARCHAR(255), endereco TEXT, cidade VARCHAR(120), estado VARCHAR(32), observacoes TEXT, ativo BOOLEAN NOT NULL DEFAULT TRUE, created_at VARCHAR(40) NOT NULL, updated_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS produtos (id BIGSERIAL PRIMARY KEY, codigo VARCHAR(80), descricao VARCHAR(255) NOT NULL, tipo VARCHAR(80), unidade VARCHAR(32), valor NUMERIC(15,4) NOT NULL DEFAULT 0, ativo BOOLEAN NOT NULL DEFAULT TRUE, created_at VARCHAR(40) NOT NULL, updated_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS audit_logs (id BIGSERIAL PRIMARY KEY, entity_name VARCHAR(120) NOT NULL, action_name VARCHAR(80) NOT NULL, record_id BIGINT, payload_json TEXT, created_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS sync_queue (id BIGSERIAL PRIMARY KEY, entity_name VARCHAR(120) NOT NULL, action_name VARCHAR(80) NOT NULL, record_id BIGINT, payload_json TEXT, status VARCHAR(40) NOT NULL DEFAULT 'pending', created_at VARCHAR(40) NOT NULL, updated_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS app_settings (chave VARCHAR(190) PRIMARY KEY, valor TEXT, created_at VARCHAR(40) NOT NULL, updated_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS app_logs (id BIGSERIAL PRIMARY KEY, level VARCHAR(40) NOT NULL, category VARCHAR(120) NOT NULL, message TEXT NOT NULL, source VARCHAR(255), route VARCHAR(255), details_json TEXT, created_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS admin_guard (id BIGINT PRIMARY KEY, support_secret_hash TEXT, totp_secret_encrypted TEXT, totp_enabled BOOLEAN NOT NULL DEFAULT FALSE, recovery_codes_encrypted TEXT, licensing_protected BOOLEAN NOT NULL DEFAULT TRUE, white_label_protected BOOLEAN NOT NULL DEFAULT TRUE, created_at VARCHAR(40) NOT NULL, updated_at VARCHAR(40) NOT NULL, last_rotated_at VARCHAR(40))",
        "CREATE TABLE IF NOT EXISTS admin_unlock_sessions (id BIGSERIAL PRIMARY KEY, usuario_id BIGINT NOT NULL, scope VARCHAR(120) NOT NULL, unlock_token VARCHAR(190) NOT NULL UNIQUE, expires_at VARCHAR(40) NOT NULL, created_at VARCHAR(40) NOT NULL, last_used_at VARCHAR(40))",
        "CREATE TABLE IF NOT EXISTS local_licenses (id BIGSERIAL PRIMARY KEY, empresa_id BIGINT NOT NULL, cnpj VARCHAR(32) NOT NULL, license_kind VARCHAR(80) NOT NULL, status VARCHAR(40) NOT NULL DEFAULT 'active', issued_at VARCHAR(40) NOT NULL, expires_at VARCHAR(40) NOT NULL, fingerprint TEXT, payload_encrypted TEXT, integrity_hash TEXT, created_at VARCHAR(40) NOT NULL, updated_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS feature_flags (chave VARCHAR(190) PRIMARY KEY, ativo BOOLEAN NOT NULL DEFAULT TRUE, descricao TEXT, created_at VARCHAR(40) NOT NULL, updated_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS integration_configs (id BIGSERIAL PRIMARY KEY, nome VARCHAR(255) NOT NULL, tipo VARCHAR(40) NOT NULL DEFAULT 'rest', base_url TEXT NOT NULL, metodo_padrao VARCHAR(16) NOT NULL DEFAULT 'GET', headers_json TEXT, token_encrypted TEXT, ambiente VARCHAR(80) NOT NULL DEFAULT 'production', status VARCHAR(40) NOT NULL DEFAULT 'inactive', timeout_seconds INT NOT NULL DEFAULT 30, retry_attempts INT NOT NULL DEFAULT 0, ultimo_erro TEXT, ultima_execucao_em VARCHAR(40), ativo BOOLEAN NOT NULL DEFAULT TRUE, created_at VARCHAR(40) NOT NULL, updated_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS integration_logs (id BIGSERIAL PRIMARY KEY, integration_id BIGINT, method VARCHAR(16), url TEXT, request_headers_json TEXT, status_code INT, success BOOLEAN NOT NULL DEFAULT FALSE, duration_ms BIGINT, error_message TEXT, created_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS api_tokens (id BIGSERIAL PRIMARY KEY, nome VARCHAR(255) NOT NULL, token_hash TEXT NOT NULL, escopo TEXT, ativo BOOLEAN NOT NULL DEFAULT TRUE, expires_at VARCHAR(40), created_at VARCHAR(40) NOT NULL, updated_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS configuracoes (nome VARCHAR(190) PRIMARY KEY, valor TEXT, updated_at VARCHAR(40) NOT NULL)",
        "CREATE INDEX IF NOT EXISTS idx_empresas_nome ON empresas(nome)",
        "CREATE INDEX IF NOT EXISTS idx_empresas_documento ON empresas(documento)",
        "CREATE INDEX IF NOT EXISTS idx_usuarios_login ON usuarios(login)",
        "CREATE INDEX IF NOT EXISTS idx_usuarios_master ON usuarios(master_user, ativo)",
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_perfis_permissao ON perfis_permissoes(perfil_id, permissao_chave)",
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_usuarios_perfis ON usuarios_perfis(usuario_id, perfil_id)",
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_usuarios_empresas ON usuarios_empresas(usuario_id, empresa_id)",
        "CREATE INDEX IF NOT EXISTS idx_app_logs_created_at ON app_logs(created_at)",
        "CREATE INDEX IF NOT EXISTS idx_app_logs_category ON app_logs(category)",
        "CREATE INDEX IF NOT EXISTS idx_admin_unlock_sessions_usuario ON admin_unlock_sessions(usuario_id)",
        "CREATE INDEX IF NOT EXISTS idx_local_licenses_cnpj ON local_licenses(cnpj)",
        "CREATE INDEX IF NOT EXISTS idx_clientes_nome ON clientes(nome)",
        "CREATE INDEX IF NOT EXISTS idx_fornecedores_nome ON fornecedores(nome)",
        "CREATE INDEX IF NOT EXISTS idx_produtos_descricao ON produtos(descricao)",
        "CREATE INDEX IF NOT EXISTS idx_sync_queue_status ON sync_queue(status)",
    ]
}

#[derive(Debug, Clone)]
pub struct PostgresProvider {
    config: DatabaseConfig,
}

impl PostgresProvider {
    pub fn new(config: DatabaseConfig) -> Self {
        Self { config }
    }
}

impl super::provider::DatabaseProvider for PostgresProvider {
    fn driver(&self) -> DatabaseDriver {
        DatabaseDriver::Postgres
    }

    fn health(&self) -> Result<super::provider::ProviderStatus, String> {
        let ok = health(&self.config)?;
        Ok(super::provider::ProviderStatus {
            driver: "postgres".to_string(),
            available: ok,
            message: "PostgreSQL disponível via feature Rust postgres-db.".to_string(),
        })
    }

    fn migrate(&self) -> Result<(), String> {
        migrate(&self.config)
    }

    #[cfg(feature = "postgres-db")]
    fn execute(&self, sql: &str, params: &[DbValue]) -> Result<u64, String> {
        execute_postgres(&self.config, sql, params)
    }

    #[cfg(not(feature = "postgres-db"))]
    fn execute(&self, _sql: &str, _params: &[DbValue]) -> Result<u64, String> {
        Err("CRUD provider PostgreSQL exige compilação com --features postgres-db.".to_string())
    }

    #[cfg(feature = "postgres-db")]
    fn query(&self, sql: &str, params: &[DbValue]) -> Result<Vec<DbRow>, String> {
        query_postgres(&self.config, sql, params)
    }

    #[cfg(not(feature = "postgres-db"))]
    fn query(&self, _sql: &str, _params: &[DbValue]) -> Result<Vec<DbRow>, String> {
        Err("CRUD provider PostgreSQL exige compilação com --features postgres-db.".to_string())
    }

    #[cfg(feature = "postgres-db")]
    fn query_one(&self, sql: &str, params: &[DbValue]) -> Result<Option<DbRow>, String> {
        query_postgres(&self.config, sql, params).map(|mut rows| rows.pop())
    }

    #[cfg(not(feature = "postgres-db"))]
    fn query_one(&self, _sql: &str, _params: &[DbValue]) -> Result<Option<DbRow>, String> {
        Err("CRUD provider PostgreSQL exige compilação com --features postgres-db.".to_string())
    }

    fn list_entities(&self, entity: &str, search: &str) -> Result<Vec<DbRow>, String> {
        crate::commands::entities::provider_list_with_database(self, entity, search)
    }
}
