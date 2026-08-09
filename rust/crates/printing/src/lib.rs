//! Contratos de impressão local.
//!
//! O spool é persistido pelo banco offline; a execução física permanece
//! desacoplada para permitir drivers do SO, ESC/POS ou PDF sem mudar o domínio.

use pige360_offline_database::{OfflineDatabase, OfflineDbError};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use thiserror::Error;

/// Trabalho de impressão.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PrintJob {
    /// Chave idempotente definida pelo fluxo de negócio.
    pub idempotency_key: String,
    /// Tipo: receipt, report, label, fiscal_auxiliary etc.
    pub document_type: String,
    /// Payload tipado pelo renderer/driver selecionado.
    pub payload: Value,
}

/// Erros do spool.
#[derive(Debug, Error)]
pub enum PrintingError {
    /// Falha de persistência local.
    #[error(transparent)]
    Database(#[from] OfflineDbError),
}

/// Enfileira a impressão como uma operação offline idempotente.
pub fn enqueue(database: &OfflineDatabase, job: &PrintJob) -> Result<(), PrintingError> {
    database.outbox_enqueue(
        &format!("print:{}", job.idempotency_key),
        "print_job",
        &job.idempotency_key,
        0,
        &json!({"document_type":job.document_type,"payload":job.payload}),
    )?;
    Ok(())
}
