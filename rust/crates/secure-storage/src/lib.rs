//! Cofre de credenciais do PIGE360.
//!
//! A implementação usa o credential vault nativo exposto pela crate `keyring`
//! (Credential Manager no Windows, Keychain no macOS/iOS e Secret Service no
//! Linux). Nenhum segredo administrativo é embutido no binário.

use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine as _};
use keyring::Entry;
use rand::{rngs::OsRng, RngCore};
use serde::{Deserialize, Serialize};
use thiserror::Error;

const SERVICE: &str = "br.com.argws.pige360";

/// Erros da fronteira de armazenamento seguro.
#[derive(Debug, Error)]
pub enum SecureStorageError {
    /// Identificador inválido para compor uma chave lógica.
    #[error("identificador seguro inválido")]
    InvalidIdentifier,
    /// Erro retornado pelo cofre nativo.
    #[error("falha no cofre nativo: {0}")]
    Keyring(#[from] keyring::Error),
}

/// Escopo lógico de um segredo.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SecretScope {
    /// Tenant imutável.
    pub tenant_id: String,
    /// Usuário local associado ao segredo.
    pub user_id: String,
    /// Nome funcional, por exemplo `session` ou `offline-db-key`.
    pub name: String,
}

impl SecretScope {
    /// Cria um escopo validando os componentes contra path/key injection.
    pub fn new(tenant_id: impl Into<String>, user_id: impl Into<String>, name: impl Into<String>) -> Result<Self, SecureStorageError> {
        let value = Self { tenant_id: tenant_id.into(), user_id: user_id.into(), name: name.into() };
        if [&value.tenant_id, &value.user_id, &value.name].iter().all(|part| valid_component(part)) {
            Ok(value)
        } else {
            Err(SecureStorageError::InvalidIdentifier)
        }
    }

    fn account(&self) -> String {
        format!("{}:{}:{}", self.tenant_id, self.user_id, self.name)
    }
}

fn valid_component(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 180
        && value.bytes().all(|b| b.is_ascii_alphanumeric() || matches!(b, b'-' | b'_' | b'.' | b'@'))
}

fn entry(scope: &SecretScope) -> Result<Entry, SecureStorageError> {
    Ok(Entry::new(SERVICE, &scope.account())?)
}

/// Armazena ou substitui um segredo no cofre nativo.
pub fn put(scope: &SecretScope, value: &str) -> Result<(), SecureStorageError> {
    entry(scope)?.set_password(value)?;
    Ok(())
}

/// Recupera um segredo; ausência retorna `Ok(None)`.
pub fn get(scope: &SecretScope) -> Result<Option<String>, SecureStorageError> {
    match entry(scope)?.get_password() {
        Ok(value) => Ok(Some(value)),
        Err(keyring::Error::NoEntry) => Ok(None),
        Err(error) => Err(error.into()),
    }
}

/// Remove um segredo de forma idempotente.
pub fn delete(scope: &SecretScope) -> Result<(), SecureStorageError> {
    match entry(scope)?.delete_credential() {
        Ok(()) | Err(keyring::Error::NoEntry) => Ok(()),
        Err(error) => Err(error.into()),
    }
}

/// Retorna um segredo aleatório de 256 bits, criando-o apenas na primeira vez.
pub fn get_or_create_256_bit_key(scope: &SecretScope) -> Result<String, SecureStorageError> {
    if let Some(value) = get(scope)? {
        return Ok(value);
    }
    let mut bytes = [0_u8; 32];
    OsRng.fill_bytes(&mut bytes);
    let value = URL_SAFE_NO_PAD.encode(bytes);
    put(scope, &value)?;
    Ok(value)
}

#[cfg(test)]
mod tests {
    use super::SecretScope;

    #[test]
    fn rejects_unsafe_scope() {
        assert!(SecretScope::new("tenant", "../user", "session").is_err());
        assert!(SecretScope::new("tenant", "user", "offline-db-key").is_ok());
    }
}
