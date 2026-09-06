use std::collections::HashSet;

use axum::{extract::State, http::StatusCode, Json};
use chrono::{Duration, Utc};
use rusqlite::{params, params_from_iter, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};
use uuid::Uuid;

use crate::{
    bootstrap,
    commands::{auth::build_auth_user, entities},
    core::database::{config::DatabaseConfig, provider::ActiveDatabaseProvider},
    db::{open_connection, row_to_json_map, write_app_log, AppLogInput},
    internal_api::state::InternalApiState,
    models::LoginResponse,
    security::{hash_password, verify_password},
};

#[derive(Debug, Deserialize)]
pub struct CommandRequest {
    pub command: String,
    #[serde(default)]
    pub args: Map<String, Value>,
}

#[derive(Debug, Serialize)]
pub struct CommandResponse {
    pub ok: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub result: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
}

pub async fn command(
    State(state): State<InternalApiState>,
    Json(request): Json<CommandRequest>,
) -> Result<Json<CommandResponse>, (StatusCode, Json<CommandResponse>)> {
    match execute_command(&state, &request.command, request.args) {
        Ok(result) => Ok(Json(CommandResponse {
            ok: true,
            result: Some(result),
            error: None,
        })),
        Err(error) => Err((
            StatusCode::BAD_REQUEST,
            Json(CommandResponse {
                ok: false,
                result: None,
                error: Some(error),
            }),
        )),
    }
}

fn runtime_app_name() -> String {
    std::env::var("PIGE360_DEPLOYER_NAME")
        .or_else(|_| std::env::var("APP_NAME"))
        .ok()
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| "PIGE360 Deployer".to_string())
}

fn runtime_app_short_name() -> String {
    std::env::var("PIGE360_DEPLOYER_SHORT_NAME")
        .or_else(|_| std::env::var("APP_SHORT_NAME"))
        .ok()
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| "Template".to_string())
}

fn runtime_app_identifier() -> String {
    std::env::var("PIGE360_DEPLOYER_IDENTIFIER")
        .or_else(|_| std::env::var("APP_IDENTIFIER"))
        .ok()
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| "br.com.pige360.deployer".to_string())
}

fn provider_for_state(state: &InternalApiState) -> Result<ActiveDatabaseProvider, String> {
    let driver = std::env::var("PIGE360_DEPLOYER_DATABASE_DRIVER")
        .or_else(|_| std::env::var("PIGE360_DEPLOYER_DB_DRIVER"))
        .unwrap_or_else(|_| "sqlite".to_string())
        .trim()
        .to_ascii_lowercase();
    let config = DatabaseConfig::from_env_with_driver(&driver);
    ActiveDatabaseProvider::from_config(config, &state.db_path)
}

fn now() -> String {
    Utc::now().to_rfc3339()
}

fn validate_password_policy(password: &str) -> Result<(), String> {
    if password.len() < 12
        || !password.chars().any(|value| value.is_ascii_lowercase())
        || !password.chars().any(|value| value.is_ascii_uppercase())
        || !password.chars().any(|value| value.is_ascii_digit())
        || !password.chars().any(|value| !value.is_alphanumeric())
    {
        return Err(
            "A senha deve ter ao menos 12 caracteres, com maiúscula, minúscula, número e símbolo."
                .to_string(),
        );
    }
    Ok(())
}

fn get_string(args: &Map<String, Value>, key: &str) -> String {
    args.get(key)
        .and_then(Value::as_str)
        .unwrap_or_default()
        .trim()
        .to_string()
}

fn get_i64(args: &Map<String, Value>, key: &str) -> i64 {
    args.get(key)
        .and_then(|value| {
            value
                .as_i64()
                .or_else(|| value.as_str()?.parse::<i64>().ok())
        })
        .unwrap_or_default()
}

fn get_payload(args: &Map<String, Value>) -> Map<String, Value> {
    args.get("payload")
        .and_then(Value::as_object)
        .cloned()
        .unwrap_or_default()
}

fn get_filters(args: &Map<String, Value>) -> Map<String, Value> {
    args.get("filters")
        .and_then(Value::as_object)
        .cloned()
        .unwrap_or_default()
}

fn search_from_args(args: &Map<String, Value>) -> String {
    let direct = get_string(args, "search");
    if !direct.is_empty() {
        return direct;
    }
    get_filters(args)
        .get("search")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .trim()
        .to_string()
}

fn json_to_sql_value(value: &Value) -> rusqlite::types::Value {
    match value {
        Value::Null => rusqlite::types::Value::Null,
        Value::Bool(v) => rusqlite::types::Value::Integer(if *v { 1 } else { 0 }),
        Value::Number(v) => {
            if let Some(i) = v.as_i64() {
                rusqlite::types::Value::Integer(i)
            } else if let Some(f) = v.as_f64() {
                rusqlite::types::Value::Real(f)
            } else {
                rusqlite::types::Value::Null
            }
        }
        Value::String(v) if v.trim().is_empty() => rusqlite::types::Value::Null,
        Value::String(v) => rusqlite::types::Value::Text(v.to_string()),
        _ => rusqlite::types::Value::Text(value.to_string()),
    }
}

fn quote_ident(identifier: &str) -> String {
    format!("\"{}\"", identifier.replace('"', "\"\""))
}

fn table_columns(conn: &Connection, table: &str) -> Result<HashSet<String>, String> {
    let sql = format!("PRAGMA table_info({})", quote_ident(table));
    let mut stmt = conn
        .prepare(&sql)
        .map_err(|err| format!("Falha ao inspecionar tabela {table}: {err}"))?;
    let rows = stmt
        .query_map([], |row| row.get::<_, String>(1))
        .map_err(|err| format!("Falha ao consultar colunas de {table}: {err}"))?;
    let mut columns = HashSet::new();
    for row in rows {
        columns.insert(row.map_err(|err| format!("Falha ao mapear coluna de {table}: {err}"))?);
    }
    if columns.is_empty() {
        return Err(format!("Tabela {table} não encontrada ou sem colunas."));
    }
    Ok(columns)
}

