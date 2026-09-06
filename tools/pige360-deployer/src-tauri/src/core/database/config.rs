use std::env;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DatabaseDriver {
    Sqlite,
    Mysql,
    Postgres,
    FirebirdUnsupported,
}

impl DatabaseDriver {
    pub fn from_str(value: &str) -> Self {
        match value.trim().to_ascii_lowercase().as_str() {
            "mysql" | "mariadb" => Self::Mysql,
            "postgres" | "postgresql" => Self::Postgres,
            "firebird" | "fb" => Self::FirebirdUnsupported,
            _ => Self::Sqlite,
        }
    }

    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Sqlite => "sqlite",
            Self::Mysql => "mysql",
            Self::Postgres => "postgres",
            Self::FirebirdUnsupported => "firebird-unsupported",
        }
    }

    pub fn is_external(&self) -> bool {
        matches!(self, Self::Mysql | Self::Postgres)
    }
}

#[derive(Debug, Clone)]
pub struct DatabaseConfig {
    pub driver: DatabaseDriver,
    pub sqlite_path: Option<String>,
    pub host: Option<String>,
    pub port: Option<u16>,
    pub database: Option<String>,
    pub username: Option<String>,
    pub password: Option<String>,
}

impl Default for DatabaseConfig {
    fn default() -> Self {
        Self {
            driver: DatabaseDriver::Sqlite,
            sqlite_path: Some("app.db".to_string()),
            host: None,
            port: None,
            database: None,
            username: None,
            password: None,
        }
    }
}

impl DatabaseConfig {
    pub fn from_env_with_driver(driver: &str) -> Self {
        let parsed_driver = DatabaseDriver::from_str(driver);
        let prefix = match parsed_driver {
            DatabaseDriver::Mysql => "PIGE360_DEPLOYER_MYSQL",
            DatabaseDriver::Postgres => "PIGE360_DEPLOYER_POSTGRES",
            DatabaseDriver::Sqlite | DatabaseDriver::FirebirdUnsupported => "PIGE360_DEPLOYER_DB",
        };
        let default_port = match parsed_driver {
            DatabaseDriver::Mysql => Some(3306),
            DatabaseDriver::Postgres => Some(5432),
            DatabaseDriver::Sqlite | DatabaseDriver::FirebirdUnsupported => None,
        };

        Self {
            driver: parsed_driver,
            sqlite_path: env::var("PIGE360_DEPLOYER_SQLITE_PATH")
                .ok()
                .or_else(|| Some("app.db".to_string())),
            host: env::var(format!("{prefix}_HOST"))
                .ok()
                .or_else(|| env::var("PIGE360_DEPLOYER_DB_HOST").ok()),
            port: env::var(format!("{prefix}_PORT"))
                .ok()
                .or_else(|| env::var("PIGE360_DEPLOYER_DB_PORT").ok())
                .and_then(|value| value.parse::<u16>().ok())
                .or(default_port),
            database: env::var(format!("{prefix}_DATABASE"))
                .ok()
                .or_else(|| env::var("PIGE360_DEPLOYER_DB_DATABASE").ok()),
            username: env::var(format!("{prefix}_USERNAME"))
                .ok()
                .or_else(|| env::var("PIGE360_DEPLOYER_DB_USERNAME").ok()),
            password: env::var(format!("{prefix}_PASSWORD"))
                .ok()
                .or_else(|| env::var("PIGE360_DEPLOYER_DB_PASSWORD").ok()),
        }
    }

    pub fn external_dsn_label(&self) -> String {
        match self.driver {
            DatabaseDriver::Sqlite => self
                .sqlite_path
                .clone()
                .unwrap_or_else(|| "app.db".to_string()),
            DatabaseDriver::Mysql | DatabaseDriver::Postgres => format!(
                "{}:{} / {}",
                self.host.clone().unwrap_or_else(|| "127.0.0.1".to_string()),
                self.port.unwrap_or_default(),
                self.database
                    .clone()
                    .unwrap_or_else(|| "<database>".to_string())
            ),
            DatabaseDriver::FirebirdUnsupported => {
                "Firebird ignorado nesta etapa por compatibilidade".to_string()
            }
        }
    }
}
