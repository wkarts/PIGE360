use std::collections::BTreeMap;

use reqwest::blocking::Client;
use rusqlite::{params, OptionalExtension};
use serde_json::{Map, Value};
use tauri::State;

use crate::{
    app_state::SharedState,
    db::{open_connection, row_to_json_map},
    security::{decrypt_text, encrypt_text, machine_key},
};

fn now() -> String {
    chrono::Utc::now().to_rfc3339()
}

fn get_str<'a>(payload: &'a Map<String, Value>, key: &str) -> Option<&'a str> {
    payload
        .get(key)
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
}

#[tauri::command]
pub fn integration_list(state: State<'_, SharedState>) -> Result<Vec<Value>, String> {
    let conn = open_connection(&state.db_path()?)?;
    let mut stmt = conn
        .prepare(
            "SELECT id, nome, tipo, base_url, metodo_padrao, headers_json, ambiente, status, timeout_seconds, retry_attempts, ultimo_erro, ultima_execucao_em, ativo, created_at, updated_at FROM integration_configs ORDER BY nome",
        )
        .map_err(|err| format!("Falha ao preparar listagem de integrações: {err}"))?;
    let rows = stmt
        .query_map([], |row| Ok(Value::Object(row_to_json_map(row)?)))
        .map_err(|err| format!("Falha ao consultar integrações: {err}"))?;
    let mut items = Vec::new();
    for row in rows {
        items.push(row.map_err(|err| format!("Falha ao mapear integração: {err}"))?);
    }
    Ok(items)
}

#[tauri::command]
pub fn integration_save(
    state: State<'_, SharedState>,
    payload: Map<String, Value>,
) -> Result<i64, String> {
    let conn = open_connection(&state.db_path()?)?;
    let id = payload.get("id").and_then(Value::as_i64);
    let nome =
        get_str(&payload, "nome").ok_or_else(|| "Informe o nome da integração.".to_string())?;
    let base_url = get_str(&payload, "base_url")
        .ok_or_else(|| "Informe a URL base da integração.".to_string())?;
    let tipo = get_str(&payload, "tipo").unwrap_or("rest");
    let metodo = get_str(&payload, "metodo_padrao").unwrap_or("GET");
    let headers_json = payload
        .get("headers")
        .or_else(|| payload.get("headers_json"))
        .map(Value::to_string);
    let ambiente = get_str(&payload, "ambiente").unwrap_or("production");
    let status = get_str(&payload, "status").unwrap_or("inactive");
    let timeout = payload
        .get("timeout_seconds")
        .and_then(Value::as_i64)
        .unwrap_or(30);
    let retries = payload
        .get("retry_attempts")
        .and_then(Value::as_i64)
        .unwrap_or(0);
    let ativo = payload
        .get("ativo")
        .and_then(Value::as_bool)
        .unwrap_or(true) as i64;
    let token = get_str(&payload, "token").map(|v| encrypt_text(&machine_key(), v));
    let now = now();

    if let Some(id) = id {
        if let Some(token) = token {
            conn.execute(
                "UPDATE integration_configs SET nome=?1,tipo=?2,base_url=?3,metodo_padrao=?4,headers_json=?5,token_encrypted=?6,ambiente=?7,status=?8,timeout_seconds=?9,retry_attempts=?10,ativo=?11,updated_at=?12 WHERE id=?13",
                params![
                    nome,
                    tipo,
                    base_url,
                    metodo,
                    headers_json,
                    token,
                    ambiente,
                    status,
                    timeout,
                    retries,
                    ativo,
                    now,
                    id
                ]
            ).map_err(|err| format!("Falha ao atualizar integração: {err}"))?;
        } else {
            conn.execute(
                "UPDATE integration_configs SET nome=?1,tipo=?2,base_url=?3,metodo_padrao=?4,headers_json=?5,ambiente=?6,status=?7,timeout_seconds=?8,retry_attempts=?9,ativo=?10,updated_at=?11 WHERE id=?12",
                params![
                    nome,
                    tipo,
                    base_url,
                    metodo,
                    headers_json,
                    ambiente,
                    status,
                    timeout,
                    retries,
                    ativo,
                    now,
                    id
                ]
            ).map_err(|err| format!("Falha ao atualizar integração: {err}"))?;
        }
        Ok(id)
    } else {
        conn.execute(
            "INSERT INTO integration_configs (nome,tipo,base_url,metodo_padrao,headers_json,token_encrypted,ambiente,status,timeout_seconds,retry_attempts,ativo,created_at,updated_at) VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,?12,?12)",
            params![
                nome,
                tipo,
                base_url,
                metodo,
                headers_json,
                token,
                ambiente,
                status,
                timeout,
                retries,
                ativo,
                now
            ]
        ).map_err(|err| format!("Falha ao criar integração: {err}"))?;
        Ok(conn.last_insert_rowid())
    }
}

