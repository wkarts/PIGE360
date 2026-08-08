//! Verificação de snapshot fiscal para operação offline.

use base64::{engine::general_purpose::STANDARD, Engine as _};
use ed25519_dalek::{Signature, Verifier, VerifyingKey};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use thiserror::Error;
use time::OffsetDateTime;

/// Envelope fiscal assinado pelo servidor.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FiscalSnapshot {
    /// Tenant ao qual o snapshot pertence.
    pub tenant_id: String,
    /// Versão monotônica do catálogo/ruleset.
    pub revision: i64,
    /// Emissão UTC RFC3339.
    pub issued_at: String,
    /// Validade UTC RFC3339.
    pub expires_at: String,
    /// Regras/catálogos necessários ao fluxo offline.
    pub payload: Value,
    /// SHA-256 hexadecimal da representação canônica do payload.
    pub payload_sha256: String,
    /// Assinatura Ed25519 em Base64 da mensagem canônica.
    pub signature: String,
}

/// Erros de validação do snapshot.
#[derive(Debug, Error)]
pub enum FiscalSnapshotError {
    /// Tenant diverge do aplicativo fixado.
    #[error("snapshot pertence a outro tenant")]
    TenantMismatch,
    /// Snapshot expirado.
    #[error("snapshot fiscal expirado")]
    Expired,
    /// Hash não corresponde ao payload.
    #[error("hash do snapshot fiscal inválido")]
    InvalidHash,
    /// Chave pública inválida.
    #[error("chave Ed25519 inválida")]
    InvalidPublicKey,
    /// Assinatura inválida.
    #[error("assinatura do snapshot fiscal inválida")]
    InvalidSignature,
    /// Serialização inválida.
    #[error("snapshot fiscal malformado")]
    InvalidPayload,
}

/// Valida tenant, validade, hash e assinatura Ed25519.
pub fn verify(snapshot: &FiscalSnapshot, expected_tenant: &str, public_key_base64: &str) -> Result<(), FiscalSnapshotError> {
    if snapshot.tenant_id != expected_tenant { return Err(FiscalSnapshotError::TenantMismatch); }
    let expires = OffsetDateTime::parse(&snapshot.expires_at, &time::format_description::well_known::Rfc3339).map_err(|_| FiscalSnapshotError::InvalidPayload)?;
    if expires <= OffsetDateTime::now_utc() { return Err(FiscalSnapshotError::Expired); }
    let payload_raw = canonical_json(&snapshot.payload)?;
    let payload_hash = hex::encode(Sha256::digest(payload_raw.as_bytes()));
    if !constant_time_eq(&payload_hash, &snapshot.payload_sha256) { return Err(FiscalSnapshotError::InvalidHash); }
    let message = format!("{}\n{}\n{}\n{}\n{}", snapshot.tenant_id, snapshot.revision, snapshot.issued_at, snapshot.expires_at, snapshot.payload_sha256);
    let public = STANDARD.decode(public_key_base64).map_err(|_| FiscalSnapshotError::InvalidPublicKey)?;
    let key_bytes: [u8;32] = public.try_into().map_err(|_| FiscalSnapshotError::InvalidPublicKey)?;
    let key = VerifyingKey::from_bytes(&key_bytes).map_err(|_| FiscalSnapshotError::InvalidPublicKey)?;
    let signature_raw = STANDARD.decode(&snapshot.signature).map_err(|_| FiscalSnapshotError::InvalidSignature)?;
    let signature = Signature::from_slice(&signature_raw).map_err(|_| FiscalSnapshotError::InvalidSignature)?;
    key.verify(message.as_bytes(), &signature).map_err(|_| FiscalSnapshotError::InvalidSignature)
}

fn canonical_json(value: &Value) -> Result<String, FiscalSnapshotError> {
    serde_json::to_string(value).map_err(|_| FiscalSnapshotError::InvalidPayload)
}

fn constant_time_eq(a: &str, b: &str) -> bool {
    if a.len() != b.len() { return false; }
    a.as_bytes().iter().zip(b.as_bytes()).fold(0_u8, |acc,(x,y)| acc | (x ^ y)) == 0
}
