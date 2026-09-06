use std::{
    collections::HashMap,
    sync::{Mutex, OnceLock},
};

use axum::extract::ws::Message;
use chrono::Utc;
use serde::Serialize;
use tokio::sync::mpsc;

#[derive(Debug, Clone, Serialize)]
pub struct WebSocketClientInfo {
    pub id: String,
    pub connected_at: String,
    pub user_agent: Option<String>,
}

struct WebSocketClient {
    info: WebSocketClientInfo,
    sender: mpsc::UnboundedSender<Message>,
}

static CLIENTS: OnceLock<Mutex<HashMap<String, WebSocketClient>>> = OnceLock::new();

fn clients_slot() -> &'static Mutex<HashMap<String, WebSocketClient>> {
    CLIENTS.get_or_init(|| Mutex::new(HashMap::new()))
}

pub fn register_client(
    id: String,
    user_agent: Option<String>,
    sender: mpsc::UnboundedSender<Message>,
) -> WebSocketClientInfo {
    let info = WebSocketClientInfo {
        id: id.clone(),
        connected_at: Utc::now().to_rfc3339(),
        user_agent,
    };
    clients_slot()
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .insert(
            id,
            WebSocketClient {
                info: info.clone(),
                sender,
            },
        );
    info
}

pub fn unregister_client(id: &str) {
    clients_slot()
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .remove(id);
}

pub fn list_clients() -> Vec<WebSocketClientInfo> {
    clients_slot()
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .values()
        .map(|client| client.info.clone())
        .collect()
}

pub fn broadcast_text(text: String) -> usize {
    let mut disconnected = Vec::new();
    let mut sent = 0usize;
    {
        let guard = clients_slot()
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        for (id, client) in guard.iter() {
            if client.sender.send(Message::Text(text.clone())).is_ok() {
                sent += 1;
            } else {
                disconnected.push(id.clone());
            }
        }
    }
    for id in disconnected {
        unregister_client(&id);
    }
    sent
}
