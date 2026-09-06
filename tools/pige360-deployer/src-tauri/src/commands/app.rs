use std::{collections::BTreeMap, fs, path::PathBuf};

use super::auth::require_session_by_token;

use serde_json::{json, Map, Value};
use tauri::State;

use crate::{
    app_state::SharedState,
    db::{
        app_log_file_path, count_table, open_connection, row_to_json_map, write_app_log,
        AppLogInput,
    },
};

fn build_hash() -> String {
    option_env!("BUILD_HASH")
        .or(option_env!("GITHUB_SHA"))
        .map(|value| value.chars().take(8).collect::<String>())
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| "dev".to_string())
}

fn runtime_app_name() -> String {
    std::env::var("PIGE360_DEPLOYER_NAME")
        .or_else(|_| std::env::var("APP_NAME"))
        .ok()
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| "PIGE360 Deployer".to_string())
}

fn runtime_app_identifier() -> String {
    std::env::var("PIGE360_DEPLOYER_IDENTIFIER")
        .or_else(|_| std::env::var("APP_IDENTIFIER"))
        .ok()
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| "br.com.pige360.deployer".to_string())
}

fn export_dir_for(data_dir: &std::path::Path) -> PathBuf {
    data_dir.join("exports")
}

#[tauri::command]
pub fn app_bootstrap(state: State<'_, SharedState>) -> Result<BTreeMap<String, Value>, String> {
    let db_path = state.db_path()?;
    let data_dir = state.data_dir()?;
    let conn = open_connection(&db_path)?;

    let mut payload = BTreeMap::new();
    payload.insert(
        "db_path".to_string(),
        Value::String(db_path.to_string_lossy().to_string()),
    );
    payload.insert(
        "data_dir".to_string(),
        Value::String(data_dir.to_string_lossy().to_string()),
    );
    payload.insert(
        "exports_dir".to_string(),
        Value::String(export_dir_for(&data_dir).to_string_lossy().to_string()),
    );
    payload.insert(
        "empresas".to_string(),
        Value::from(count_table(&conn, "empresas")?),
    );
    payload.insert(
        "usuarios".to_string(),
        Value::from(count_table(&conn, "usuarios")?),
    );
    payload.insert(
        "perfis".to_string(),
        Value::from(count_table(&conn, "perfis_acesso")?),
    );
    payload.insert(
        "clientes".to_string(),
        Value::from(count_table(&conn, "clientes")?),
    );
    payload.insert(
        "fornecedores".to_string(),
        Value::from(count_table(&conn, "fornecedores")?),
    );
    payload.insert(
        "produtos".to_string(),
        Value::from(count_table(&conn, "produtos")?),
    );
    payload.insert(
        "sync_pendente".to_string(),
        Value::from(
            conn.query_row(
                "SELECT COUNT(*) FROM sync_queue WHERE status = 'pending'",
                [],
                |row| row.get::<_, i64>(0),
            )
            .map_err(|err| format!("Falha ao contar fila de sincronização: {err}"))?,
        ),
    );

    payload.insert(
        "logs_error_today".to_string(),
        Value::from(
            conn.query_row(
                "SELECT COUNT(*) FROM app_logs WHERE level IN ('error','critical') AND substr(created_at, 1, 10) = date('now')",
                [],
                |row| row.get::<_, i64>(0),
            )
            .unwrap_or(0),
        ),
    );
    payload.insert(
        "integrations_total".to_string(),
        Value::from(
            conn.query_row("SELECT COUNT(*) FROM integration_configs", [], |row| {
                row.get::<_, i64>(0)
            })
            .unwrap_or(0),
        ),
    );
    payload.insert(
        "integrations_active".to_string(),
        Value::from(
            conn.query_row(
                "SELECT COUNT(*) FROM integration_configs WHERE ativo=1 AND status='active'",
                [],
                |row| row.get::<_, i64>(0),
            )
            .unwrap_or(0),
        ),
    );
    payload.insert(
        "database_status".to_string(),
        Value::String("ok".to_string()),
    );
    payload.insert(
        "internal_api_status".to_string(),
        Value::String("headless-capable".to_string()),
    );

    Ok(payload)
}

