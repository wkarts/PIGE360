//! Banco offline criptografado do PIGE360.
//!
//! O arquivo é exclusivo por tenant/usuário e só é aberto após aplicação de
//! `PRAGMA key`. A presença de `cipher_version` é verificada para impedir que
//! uma build sem SQLCipher opere silenciosamente em texto aberto.

use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine as _};
use rusqlite::{params, Connection, OptionalExtension, TransactionBehavior};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::{fs, path::{Path, PathBuf}};
use thiserror::Error;
use time::OffsetDateTime;
use uuid::Uuid;

const SCHEMA_VERSION: i64 = 1;

/// Erros do banco offline.
#[derive(Debug, Error)]
pub enum OfflineDbError {
    /// Identificador inválido.
    #[error("identificador offline inválido")]
    InvalidIdentifier,
    /// Chave criptográfica inválida.
    #[error("chave do banco offline inválida")]
    InvalidKey,
    /// Build sem suporte efetivo a SQLCipher.
    #[error("SQLCipher indisponível nesta build")]
    SqlCipherUnavailable,
    /// Erro SQLite/SQLCipher.
    #[error("erro no banco offline: {0}")]
    Sql(#[from] rusqlite::Error),
    /// Erro de filesystem.
    #[error("erro no filesystem offline: {0}")]
    Io(#[from] std::io::Error),
    /// Erro de serialização.
    #[error("erro de serialização offline: {0}")]
    Json(#[from] serde_json::Error),
    /// Erro de base64 da chave.
    #[error("chave offline não é base64url válida")]
    Base64(#[from] base64::DecodeError),
}

/// Contexto físico do banco offline.
#[derive(Debug, Clone)]
pub struct OfflineDatabase {
    path: PathBuf,
    key_hex: String,
    tenant_id: String,
    user_id: String,
}

/// Operação pendente da outbox local.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OutboxRecord {
    /// Identificador interno.
    pub id: String,
    /// Chave idempotente preservada durante retries.
    pub idempotency_key: String,
    /// Tipo do agregado.
    pub aggregate_type: String,
    /// ID do agregado.
    pub aggregate_id: String,
    /// Revisão do servidor conhecida no momento da alteração.
    pub base_revision: i64,
    /// Payload JSON da operação.
    pub payload: Value,
    /// Quantidade de tentativas já realizadas.
    pub attempts: i64,
    /// Data de criação em UTC.
    pub created_at: String,
}

/// Registro de conflito explícito.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConflictRecord {
    /// Chave idempotente da operação original.
    pub idempotency_key: String,
    /// Revisão conhecida pelo cliente.
    pub local_revision: i64,
    /// Revisão recebida do servidor.
    pub server_revision: i64,
    /// Snapshot recebido do servidor.
    pub server_payload: Value,
    /// Política escolhida; inicialmente sempre manual.
    pub policy: String,
}

impl OfflineDatabase {
    /// Abre (ou cria) um banco por tenant/usuário.
    pub fn open(root: &Path, tenant_id: &str, user_id: &str, key_base64url: &str) -> Result<Self, OfflineDbError> {
        if !valid_id(tenant_id) || !valid_id(user_id) {
            return Err(OfflineDbError::InvalidIdentifier);
        }
        let key = URL_SAFE_NO_PAD.decode(key_base64url)?;
        if key.len() != 32 {
            return Err(OfflineDbError::InvalidKey);
        }
        let dir = root.join("offline").join(tenant_id).join(user_id);
        fs::create_dir_all(&dir)?;
        let database = Self {
            path: dir.join("pige360.db"),
            key_hex: hex::encode(key),
            tenant_id: tenant_id.to_owned(),
            user_id: user_id.to_owned(),
        };
        database.initialize()?;
        Ok(database)
    }

    /// Caminho físico do banco, útil apenas para diagnóstico nativo.
    #[must_use]
    pub fn path(&self) -> &Path { &self.path }

    fn connect(&self) -> Result<Connection, OfflineDbError> {
        let conn = Connection::open(&self.path)?;
        conn.pragma_update(None, "key", format!("x'{}'", self.key_hex))?;
        conn.pragma_update(None, "foreign_keys", "ON")?;
        conn.pragma_update(None, "journal_mode", "WAL")?;
        conn.pragma_update(None, "synchronous", "NORMAL")?;
        let cipher: Option<String> = conn.query_row("PRAGMA cipher_version", [], |row| row.get(0)).optional()?;
        if cipher.as_deref().unwrap_or_default().trim().is_empty() {
            return Err(OfflineDbError::SqlCipherUnavailable);
        }
        Ok(conn)
    }

    fn initialize(&self) -> Result<(), OfflineDbError> {
        let mut conn = self.connect()?;
        let tx = conn.transaction_with_behavior(TransactionBehavior::Immediate)?;
        tx.execute_batch(r#"
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS authorized_cache(
              cache_key TEXT PRIMARY KEY,
              payload_json TEXT NOT NULL,
              server_revision INTEGER NOT NULL DEFAULT 0,
              expires_at TEXT,
              sha256 TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS outbox(
              id TEXT PRIMARY KEY,
              idempotency_key TEXT NOT NULL UNIQUE,
              aggregate_type TEXT NOT NULL,
              aggregate_id TEXT NOT NULL,
              base_revision INTEGER NOT NULL DEFAULT 0,
              payload_json TEXT NOT NULL,
              attempts INTEGER NOT NULL DEFAULT 0,
              next_attempt_at TEXT,
              last_error TEXT,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS inbox(
              event_id TEXT PRIMARY KEY,
              event_type TEXT NOT NULL,
              payload_sha256 TEXT NOT NULL,
              received_at TEXT NOT NULL,
              processed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS conflicts(
              id TEXT PRIMARY KEY,
              idempotency_key TEXT NOT NULL UNIQUE,
              local_revision INTEGER NOT NULL,
              server_revision INTEGER NOT NULL,
              server_payload_json TEXT NOT NULL,
              policy TEXT NOT NULL DEFAULT 'manual',
              resolved_at TEXT,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tombstones(
              aggregate_type TEXT NOT NULL,
              aggregate_id TEXT NOT NULL,
              revision INTEGER NOT NULL,
              deleted_at TEXT NOT NULL,
              PRIMARY KEY(aggregate_type, aggregate_id)
            );
            CREATE TABLE IF NOT EXISTS checkpoints(
              stream TEXT PRIMARY KEY,
              revision INTEGER NOT NULL,
              cursor TEXT,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS print_spool(
              id TEXT PRIMARY KEY,
              idempotency_key TEXT NOT NULL UNIQUE,
              document_type TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              state TEXT NOT NULL,
              attempts INTEGER NOT NULL DEFAULT 0,
              error TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
        "#)?;
        tx.execute("INSERT INTO meta(key,value) VALUES('schema_version',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", [SCHEMA_VERSION.to_string()])?;
        tx.execute("INSERT INTO meta(key,value) VALUES('tenant_id',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", [&self.tenant_id])?;
        tx.execute("INSERT INTO meta(key,value) VALUES('user_id',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", [&self.user_id])?;
        tx.commit()?;
        Ok(())
    }

    /// Grava um item de cache autorizado com hash de integridade.
    pub fn cache_put(&self, key: &str, payload: &Value, server_revision: i64, expires_at: Option<&str>) -> Result<(), OfflineDbError> {
        let raw = serde_json::to_string(payload)?;
        let sha = sha256(raw.as_bytes());
        let now = now();
        self.connect()?.execute(
            "INSERT INTO authorized_cache(cache_key,payload_json,server_revision,expires_at,sha256,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(cache_key) DO UPDATE SET payload_json=excluded.payload_json,server_revision=excluded.server_revision,expires_at=excluded.expires_at,sha256=excluded.sha256,updated_at=excluded.updated_at",
            params![key, raw, server_revision, expires_at, sha, now],
        )?;
        Ok(())
    }

    /// Recupera um item e verifica o hash antes de desserializar.
    pub fn cache_get(&self, key: &str) -> Result<Option<Value>, OfflineDbError> {
        let row: Option<(String, String, Option<String>)> = self.connect()?.query_row(
            "SELECT payload_json,sha256,expires_at FROM authorized_cache WHERE cache_key=?",
            [key], |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)),
        ).optional()?;
        let Some((raw, expected, expires_at)) = row else { return Ok(None); };
        if expected != sha256(raw.as_bytes()) { return Ok(None); }
        if let Some(exp) = expires_at {
            if exp < now() { return Ok(None); }
        }
        Ok(Some(serde_json::from_str(&raw)?))
    }

    /// Enfileira operação idempotente. Reuso da chave com conteúdo diferente é erro.
    pub fn outbox_enqueue(&self, idempotency_key: &str, aggregate_type: &str, aggregate_id: &str, base_revision: i64, payload: &Value) -> Result<(), OfflineDbError> {
        let conn = self.connect()?;
        let existing: Option<String> = conn.query_row("SELECT payload_json FROM outbox WHERE idempotency_key=?", [idempotency_key], |r| r.get(0)).optional()?;
        let raw = serde_json::to_string(payload)?;
        if let Some(value) = existing {
            if value == raw { return Ok(()); }
            return Err(OfflineDbError::Sql(rusqlite::Error::InvalidQuery));
        }
        conn.execute(
            "INSERT INTO outbox(id,idempotency_key,aggregate_type,aggregate_id,base_revision,payload_json,created_at) VALUES(?,?,?,?,?,?,?)",
            params![Uuid::new_v4().to_string(), idempotency_key, aggregate_type, aggregate_id, base_revision, raw, now()],
        )?;
        Ok(())
    }

    /// Lista operações prontas para envio em ordem estável.
    pub fn outbox_pending(&self, limit: usize) -> Result<Vec<OutboxRecord>, OfflineDbError> {
        let conn = self.connect()?;
        let mut stmt = conn.prepare("SELECT id,idempotency_key,aggregate_type,aggregate_id,base_revision,payload_json,attempts,created_at FROM outbox WHERE next_attempt_at IS NULL OR next_attempt_at<=? ORDER BY created_at,id LIMIT ?")?;
        let current = now();
        let rows = stmt.query_map(params![current, i64::try_from(limit.min(500)).unwrap_or(500)], |r| {
            Ok((r.get::<_,String>(0)?,r.get::<_,String>(1)?,r.get::<_,String>(2)?,r.get::<_,String>(3)?,r.get::<_,i64>(4)?,r.get::<_,String>(5)?,r.get::<_,i64>(6)?,r.get::<_,String>(7)?))
        })?;
        let mut out = Vec::new();
        for row in rows {
            let (id,key,kind,aggregate,revision,payload,attempts,created_at)=row?;
            out.push(OutboxRecord { id, idempotency_key:key, aggregate_type:kind, aggregate_id:aggregate, base_revision:revision, payload:serde_json::from_str(&payload)?, attempts, created_at });
        }
        Ok(out)
    }

    /// Confirma envio e remove a operação local.
    pub fn outbox_ack(&self, idempotency_key: &str) -> Result<bool, OfflineDbError> {
        Ok(self.connect()?.execute("DELETE FROM outbox WHERE idempotency_key=?", [idempotency_key])? > 0)
    }

    /// Registra falha e agenda retry exponencial com teto de uma hora.
    pub fn outbox_fail(&self, idempotency_key: &str, error: &str) -> Result<(), OfflineDbError> {
        let conn = self.connect()?;
        let attempts: i64 = conn.query_row("SELECT attempts FROM outbox WHERE idempotency_key=?", [idempotency_key], |r| r.get(0))?;
        let next_attempt = attempts.saturating_add(1);
        let delay = 2_i64.saturating_pow(u32::try_from(next_attempt.min(10)).unwrap_or(10)).min(3600);
        let when = OffsetDateTime::now_utc().saturating_add(time::Duration::seconds(delay)).format(&time::format_description::well_known::Rfc3339).unwrap_or_default();
        conn.execute("UPDATE outbox SET attempts=?,next_attempt_at=?,last_error=? WHERE idempotency_key=?", params![next_attempt, when, truncate(error, 1000), idempotency_key])?;
        Ok(())
    }

    /// Persiste um conflito sem aplicar merge implícito.
    pub fn conflict_put(&self, conflict: &ConflictRecord) -> Result<(), OfflineDbError> {
        self.connect()?.execute(
            "INSERT INTO conflicts(id,idempotency_key,local_revision,server_revision,server_payload_json,policy,created_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(idempotency_key) DO UPDATE SET server_revision=excluded.server_revision,server_payload_json=excluded.server_payload_json,policy='manual',resolved_at=NULL",
            params![Uuid::new_v4().to_string(), conflict.idempotency_key, conflict.local_revision, conflict.server_revision, serde_json::to_string(&conflict.server_payload)?, conflict.policy, now()],
        )?;
        Ok(())
    }

    /// Lê um checkpoint de sincronização.
    pub fn checkpoint_get(&self, stream: &str) -> Result<Option<(i64, Option<String>)>, OfflineDbError> {
        Ok(self.connect()?.query_row("SELECT revision,cursor FROM checkpoints WHERE stream=?", [stream], |r| Ok((r.get(0)?,r.get(1)?))).optional()?)
    }

    /// Atualiza checkpoint monotonicamente.
    pub fn checkpoint_set(&self, stream: &str, revision: i64, cursor: Option<&str>) -> Result<(), OfflineDbError> {
        self.connect()?.execute(
            "INSERT INTO checkpoints(stream,revision,cursor,updated_at) VALUES(?,?,?,?) ON CONFLICT(stream) DO UPDATE SET revision=CASE WHEN excluded.revision>=checkpoints.revision THEN excluded.revision ELSE checkpoints.revision END,cursor=CASE WHEN excluded.revision>=checkpoints.revision THEN excluded.cursor ELSE checkpoints.cursor END,updated_at=excluded.updated_at",
            params![stream,revision,cursor,now()],
        )?;
        Ok(())
    }

    /// Remove dados locais; usado no logout/revogação quando a política exigir.
    pub fn purge(self) -> Result<(), OfflineDbError> {
        if self.path.exists() { fs::remove_file(&self.path)?; }
        for suffix in ["-wal", "-shm"] {
            let sidecar = PathBuf::from(format!("{}{}", self.path.display(), suffix));
            if sidecar.exists() { let _ = fs::remove_file(sidecar); }
        }
        Ok(())
    }
}

fn valid_id(value: &str) -> bool {
    !value.is_empty() && value.len() <= 128 && value.bytes().all(|b| b.is_ascii_alphanumeric() || matches!(b,b'-'|b'_'))
}

fn now() -> String {
    OffsetDateTime::now_utc().format(&time::format_description::well_known::Rfc3339).unwrap_or_else(|_| "1970-01-01T00:00:00Z".into())
}

fn sha256(bytes: &[u8]) -> String { hex::encode(Sha256::digest(bytes)) }
fn truncate(value: &str, max: usize) -> String { value.chars().take(max).collect() }

#[cfg(test)]
mod tests {
    use super::valid_id;
    #[test]
    fn identifiers_reject_traversal() { assert!(!valid_id("../tenant")); assert!(valid_id("019abc-def")); }
}