fn query_json(conn: &Connection, sql: &str) -> Result<Vec<Value>, String> {
    let mut stmt = conn
        .prepare(sql)
        .map_err(|err| format!("Falha ao preparar consulta: {err}"))?;
    let rows = stmt
        .query_map([], |row| Ok(Value::Object(row_to_json_map(row)?)))
        .map_err(|err| format!("Falha ao executar consulta: {err}"))?;
    let mut result = Vec::new();
    for row in rows {
        result.push(row.map_err(|err| format!("Falha ao mapear linha: {err}"))?);
    }
    Ok(result)
}

fn query_json_params<P>(conn: &Connection, sql: &str, params: P) -> Result<Vec<Value>, String>
where
    P: rusqlite::Params,
{
    let mut stmt = conn
        .prepare(sql)
        .map_err(|err| format!("Falha ao preparar consulta: {err}"))?;
    let rows = stmt
        .query_map(params, |row| Ok(Value::Object(row_to_json_map(row)?)))
        .map_err(|err| format!("Falha ao executar consulta: {err}"))?;
    let mut result = Vec::new();
    for row in rows {
        result.push(row.map_err(|err| format!("Falha ao mapear linha: {err}"))?);
    }
    Ok(result)
}

fn query_one_json(conn: &Connection, sql: &str, id: i64) -> Result<Value, String> {
    conn.query_row(sql, [id], |row| Ok(Value::Object(row_to_json_map(row)?)))
        .optional()
        .map_err(|err| format!("Falha ao consultar registro: {err}"))?
        .ok_or_else(|| "Registro não encontrado.".to_string())
}

fn table_record(conn: &Connection, table: &str, id: i64) -> Result<Value, String> {
    let sql = format!("SELECT * FROM {} WHERE id = ?1", quote_ident(table));
    query_one_json(conn, &sql, id)
}

fn table_list(
    conn: &Connection,
    table: &str,
    search: &str,
    searchable: &[&str],
) -> Result<Vec<Value>, String> {
    let available = table_columns(conn, table)?;
    let order_col = if available.contains("nome") {
        "nome"
    } else if available.contains("descricao") {
        "descricao"
    } else if available.contains("id") {
        "id"
    } else {
        "rowid"
    };

    if search.trim().is_empty() {
        let sql = format!(
            "SELECT * FROM {} ORDER BY {}",
            quote_ident(table),
            quote_ident(order_col)
        );
        return query_json(conn, &sql);
    }

    let columns = searchable
        .iter()
        .copied()
        .filter(|field| available.contains(*field))
        .map(|field| format!("LOWER(COALESCE({}, '')) LIKE LOWER(?1)", quote_ident(field)))
        .collect::<Vec<_>>();

    if columns.is_empty() {
        let sql = format!(
            "SELECT * FROM {} ORDER BY {}",
            quote_ident(table),
            quote_ident(order_col)
        );
        return query_json(conn, &sql);
    }

    let sql = format!(
        "SELECT * FROM {} WHERE {} ORDER BY {}",
        quote_ident(table),
        columns.join(" OR "),
        quote_ident(order_col)
    );
    let like = format!("%{}%", search.trim());
    query_json_params(conn, &sql, params![like])
}

fn save_record(
    conn: &Connection,
    table: &str,
    payload: &Map<String, Value>,
) -> Result<Value, String> {
    let available = table_columns(conn, table)?;
    let mut data = payload.clone();
    let timestamp = now();
    let id = data
        .get("id")
        .and_then(|value| {
            value
                .as_i64()
                .or_else(|| value.as_str()?.parse::<i64>().ok())
        })
        .filter(|value| *value > 0);

    if available.contains("updated_at") && !data.contains_key("updated_at") {
        data.insert("updated_at".to_string(), Value::String(timestamp.clone()));
    }
    if id.is_none() && available.contains("created_at") && !data.contains_key("created_at") {
        data.insert("created_at".to_string(), Value::String(timestamp.clone()));
    }

    let mut fields = data
        .iter()
        .filter_map(|(key, value)| {
            if key == "id" || !available.contains(key) {
                None
            } else {
                Some((key.clone(), value.clone()))
            }
        })
        .collect::<Vec<_>>();
    fields.sort_by(|left, right| left.0.cmp(&right.0));

    if fields.is_empty() {
        return Err(format!("Nenhum campo válido foi informado para {table}."));
    }

    if let Some(id) = id {
        let assignments = fields
            .iter()
            .enumerate()
            .map(|(index, (field, _))| format!("{} = ?{}", quote_ident(field), index + 1))
            .collect::<Vec<_>>()
            .join(", ");
        let mut values = fields
            .iter()
            .map(|(_, value)| json_to_sql_value(value))
            .collect::<Vec<_>>();
        values.push(rusqlite::types::Value::Integer(id));
        let sql = format!(
            "UPDATE {} SET {} WHERE id = ?{}",
            quote_ident(table),
            assignments,
            values.len()
        );
        conn.execute(&sql, params_from_iter(values.iter()))
            .map_err(|err| format!("Falha ao atualizar {table}: {err}"))?;
        table_record(conn, table, id)
    } else {
        let columns = fields
            .iter()
            .map(|(field, _)| quote_ident(field))
            .collect::<Vec<_>>()
            .join(", ");
        let placeholders = (1..=fields.len())
            .map(|index| format!("?{index}"))
            .collect::<Vec<_>>()
            .join(", ");
        let values = fields
            .iter()
            .map(|(_, value)| json_to_sql_value(value))
            .collect::<Vec<_>>();
        let sql = format!(
            "INSERT INTO {} ({}) VALUES ({})",
            quote_ident(table),
            columns,
            placeholders
        );
        conn.execute(&sql, params_from_iter(values.iter()))
            .map_err(|err| format!("Falha ao inserir em {table}: {err}"))?;
        table_record(conn, table, conn.last_insert_rowid())
    }
}

fn delete_record(conn: &Connection, table: &str, id: i64) -> Result<bool, String> {
    let sql = format!("DELETE FROM {} WHERE id = ?1", quote_ident(table));
    conn.execute(&sql, [id])
        .map_err(|err| format!("Falha ao excluir registro de {table}: {err}"))?;
    Ok(true)
}

