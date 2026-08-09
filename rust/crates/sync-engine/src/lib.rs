//! Motor de sincronização offline do PIGE360.

use pige360_offline_database::{ConflictRecord, OfflineDatabase, OfflineDbError, OutboxRecord};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use thiserror::Error;

/// Resultado que o transporte HTTP deve devolver ao motor.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "status", rename_all = "snake_case")]
pub enum PushResult {
    /// Operação aceita pelo servidor.
    Accepted { server_revision: i64 },
    /// O servidor já processou a mesma chave idempotente.
    Duplicate { server_revision: i64 },
    /// Existe conflito de revisão e ele deve ser resolvido explicitamente.
    Conflict { server_revision: i64, server_payload: Value },
    /// Falha transitória, apta a retry.
    Retryable { message: String },
    /// Falha permanente de validação/autorização.
    Rejected { message: String },
}

/// Erro do motor.
#[derive(Debug, Error)]
pub enum SyncError {
    /// Erro de persistência offline.
    #[error(transparent)]
    Database(#[from] OfflineDbError),
}

/// Ação resultante do processamento de uma resposta.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum SyncAction { Acknowledged, ConflictStored, RetryScheduled, Rejected }

/// Lista operações locais prontas para o transporte.
pub fn pending(database: &OfflineDatabase, limit: usize) -> Result<Vec<OutboxRecord>, SyncError> {
    Ok(database.outbox_pending(limit)?)
}

/// Aplica a resposta do servidor sem sobrescrever conflitos silenciosamente.
pub fn apply_result(database: &OfflineDatabase, operation: &OutboxRecord, result: PushResult) -> Result<SyncAction, SyncError> {
    match result {
        PushResult::Accepted { .. } | PushResult::Duplicate { .. } => {
            database.outbox_ack(&operation.idempotency_key)?;
            Ok(SyncAction::Acknowledged)
        }
        PushResult::Conflict { server_revision, server_payload } => {
            database.conflict_put(&ConflictRecord {
                idempotency_key: operation.idempotency_key.clone(),
                local_revision: operation.base_revision,
                server_revision,
                server_payload,
                policy: "manual".into(),
            })?;
            database.outbox_ack(&operation.idempotency_key)?;
            Ok(SyncAction::ConflictStored)
        }
        PushResult::Retryable { message } => {
            database.outbox_fail(&operation.idempotency_key, &message)?;
            Ok(SyncAction::RetryScheduled)
        }
        PushResult::Rejected { .. } => Ok(SyncAction::Rejected),
    }
}
