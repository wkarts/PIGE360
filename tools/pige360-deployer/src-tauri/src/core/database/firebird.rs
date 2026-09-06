use super::config::{DatabaseConfig, DatabaseDriver};

pub fn health(config: &DatabaseConfig) -> Result<bool, String> {
    if config.driver != DatabaseDriver::FirebirdUnsupported {
        return Err("Driver informado não é Firebird.".to_string());
    }
    Err("Firebird foi ignorado nesta etapa por compatibilidade. Use SQLite, MySQL/MariaDB ou PostgreSQL.".to_string())
}

pub fn migrate(config: &DatabaseConfig) -> Result<(), String> {
    if config.driver != DatabaseDriver::FirebirdUnsupported {
        return Err("Driver informado não é Firebird.".to_string());
    }
    Err("Migrations Firebird não fazem parte da Etapa 2.2.".to_string())
}