fn as_i64_list(value: Option<&Value>) -> Vec<i64> {
    value
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(|item| item.as_i64().or_else(|| item.as_str()?.parse::<i64>().ok()))
                .filter(|value| *value > 0)
                .collect::<Vec<_>>()
        })
        .unwrap_or_default()
}

fn sync_link_table(
    conn: &Connection,
    table: &str,
    owner_field: &str,
    target_field: &str,
    owner_id: i64,
    target_ids: &[i64],
) -> Result<(), String> {
    if target_ids.is_empty() {
        return Ok(());
    }
    conn.execute(
        &format!(
            "DELETE FROM {} WHERE {} = ?1",
            quote_ident(table),
            quote_ident(owner_field)
        ),
        [owner_id],
    )
    .map_err(|err| format!("Falha ao limpar vínculos de {table}: {err}"))?;
    let timestamp = now();
    for target_id in target_ids {
        conn.execute(
            &format!(
                "INSERT INTO {} ({}, {}, created_at) VALUES (?1, ?2, ?3)",
                quote_ident(table),
                quote_ident(owner_field),
                quote_ident(target_field)
            ),
            params![owner_id, target_id, timestamp],
        )
        .map_err(|err| format!("Falha ao gravar vínculo de {table}: {err}"))?;
    }
    Ok(())
}

fn profile_permissions(conn: &Connection, profile_id: i64) -> Result<Vec<String>, String> {
    let mut stmt = conn
        .prepare("SELECT permissao_chave FROM perfis_permissoes WHERE perfil_id = ?1 ORDER BY permissao_chave")
        .map_err(|err| format!("Falha ao preparar permissões: {err}"))?;
    let rows = stmt
        .query_map([profile_id], |row| row.get::<_, String>(0))
        .map_err(|err| format!("Falha ao consultar permissões: {err}"))?;
    let mut out = Vec::new();
    for row in rows {
        out.push(row.map_err(|err| format!("Falha ao mapear permissão: {err}"))?);
    }
    Ok(out)
}

fn save_settings_value(conn: &Connection, key: &str, value: &Value) -> Result<(), String> {
    let timestamp = now();
    conn.execute(
        "INSERT INTO app_settings (chave, valor, created_at, updated_at)
         VALUES (?1, ?2, ?3, ?3)
         ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor, updated_at = excluded.updated_at",
        params![key, value.to_string(), timestamp],
    )
    .map_err(|err| format!("Falha ao salvar configuração {key}: {err}"))?;
    Ok(())
}

fn load_settings_value(conn: &Connection, key: &str) -> Result<Option<Value>, String> {
    let raw = conn
        .query_row(
            "SELECT valor FROM app_settings WHERE chave = ?1",
            [key],
            |row| row.get::<_, String>(0),
        )
        .optional()
        .map_err(|err| format!("Falha ao carregar configuração {key}: {err}"))?;
    Ok(raw.and_then(|value| serde_json::from_str(&value).ok()))
}

fn runtime_settings_payload(state: &InternalApiState, settings: Value) -> Value {
    json!({
        "env_path": "app_settings:runtime.settings",
        "settings": settings,
        "ports": [
            {"key": "internal_api", "label": "API interna", "host": state.host, "configured_port": state.port, "effective_port": state.port, "default_port": 61001, "available": true, "fallback_applied": false},
            {"key": "local_web", "label": "Servidor web local", "host": "0.0.0.0", "configured_port": 61002, "effective_port": 61002, "default_port": 61002, "available": true, "fallback_applied": false},
            {"key": "auxiliary", "label": "Webhook Service", "host": "0.0.0.0", "configured_port": 61003, "effective_port": 61003, "default_port": 61003, "available": true, "fallback_applied": false},
            {"key": "bridge_core", "label": "WebSocket Service", "host": "0.0.0.0", "configured_port": 61004, "effective_port": 61004, "default_port": 61004, "available": true, "fallback_applied": false}
        ],
        "warnings": ["Configurações carregadas pela API interna web. Reinicie os serviços nativos pelo desktop quando necessário."]
    })
}

