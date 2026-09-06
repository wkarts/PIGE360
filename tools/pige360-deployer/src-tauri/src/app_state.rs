use std::{
    path::PathBuf,
    sync::{Arc, RwLock},
};

use serde::{Deserialize, Serialize};

use crate::{bootstrap, legacy_data, migrations, storage_contract};

#[derive(Debug, Clone)]
pub struct AppContext {
    pub data_dir: PathBuf,
    pub db_path: PathBuf,
}

#[derive(Debug, Default, Clone, Serialize, Deserialize)]
struct BootstrapConfig {
    pub data_dir_override: Option<String>,
}

#[derive(Clone)]
pub struct SharedState {
    inner: Arc<RwLock<Option<AppContext>>>,
}

impl SharedState {
    pub fn new() -> Self {
        Self {
            inner: Arc::new(RwLock::new(None)),
        }
    }

    pub fn init(&self) -> Result<(), String> {
        let data_dir = Self::resolve_data_dir()?;
        self.init_with_data_dir(data_dir)
    }

    pub fn init_with_data_dir(&self, data_dir: PathBuf) -> Result<(), String> {
        std::fs::create_dir_all(&data_dir)
            .map_err(|err| format!("Falha ao criar diretório de dados: {err}"))?;

        let db_path = storage_contract::sqlite_database_path(&data_dir);
        let recovery = legacy_data::prepare(&data_dir, &db_path)?;
        let preserved_legacy_credentials = recovery
            .as_ref()
            .map(legacy_data::DatabaseRecovery::preserved_user_credentials)
            .transpose()?
            .unwrap_or(false);
        let mut legacy_credential_restored = false;
        if let Err(error) = legacy_data::restore_rotated_legacy_credential(&data_dir, &db_path)
            .and_then(|restored| {
                legacy_credential_restored = restored;
                migrations::migrate(&db_path)
            })
            .and_then(|_| legacy_data::finalize(&data_dir, &db_path, recovery.as_ref()))
        {
            let rollback_error = legacy_data::rollback(&db_path, recovery.as_ref()).err();
            return Err(match rollback_error {
                Some(rollback_error) => format!(
                    "Falha ao preparar o banco do PIGE360 Deployer: {error}. O rollback também falhou: {rollback_error}"
                ),
                None => format!(
                    "Falha ao preparar o banco do PIGE360 Deployer: {error}. O estado anterior foi restaurado."
                ),
            });
        }
        if preserved_legacy_credentials || legacy_credential_restored {
            if let Err(error) = bootstrap::remove_after_password_change(&db_path) {
                eprintln!(
                    "Aviso: os dados e a credencial legados foram preservados, mas o arquivo bootstrap obsoleto não pôde ser removido: {error}"
                );
            }
        }

        let mut guard = self
            .inner
            .write()
            .map_err(|_| "Falha ao obter lock de escrita do estado.".to_string())?;

        *guard = Some(AppContext { data_dir, db_path });
        Ok(())
    }

    pub fn reconfigure_data_dir(&self, data_dir: PathBuf) -> Result<(), String> {
        self.init_with_data_dir(data_dir)
    }

    pub fn data_dir(&self) -> Result<PathBuf, String> {
        let guard = self
            .inner
            .read()
            .map_err(|_| "Falha ao obter lock de leitura do estado.".to_string())?;

        guard
            .as_ref()
            .map(|ctx| ctx.data_dir.clone())
            .ok_or_else(|| "Aplicação ainda não inicializada.".to_string())
    }

    pub fn db_path(&self) -> Result<PathBuf, String> {
        let guard = self
            .inner
            .read()
            .map_err(|_| "Falha ao obter lock de leitura do estado.".to_string())?;

        guard
            .as_ref()
            .map(|ctx| ctx.db_path.clone())
            .ok_or_else(|| "Aplicação ainda não inicializada.".to_string())
    }

    pub fn bootstrap_config_path() -> Result<PathBuf, String> {
        let config_dir = dirs::config_local_dir()
            .or_else(|| std::env::current_dir().ok())
            .ok_or_else(|| "Não foi possível resolver o diretório de configuração.".to_string())?
            .join(runtime_app_local_data_dir());
        std::fs::create_dir_all(&config_dir)
            .map_err(|err| format!("Falha ao criar diretório de configuração: {err}"))?;
        Ok(config_dir.join("bootstrap.json"))
    }

    fn load_bootstrap_config() -> Result<BootstrapConfig, String> {
        let path = Self::bootstrap_config_path()?;
        if !path.exists() {
            return Ok(BootstrapConfig::default());
        }
        let raw = std::fs::read_to_string(&path)
            .map_err(|err| format!("Falha ao ler bootstrap config: {err}"))?;
        serde_json::from_str::<BootstrapConfig>(&raw)
            .map_err(|err| format!("Falha ao interpretar bootstrap config: {err}"))
    }

    pub fn save_bootstrap_config(config: &serde_json::Value) -> Result<PathBuf, String> {
        let path = Self::bootstrap_config_path()?;
        let json = serde_json::to_string_pretty(config)
            .map_err(|err| format!("Falha ao serializar bootstrap config: {err}"))?;
        std::fs::write(&path, json)
            .map_err(|err| format!("Falha ao salvar bootstrap config: {err}"))?;
        Ok(path)
    }

    fn resolve_data_dir() -> Result<PathBuf, String> {
        let config = Self::load_bootstrap_config()?;
        if let Some(override_dir) = config.data_dir_override {
            let trimmed = override_dir.trim();
            if !trimmed.is_empty() {
                return Ok(PathBuf::from(trimmed));
            }
        }

        dirs::data_local_dir()
            .or_else(|| std::env::current_dir().ok())
            .map(|path| path.join(runtime_app_local_data_dir()))
            .ok_or_else(|| "Não foi possível resolver o diretório de dados.".to_string())
    }
}

fn runtime_app_local_data_dir() -> String {
    std::env::var("PIGE360_DEPLOYER_LOCAL_DATA_DIR")
        .or_else(|_| std::env::var("APP_LOCAL_DATA_DIR"))
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| storage_contract::CURRENT_LOCAL_DATA_DIR.to_string())
}
