use std::sync::{Mutex, OnceLock};

use axum::{
    body::Bytes,
    extract::{Path, State},
    http::{HeaderMap, Method, StatusCode},
    response::IntoResponse,
    routing::{get, post},
    Json, Router,
};
use chrono::Utc;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

use crate::{
    app_state::SharedState,
    db::{open_connection, write_app_log, AppLogInput},
    native_webhook::config::WebhookConfig,
};

#[derive(Clone)]
pub struct WebhookState {
    pub app_state: SharedState,
    pub config: WebhookConfig,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WebhookEventRecord {
    pub id: u64,
    pub provider: String,
    pub event: String,
    pub method: String,
    pub path: String,
    pub status: String,
    pub headers_json: Value,
    pub payload_json: Value,
    pub received_at: String,
}

static WEBHOOK_EVENTS: OnceLock<Mutex<Vec<WebhookEventRecord>>> = OnceLock::new();
static WEBHOOK_SEQ: OnceLock<Mutex<u64>> = OnceLock::new();

fn events_slot() -> &'static Mutex<Vec<WebhookEventRecord>> {
    WEBHOOK_EVENTS.get_or_init(|| Mutex::new(Vec::new()))
}

fn next_id() -> u64 {
    let slot = WEBHOOK_SEQ.get_or_init(|| Mutex::new(0));
    let mut guard = slot.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
    *guard += 1;
    *guard
}

pub fn router(state: WebhookState) -> Router {
    let base = state.config.base_path.clone();
    let base_event = format!("{base}/:provider/:event");
    let base_provider = format!("{base}/:provider");
    let base_test = format!("{base}/test");
    let base_events = format!("{base}/events");

    Router::new()
        .route("/", get(root))
        .route("/health", get(health))
        .route("/events", get(list_events))
        .route("/test", post(test_receive))
        .route(&base_events, get(list_events))
        .route(&base_test, post(test_receive))
        .route(&base_provider, post(receive_provider))
        .route(&base_event, post(receive_provider_event))
        .with_state(state)
}

async fn root(State(state): State<WebhookState>) -> impl IntoResponse {
    Json(json!({
        "service": "webhook",
        "running": true,
        "port": state.config.port,
        "base_path": state.config.base_path,
        "endpoints": ["/health", "/events", "/test", state.config.base_path]
    }))
}

async fn health(State(state): State<WebhookState>) -> impl IntoResponse {
    Json(json!({
        "ok": true,
        "service": "webhook",
        "host": state.config.public_host(),
        "port": state.config.port,
        "base_path": state.config.base_path,
        "received_events": list_events_snapshot().len()
    }))
}

async fn list_events() -> impl IntoResponse {
    Json(json!({ "items": list_events_snapshot() }))
}

async fn test_receive(
    State(state): State<WebhookState>,
    headers: HeaderMap,
    body: Bytes,
) -> impl IntoResponse {
    receive_event(
        state,
        headers,
        Method::POST,
        "/test".to_string(),
        "test".to_string(),
        "manual".to_string(),
        body,
    )
    .await
}

async fn receive_provider(
    State(state): State<WebhookState>,
    Path(provider): Path<String>,
    headers: HeaderMap,
    body: Bytes,
) -> impl IntoResponse {
    receive_event(
        state,
        headers,
        Method::POST,
        format!("/webhooks/{provider}"),
        provider,
        "generic".to_string(),
        body,
    )
    .await
}

async fn receive_provider_event(
    State(state): State<WebhookState>,
    Path((provider, event)): Path<(String, String)>,
    headers: HeaderMap,
    body: Bytes,
) -> impl IntoResponse {
    receive_event(
        state,
        headers,
        Method::POST,
        format!("/webhooks/{provider}/{event}"),
        provider,
        event,
        body,
    )
    .await
}

async fn receive_event(
    state: WebhookState,
    headers: HeaderMap,
    method: Method,
    path: String,
    provider: String,
    event: String,
    body: Bytes,
) -> impl IntoResponse {
    if let Err(message) = validate_token(&state.config, &headers) {
        return (
            StatusCode::UNAUTHORIZED,
            Json(json!({ "ok": false, "error": message })),
        )
            .into_response();
    }

    let payload_json = parse_payload(&body);
    let record = WebhookEventRecord {
        id: next_id(),
        provider,
        event,
        method: method.to_string(),
        path,
        status: "received".to_string(),
        headers_json: headers_to_json(&headers),
        payload_json,
        received_at: Utc::now().to_rfc3339(),
    };
    push_event(record.clone());
    log_webhook_event(&state.app_state, &record);

    Json(json!({ "ok": true, "event": record })).into_response()
}

fn validate_token(config: &WebhookConfig, headers: &HeaderMap) -> Result<(), String> {
    if !config.token_required {
        return Ok(());
    }
    if config.token.trim().is_empty() {
        return Ok(());
    }
    let header_name = config.token_header.trim();
    let received = headers
        .get(header_name)
        .and_then(|value| value.to_str().ok())
        .unwrap_or_default();
    if received == config.token {
        Ok(())
    } else {
        Err("Token do webhook ausente ou inválido.".to_string())
    }
}

fn parse_payload(body: &[u8]) -> Value {
    if body.is_empty() {
        return json!({});
    }
    serde_json::from_slice(body)
        .unwrap_or_else(|_| json!({ "raw": String::from_utf8_lossy(body).to_string() }))
}

fn headers_to_json(headers: &HeaderMap) -> Value {
    let mut result = serde_json::Map::new();
    for (key, value) in headers {
        result.insert(key.to_string(), json!(value.to_str().unwrap_or_default()));
    }
    Value::Object(result)
}

fn push_event(record: WebhookEventRecord) {
    let mut guard = events_slot()
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner());
    guard.push(record);
    if guard.len() > 500 {
        let overflow = guard.len() - 500;
        guard.drain(0..overflow);
    }
}

pub fn list_events_snapshot() -> Vec<WebhookEventRecord> {
    events_slot()
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .iter()
        .rev()
        .cloned()
        .collect()
}

pub fn clear_events() {
    events_slot()
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .clear();
}

fn log_webhook_event(state: &SharedState, record: &WebhookEventRecord) {
    if let (Ok(db_path), Ok(data_dir)) = (state.db_path(), state.data_dir()) {
        if let Ok(conn) = open_connection(&db_path) {
            let _ = write_app_log(
                &conn,
                &data_dir,
                AppLogInput {
                    level: "info",
                    category: "webhook",
                    message: "Webhook recebido",
                    source: Some("native_webhook"),
                    route: Some("-"),
                    details: Some(&json!(record)),
                },
            );
        }
    }
}