fn default_runtime_settings(state: &InternalApiState) -> Value {
    let mut settings = Map::new();

    settings.insert(
        "internal_api_host".to_string(),
        Value::String(state.host.clone()),
    );
    settings.insert("internal_api_port".to_string(), Value::from(state.port));
    settings.insert("internal_api_auto_start".to_string(), Value::Bool(true));
    settings.insert(
        "internal_api_base_url".to_string(),
        Value::String(format!("http://127.0.0.1:{}", state.port)),
    );
    settings.insert(
        "internal_api_docs_url".to_string(),
        Value::String(format!("http://127.0.0.1:{}/docs", state.port)),
    );
    settings.insert(
        "internal_api_restart_on_config_change".to_string(),
        Value::Bool(true),
    );
    settings.insert(
        "internal_api_require_token".to_string(),
        Value::Bool(state.config.security.require_token),
    );
    settings.insert(
        "internal_api_allow_public_network".to_string(),
        Value::Bool(state.config.security.allow_public_network),
    );
    settings.insert(
        "internal_api_cors_enabled".to_string(),
        Value::Bool(state.config.security.cors_enabled),
    );
    settings.insert(
        "internal_api_token_header".to_string(),
        Value::String(state.config.security.token_header.clone()),
    );
    settings.insert(
        "internal_api_token".to_string(),
        Value::String(String::new()),
    );
    settings.insert(
        "internal_api_docs_public_local".to_string(),
        Value::Bool(state.config.security.docs_public_local),
    );
    settings.insert(
        "internal_api_open_scalar_after_start".to_string(),
        Value::Bool(false),
    );
    settings.insert("internal_api_timeout_ms".to_string(), Value::from(8000));
    settings.insert(
        "internal_api_log_mode".to_string(),
        Value::String("normal".to_string()),
    );
    settings.insert(
        "internal_api_docs_enabled".to_string(),
        Value::Bool(state.config.expose_docs),
    );
    settings.insert(
        "internal_api_docs_path".to_string(),
        Value::String(state.config.docs.path.clone()),
    );
    settings.insert("local_web_enabled".to_string(), Value::Bool(true));
    settings.insert("local_web_auto_start".to_string(), Value::Bool(true));
    settings.insert(
        "local_web_host".to_string(),
        Value::String("0.0.0.0".to_string()),
    );
    settings.insert("local_web_port".to_string(), Value::from(61002));
    settings.insert(
        "auxiliary_host".to_string(),
        Value::String("0.0.0.0".to_string()),
    );
    settings.insert("auxiliary_port".to_string(), Value::from(61003));
    settings.insert(
        "bridge_core_host".to_string(),
        Value::String("0.0.0.0".to_string()),
    );
    settings.insert("bridge_core_port".to_string(), Value::from(61004));
    settings.insert("webhook_enabled".to_string(), Value::Bool(false));
    settings.insert("webhook_auto_start".to_string(), Value::Bool(false));
    settings.insert(
        "webhook_host".to_string(),
        Value::String("0.0.0.0".to_string()),
    );
    settings.insert("webhook_port".to_string(), Value::from(61003));
    settings.insert(
        "webhook_base_path".to_string(),
        Value::String("/webhooks".to_string()),
    );
    settings.insert("webhook_token_required".to_string(), Value::Bool(true));
    settings.insert(
        "webhook_token_header".to_string(),
        Value::String("X-Webhook-Token".to_string()),
    );
    settings.insert("webhook_token".to_string(), Value::String(String::new()));
    settings.insert("webhook_allow_lan".to_string(), Value::Bool(true));
    settings.insert("webhook_allow_external".to_string(), Value::Bool(false));
    settings.insert("websocket_enabled".to_string(), Value::Bool(false));
    settings.insert("websocket_auto_start".to_string(), Value::Bool(false));
    settings.insert(
        "websocket_host".to_string(),
        Value::String("0.0.0.0".to_string()),
    );
    settings.insert("websocket_port".to_string(), Value::from(61004));
    settings.insert(
        "websocket_path".to_string(),
        Value::String("/ws".to_string()),
    );
    settings.insert("websocket_token_required".to_string(), Value::Bool(true));
    settings.insert(
        "websocket_token_query".to_string(),
        Value::String("token".to_string()),
    );
    settings.insert(
        "websocket_token_header".to_string(),
        Value::String("X-WebSocket-Token".to_string()),
    );
    settings.insert("websocket_token".to_string(), Value::String(String::new()));
    settings.insert("websocket_allow_lan".to_string(), Value::Bool(true));
    settings.insert("websocket_allow_external".to_string(), Value::Bool(false));
    settings.insert("websocket_heartbeat_seconds".to_string(), Value::from(30));
    settings.insert("tray_enabled".to_string(), Value::Bool(false));
    settings.insert("minimize_to_tray".to_string(), Value::Bool(false));
    settings.insert("close_to_tray".to_string(), Value::Bool(false));
    settings.insert("start_with_windows".to_string(), Value::Bool(false));
    settings.insert("services_auto_start".to_string(), Value::Bool(true));
    settings.insert(
        "app_service_name".to_string(),
        Value::String("Pige360DeployerServer".to_string()),
    );

    Value::Object(settings)
}

fn auth_login_http(
    state: &InternalApiState,
    login: String,
    senha: String,
) -> Result<Value, String> {
    let conn = open_connection(&state.db_path)?;
    let normalized_login = login.trim().to_lowercase();
    let row = conn
        .query_row(
            "SELECT id, nome, login, senha_hash, administrador, ativo FROM usuarios WHERE LOWER(login) = ?1 LIMIT 1",
            [normalized_login],
            |row| {
                Ok((
                    row.get::<_, i64>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                    row.get::<_, String>(3)?,
                    row.get::<_, i64>(4)?,
                    row.get::<_, i64>(5)?,
                ))
            },
        )
        .optional()
        .map_err(|err| format!("Falha ao consultar usuário: {err}"))?;

    let Some(row) = row else {
        return serde_json::to_value(LoginResponse {
            success: false,
            message: "Credenciais inválidas.".to_string(),
            session_token: None,
            user: None,
        })
        .map_err(|err| err.to_string());
    };
    if row.5 == 0 {
        return serde_json::to_value(LoginResponse {
            success: false,
            message: "Credenciais inválidas.".to_string(),
            session_token: None,
            user: None,
        })
        .map_err(|err| err.to_string());
    }
    if !verify_password(&senha, &row.3)? {
        return serde_json::to_value(LoginResponse {
            success: false,
            message: "Credenciais inválidas.".to_string(),
            session_token: None,
            user: None,
        })
        .map_err(|err| err.to_string());
    }

    let now_dt = Utc::now();
    let session_token = Uuid::new_v4().to_string();
    let expires_at = (now_dt + Duration::days(7)).to_rfc3339();
    let now_str = now_dt.to_rfc3339();
    conn.execute(
        "DELETE FROM user_sessions WHERE usuario_id = ?1 OR expires_at <= ?2",
        params![row.0, now_str],
    )
    .map_err(|err| format!("Falha ao limpar sessões antigas: {err}"))?;
    conn.execute(
        "INSERT INTO user_sessions (usuario_id, session_token, created_at, expires_at, last_activity_at) VALUES (?1, ?2, ?3, ?4, ?3)",
        params![row.0, session_token, now_str, expires_at],
    )
    .map_err(|err| format!("Falha ao criar sessão: {err}"))?;
    conn.execute(
        "UPDATE usuarios SET ultimo_login_em = ?1 WHERE id = ?2",
        params![Utc::now().to_rfc3339(), row.0],
    )
    .map_err(|err| format!("Falha ao atualizar último login: {err}"))?;
    let user = build_auth_user(&conn, row.0)?;
    serde_json::to_value(LoginResponse {
        success: true,
        message: "Login efetuado com sucesso.".to_string(),
        session_token: Some(session_token),
        user: Some(user),
    })
    .map_err(|err| err.to_string())
}

fn auth_restore_http(state: &InternalApiState, session_token: String) -> Result<Value, String> {
    let conn = open_connection(&state.db_path)?;
    let identity = crate::commands::auth::load_session_identity(&conn, &session_token)?;
    let user = build_auth_user(&conn, identity.user_id)?;
    serde_json::to_value(LoginResponse {
        success: true,
        message: "Sessão restaurada.".to_string(),
        session_token: Some(session_token),
        user: Some(user),
    })
    .map_err(|err| err.to_string())
}

