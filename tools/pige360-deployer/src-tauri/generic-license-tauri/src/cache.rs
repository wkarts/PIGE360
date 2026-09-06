use std::path::PathBuf;

use chrono::{FixedOffset, Utc};
use directories::ProjectDirs;
use tokio::fs;

use crate::error::LicenseError;
use crate::models::{CachedLicenseFile, LicenseApiResponse, LicenseDecision};

pub struct OfflineCache {
    namespace: String,
}

impl OfflineCache {
    pub fn new(namespace: impl Into<String>) -> Self {
        Self {
            namespace: namespace.into(),
        }
    }

    pub async fn put_payload(
        &self,
        document: &str,
        payload: &LicenseApiResponse,
    ) -> Result<(), LicenseError> {
        self.write(
            document,
            CachedLicenseFile {
                cached_at: Utc::now().with_timezone(&FixedOffset::east_opt(0).unwrap()),
                decision: None,
                payload: Some(payload.clone()),
            },
        )
        .await
    }

    pub async fn put_decision(
        &self,
        document: &str,
        decision: &LicenseDecision,
    ) -> Result<(), LicenseError> {
        self.write(
            document,
            CachedLicenseFile {
                cached_at: Utc::now().with_timezone(&FixedOffset::east_opt(0).unwrap()),
                decision: Some(decision.clone()),
                payload: None,
            },
        )
        .await
    }

    pub async fn get(&self, document: &str) -> Result<Option<CachedLicenseFile>, LicenseError> {
        let path = self.file_path(document)?;

        if !path.exists() {
            return Ok(None);
        }

        let contents = fs::read_to_string(path)
            .await
            .map_err(|e| LicenseError::Io(e.to_string()))?;

        let decoded = serde_json::from_str::<CachedLicenseFile>(&contents)
            .map_err(|e| LicenseError::Serde(e.to_string()))?;

        Ok(Some(decoded))
    }

    async fn write(&self, document: &str, cached: CachedLicenseFile) -> Result<(), LicenseError> {
        let path = self.file_path(document)?;
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)
                .await
                .map_err(|e| LicenseError::Io(e.to_string()))?;
        }

        let json = serde_json::to_string_pretty(&cached)
            .map_err(|e| LicenseError::Serde(e.to_string()))?;

        fs::write(path, json)
            .await
            .map_err(|e| LicenseError::Io(e.to_string()))?;

        Ok(())
    }

    fn file_path(&self, document: &str) -> Result<PathBuf, LicenseError> {
        let dirs = ProjectDirs::from("br", "argws", "generic-license").ok_or_else(|| {
            LicenseError::Io("não foi possível resolver o diretório de dados do app".to_string())
        })?;

        let mut path = dirs.data_local_dir().to_path_buf();
        path.push("offline");
        path.push(&self.namespace);
        path.push(format!("{}.json", sha_file_name(document)));
        Ok(path)
    }
}

fn sha_file_name(document: &str) -> String {
    use sha2::{Digest, Sha256};
    let mut hasher = Sha256::new();
    hasher.update(document.as_bytes());
    hex::encode(hasher.finalize())
}
