use std::path::PathBuf;

use super::config::InternalApiConfig;

#[derive(Debug, Clone)]
pub struct InternalApiState {
    pub db_path: PathBuf,
    pub data_dir: PathBuf,
    pub started_at: String,
    pub host: String,
    pub port: u16,
    pub config: InternalApiConfig,
}
