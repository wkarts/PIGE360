use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IntegrationModuleStatus {
    pub enabled: bool,
    pub status: String,
}

pub fn module_status() -> IntegrationModuleStatus {
    IntegrationModuleStatus {
        enabled: true,
        status: "available".to_string(),
    }
}
