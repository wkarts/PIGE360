pub mod types;

use std::path::Path;

use serde::Serialize;

use self::types::{DbRow, DbValue};
use super::{
    config::{DatabaseConfig, DatabaseDriver},
    mysql::MySqlProvider,
    postgres::PostgresProvider,
    sqlite::SqliteProvider,
};

#[derive(Debug, Clone, Serialize)]
pub struct ProviderStatus {
    pub driver: String,
    pub available: bool,
    pub message: String,
}

pub trait DatabaseProvider: Send + Sync {
    fn driver(&self) -> DatabaseDriver;
    fn health(&self) -> Result<ProviderStatus, String>;
    fn migrate(&self) -> Result<(), String>;

    fn placeholder(&self, index: usize) -> String {
        match self.driver() {
            DatabaseDriver::Postgres => format!("${index}"),
            DatabaseDriver::Sqlite
            | DatabaseDriver::Mysql
            | DatabaseDriver::FirebirdUnsupported => "?".to_string(),
        }
    }

    fn last_insert_id_sql(&self) -> &'static str {
        match self.driver() {
            DatabaseDriver::Sqlite => "SELECT last_insert_rowid() AS id",
            DatabaseDriver::Mysql => "SELECT LAST_INSERT_ID() AS id",
            DatabaseDriver::Postgres => "",
            DatabaseDriver::FirebirdUnsupported => "",
        }
    }

    fn execute(&self, sql: &str, params: &[DbValue]) -> Result<u64, String>;
    fn query(&self, sql: &str, params: &[DbValue]) -> Result<Vec<DbRow>, String>;
    fn query_one(&self, sql: &str, params: &[DbValue]) -> Result<Option<DbRow>, String>;

    fn begin_transaction(&self) -> Result<(), String> {
        self.execute("BEGIN", &[]).map(|_| ())
    }

    fn commit(&self) -> Result<(), String> {
        self.execute("COMMIT", &[]).map(|_| ())
    }

    fn rollback(&self) -> Result<(), String> {
        self.execute("ROLLBACK", &[]).map(|_| ())
    }

    fn list_entities(&self, entity: &str, search: &str) -> Result<Vec<DbRow>, String>;
}

pub enum ActiveDatabaseProvider {
    Sqlite(SqliteProvider),
    Mysql(MySqlProvider),
    Postgres(PostgresProvider),
}

impl ActiveDatabaseProvider {
    pub fn from_config(config: DatabaseConfig, sqlite_path: &Path) -> Result<Self, String> {
        match config.driver {
            DatabaseDriver::Sqlite => {
                Ok(Self::Sqlite(SqliteProvider::new(sqlite_path.to_path_buf())))
            }
            DatabaseDriver::Mysql => Ok(Self::Mysql(MySqlProvider::new(config))),
            DatabaseDriver::Postgres => Ok(Self::Postgres(PostgresProvider::new(config))),
            DatabaseDriver::FirebirdUnsupported => {
                Err("Firebird permanece fora do escopo funcional por compatibilidade.".to_string())
            }
        }
    }
}

impl DatabaseProvider for ActiveDatabaseProvider {
    fn driver(&self) -> DatabaseDriver {
        match self {
            Self::Sqlite(provider) => provider.driver(),
            Self::Mysql(provider) => provider.driver(),
            Self::Postgres(provider) => provider.driver(),
        }
    }

    fn health(&self) -> Result<ProviderStatus, String> {
        match self {
            Self::Sqlite(provider) => provider.health(),
            Self::Mysql(provider) => provider.health(),
            Self::Postgres(provider) => provider.health(),
        }
    }

    fn migrate(&self) -> Result<(), String> {
        match self {
            Self::Sqlite(provider) => provider.migrate(),
            Self::Mysql(provider) => provider.migrate(),
            Self::Postgres(provider) => provider.migrate(),
        }
    }

    fn execute(&self, sql: &str, params: &[DbValue]) -> Result<u64, String> {
        match self {
            Self::Sqlite(provider) => provider.execute(sql, params),
            Self::Mysql(provider) => provider.execute(sql, params),
            Self::Postgres(provider) => provider.execute(sql, params),
        }
    }

    fn query(&self, sql: &str, params: &[DbValue]) -> Result<Vec<DbRow>, String> {
        match self {
            Self::Sqlite(provider) => provider.query(sql, params),
            Self::Mysql(provider) => provider.query(sql, params),
            Self::Postgres(provider) => provider.query(sql, params),
        }
    }

    fn query_one(&self, sql: &str, params: &[DbValue]) -> Result<Option<DbRow>, String> {
        match self {
            Self::Sqlite(provider) => provider.query_one(sql, params),
            Self::Mysql(provider) => provider.query_one(sql, params),
            Self::Postgres(provider) => provider.query_one(sql, params),
        }
    }

    fn begin_transaction(&self) -> Result<(), String> {
        match self {
            Self::Sqlite(provider) => provider.begin_transaction(),
            Self::Mysql(provider) => provider.begin_transaction(),
            Self::Postgres(provider) => provider.begin_transaction(),
        }
    }

    fn commit(&self) -> Result<(), String> {
        match self {
            Self::Sqlite(provider) => provider.commit(),
            Self::Mysql(provider) => provider.commit(),
            Self::Postgres(provider) => provider.commit(),
        }
    }

    fn rollback(&self) -> Result<(), String> {
        match self {
            Self::Sqlite(provider) => provider.rollback(),
            Self::Mysql(provider) => provider.rollback(),
            Self::Postgres(provider) => provider.rollback(),
        }
    }

    fn list_entities(&self, entity: &str, search: &str) -> Result<Vec<DbRow>, String> {
        match self {
            Self::Sqlite(provider) => provider.list_entities(entity, search),
            Self::Mysql(provider) => provider.list_entities(entity, search),
            Self::Postgres(provider) => provider.list_entities(entity, search),
        }
    }
}
