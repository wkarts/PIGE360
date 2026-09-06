use super::{
    config::{DatabaseConfig, DatabaseDriver},
    provider::types::{DbRow, DbValue},
};

#[derive(Debug, Clone)]
pub struct MysqlConnectionInfo {
    pub host: String,
    pub port: u16,
    pub database: String,
    pub username: String,
    pub password_configured: bool,
}

pub fn build_connection_info(config: &DatabaseConfig) -> Result<MysqlConnectionInfo, String> {
    if config.driver != DatabaseDriver::Mysql {
        return Err("Driver informado não é MySQL/MariaDB.".to_string());
    }

    Ok(MysqlConnectionInfo {
        host: config
            .host
            .clone()
            .unwrap_or_else(|| "127.0.0.1".to_string()),
        port: config.port.unwrap_or(3306),
        database: config
            .database
            .clone()
            .ok_or_else(|| "Banco MySQL não informado.".to_string())?,
        username: config
            .username
            .clone()
            .unwrap_or_else(|| "root".to_string()),
        password_configured: config
            .password
            .as_ref()
            .is_some_and(|value| !value.is_empty()),
    })
}

fn connection_url(config: &DatabaseConfig) -> Result<String, String> {
    let info = build_connection_info(config)?;
    let password = config.password.clone().unwrap_or_default();
    Ok(format!(
        "mysql://{}:{}@{}:{}/{}",
        urlencoding(&info.username),
        urlencoding(&password),
        info.host,
        info.port,
        info.database
    ))
}

fn urlencoding(value: &str) -> String {
    value
        .replace('@', "%40")
        .replace(':', "%3A")
        .replace('/', "%2F")
        .replace('#', "%23")
}

#[cfg(feature = "mysql-db")]
fn pool(config: &DatabaseConfig) -> Result<mysql::Pool, String> {
    let url = connection_url(config)?;
    mysql::Pool::new(url.as_str()).map_err(|err| format!("Falha ao criar pool MySQL: {err}"))
}

#[cfg(feature = "mysql-db")]
pub fn health(config: &DatabaseConfig) -> Result<bool, String> {
    use mysql::prelude::Queryable;

    let pool = pool(config)?;
    let mut conn = pool
        .get_conn()
        .map_err(|err| format!("Falha ao conectar MySQL: {err}"))?;
    conn.query_drop("SELECT 1")
        .map_err(|err| format!("Falha no health check MySQL: {err}"))?;
    Ok(true)
}

#[cfg(not(feature = "mysql-db"))]
pub fn health(config: &DatabaseConfig) -> Result<bool, String> {
    let _ = build_connection_info(config)?;
    Err("MySQL/MariaDB configurado, mas a feature Rust 'mysql-db' não está habilitada. Compile com --features mysql-db para conexão real.".to_string())
}

#[cfg(feature = "mysql-db")]
pub fn migrate(config: &DatabaseConfig) -> Result<(), String> {
    use mysql::prelude::Queryable;

    let pool = pool(config)?;
    let mut conn = pool
        .get_conn()
        .map_err(|err| format!("Falha ao conectar MySQL: {err}"))?;
    for sql in mysql_schema() {
        if let Err(err) = conn.query_drop(sql) {
            let message = err.to_string();
            let duplicate_index =
                message.contains("Duplicate key name") || message.contains("1061");
            if !duplicate_index {
                return Err(format!("Falha ao migrar MySQL: {err}; SQL: {sql}"));
            }
        }
    }
    Ok(())
}

#[cfg(not(feature = "mysql-db"))]
pub fn migrate(config: &DatabaseConfig) -> Result<(), String> {
    let _ = build_connection_info(config)?;
    Err("Migrations MySQL exigem compilação com --features mysql-db.".to_string())
}

#[cfg(feature = "mysql-db")]
fn to_mysql_value(value: &DbValue) -> mysql::Value {
    match value {
        DbValue::Null => mysql::Value::NULL,
        DbValue::Bool(value) => mysql::Value::Int(if *value { 1 } else { 0 }),
        DbValue::Integer(value) => mysql::Value::Int(*value),
        DbValue::Real(value) => mysql::Value::Double(*value),
        DbValue::Text(value) => mysql::Value::Bytes(value.clone().into_bytes()),
        DbValue::Json(value) => mysql::Value::Bytes(value.to_string().into_bytes()),
    }
}

