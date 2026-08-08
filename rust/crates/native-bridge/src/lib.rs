//! Comandos Tauri do PIGE360.
//!
//! Esta crate centraliza a fronteira nativa para impedir que cada aplicativo
//! implemente sua própria política de segredo/offline.

use pige360_device_identity::get_or_create as get_or_create_device;
use pige360_fiscal_snapshot::{verify as verify_snapshot, FiscalSnapshot};
use pige360_offline_database::OfflineDatabase;
use pige360_printing::{enqueue as enqueue_print, PrintJob};
use pige360_secure_storage::{delete, get, get_or_create_256_bit_key, put, SecretScope};
use pige360_sync_engine::{apply_result, pending, PushResult};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::path::PathBuf;
use tauri::{AppHandle, Manager};

/// Resposta padronizada de identidade/disco offline.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NativeOfflineContext {
    /// ID estável do dispositivo.
    pub device_id: String,
    /// Caminho do banco local (diagnóstico; não contém a chave).
    pub database_path: String,
}

fn scope(tenant_id: &str, user_id: &str, name: &str) -> Result<SecretScope, String> {
    SecretScope::new(tenant_id, user_id, name).map_err(|e| e.to_string())
}

fn app_root(app: &AppHandle) -> Result<PathBuf, String> {
    app.path().app_data_dir().map_err(|e| e.to_string())
}

fn database(app: &AppHandle, tenant_id: &str, user_id: &str) -> Result<OfflineDatabase, String> {
    let key_scope = scope(tenant_id, user_id, "offline-db-key")?;
    let key = get_or_create_256_bit_key(&key_scope).map_err(|e| e.to_string())?;
    OfflineDatabase::open(&app_root(app)?, tenant_id, user_id, &key).map_err(|e| e.to_string())
}

/// Armazena a sessão autenticada no credential vault do SO e registra o usuário ativo.
#[tauri::command]
pub fn secure_session_put(tenant_id: String, user_id: String, value: String) -> Result<(), String> {
    put(&scope(&tenant_id, &user_id, "session")?, &value).map_err(|e| e.to_string())?;
    put(&scope(&tenant_id, "_app", "active-user")?, &user_id).map_err(|e| e.to_string())
}

/// Recupera a sessão ativa do tenant sem exigir que o WebView persista o `user_id`.
#[tauri::command]
pub fn secure_session_get(tenant_id: String) -> Result<Option<String>, String> {
    let Some(user_id) = get(&scope(&tenant_id, "_app", "active-user")?).map_err(|e| e.to_string())? else { return Ok(None); };
    get(&scope(&tenant_id, &user_id, "session")?).map_err(|e| e.to_string())
}

/// Remove a sessão ativa e o ponteiro do usuário no cofre nativo.
#[tauri::command]
pub fn secure_session_delete(tenant_id: String) -> Result<(), String> {
    let pointer = scope(&tenant_id, "_app", "active-user")?;
    if let Some(user_id) = get(&pointer).map_err(|e| e.to_string())? {
        delete(&scope(&tenant_id, &user_id, "session")?).map_err(|e| e.to_string())?;
    }
    delete(&pointer).map_err(|e| e.to_string())
}

/// Inicializa SQLCipher e devolve a identidade do dispositivo.
#[tauri::command]
pub fn offline_initialize(app: AppHandle, tenant_id: String, user_id: String) -> Result<NativeOfflineContext, String> {
    let db = database(&app, &tenant_id, &user_id)?;
    let identity = get_or_create_device(&tenant_id, &user_id).map_err(|e| e.to_string())?;
    Ok(NativeOfflineContext { device_id: identity.device_id, database_path: db.path().display().to_string() })
}

/// Enfileira alteração offline usando a mesma chave idempotente que será enviada à API.
#[tauri::command]
pub fn offline_outbox_enqueue(app: AppHandle, tenant_id: String, user_id: String, idempotency_key: String, aggregate_type: String, aggregate_id: String, base_revision: i64, payload: Value) -> Result<(), String> {
    database(&app,&tenant_id,&user_id)?.outbox_enqueue(&idempotency_key,&aggregate_type,&aggregate_id,base_revision,&payload).map_err(|e| e.to_string())
}

/// Lista o próximo lote da outbox.
#[tauri::command]
pub fn offline_outbox_pending(app: AppHandle, tenant_id: String, user_id: String, limit: usize) -> Result<Value, String> {
    let items = pending(&database(&app,&tenant_id,&user_id)?, limit).map_err(|e| e.to_string())?;
    serde_json::to_value(items).map_err(|e| e.to_string())
}

/// Aplica resultado de sincronização e preserva conflito explicitamente.
#[tauri::command]
pub fn offline_outbox_apply_result(app: AppHandle, tenant_id: String, user_id: String, idempotency_key: String, result: PushResult) -> Result<String, String> {
    let db=database(&app,&tenant_id,&user_id)?;
    let operation=db.outbox_pending(500).map_err(|e|e.to_string())?.into_iter().find(|x|x.idempotency_key==idempotency_key).ok_or_else(||"operação offline não localizada".to_string())?;
    let action=apply_result(&db,&operation,result).map_err(|e|e.to_string())?;
    serde_json::to_string(&action).map_err(|e|e.to_string())
}

/// Lê item do cache autorizado.
#[tauri::command]
pub fn offline_cache_get(app: AppHandle, tenant_id: String, user_id: String, cache_key: String) -> Result<Option<Value>, String> {
    database(&app,&tenant_id,&user_id)?.cache_get(&cache_key).map_err(|e|e.to_string())
}

/// Grava item do cache autorizado.
#[tauri::command]
pub fn offline_cache_put(app: AppHandle, tenant_id: String, user_id: String, cache_key: String, payload: Value, server_revision: i64, expires_at: Option<String>) -> Result<(), String> {
    database(&app,&tenant_id,&user_id)?.cache_put(&cache_key,&payload,server_revision,expires_at.as_deref()).map_err(|e|e.to_string())
}

/// Valida um snapshot fiscal assinado antes de usá-lo em operação offline.
#[tauri::command]
pub fn fiscal_snapshot_verify(snapshot: FiscalSnapshot, expected_tenant: String, public_key_base64: String) -> Result<bool, String> {
    verify_snapshot(&snapshot,&expected_tenant,&public_key_base64).map(|_|true).map_err(|e|e.to_string())
}

/// Persiste um trabalho de impressão na outbox local.
#[tauri::command]
pub fn print_enqueue(app: AppHandle, tenant_id: String, user_id: String, idempotency_key: String, document_type: String, payload: Value) -> Result<(), String> {
    enqueue_print(&database(&app,&tenant_id,&user_id)?,&PrintJob{idempotency_key,document_type,payload}).map_err(|e|e.to_string())
}

/// Elimina banco e segredos locais no logout quando a política do app exigir wipe.
#[tauri::command]
pub fn native_wipe_user(app: AppHandle, tenant_id: String, user_id: String) -> Result<(), String> {
    let db=database(&app,&tenant_id,&user_id)?;
    db.purge().map_err(|e|e.to_string())?;
    for name in ["session","offline-db-key","device-id"] {
        delete(&scope(&tenant_id,&user_id,name)?).map_err(|e|e.to_string())?;
    }
    Ok(())
}
