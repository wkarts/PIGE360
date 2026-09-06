use std::path::Path;

use rusqlite::Connection;

use super::{
    config::{DatabaseConfig, DatabaseDriver},
    mysql, postgres, sqlite,
};

pub enum AppDatabaseConnection {
    Sqlite(Connection),
    MysqlEnabled { dsn: String },
    PostgresEnabled { dsn: String },
}

pub fn connect(
    config: &DatabaseConfig,
    sqlite_path: &Path,
) -> Result<AppDatabaseConnection, String> {
    match config.driver {
        DatabaseDriver::Sqlite => sqlite::connect(sqlite_path).map(AppDatabaseConnection::Sqlite),
        DatabaseDriver::Mysql => {
            mysql::health(config)?;
            Ok(AppDatabaseConnection::MysqlEnabled {
                dsn: config.external_dsn_label(),
            })
        }
        DatabaseDriver::Postgres => {
            postgres::health(config)?;
            Ok(AppDatabaseConnection::PostgresEnabled {
                dsn: config.external_dsn_label(),
            })
        }
        DatabaseDriver::FirebirdUnsupported => Err(
            "Firebird foi ignorado nesta etapa por compatibilidade. Configure sqlite, mysql ou postgres."
                .to_string(),
        ),
    }
}