#[tauri::command]
pub fn app_meta() -> Result<BTreeMap<String, Value>, String> {
    let mut payload = BTreeMap::new();
    payload.insert(
        "version".to_string(),
        Value::String(env!("CARGO_PKG_VERSION").to_string()),
    );
    payload.insert("build_hash".to_string(), Value::String(build_hash()));
    payload.insert(
        "product_name".to_string(),
        Value::String(runtime_app_name()),
    );
    payload.insert(
        "identifier".to_string(),
        Value::String(runtime_app_identifier()),
    );
    Ok(payload)
}

#[tauri::command]
pub fn system_info(state: State<'_, SharedState>) -> Result<BTreeMap<String, Value>, String> {
    let db_path = state.db_path()?;
    let data_dir = state.data_dir()?;
    let bootstrap_path = SharedState::bootstrap_config_path()?;
    let mut payload = app_meta()?;
    payload.insert(
        "db_path".to_string(),
        Value::String(db_path.to_string_lossy().to_string()),
    );
    payload.insert(
        "data_dir".to_string(),
        Value::String(data_dir.to_string_lossy().to_string()),
    );
    payload.insert(
        "exports_dir".to_string(),
        Value::String(export_dir_for(&data_dir).to_string_lossy().to_string()),
    );
    payload.insert(
        "bootstrap_config".to_string(),
        Value::String(bootstrap_path.to_string_lossy().to_string()),
    );
    payload.insert(
        "log_file".to_string(),
        Value::String(app_log_file_path(&data_dir).to_string_lossy().to_string()),
    );
    Ok(payload)
}

#[tauri::command]
pub fn system_set_data_dir(
    state: State<'_, SharedState>,
    data_dir: String,
) -> Result<BTreeMap<String, Value>, String> {
    let target_dir = PathBuf::from(data_dir.trim());
    if data_dir.trim().is_empty() {
        return Err("Informe um diretório válido para os parâmetros/dados.".to_string());
    }
    fs::create_dir_all(&target_dir)
        .map_err(|err| format!("Falha ao criar diretório informado: {err}"))?;

    let current_db = state.db_path()?;
    let current_data_dir = state.data_dir()?;
    let new_db = target_dir.join("app.db");

    if current_db.exists() && current_db != new_db {
        if let Some(parent) = new_db.parent() {
            fs::create_dir_all(parent)
                .map_err(|err| format!("Falha ao preparar diretório do novo banco: {err}"))?;
        }
        fs::copy(&current_db, &new_db)
            .map_err(|err| format!("Falha ao copiar banco para o novo local: {err}"))?;

        let old_exports = export_dir_for(&current_data_dir);
        let new_exports = export_dir_for(&target_dir);
        if old_exports.exists() {
            fs::create_dir_all(&new_exports)
                .map_err(|err| format!("Falha ao preparar diretório de exportações: {err}"))?;
            for entry in fs::read_dir(&old_exports)
                .map_err(|err| format!("Falha ao ler exportações atuais: {err}"))?
            {
                let entry = entry.map_err(|err| format!("Falha ao iterar exportações: {err}"))?;
                let target = new_exports.join(entry.file_name());
                if entry.path().is_file() {
                    let _ = fs::copy(entry.path(), target);
                }
            }
        }
    }

    let cfg = json!({ "data_dir_override": target_dir.to_string_lossy().to_string() });
    SharedState::save_bootstrap_config(&cfg)?;
    state.reconfigure_data_dir(target_dir)?;
    system_info(state)
}

