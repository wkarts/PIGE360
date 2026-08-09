//! Identidade persistente do dispositivo.

use pige360_secure_storage::{get, put, SecretScope, SecureStorageError};
use serde::{Deserialize, Serialize};
use thiserror::Error;
use uuid::Uuid;

/// Erros da identidade local.
#[derive(Debug, Error)]
pub enum DeviceIdentityError {
    /// Falha do cofre nativo.
    #[error(transparent)]
    Storage(#[from] SecureStorageError),
}

/// Identidade técnica que pode ser enviada em auditoria e sync.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct DeviceIdentity {
    /// UUID gerado uma única vez por tenant/usuário nesta instalação.
    pub device_id: String,
    /// Tenant fixado.
    pub tenant_id: String,
    /// Usuário fixado.
    pub user_id: String,
}

/// Obtém ou cria uma identidade estável no cofre do sistema operacional.
pub fn get_or_create(tenant_id: &str, user_id: &str) -> Result<DeviceIdentity, DeviceIdentityError> {
    let scope = SecretScope::new(tenant_id, user_id, "device-id")?;
    let device_id = if let Some(value) = get(&scope)? { value } else {
        let value = Uuid::new_v4().to_string();
        put(&scope, &value)?;
        value
    };
    Ok(DeviceIdentity { device_id, tenant_id: tenant_id.to_owned(), user_id: user_id.to_owned() })
}