#[cfg(feature = "mysql-db")]
fn mysql_value_to_json(value: &mysql::Value) -> serde_json::Value {
    match value {
        mysql::Value::NULL => serde_json::Value::Null,
        mysql::Value::Bytes(value) => {
            serde_json::Value::String(String::from_utf8_lossy(value).to_string())
        }
        mysql::Value::Int(value) => serde_json::Value::from(*value),
        mysql::Value::UInt(value) => serde_json::Value::from(*value),
        mysql::Value::Float(value) => serde_json::Value::from(*value as f64),
        mysql::Value::Double(value) => serde_json::Value::from(*value),
        mysql::Value::Date(year, month, day, hour, minute, second, micros) => {
            serde_json::Value::String(format!(
                "{year:04}-{month:02}-{day:02}T{hour:02}:{minute:02}:{second:02}.{micros:06}"
            ))
        }
        mysql::Value::Time(is_negative, days, hours, minutes, seconds, micros) => {
            serde_json::Value::String(format!(
                "{}{days} {hours:02}:{minutes:02}:{seconds:02}.{micros:06}",
                if *is_negative { "-" } else { "" }
            ))
        }
    }
}

#[cfg(feature = "mysql-db")]
fn mysql_row_to_json(row: mysql::Row) -> DbRow {
    let columns = row
        .columns_ref()
        .iter()
        .map(|column| column.name_str().to_string())
        .collect::<Vec<_>>();
    let mut out = DbRow::new();
    for (index, column) in columns.iter().enumerate() {
        let value = row
            .as_ref(index)
            .map(mysql_value_to_json)
            .unwrap_or(serde_json::Value::Null);
        out.insert(column.clone(), value);
    }
    out
}

#[cfg(feature = "mysql-db")]
fn execute_mysql(config: &DatabaseConfig, sql: &str, params: &[DbValue]) -> Result<u64, String> {
    use mysql::prelude::Queryable;

    let pool = pool(config)?;
    let mut conn = pool
        .get_conn()
        .map_err(|err| format!("Falha ao conectar MySQL: {err}"))?;
    let values = params.iter().map(to_mysql_value).collect::<Vec<_>>();
    conn.exec_drop(sql, values)
        .map_err(|err| format!("Falha ao executar SQL MySQL: {err}"))?;
    Ok(conn.affected_rows())
}

#[cfg(feature = "mysql-db")]
fn query_mysql(
    config: &DatabaseConfig,
    sql: &str,
    params: &[DbValue],
) -> Result<Vec<DbRow>, String> {
    use mysql::prelude::Queryable;

    let pool = pool(config)?;
    let mut conn = pool
        .get_conn()
        .map_err(|err| format!("Falha ao conectar MySQL: {err}"))?;
    let values = params.iter().map(to_mysql_value).collect::<Vec<_>>();
    let rows = conn
        .exec::<mysql::Row, _, _>(sql, values)
        .map_err(|err| format!("Falha ao consultar MySQL: {err}"))?;
    Ok(rows.into_iter().map(mysql_row_to_json).collect())
}