fn auth_change_password_http(
    state: &InternalApiState,
    args: &Map<String, Value>,
) -> Result<Value, String> {
    let session_token = get_string(args, "session_token");
    let current_password = get_string(args, "current_password");
    let new_password = get_string(args, "new_password");
    validate_password_policy(&new_password)?;
    let conn = open_connection(&state.db_path)?;
    let identity = crate::commands::auth::load_session_identity(&conn, &session_token)?;
    let current_hash = conn
        .query_row(
            "SELECT senha_hash FROM usuarios WHERE id = ?1 LIMIT 1",
            [identity.user_id],
            |row| row.get::<_, String>(0),
        )
        .map_err(|err| format!("Falha ao carregar senha atual: {err}"))?;
    if current_password.is_empty() || !verify_password(&current_password, &current_hash)? {
        return Err("Senha atual inválida.".to_string());
    }
    let new_hash = hash_password(&new_password)?;
    conn.execute(
        "UPDATE usuarios SET senha_hash = ?1, senha_provisoria = 0, updated_at = ?2 WHERE id = ?3",
        params![new_hash, now(), identity.user_id],
    )
    .map_err(|err| format!("Falha ao atualizar senha: {err}"))?;
    if identity.master_user {
        bootstrap::remove_after_password_change(&state.db_path)?;
    }
    Ok(Value::Bool(true))
}