#[tauri::command]
pub fn integration_delete(state: State<'_, SharedState>, id: i64) -> Result<bool, String> {
    let conn = open_connection(&state.db_path()?)?;
    conn.execute("DELETE FROM integration_configs WHERE id=?1", params![id])
        .map_err(|err| format!("Falha ao excluir integração: {err}"))?;
    Ok(true)
}

#[tauri::command]
pub fn integration_test(
    state: State<'_, SharedState>,
    id: i64,
) -> Result<BTreeMap<String, Value>, String> {
    let conn = open_connection(&state.db_path()?)?;
    let row = conn.query_row(
        "SELECT base_url, metodo_padrao, headers_json, token_encrypted, timeout_seconds FROM integration_configs WHERE id=?1",
        params![id],
        |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, Option<String>>(2)?,
                row.get::<_, Option<String>>(3)?,
                row.get::<_, i64>(4)?,
            ))
        },
    )
    .optional()
    .map_err(|err| format!("Falha ao localizar integração: {err}"))?
    .ok_or_else(|| "Integração não encontrada.".to_string())?;
    let (url, method, headers_json, token_encrypted, timeout) = row;
    let started = std::time::Instant::now();
    let client = Client::builder()
        .timeout(std::time::Duration::from_secs(timeout.max(1) as u64))
        .build()
        .map_err(|err| format!("Falha ao criar cliente HTTP: {err}"))?;
    let mut request = match method.to_ascii_uppercase().as_str() {
        "POST" => client.post(&url),
        "PUT" => client.put(&url),
        "PATCH" => client.patch(&url),
        "DELETE" => client.delete(&url),
        _ => client.get(&url),
    };
    if let Some(raw) = headers_json.as_deref() {
        if let Ok(Value::Object(map)) = serde_json::from_str::<Value>(raw) {
            for (key, value) in map {
                if let Some(v) = value.as_str() {
                    request = request.header(key, v);
                }
            }
        }
    }
    if let Some(cipher) = token_encrypted.as_deref() {
        if let Ok(token) = decrypt_text(&machine_key(), cipher) {
            if !token.trim().is_empty() {
                request = request.bearer_auth(token);
            }
        }
    }
    let response = request.send();
    let duration = started.elapsed().as_millis() as i64;
    let (success, status_code, error_message) = match response {
        Ok(resp) => (
            resp.status().is_success(),
            Some(resp.status().as_u16() as i64),
            None,
        ),
        Err(err) => (false, None, Some(err.to_string())),
    };
    let created = now();
    conn.execute(
        "INSERT INTO integration_logs (integration_id, method, url, status_code, success, duration_ms, error_message, created_at) VALUES (?1,?2,?3,?4,?5,?6,?7,?8)",
        params![
            id,
            method,
            url,
            status_code,
            success as i64,
            duration,
            error_message,
            created
        ]
    ).map_err(|err| format!("Falha ao registrar log de integração: {err}"))?;
    conn.execute(
        "UPDATE integration_configs SET status=?1, ultimo_erro=?2, ultima_execucao_em=?3, updated_at=?3 WHERE id=?4",
        params![
            if success { "active" } else { "error" },
            error_message,
            created,
            id
        ]
    ).map_err(|err| format!("Falha ao atualizar status da integração: {err}"))?;
    let mut out = BTreeMap::new();
    out.insert("success".to_string(), Value::Bool(success));
    out.insert(
        "status_code".to_string(),
        status_code.map(Value::from).unwrap_or(Value::Null),
    );
    out.insert("duration_ms".to_string(), Value::from(duration));
    out.insert(
        "error_message".to_string(),
        error_message.map(Value::from).unwrap_or(Value::Null),
    );
    Ok(out)
}

#[tauri::command]
pub fn integration_logs(
    state: State<'_, SharedState>,
    integration_id: Option<i64>,
) -> Result<Vec<Value>, String> {
    let conn = open_connection(&state.db_path()?)?;
    let sql_all = "SELECT id, integration_id, method, url, status_code, success, duration_ms, error_message, created_at FROM integration_logs ORDER BY id DESC LIMIT 200";
    let sql_one = "SELECT id, integration_id, method, url, status_code, success, duration_ms, error_message, created_at FROM integration_logs WHERE integration_id=?1 ORDER BY id DESC LIMIT 200";
    let mut items = Vec::new();
    if let Some(integration_id) = integration_id {
        let mut stmt = conn.prepare(sql_one).map_err(|err| err.to_string())?;
        let rows = stmt
            .query_map(params![integration_id], |row| {
                Ok(Value::Object(row_to_json_map(row)?))
            })
            .map_err(|err| err.to_string())?;
        for row in rows {
            items.push(row.map_err(|err| err.to_string())?);
        }
    } else {
        let mut stmt = conn.prepare(sql_all).map_err(|err| err.to_string())?;
        let rows = stmt
            .query_map([], |row| Ok(Value::Object(row_to_json_map(row)?)))
            .map_err(|err| err.to_string())?;
        for row in rows {
            items.push(row.map_err(|err| err.to_string())?);
        }
    }
    Ok(items)
}
