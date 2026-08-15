//! Adaptadores Tauri incluídos pelo crate binário de cada aplicativo.
//!
//! `#[tauri::command]` gera macros que precisam pertencer ao crate que chama
//! `generate_handler!`. Este arquivo é incluído como módulo pelos aplicativos,
//! enquanto a política nativa permanece centralizada em `pige360-native-bridge`.

use serde_json::Value;
use tauri::AppHandle;

#[tauri::command]
pub fn secure_session_put(tenant_id: String, user_id: String, value: String) -> Result<(), String> {
    pige360_native_bridge::secure_session_put(tenant_id, user_id, value)
}

#[tauri::command]
pub fn secure_session_get(tenant_id: String) -> Result<Option<String>, String> {
    pige360_native_bridge::secure_session_get(tenant_id)
}

#[tauri::command]
pub fn secure_session_delete(tenant_id: String) -> Result<(), String> {
    pige360_native_bridge::secure_session_delete(tenant_id)
}

#[tauri::command]
pub fn offline_initialize(
    app: AppHandle,
    tenant_id: String,
    user_id: String,
) -> Result<pige360_native_bridge::NativeOfflineContext, String> {
    pige360_native_bridge::offline_initialize(app, tenant_id, user_id)
}

#[tauri::command]
pub fn offline_outbox_enqueue(
    app: AppHandle,
    tenant_id: String,
    user_id: String,
    idempotency_key: String,
    aggregate_type: String,
    aggregate_id: String,
    base_revision: i64,
    payload: Value,
) -> Result<(), String> {
    pige360_native_bridge::offline_outbox_enqueue(
        app,
        tenant_id,
        user_id,
        idempotency_key,
        aggregate_type,
        aggregate_id,
        base_revision,
        payload,
    )
}

#[tauri::command]
pub fn offline_outbox_pending(
    app: AppHandle,
    tenant_id: String,
    user_id: String,
    limit: usize,
) -> Result<Value, String> {
    pige360_native_bridge::offline_outbox_pending(app, tenant_id, user_id, limit)
}

#[tauri::command]
pub fn offline_outbox_apply_result(
    app: AppHandle,
    tenant_id: String,
    user_id: String,
    idempotency_key: String,
    result: pige360_native_bridge::PushResult,
) -> Result<String, String> {
    pige360_native_bridge::offline_outbox_apply_result(app, tenant_id, user_id, idempotency_key, result)
}

#[tauri::command]
pub fn offline_cache_get(
    app: AppHandle,
    tenant_id: String,
    user_id: String,
    cache_key: String,
) -> Result<Option<Value>, String> {
    pige360_native_bridge::offline_cache_get(app, tenant_id, user_id, cache_key)
}

#[tauri::command]
pub fn offline_cache_put(
    app: AppHandle,
    tenant_id: String,
    user_id: String,
    cache_key: String,
    payload: Value,
    server_revision: i64,
    expires_at: Option<String>,
) -> Result<(), String> {
    pige360_native_bridge::offline_cache_put(
        app,
        tenant_id,
        user_id,
        cache_key,
        payload,
        server_revision,
        expires_at,
    )
}

#[tauri::command]
pub fn fiscal_snapshot_verify(
    snapshot: pige360_native_bridge::FiscalSnapshot,
    expected_tenant: String,
    public_key_base64: String,
) -> Result<bool, String> {
    pige360_native_bridge::fiscal_snapshot_verify(snapshot, expected_tenant, public_key_base64)
}

#[tauri::command]
pub fn print_enqueue(
    app: AppHandle,
    tenant_id: String,
    user_id: String,
    idempotency_key: String,
    document_type: String,
    payload: Value,
) -> Result<(), String> {
    pige360_native_bridge::print_enqueue(app, tenant_id, user_id, idempotency_key, document_type, payload)
}

#[tauri::command]
pub fn native_wipe_user(app: AppHandle, tenant_id: String, user_id: String) -> Result<(), String> {
    pige360_native_bridge::native_wipe_user(app, tenant_id, user_id)
}
