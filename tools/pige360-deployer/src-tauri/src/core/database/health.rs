use std::path::Path;

use serde::Serialize;

use super::{
    config::{DatabaseConfig, DatabaseDriver},
    firebird, mysql, postgres, sqlite,
};

#[derive(Debug, Clone, Serialize)]
pub struct DatabaseHealthReport {
    pub driver: String,
    pub ok: bool,
    pub message: String,
    pub target: String,
    pub feature_required: Option<String>,
}

pub fn check(config: &DatabaseConfig, sqlite_path: &Path) -> Result<bool, String> {
    match config.driver {
        DatabaseDriver::Sqlite => sqlite::health(sqlite_path),
        DatabaseDriver::Mysql => mysql::health(config),
        DatabaseDriver::Postgres => postgres::health(config),
        DatabaseDriver::FirebirdUnsupported => firebird::health(config),
    }
}

pub fn report(config: &DatabaseConfig, sqlite_path: &Path) -> DatabaseHealthReport {
    let target = if config.driver == DatabaseDriver::Sqlite {
        sqlite_path.display().to_string()
    } else {
        config.external_dsn_label()
    };

    match check(config, sqlite_path) {
        Ok(ok) => DatabaseHealthReport {
            driver: config.driver.as_str().to_string(),
            ok,
            message: if ok {
                "Conexão verificada com sucesso."
            } else {
                "Conexão indisponível."
            }
            .to_string(),
            target,
            feature_required: None,
        },
        Err(message) => DatabaseHealthReport {
            driver: config.driver.as_str().to_string(),
            ok: false,
            feature_required: match config.driver {
                DatabaseDriver::Mysql => Some("mysql-db".to_string()),
                DatabaseDriver::Postgres => Some("postgres-db".to_string()),
                DatabaseDriver::Sqlite | DatabaseDriver::FirebirdUnsupported => None,
            },
            message,
            target,
        },
    }
}
