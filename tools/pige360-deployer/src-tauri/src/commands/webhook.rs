use serde_json::{json, Value};
use tauri::State;

use crate::{app_state::SharedState, native_webhook};

#[tauri::command]
pub fn webhook_status() -> Result<Value, String> {
    serde_json::to_value(native_webhook::server::status()?).map_err(|err| err.to_string())
}

#[tauri::command]
pub fn webhook_start(state: State<'_, SharedState>) -> Result<Value, String> {
    serde_json::to_value(native_webhook::server::start_background(
        state.inner().clone(),
    )?)
    .map_err(|err| err.to_string())
}

#[tauri::command]
pub fn webhook_stop() -> Result<Value, String> {
    serde_json::to_value(native_webhook::server::stop_background()?).map_err(|err| err.to_string())
}

#[tauri::command]
pub fn webhook_restart(state: State<'_, SharedState>) -> Result<Value, String> {
    let _ = native_webhook::server::stop_background();
    webhook_start(state)
}

#[tauri::command]
pub fn webhook_list_events() -> Result<Value, String> {
    Ok(json!({ "items": native_webhook::routes::list_events_snapshot() }))
}

#[tauri::command]
pub fn webhook_clear_events() -> Result<bool, String> {
    native_webhook::routes::clear_events();
    Ok(true)
}

#[tauri::command]
pub fn webhook_test_receive(
    provider: Option<String>,
    event: Option<String>,
    payload: Option<Value>,
) -> Result<Value, String> {
    Ok(json!({
        "ok": true,
        "simulated": true,
        "provider": provider.unwrap_or_else(|| "manual".to_string()),
        "event": event.unwrap_or_else(|| "test".to_string()),
        "payload": payload.unwrap_or_else(|| json!({ "message": "Teste local do Webhook Service" })),
        "received_at": chrono::Utc::now().to_rfc3339()
    }))
}
