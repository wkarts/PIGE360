use std::path::Path;

use crate::migrations as sqlite_migrations;

use super::{
    config::{DatabaseConfig, DatabaseDriver},
    firebird, mysql, postgres,
};

pub fn migrate(config: &DatabaseConfig, sqlite_path: &Path) -> Result<(), String> {
    match config.driver {
        DatabaseDriver::Sqlite => sqlite_migrations::migrate(sqlite_path),
        DatabaseDriver::Mysql => mysql::migrate(config),
        DatabaseDriver::Postgres => postgres::migrate(config),
        DatabaseDriver::FirebirdUnsupported => firebird::migrate(config),
    }
}