#[tauri::command]
pub fn app_log_write(
    state: State<'_, SharedState>,
    payload: Map<String, Value>,
) -> Result<bool, String> {
    let db_path = state.db_path()?;
    let data_dir = state.data_dir()?;
    let conn = open_connection(&db_path)?;
    let level = payload
        .get("level")
        .and_then(Value::as_str)
        .unwrap_or("info");
    let category = payload
        .get("category")
        .and_then(Value::as_str)
        .unwrap_or("app");
    let message = payload
        .get("message")
        .and_then(Value::as_str)
        .unwrap_or("evento sem mensagem");
    let source = payload.get("source").and_then(Value::as_str);
    let route = payload.get("route").and_then(Value::as_str);
    let details = payload.get("details");
    write_app_log(
        &conn,
        &data_dir,
        AppLogInput {
            level,
            category,
            message,
            source,
            route,
            details,
        },
    )?;
    Ok(true)
}

#[tauri::command]
pub fn app_log_list(
    state: State<'_, SharedState>,
    session_token: String,
    filters: Map<String, Value>,
) -> Result<Vec<Map<String, Value>>, String> {
    let db_path = state.db_path()?;
    let conn = open_connection(&db_path)?;
    let _ = require_session_by_token(&conn, &session_token)?;
    let level = filters.get("level").and_then(Value::as_str).unwrap_or("");
    let category = filters
        .get("category")
        .and_then(Value::as_str)
        .unwrap_or("");
    let search = filters.get("search").and_then(Value::as_str).unwrap_or("");
    let limit = filters
        .get("limit")
        .and_then(Value::as_i64)
        .unwrap_or(300)
        .clamp(1, 5000);

    let mut sql = String::from(
        "SELECT id, level, category, message, source, route, details_json, created_at FROM app_logs WHERE 1=1",
    );
    let mut params_vec: Vec<rusqlite::types::Value> = Vec::new();
    if !level.trim().is_empty() {
        sql.push_str(" AND level = ?");
        params_vec.push(rusqlite::types::Value::Text(level.trim().to_string()));
    }
    if !category.trim().is_empty() {
        sql.push_str(" AND category = ?");
        params_vec.push(rusqlite::types::Value::Text(category.trim().to_string()));
    }
    if !search.trim().is_empty() {
        sql.push_str(" AND (message LIKE ? OR COALESCE(details_json,'') LIKE ? OR COALESCE(route,'') LIKE ?)");
        let wild = format!("%{}%", search.trim());
        params_vec.push(rusqlite::types::Value::Text(wild.clone()));
        params_vec.push(rusqlite::types::Value::Text(wild.clone()));
        params_vec.push(rusqlite::types::Value::Text(wild));
    }
    sql.push_str(" ORDER BY id DESC LIMIT ?");
    params_vec.push(rusqlite::types::Value::Integer(limit));

    let mut stmt = conn
        .prepare(&sql)
        .map_err(|err| format!("Falha ao preparar logs da aplicação: {err}"))?;
    let rows = stmt
        .query_map(
            rusqlite::params_from_iter(params_vec.iter()),
            row_to_json_map,
        )
        .map_err(|err| format!("Falha ao consultar logs da aplicação: {err}"))?;
    rows.collect::<Result<Vec<_>, _>>()
        .map_err(|err| format!("Falha ao mapear logs da aplicação: {err}"))
}

#[tauri::command]
pub fn app_log_clear(state: State<'_, SharedState>, session_token: String) -> Result<bool, String> {
    let db_path = state.db_path()?;
    let data_dir = state.data_dir()?;
    let conn = open_connection(&db_path)?;
    let identity = require_session_by_token(&conn, &session_token)?;
    if !identity.master_user {
        return Err("Apenas usuário master pode limpar os logs da aplicação.".to_string());
    }
    conn.execute("DELETE FROM app_logs", [])
        .map_err(|err| format!("Falha ao limpar logs da aplicação: {err}"))?;
    let log_path = app_log_file_path(&data_dir);
    if log_path.exists() {
        fs::write(&log_path, "").map_err(|err| format!("Falha ao limpar arquivo de log: {err}"))?;
    }
    Ok(true)
}