pub(crate) fn execute_command(
    state: &InternalApiState,
    command: &str,
    args: Map<String, Value>,
) -> Result<Value, String> {
    let public_or_first_access_command = matches!(
        command,
        "app_meta"
            | "app_bootstrap"
            | "system_info"
            | "auth_login"
            | "auth_restore"
            | "auth_logout"
            | "auth_change_password"
    );
    if !public_or_first_access_command {
        let conn = open_connection(&state.db_path)?;
        crate::commands::auth::require_session_by_token(
            &conn,
            &get_string(&args, "session_token"),
        )?;
    }

    match command {
        "app_meta" => Ok(json!({
            "name": runtime_app_name(),
            "short_name": runtime_app_short_name(),
            "version": env!("CARGO_PKG_VERSION"),
            "identifier": runtime_app_identifier(),
            "runtime": "internal-api-web",
        })),
        "app_bootstrap" => Ok(json!({
            "ok": true,
            "runtime": {"mode": "internal-api-web", "isWeb": true, "isTauri": false},
            "database": "internal-api"
        })),
        "system_info" => Ok(json!({
            "runtime": {"mode": "internal-api-web"},
            "database_provider": std::env::var("PIGE360_DEPLOYER_DATABASE_DRIVER").unwrap_or_else(|_| "sqlite".to_string()),
            "online": true,
            "api": {"host": state.host, "port": state.port},
        })),
        "system_set_data_dir" => Ok(json!({
            "ok": false,
            "warning": "Alteração de diretório de dados deve ser aplicada pelo runtime desktop/Tauri."
        })),
        "auth_login" => {
            let login = if !get_string(&args, "login").is_empty() {
                get_string(&args, "login")
            } else {
                get_string(&args, "username")
            };
            let senha = if !get_string(&args, "senha").is_empty() {
                get_string(&args, "senha")
            } else {
                get_string(&args, "password")
            };
            auth_login_http(state, login, senha)
        }
        "auth_restore" => auth_restore_http(state, get_string(&args, "session_token")),
        "auth_logout" => {
            let token = get_string(&args, "session_token");
            let conn = open_connection(&state.db_path)?;
            conn.execute(
                "DELETE FROM user_sessions WHERE session_token = ?1",
                [token],
            )
            .map_err(|err| format!("Falha ao encerrar sessão: {err}"))?;
            Ok(Value::Bool(true))
        }
        "auth_change_password" => auth_change_password_http(state, &args),
        "permission_catalog" => {
            let rows = crate::commands::auth::PERMISSION_CATALOG
                .iter()
                .map(|(key, label)| {
                    json!({
                        "key": key,
                        "label": label,
                        "descricao": label,
                        "module": key.split(':').next().unwrap_or("geral"),
                        "group": key.split(':').next().unwrap_or("geral")
                    })
                })
                .collect::<Vec<_>>();
            Ok(Value::Array(rows))
        }
        "profile_list" => {
            let conn = open_connection(&state.db_path)?;
            let mut rows = table_list(
                &conn,
                "perfis_acesso",
                &search_from_args(&args),
                &["nome", "descricao"],
            )?;
            for row in rows.iter_mut() {
                if let Value::Object(map) = row {
                    if let Some(id) = map.get("id").and_then(Value::as_i64) {
                        map.insert(
                            "permissions".to_string(),
                            Value::Array(
                                profile_permissions(&conn, id)?
                                    .into_iter()
                                    .map(Value::String)
                                    .collect(),
                            ),
                        );
                    }
                }
            }
            Ok(Value::Array(rows))
        }
        "profile_get" => {
            let conn = open_connection(&state.db_path)?;
            let mut row = table_record(&conn, "perfis_acesso", get_i64(&args, "id"))?;
            if let Value::Object(map) = &mut row {
                let id = map.get("id").and_then(Value::as_i64).unwrap_or_default();
                let permissions = profile_permissions(&conn, id)?;
                map.insert(
                    "permissions".to_string(),
                    Value::Array(permissions.iter().cloned().map(Value::String).collect()),
                );
                map.insert(
                    "permission_keys".to_string(),
                    Value::Array(permissions.into_iter().map(Value::String).collect()),
                );
            }
            Ok(row)
        }
        "profile_save" => {
            let conn = open_connection(&state.db_path)?;
            let payload = get_payload(&args);
            let saved = save_record(&conn, "perfis_acesso", &payload)?;
            let saved_id = saved.get("id").and_then(Value::as_i64).unwrap_or_default();
            let permissions = payload
                .get("permission_keys")
                .or_else(|| payload.get("permissions"))
                .or_else(|| payload.get("permissoes"))
                .and_then(Value::as_array)
                .map(|items| {
                    items
                        .iter()
                        .filter_map(Value::as_str)
                        .map(str::to_string)
                        .collect::<Vec<_>>()
                })
                .unwrap_or_default();
            if !permissions.is_empty() {
                conn.execute(
                    "DELETE FROM perfis_permissoes WHERE perfil_id = ?1",
                    [saved_id],
                )
                .map_err(|err| format!("Falha ao limpar permissões: {err}"))?;
                for permission in permissions {
                    conn.execute(
                        "INSERT INTO perfis_permissoes (perfil_id, permissao_chave, created_at) VALUES (?1, ?2, ?3)",
                        params![saved_id, permission, now()],
                    )
                    .map_err(|err| format!("Falha ao gravar permissão: {err}"))?;
                }
            }
            table_record(&conn, "perfis_acesso", saved_id)
        }
        "profile_delete" => {
            let conn = open_connection(&state.db_path)?;
            delete_record(&conn, "perfis_acesso", get_i64(&args, "id")).map(Value::Bool)
        }
        "user_policy_get" => Ok(
            json!({"login_min_length": 3, "login_min_allowed": 3, "login_max_allowed": 60, "password_min_length": 12}),
        ),
        "user_policy_save" => Ok(Value::Object(get_payload(&args))),
        "user_list" => {
            let conn = open_connection(&state.db_path)?;
            Ok(Value::Array(table_list(
                &conn,
                "usuarios",
                &search_from_args(&args),
                &["nome", "login", "email"],
            )?))
        }
        "user_get" => {
            let conn = open_connection(&state.db_path)?;
            let mut row = table_record(&conn, "usuarios", get_i64(&args, "id"))?;
            if let Value::Object(map) = &mut row {
                map.remove("senha_hash");
            }
            Ok(row)
        }
        "user_save" => {
            let conn = open_connection(&state.db_path)?;
            let mut payload = get_payload(&args);
            let id = payload
                .get("id")
                .and_then(Value::as_i64)
                .unwrap_or_default();
            let senha = payload
                .get("senha")
                .or_else(|| payload.get("password"))
                .and_then(Value::as_str)
                .unwrap_or_default()
                .trim()
                .to_string();
            if id <= 0 && senha.is_empty() {
                return Err("Informe uma senha inicial forte para o novo usuário.".to_string());
            } else if !senha.is_empty() {
                validate_password_policy(&senha)?;
                payload.insert(
                    "senha_hash".to_string(),
                    Value::String(hash_password(&senha)?),
                );
                payload.insert("senha_provisoria".to_string(), json!(1));
            }
            if !payload.contains_key("ativo") {
                payload.insert("ativo".to_string(), json!(1));
            }
            let profile_ids = as_i64_list(
                payload
                    .get("profile_ids")
                    .or_else(|| payload.get("perfil_ids"))
                    .or_else(|| payload.get("perfis")),
            );
            let company_ids = as_i64_list(
                payload
                    .get("company_ids")
                    .or_else(|| payload.get("empresa_ids"))
                    .or_else(|| payload.get("empresas")),
            );
            let saved = save_record(&conn, "usuarios", &payload)?;
            let saved_id = saved.get("id").and_then(Value::as_i64).unwrap_or_default();
            sync_link_table(
                &conn,
                "usuarios_perfis",
                "usuario_id",
                "perfil_id",
                saved_id,
                &profile_ids,
            )?;
            sync_link_table(
                &conn,
                "usuarios_empresas",
                "usuario_id",
                "empresa_id",
                saved_id,
                &company_ids,
            )?;
            let mut row = table_record(&conn, "usuarios", saved_id)?;
            if let Value::Object(map) = &mut row {
                map.remove("senha_hash");
            }
            Ok(row)
        }
        "user_delete" => {
            let conn = open_connection(&state.db_path)?;
            delete_record(&conn, "usuarios", get_i64(&args, "id")).map(Value::Bool)
        }
        "company_list" => {
            let conn = open_connection(&state.db_path)?;
            Ok(Value::Array(table_list(
                &conn,
                "empresas",
                &search_from_args(&args),
                &["nome", "nome_fantasia", "documento", "cidade", "estado"],
            )?))
        }
        "company_get" => {
            let conn = open_connection(&state.db_path)?;
            table_record(&conn, "empresas", get_i64(&args, "id"))
        }
        "company_save" => {
            let conn = open_connection(&state.db_path)?;
            save_record(&conn, "empresas", &get_payload(&args))
        }
        "company_delete" => {
            let conn = open_connection(&state.db_path)?;
            delete_record(&conn, "empresas", get_i64(&args, "id")).map(Value::Bool)
        }
        "company_lookup_cnpj" | "company_lookup_ie" => Ok(
            json!({"ok": false, "message": "Consulta externa não configurada nesta API interna."}),
        ),
        "entity_list" => {
            let provider = provider_for_state(state)?;
            let entity = get_string(&args, "entity");
            let search = search_from_args(&args);
            Ok(Value::Array(
                entities::provider_list_with_database(&provider, &entity, &search)?
                    .into_iter()
                    .map(Value::Object)
                    .collect(),
            ))
        }
        "entity_save" => {
            let provider = provider_for_state(state)?;
            Ok(Value::Object(entities::provider_save_with_database(
                &provider,
                get_string(&args, "entity"),
                get_payload(&args),
            )?))
        }
        "entity_delete" => {
            let provider = provider_for_state(state)?;
            Ok(Value::Bool(entities::provider_delete_with_database(
                &provider,
                get_string(&args, "entity"),
                get_i64(&args, "id"),
            )?))
        }
        "combo_list" => {
            let provider = provider_for_state(state)?;
            let entity = get_string(&args, "entity");
            let rows = entities::provider_list_with_database(&provider, &entity, "")?;
            let result = rows
                .into_iter()
                .map(|row| {
                    let id = row.get("id").cloned().unwrap_or(Value::Null);
                    let label = row
                        .get("nome")
                        .or_else(|| row.get("descricao"))
                        .or_else(|| row.get("titulo"))
                        .cloned()
                        .unwrap_or_else(|| Value::String(format!("Registro {}", id)));
                    json!({ "id": id, "label": label })
                })
                .collect::<Vec<_>>();
            Ok(Value::Array(result))
        }
        "app_log_write" => {
            let payload = get_payload(&args);
            let conn = open_connection(&state.db_path)?;
            let details = payload.get("details").cloned().unwrap_or(Value::Null);
            write_app_log(
                &conn,
                &state.data_dir,
                AppLogInput {
                    level: payload
                        .get("level")
                        .and_then(Value::as_str)
                        .unwrap_or("info"),
                    category: payload
                        .get("category")
                        .and_then(Value::as_str)
                        .unwrap_or("frontend"),
                    message: payload
                        .get("message")
                        .and_then(Value::as_str)
                        .unwrap_or("Evento da aplicação web"),
                    source: payload.get("source").and_then(Value::as_str),
                    route: payload.get("route").and_then(Value::as_str),
                    details: Some(&details),
                },
            )?;
            Ok(Value::Bool(true))
        }
        "app_log_list" => {
            let conn = open_connection(&state.db_path)?;
            Ok(Value::Array(query_json(&conn, "SELECT id, level, category, message, source, route, details_json, created_at FROM app_logs ORDER BY id DESC LIMIT 300")?))
        }
        "app_log_clear" => {
            let conn = open_connection(&state.db_path)?;
            conn.execute("DELETE FROM app_logs", [])
                .map_err(|err| format!("Falha ao limpar logs: {err}"))?;
            Ok(Value::Bool(true))
        }
        "licensing_load_settings"
        | "licensing_status"
        | "licensing_device_info"
        | "licensing_check_runtime"
        | "support_guard_status" => Ok(json!({
            "enabled": false,
            "status": "disabled",
            "message": "Recurso administrativo disponível pelo runtime desktop/Tauri."
        })),
        "licensing_save_settings"
        | "licensing_start_trial"
        | "support_guard_provision"
        | "support_guard_enable_totp"
        | "support_guard_unlock" => Ok(json!({
            "ok": true,
            "message": "Solicitação registrada pela API interna web."
        })),
        "integration_list" => {
            let conn = open_connection(&state.db_path)?;
            Ok(Value::Array(table_list(
                &conn,
                "integration_configs",
                &search_from_args(&args),
                &["nome", "tipo", "base_url", "ambiente", "status"],
            )?))
        }
        "integration_save" => {
            let conn = open_connection(&state.db_path)?;
            save_record(&conn, "integration_configs", &get_payload(&args))
        }
        "integration_delete" => {
            let conn = open_connection(&state.db_path)?;
            delete_record(&conn, "integration_configs", get_i64(&args, "id")).map(Value::Bool)
        }
        "integration_test" => Ok(
            json!({"ok": true, "status": "not_tested", "message": "Teste real de integração disponível no desktop/API dedicada."}),
        ),
        "integration_logs" => {
            let conn = open_connection(&state.db_path)?;
            Ok(Value::Array(query_json(
                &conn,
                "SELECT * FROM integration_logs ORDER BY id DESC LIMIT 200",
            )?))
        }
        "sync_queue_list" => {
            let conn = open_connection(&state.db_path)?;
            Ok(Value::Array(query_json(&conn, "SELECT id, entity_name, action_name, record_id, payload_json, status, created_at, updated_at FROM sync_queue ORDER BY id DESC LIMIT 300")?))
        }
        "sync_queue_mark_synced" => {
            let conn = open_connection(&state.db_path)?;
            conn.execute(
                "UPDATE sync_queue SET status = 'synced', updated_at = ?1 WHERE id = ?2",
                params![now(), get_i64(&args, "id")],
            )
            .map_err(|err| format!("Falha ao marcar item como sincronizado: {err}"))?;
            Ok(Value::Bool(true))
        }
        "runtime_settings_load" => {
            let conn = open_connection(&state.db_path)?;
            let settings = load_settings_value(&conn, "runtime.settings")?
                .unwrap_or_else(|| default_runtime_settings(state));
            Ok(runtime_settings_payload(state, settings))
        }
        "runtime_settings_save" => {
            let conn = open_connection(&state.db_path)?;
            let settings = args
                .get("settings")
                .cloned()
                .unwrap_or_else(|| Value::Object(get_payload(&args)));
            save_settings_value(&conn, "runtime.settings", &settings)?;
            Ok(runtime_settings_payload(state, settings))
        }
        "runtime_env_example" => Ok(Value::String(crate::runtime_config::default_env_template())),
        "internal_api_status" => {
            let web_status = crate::internal_api::web_server::status().ok();
            Ok(json!({
                "running": true,
                "status": "running",
                "host": state.host,
                "port": state.port,
                "url": format!("http://127.0.0.1:{}", state.port),
                "bind_url": format!("http://{}:{}", state.host, state.port),
                "docs_url": format!("http://127.0.0.1:{}/docs", state.port),
                "token_required": state.config.security.require_token,
                "auto_start": true,
                "web_server": web_status
            }))
        }
        "internal_api_test" => {
            Ok(json!({"ok": true, "url": format!("http://127.0.0.1:{}/health", state.port)}))
        }
        "web_proxy_status" => Ok(serde_json::to_value(
            crate::internal_api::web_server::status().ok(),
        )
        .unwrap_or(Value::Null)),
        "web_proxy_start" | "web_proxy_restart" => Ok(
            json!({"ok": true, "running": true, "message": "Webport já está ativo, pois esta chamada chegou pela própria API interna/proxy."}),
        ),
        "web_proxy_stop" => Ok(
            json!({"ok": false, "running": true, "warning": "O webport que serve a sessão atual não pode ser parado pela própria sessão web."}),
        ),
        "internal_api_test_port" => {
            Ok(json!({"available": false, "running_here": true, "port": state.port}))
        }
        "internal_api_start" | "internal_api_restart" => {
            Ok(json!({"ok": true, "running": true, "message": "API já está ativa neste processo."}))
        }
        "internal_api_stop" => Ok(
            json!({"ok": false, "running": true, "warning": "A API que serve a aplicação web não pode ser parada por esta própria sessão."}),
        ),
        "webhook_status" => Ok(
            serde_json::to_value(crate::native_webhook::server::status()?)
                .map_err(|err| format!("Falha ao serializar status do Webhook Service: {err}"))?,
        ),
        "webhook_start" | "webhook_restart" => Ok(
            json!({"running": crate::native_webhook::server::status()?.running, "runtime": "internal-api-web", "message": "Inicie/reinicie o Webhook Service pelo desktop/headless; a sessão web apenas monitora o serviço real."}),
        ),
        "webhook_stop" => Ok(serde_json::to_value(
            crate::native_webhook::server::stop_background()?
        )
        .map_err(|err| format!("Falha ao serializar stop do Webhook Service: {err}"))?),
        "webhook_list_events" => {
            Ok(json!({"items": crate::native_webhook::routes::list_events_snapshot()}))
        }
        "webhook_clear_events" => {
            crate::native_webhook::routes::clear_events();
            Ok(Value::Bool(true))
        }
        "webhook_test_receive" => Ok(
            json!({"ok": true, "event": {"provider": get_string(&args, "provider"), "event": get_string(&args, "event"), "status": "received", "received_at": now()}}),
        ),
        "websocket_status" => Ok(
            serde_json::to_value(crate::native_websocket::server::status()?)
                .map_err(|err| format!("Falha ao serializar status do WebSocket Service: {err}"))?,
        ),
        "websocket_start" | "websocket_restart" => Ok(
            json!({"running": crate::native_websocket::server::status()?.running, "runtime": "internal-api-web", "message": "Inicie/reinicie o WebSocket Service pelo desktop/headless; a sessão web apenas monitora o serviço real."}),
        ),
        "websocket_stop" => Ok(serde_json::to_value(
            crate::native_websocket::server::stop_background()?,
        )
        .map_err(|err| format!("Falha ao serializar stop do WebSocket Service: {err}"))?),
        "websocket_list_clients" => {
            Ok(json!({"items": crate::native_websocket::hub::list_clients()}))
        }
        "websocket_broadcast_test" => {
            let payload = json!({"type": "template.broadcast.test", "message": get_string(&args, "message"), "sent_at": now()});
            let sent = crate::native_websocket::hub::broadcast_text(payload.to_string());
            Ok(json!({"ok": true, "sent": sent, "payload": payload}))
        }
        "startup_with_windows_set" => Ok(
            json!({"implemented": false, "runtime": "internal-api-web", "message": "Inicialização com Windows deve ser aplicada pelo runtime desktop/Tauri."}),
        ),
        "app_service_install"
        | "app_service_uninstall"
        | "app_service_start"
        | "app_service_stop"
        | "app_service_restart" => Ok(
            json!({"ok": false, "warning": "Controle de serviço nativo indisponível pela sessão web interna."}),
        ),
        "app_service_status" => Ok(
            json!({"running": false, "installed": false, "available": false, "runtime": "internal-api-web"}),
        ),
        "tray_status" => Ok(
            json!({"enabled": false, "available": false, "runtime": "internal-api-web", "message": "Tray icon é recurso do processo desktop."}),
        ),
        "open_print_preview" => Ok(Value::Bool(true)),
        "tray_restore_window" | "tray_exit_app" => Ok(Value::Bool(true)),
        "provider_list_with_database" => Ok(json!([
            {"id": "sqlite", "name": "SQLite interno", "runtime": "internal-api-web"},
            {"id": "mysql", "name": "MySQL", "runtime": "internal-api-web"},
            {"id": "postgres", "name": "PostgreSQL", "runtime": "internal-api-web"}
        ])),
        "entity_provider_list" | "provider_entity_list" | "entity_provider_list_data" => {
            let provider = provider_for_state(state)?;
            let entity = get_string(&args, "entity");
            Ok(Value::Array(
                entities::provider_list_with_database(
                    &provider,
                    &entity,
                    &search_from_args(&args),
                )?
                .into_iter()
                .map(Value::Object)
                .collect(),
            ))
        }
        "provider_entity_get" => {
            let provider = provider_for_state(state)?;
            Ok(Value::Object(
                entities::provider_get_with_database(
                    &provider,
                    &get_string(&args, "entity"),
                    get_i64(&args, "id"),
                )?
                .ok_or_else(|| "Registro não encontrado.".to_string())?,
            ))
        }
        "provider_entity_create" | "provider_entity_update" => {
            let provider = provider_for_state(state)?;
            Ok(Value::Object(entities::provider_save_with_database(
                &provider,
                get_string(&args, "entity"),
                get_payload(&args),
            )?))
        }
        "provider_entity_delete" => {
            let provider = provider_for_state(state)?;
            Ok(Value::Bool(entities::provider_delete_with_database(
                &provider,
                get_string(&args, "entity"),
                get_i64(&args, "id"),
            )?))
        }
        other if other.ends_with("_list") => {
            let entity = other.trim_end_matches("_list").replace('_', "-");
            let provider = provider_for_state(state)?;
            Ok(Value::Array(
                entities::provider_list_with_database(
                    &provider,
                    &entity,
                    &search_from_args(&args),
                )?
                .into_iter()
                .map(Value::Object)
                .collect(),
            ))
        }
        other if other.ends_with("_get") => {
            let entity = other.trim_end_matches("_get").replace('_', "-");
            let provider = provider_for_state(state)?;
            Ok(Value::Object(
                entities::provider_get_with_database(&provider, &entity, get_i64(&args, "id"))?
                    .ok_or_else(|| "Registro não encontrado.".to_string())?,
            ))
        }
        other if other.ends_with("_save") => {
            let entity = other.trim_end_matches("_save").replace('_', "-");
            let provider = provider_for_state(state)?;
            Ok(Value::Object(entities::provider_save_with_database(
                &provider,
                entity,
                get_payload(&args),
            )?))
        }
        other if other.ends_with("_delete") => {
            let entity = other.trim_end_matches("_delete").replace('_', "-");
            let provider = provider_for_state(state)?;
            Ok(Value::Bool(entities::provider_delete_with_database(
                &provider,
                entity,
                get_i64(&args, "id"),
            )?))
        }
        _ => Err(format!(
            "Comando ainda não exposto na API web interna: {command}"
        )),
    }
}