pub fn mysql_schema() -> Vec<&'static str> {
    vec![
        "CREATE TABLE IF NOT EXISTS empresas (id BIGINT PRIMARY KEY AUTO_INCREMENT, nome VARCHAR(255) NOT NULL, nome_fantasia VARCHAR(255), documento VARCHAR(32), inscricao_estadual VARCHAR(64), inscricao_municipal VARCHAR(64), telefone VARCHAR(64), email VARCHAR(255), responsavel_nome VARCHAR(255), responsavel_telefone VARCHAR(64), cep VARCHAR(32), endereco TEXT, numero VARCHAR(32), complemento VARCHAR(255), bairro VARCHAR(120), cidade VARCHAR(120), estado VARCHAR(32), observacoes TEXT, ativo TINYINT NOT NULL DEFAULT 1, created_at VARCHAR(40) NOT NULL, updated_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS usuarios (id BIGINT PRIMARY KEY AUTO_INCREMENT, nome VARCHAR(255) NOT NULL, login VARCHAR(120) NOT NULL UNIQUE, email VARCHAR(255), telefone VARCHAR(64), cargo VARCHAR(120), observacoes TEXT, senha_hash TEXT NOT NULL, master_user TINYINT NOT NULL DEFAULT 0, administrador TINYINT NOT NULL DEFAULT 0, senha_provisoria TINYINT NOT NULL DEFAULT 0, ultimo_login_em VARCHAR(40), ativo TINYINT NOT NULL DEFAULT 1, created_at VARCHAR(40) NOT NULL, updated_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS perfis_acesso (id BIGINT PRIMARY KEY AUTO_INCREMENT, nome VARCHAR(160) NOT NULL UNIQUE, descricao TEXT, perfil_master TINYINT NOT NULL DEFAULT 0, ativo TINYINT NOT NULL DEFAULT 1, created_at VARCHAR(40) NOT NULL, updated_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS perfis_permissoes (id BIGINT PRIMARY KEY AUTO_INCREMENT, perfil_id BIGINT NOT NULL, permissao_chave VARCHAR(190) NOT NULL, created_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS usuarios_perfis (id BIGINT PRIMARY KEY AUTO_INCREMENT, usuario_id BIGINT NOT NULL, perfil_id BIGINT NOT NULL, created_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS usuarios_empresas (id BIGINT PRIMARY KEY AUTO_INCREMENT, usuario_id BIGINT NOT NULL, empresa_id BIGINT NOT NULL, created_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS user_sessions (id BIGINT PRIMARY KEY AUTO_INCREMENT, usuario_id BIGINT NOT NULL, session_token VARCHAR(190) NOT NULL UNIQUE, created_at VARCHAR(40) NOT NULL, expires_at VARCHAR(40) NOT NULL, last_activity_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS departamentos (id BIGINT PRIMARY KEY AUTO_INCREMENT, descricao VARCHAR(255) NOT NULL, ativo TINYINT NOT NULL DEFAULT 1, created_at VARCHAR(40) NOT NULL, updated_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS funcoes (id BIGINT PRIMARY KEY AUTO_INCREMENT, descricao VARCHAR(255) NOT NULL, ativo TINYINT NOT NULL DEFAULT 1, created_at VARCHAR(40) NOT NULL, updated_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS centro_custos (id BIGINT PRIMARY KEY AUTO_INCREMENT, codigo VARCHAR(80), descricao VARCHAR(255) NOT NULL, ativo TINYINT NOT NULL DEFAULT 1, created_at VARCHAR(40) NOT NULL, updated_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS clientes (id BIGINT PRIMARY KEY AUTO_INCREMENT, nome VARCHAR(255) NOT NULL, documento VARCHAR(32), telefone VARCHAR(64), email VARCHAR(255), endereco TEXT, cidade VARCHAR(120), estado VARCHAR(32), observacoes TEXT, ativo TINYINT NOT NULL DEFAULT 1, created_at VARCHAR(40) NOT NULL, updated_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS fornecedores (id BIGINT PRIMARY KEY AUTO_INCREMENT, nome VARCHAR(255) NOT NULL, documento VARCHAR(32), telefone VARCHAR(64), email VARCHAR(255), endereco TEXT, cidade VARCHAR(120), estado VARCHAR(32), observacoes TEXT, ativo TINYINT NOT NULL DEFAULT 1, created_at VARCHAR(40) NOT NULL, updated_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS produtos (id BIGINT PRIMARY KEY AUTO_INCREMENT, codigo VARCHAR(80), descricao VARCHAR(255) NOT NULL, tipo VARCHAR(80), unidade VARCHAR(32), valor DECIMAL(15,4) NOT NULL DEFAULT 0, ativo TINYINT NOT NULL DEFAULT 1, created_at VARCHAR(40) NOT NULL, updated_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS audit_logs (id BIGINT PRIMARY KEY AUTO_INCREMENT, entity_name VARCHAR(120) NOT NULL, action_name VARCHAR(80) NOT NULL, record_id BIGINT, payload_json TEXT, created_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS sync_queue (id BIGINT PRIMARY KEY AUTO_INCREMENT, entity_name VARCHAR(120) NOT NULL, action_name VARCHAR(80) NOT NULL, record_id BIGINT, payload_json TEXT, status VARCHAR(40) NOT NULL DEFAULT 'pending', created_at VARCHAR(40) NOT NULL, updated_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS app_settings (chave VARCHAR(190) PRIMARY KEY, valor TEXT, created_at VARCHAR(40) NOT NULL, updated_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS app_logs (id BIGINT PRIMARY KEY AUTO_INCREMENT, level VARCHAR(40) NOT NULL, category VARCHAR(120) NOT NULL, message TEXT NOT NULL, source VARCHAR(255), route VARCHAR(255), details_json TEXT, created_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS admin_guard (id BIGINT PRIMARY KEY, support_secret_hash TEXT, totp_secret_encrypted TEXT, totp_enabled TINYINT NOT NULL DEFAULT 0, recovery_codes_encrypted TEXT, licensing_protected TINYINT NOT NULL DEFAULT 1, white_label_protected TINYINT NOT NULL DEFAULT 1, created_at VARCHAR(40) NOT NULL, updated_at VARCHAR(40) NOT NULL, last_rotated_at VARCHAR(40))",
        "CREATE TABLE IF NOT EXISTS admin_unlock_sessions (id BIGINT PRIMARY KEY AUTO_INCREMENT, usuario_id BIGINT NOT NULL, scope VARCHAR(120) NOT NULL, unlock_token VARCHAR(190) NOT NULL UNIQUE, expires_at VARCHAR(40) NOT NULL, created_at VARCHAR(40) NOT NULL, last_used_at VARCHAR(40))",
        "CREATE TABLE IF NOT EXISTS local_licenses (id BIGINT PRIMARY KEY AUTO_INCREMENT, empresa_id BIGINT NOT NULL, cnpj VARCHAR(32) NOT NULL, license_kind VARCHAR(80) NOT NULL, status VARCHAR(40) NOT NULL DEFAULT 'active', issued_at VARCHAR(40) NOT NULL, expires_at VARCHAR(40) NOT NULL, fingerprint TEXT, payload_encrypted TEXT, integrity_hash TEXT, created_at VARCHAR(40) NOT NULL, updated_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS feature_flags (chave VARCHAR(190) PRIMARY KEY, ativo TINYINT NOT NULL DEFAULT 1, descricao TEXT, created_at VARCHAR(40) NOT NULL, updated_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS integration_configs (id BIGINT PRIMARY KEY AUTO_INCREMENT, nome VARCHAR(255) NOT NULL, tipo VARCHAR(40) NOT NULL DEFAULT 'rest', base_url TEXT NOT NULL, metodo_padrao VARCHAR(16) NOT NULL DEFAULT 'GET', headers_json TEXT, token_encrypted TEXT, ambiente VARCHAR(80) NOT NULL DEFAULT 'production', status VARCHAR(40) NOT NULL DEFAULT 'inactive', timeout_seconds INT NOT NULL DEFAULT 30, retry_attempts INT NOT NULL DEFAULT 0, ultimo_erro TEXT, ultima_execucao_em VARCHAR(40), ativo TINYINT NOT NULL DEFAULT 1, created_at VARCHAR(40) NOT NULL, updated_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS integration_logs (id BIGINT PRIMARY KEY AUTO_INCREMENT, integration_id BIGINT, method VARCHAR(16), url TEXT, request_headers_json TEXT, status_code INT, success TINYINT NOT NULL DEFAULT 0, duration_ms BIGINT, error_message TEXT, created_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS api_tokens (id BIGINT PRIMARY KEY AUTO_INCREMENT, nome VARCHAR(255) NOT NULL, token_hash TEXT NOT NULL, escopo TEXT, ativo TINYINT NOT NULL DEFAULT 1, expires_at VARCHAR(40), created_at VARCHAR(40) NOT NULL, updated_at VARCHAR(40) NOT NULL)",
        "CREATE TABLE IF NOT EXISTS configuracoes (nome VARCHAR(190) PRIMARY KEY, valor TEXT, updated_at VARCHAR(40) NOT NULL)",
        "CREATE INDEX idx_empresas_nome ON empresas(nome)",
        "CREATE INDEX idx_empresas_documento ON empresas(documento)",
        "CREATE INDEX idx_usuarios_login ON usuarios(login)",
        "CREATE INDEX idx_usuarios_master ON usuarios(master_user, ativo)",
        "CREATE UNIQUE INDEX ux_perfis_permissao ON perfis_permissoes(perfil_id, permissao_chave)",
        "CREATE UNIQUE INDEX ux_usuarios_perfis ON usuarios_perfis(usuario_id, perfil_id)",
        "CREATE UNIQUE INDEX ux_usuarios_empresas ON usuarios_empresas(usuario_id, empresa_id)",
        "CREATE INDEX idx_app_logs_created_at ON app_logs(created_at)",
        "CREATE INDEX idx_app_logs_category ON app_logs(category)",
        "CREATE INDEX idx_admin_unlock_sessions_usuario ON admin_unlock_sessions(usuario_id)",
        "CREATE INDEX idx_local_licenses_cnpj ON local_licenses(cnpj)",
        "CREATE INDEX idx_clientes_nome ON clientes(nome)",
        "CREATE INDEX idx_fornecedores_nome ON fornecedores(nome)",
        "CREATE INDEX idx_produtos_descricao ON produtos(descricao)",
        "CREATE INDEX idx_sync_queue_status ON sync_queue(status)",
    ]
}

