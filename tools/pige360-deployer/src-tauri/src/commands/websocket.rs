use serde_json::{json, Value};
use tauri::State;

use crate::{app_state::SharedState, native_websocket};

#[tauri::command]
pub fn websocket_status() -> Result<Value, String> {
    serde_json::to_value(native_websocket::server::status()?).map_err(|err| err.to_string())
}

#[tauri::command]
pub fn websocket_start(state: State<'_, SharedState>) -> Result<Value, String> {
    serde_json::to_value(native_websocket::server::start_background(
        state.inner().clone(),
    )?)
    .map_err(|err| err.to_string())
}

#[tauri::command]
pub fn websocket_stop() -> Result<Value, String> {
    serde_json::to_value(native_websocket::server::stop_background()?)
        .map_err(|err| err.to_string())
}

#[tauri::command]
pub fn websocket_restart(state: State<'_, SharedState>) -> Result<Value, String> {
    let _ = native_websocket::server::stop_background();
    websocket_start(state)
}

#[tauri::command]
pub fn websocket_list_clients() -> Result<Value, String> {
    Ok(json!({ "items": native_websocket::hub::list_clients() }))
}

#[tauri::command]
pub fn websocket_broadcast_test(message: Option<String>) -> Result<Value, String> {
    let payload = json!({
        "type": "template.broadcast.test",
        "message": message.unwrap_or_else(|| "Mensagem de teste do WebSocket Service".to_string()),
        "sent_at": chrono::Utc::now().to_rfc3339()
    });
    let sent = native_websocket::hub::broadcast_text(payload.to_string());
    Ok(json!({ "ok": true, "sent": sent, "payload": payload }))
}