#[derive(Debug, Clone)]
pub struct MySqlProvider {
    config: DatabaseConfig,
}

impl MySqlProvider {
    pub fn new(config: DatabaseConfig) -> Self {
        Self { config }
    }
}

impl super::provider::DatabaseProvider for MySqlProvider {
    fn driver(&self) -> DatabaseDriver {
        DatabaseDriver::Mysql
    }

    fn health(&self) -> Result<super::provider::ProviderStatus, String> {
        let ok = health(&self.config)?;
        Ok(super::provider::ProviderStatus {
            driver: "mysql".to_string(),
            available: ok,
            message: "MySQL/MariaDB disponível via feature Rust mysql-db.".to_string(),
        })
    }

    fn migrate(&self) -> Result<(), String> {
        migrate(&self.config)
    }

    #[cfg(feature = "mysql-db")]
    fn execute(&self, sql: &str, params: &[DbValue]) -> Result<u64, String> {
        execute_mysql(&self.config, sql, params)
    }

    #[cfg(not(feature = "mysql-db"))]
    fn execute(&self, _sql: &str, _params: &[DbValue]) -> Result<u64, String> {
        Err("CRUD provider MySQL exige compilação com --features mysql-db.".to_string())
    }

    #[cfg(feature = "mysql-db")]
    fn query(&self, sql: &str, params: &[DbValue]) -> Result<Vec<DbRow>, String> {
        query_mysql(&self.config, sql, params)
    }

    #[cfg(not(feature = "mysql-db"))]
    fn query(&self, _sql: &str, _params: &[DbValue]) -> Result<Vec<DbRow>, String> {
        Err("CRUD provider MySQL exige compilação com --features mysql-db.".to_string())
    }

    #[cfg(feature = "mysql-db")]
    fn query_one(&self, sql: &str, params: &[DbValue]) -> Result<Option<DbRow>, String> {
        query_mysql(&self.config, sql, params).map(|mut rows| rows.pop())
    }

    #[cfg(not(feature = "mysql-db"))]
    fn query_one(&self, _sql: &str, _params: &[DbValue]) -> Result<Option<DbRow>, String> {
        Err("CRUD provider MySQL exige compilação com --features mysql-db.".to_string())
    }

    fn list_entities(&self, entity: &str, search: &str) -> Result<Vec<DbRow>, String> {
        crate::commands::entities::provider_list_with_database(self, entity, search)
    }
}
