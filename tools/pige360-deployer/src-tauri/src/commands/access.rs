use chrono::Utc;
use rusqlite::{params, OptionalExtension};
use serde_json::{json, Map, Value};
use tauri::State;

use crate::{
    app_state::SharedState,
    db::{enqueue_sync, open_connection, row_to_json_map, write_audit},
    security::hash_password,
};

use super::auth::{all_permission_keys, require_session_by_token};

const USER_LOGIN_MIN_LENGTH_KEY: &str = "user_login_min_length";
const USER_LOGIN_MIN_LENGTH_DEFAULT: i64 = 2;
const USER_LOGIN_MIN_LENGTH_MIN: i64 = 1;
const USER_LOGIN_MIN_LENGTH_MAX: i64 = 64;

fn get_string(payload: &Map<String, Value>, key: &str) -> Option<String> {
    payload
        .get(key)
        .and_then(|value| match value {
            Value::String(text) => Some(text.trim().to_string()),
            Value::Number(number) => Some(number.to_string()),
            Value::Bool(flag) => Some(if *flag {
                "1".to_string()
            } else {
                "0".to_string()
            }),
            _ => None,
        })
        .filter(|value| !value.is_empty())
}

fn get_bool(payload: &Map<String, Value>, key: &str, default: bool) -> i64 {
    match payload.get(key) {
        Some(Value::Bool(flag)) => {
            if *flag {
                1
            } else {
                0
            }
        }
        Some(Value::Number(number)) => {
            if number.as_i64().unwrap_or(0) != 0 {
                1
            } else {
                0
            }
        }
        Some(Value::String(text)) => {
            if matches!(
                text.trim().to_lowercase().as_str(),
                "1" | "true" | "sim" | "yes"
            ) {
                1
            } else {
                0
            }
        }
        _ => {
            if default {
                1
            } else {
                0
            }
        }
    }
}

fn get_i64(payload: &Map<String, Value>, key: &str) -> Option<i64> {
    payload.get(key).and_then(|value| match value {
        Value::Number(number) => number.as_i64(),
        Value::String(text) => text.trim().parse::<i64>().ok(),
        _ => None,
    })
}

fn get_id(payload: &Map<String, Value>) -> Option<i64> {
    get_i64(payload, "id")
}

fn get_string_array(payload: &Map<String, Value>, key: &str) -> Vec<String> {
    match payload.get(key) {
        Some(Value::Array(items)) => items
            .iter()
            .filter_map(|item| match item {
                Value::String(text) => Some(text.trim().to_string()),
                Value::Number(number) => Some(number.to_string()),
                _ => None,
            })
            .filter(|value| !value.is_empty())
            .collect::<Vec<_>>(),
        Some(Value::String(text)) if !text.trim().is_empty() => text
            .split(',')
            .map(|item| item.trim().to_string())
            .filter(|item| !item.is_empty())
            .collect::<Vec<_>>(),
        _ => Vec::new(),
    }
}

fn get_i64_array(payload: &Map<String, Value>, key: &str) -> Vec<i64> {
    match payload.get(key) {
        Some(Value::Array(items)) => items
            .iter()
            .filter_map(|item| match item {
                Value::Number(number) => number.as_i64(),
                Value::String(text) => text.trim().parse::<i64>().ok(),
                _ => None,
            })
            .collect::<Vec<_>>(),
        Some(Value::String(text)) if !text.trim().is_empty() => text
            .split(',')
            .filter_map(|item| item.trim().parse::<i64>().ok())
            .collect::<Vec<_>>(),
        _ => Vec::new(),
    }
}

fn ensure_master(conn: &rusqlite::Connection, session_token: &str) -> Result<i64, String> {
    let identity = require_session_by_token(conn, session_token)?;
    if !identity.master_user {
        return Err("Apenas usuário master pode executar esta operação.".to_string());
    }
    Ok(identity.user_id)
}

fn validate_email(value: &str) -> bool {
    let email = value.trim();
    !email.is_empty() && email.contains('@') && email.contains('.')
}

fn normalize_login(value: &str) -> String {
    value.trim().to_lowercase()
}

fn clamp_login_min_length(value: i64) -> i64 {
    value.clamp(USER_LOGIN_MIN_LENGTH_MIN, USER_LOGIN_MIN_LENGTH_MAX)
}

fn load_login_min_length(conn: &rusqlite::Connection) -> Result<i64, String> {
    let raw: Option<String> = conn
        .query_row(
            "SELECT valor FROM app_settings WHERE chave = ?1 LIMIT 1",
            [USER_LOGIN_MIN_LENGTH_KEY],
            |row| row.get(0),
        )
        .optional()
        .map_err(|err| format!("Falha ao consultar política de login: {err}"))?;

    let parsed = raw
        .as_deref()
        .and_then(|value| value.trim().parse::<i64>().ok())
        .unwrap_or(USER_LOGIN_MIN_LENGTH_DEFAULT);
    Ok(clamp_login_min_length(parsed))
}

#[tauri::command]
pub fn user_policy_get(
    state: State<'_, SharedState>,
    session_token: String,
) -> Result<Map<String, Value>, String> {
    let db_path = state.db_path()?;
    let conn = open_connection(&db_path)?;
    let _ = ensure_master(&conn, &session_token)?;
    let login_min_length = load_login_min_length(&conn)?;
    Ok(json!({
        "login_min_length": login_min_length,
        "login_min_allowed": USER_LOGIN_MIN_LENGTH_MIN,
        "login_max_allowed": USER_LOGIN_MIN_LENGTH_MAX
    })
    .as_object()
    .cloned()
    .unwrap_or_default())
}

#[tauri::command]
pub fn user_policy_save(
    state: State<'_, SharedState>,
    session_token: String,
    payload: Map<String, Value>,
) -> Result<Map<String, Value>, String> {
    let db_path = state.db_path()?;
    let conn = open_connection(&db_path)?;
    let actor_id = ensure_master(&conn, &session_token)?;
    let now = Utc::now().to_rfc3339();

    let value = get_i64(&payload, "login_min_length")
        .ok_or_else(|| "Informe a quantidade mínima de caracteres para login.".to_string())?;
    let login_min_length = clamp_login_min_length(value);
    if login_min_length != value {
        return Err(format!(
            "A política de login deve ficar entre {} e {} caracteres.",
            USER_LOGIN_MIN_LENGTH_MIN, USER_LOGIN_MIN_LENGTH_MAX
        ));
    }

    conn.execute(
        "INSERT INTO app_settings (chave, valor, created_at, updated_at)
         VALUES (?1, ?2, ?3, ?3)
         ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor, updated_at = excluded.updated_at",
        params![USER_LOGIN_MIN_LENGTH_KEY, login_min_length.to_string(), now],
    )
    .map_err(|err| format!("Falha ao salvar política de login: {err}"))?;

    let value = json!({ "login_min_length": login_min_length });
    write_audit(&conn, "user_policy", "update", Some(actor_id), &value)?;

    Ok(json!({
        "login_min_length": login_min_length,
        "login_min_allowed": USER_LOGIN_MIN_LENGTH_MIN,
        "login_max_allowed": USER_LOGIN_MIN_LENGTH_MAX
    })
    .as_object()
    .cloned()
    .unwrap_or_default())
}

#[tauri::command]
pub fn permission_catalog(
    state: State<'_, SharedState>,
    session_token: String,
) -> Result<Vec<Map<String, Value>>, String> {
    let db_path = state.db_path()?;
    let conn = open_connection(&db_path)?;
    let _ = require_session_by_token(&conn, &session_token)?;

    let mut rows = Vec::new();
    for key in all_permission_keys() {
        let mut item = Map::new();
        item.insert("key".to_string(), Value::String(key.clone()));
        item.insert(
            "group".to_string(),
            Value::String(key.split(':').next().unwrap_or("geral").to_string()),
        );
        item.insert(
            "label".to_string(),
            Value::String(match key.as_str() {
                "usuarios:view" => "Visualizar usuários".to_string(),
                "usuarios:manage" => "Gerenciar usuários".to_string(),
                "perfis:view" => "Visualizar perfis".to_string(),
                "perfis:manage" => "Gerenciar perfis".to_string(),
                "config:view" => "Visualizar configurações".to_string(),
                "config:manage" => "Gerenciar configurações".to_string(),
                "relatorios:export" => "Exportar relatórios".to_string(),
                other => {
                    let mut parts = other.split(':');
                    let module = parts.next().unwrap_or("geral").replace('_', " ");
                    let action = parts.next().unwrap_or("view").replace('_', " ");
                    format!("{} - {}", module, action)
                }
            }),
        );
        rows.push(item);
    }
    Ok(rows)
}

#[tauri::command]
pub fn profile_list(
    state: State<'_, SharedState>,
    session_token: String,
    filters: Map<String, Value>,
) -> Result<Vec<Map<String, Value>>, String> {
    let db_path = state.db_path()?;
    let conn = open_connection(&db_path)?;
    let _ = require_session_by_token(&conn, &session_token)?;
    let search = get_string(&filters, "search").unwrap_or_default();
    let only_active = get_bool(&filters, "onlyActive", false) == 1;

    let mut sql = String::from(
        "SELECT p.id,
                p.nome,
                p.descricao,
                p.perfil_master,
                p.ativo,
                p.created_at,
                p.updated_at,
                COUNT(DISTINCT up.usuario_id) AS total_usuarios,
                COUNT(DISTINCT pp.permissao_chave) AS total_permissoes
         FROM perfis_acesso p
         LEFT JOIN usuarios_perfis up ON up.perfil_id = p.id
         LEFT JOIN perfis_permissoes pp ON pp.perfil_id = p.id
         WHERE 1=1",
    );

    let mut values: Vec<rusqlite::types::Value> = Vec::new();

    if !search.is_empty() {
        sql.push_str(" AND (p.nome LIKE ? OR p.descricao LIKE ?)");
        let wildcard = format!("%{}%", search.trim());
        values.push(rusqlite::types::Value::Text(wildcard.clone()));
        values.push(rusqlite::types::Value::Text(wildcard));
    }

    if only_active {
        sql.push_str(" AND p.ativo = 1");
    }

    sql.push_str(" GROUP BY p.id, p.nome, p.descricao, p.perfil_master, p.ativo, p.created_at, p.updated_at ORDER BY p.nome ASC");

    let mut stmt = conn
        .prepare(&sql)
        .map_err(|err| format!("Falha ao preparar listagem de perfis: {err}"))?;

    let rows = stmt
        .query_map(rusqlite::params_from_iter(values.iter()), row_to_json_map)
        .map_err(|err| format!("Falha ao executar listagem de perfis: {err}"))?;

    rows.collect::<Result<Vec<_>, _>>()
        .map_err(|err| format!("Falha ao mapear perfis: {err}"))
}

#[tauri::command]
pub fn profile_get(
    state: State<'_, SharedState>,
    session_token: String,
    id: i64,
) -> Result<Map<String, Value>, String> {
    let db_path = state.db_path()?;
    let conn = open_connection(&db_path)?;
    let _ = require_session_by_token(&conn, &session_token)?;

    let mut record = conn
        .query_row(
            "SELECT id, nome, descricao, perfil_master, ativo, created_at, updated_at
             FROM perfis_acesso
             WHERE id = ?1
             LIMIT 1",
            [id],
            row_to_json_map,
        )
        .optional()
        .map_err(|err| format!("Falha ao consultar perfil: {err}"))?
        .ok_or_else(|| "Perfil não encontrado.".to_string())?;

    let permission_keys = conn
        .prepare("SELECT permissao_chave FROM perfis_permissoes WHERE perfil_id = ?1 ORDER BY permissao_chave ASC")
        .map_err(|err| format!("Falha ao preparar permissões do perfil: {err}"))?
        .query_map([id], |row| row.get::<_, String>(0))
        .map_err(|err| format!("Falha ao consultar permissões do perfil: {err}"))?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|err| format!("Falha ao mapear permissões do perfil: {err}"))?;

    record.insert(
        "permission_keys".to_string(),
        Value::Array(permission_keys.into_iter().map(Value::String).collect()),
    );
    Ok(record)
}

#[tauri::command]
pub fn profile_save(
    state: State<'_, SharedState>,
    session_token: String,
    payload: Map<String, Value>,
) -> Result<Map<String, Value>, String> {
    let db_path = state.db_path()?;
    let conn = open_connection(&db_path)?;
    let actor_id = ensure_master(&conn, &session_token)?;
    let id = get_id(&payload);
    let now = Utc::now().to_rfc3339();

    let nome =
        get_string(&payload, "nome").ok_or_else(|| "Informe o nome do perfil.".to_string())?;
    let descricao = get_string(&payload, "descricao");
    let perfil_master = get_bool(&payload, "perfil_master", false);
    let ativo = get_bool(&payload, "ativo", true);
    let mut permission_keys = get_string_array(&payload, "permission_keys");
    permission_keys.sort();
    permission_keys.dedup();

    if permission_keys.is_empty() && perfil_master == 0 {
        return Err("Selecione pelo menos uma permissão para o perfil.".to_string());
    }

    for key in &permission_keys {
        if !all_permission_keys().contains(key) {
            return Err(format!("Permissão inválida: {key}"));
        }
    }

    let duplicate_id: Option<i64> = conn
        .query_row(
            "SELECT id FROM perfis_acesso WHERE LOWER(nome) = LOWER(?1) AND (?2 IS NULL OR id <> ?2) LIMIT 1",
            params![nome, id],
            |row| row.get(0),
        )
        .optional()
        .map_err(|err| format!("Falha ao validar nome do perfil: {err}"))?;

    if duplicate_id.is_some() {
        return Err("Já existe perfil com este nome.".to_string());
    }

    let record_id = if let Some(existing_id) = id {
        conn.execute(
            "UPDATE perfis_acesso
             SET nome = ?1, descricao = ?2, perfil_master = ?3, ativo = ?4, updated_at = ?5
             WHERE id = ?6",
            params![nome, descricao, perfil_master, ativo, now, existing_id],
        )
        .map_err(|err| format!("Falha ao atualizar perfil: {err}"))?;
        existing_id
    } else {
        conn.execute(
            "INSERT INTO perfis_acesso (nome, descricao, perfil_master, ativo, created_at, updated_at)
             VALUES (?1, ?2, ?3, ?4, ?5, ?5)",
            params![nome, descricao, perfil_master, ativo, now],
        )
        .map_err(|err| format!("Falha ao inserir perfil: {err}"))?;
        conn.last_insert_rowid()
    };

    conn.execute(
        "DELETE FROM perfis_permissoes WHERE perfil_id = ?1",
        [record_id],
    )
    .map_err(|err| format!("Falha ao limpar permissões do perfil: {err}"))?;

    let permission_rows = if perfil_master == 1 {
        all_permission_keys()
    } else {
        permission_keys
    };
    for key in permission_rows {
        conn.execute(
            "INSERT INTO perfis_permissoes (perfil_id, permissao_chave, created_at) VALUES (?1, ?2, ?3)",
            params![record_id, key, now],
        )
        .map_err(|err| format!("Falha ao gravar permissão do perfil: {err}"))?;
    }

    let payload_json = json!({
        "id": record_id,
        "nome": nome,
        "descricao": descricao,
        "perfil_master": perfil_master,
        "ativo": ativo,
    });
    enqueue_sync(
        &conn,
        "perfis_acesso",
        if id.is_some() { "update" } else { "insert" },
        Some(record_id),
        &payload_json,
    )?;
    write_audit(
        &conn,
        "perfis_acesso",
        if id.is_some() { "update" } else { "insert" },
        Some(record_id),
        &json!({
            "actor_id": actor_id,
            "payload": payload_json
        }),
    )?;

    profile_get(state, session_token, record_id)
}

#[tauri::command]
pub fn profile_delete(
    state: State<'_, SharedState>,
    session_token: String,
    id: i64,
) -> Result<bool, String> {
    let db_path = state.db_path()?;
    let conn = open_connection(&db_path)?;
    let actor_id = ensure_master(&conn, &session_token)?;

    let linked_users: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM usuarios_perfis WHERE perfil_id = ?1",
            [id],
            |row| row.get(0),
        )
        .map_err(|err| format!("Falha ao validar vínculo do perfil: {err}"))?;

    if linked_users > 0 {
        return Err(
            "Não é possível excluir o perfil porque existem usuários vinculados a ele.".to_string(),
        );
    }

    conn.execute("DELETE FROM perfis_permissoes WHERE perfil_id = ?1", [id])
        .map_err(|err| format!("Falha ao excluir permissões do perfil: {err}"))?;
    let affected = conn
        .execute("DELETE FROM perfis_acesso WHERE id = ?1", [id])
        .map_err(|err| format!("Falha ao excluir perfil: {err}"))?;

    if affected == 0 {
        return Err("Perfil não encontrado.".to_string());
    }

    write_audit(
        &conn,
        "perfis_acesso",
        "delete",
        Some(id),
        &json!({ "actor_id": actor_id }),
    )?;
    Ok(true)
}

#[tauri::command]
pub fn user_list(
    state: State<'_, SharedState>,
    session_token: String,
    filters: Map<String, Value>,
) -> Result<Vec<Map<String, Value>>, String> {
    let db_path = state.db_path()?;
    let conn = open_connection(&db_path)?;
    let _ = require_session_by_token(&conn, &session_token)?;
    let search = get_string(&filters, "search").unwrap_or_default();
    let only_active = get_bool(&filters, "onlyActive", false) == 1;
    let empresa_id = get_i64(&filters, "empresaId");

    let mut sql = String::from(
        "SELECT u.id,
                u.nome,
                u.login,
                u.email,
                u.telefone,
                u.cargo,
                u.photo_url,
                u.master_user,
                u.administrador,
                u.senha_provisoria,
                u.ativo,
                u.ultimo_login_em,
                u.created_at,
                u.updated_at,
                GROUP_CONCAT(DISTINCT p.nome) AS perfis,
                GROUP_CONCAT(DISTINCT e.nome) AS empresas
         FROM usuarios u
         LEFT JOIN usuarios_perfis up ON up.usuario_id = u.id
         LEFT JOIN perfis_acesso p ON p.id = up.perfil_id
         LEFT JOIN usuarios_empresas ue ON ue.usuario_id = u.id
         LEFT JOIN empresas e ON e.id = ue.empresa_id
         WHERE 1=1",
    );
    let mut values: Vec<rusqlite::types::Value> = Vec::new();

    if !search.is_empty() {
        sql.push_str(" AND (u.nome LIKE ? OR u.login LIKE ? OR u.email LIKE ?)");
        let wildcard = format!("%{}%", search.trim());
        values.push(rusqlite::types::Value::Text(wildcard.clone()));
        values.push(rusqlite::types::Value::Text(wildcard.clone()));
        values.push(rusqlite::types::Value::Text(wildcard));
    }

    if only_active {
        sql.push_str(" AND u.ativo = 1");
    }

    if let Some(company_id) = empresa_id {
        sql.push_str(" AND EXISTS (SELECT 1 FROM usuarios_empresas ue2 WHERE ue2.usuario_id = u.id AND ue2.empresa_id = ?)");
        values.push(rusqlite::types::Value::Integer(company_id));
    }

    sql.push_str(" GROUP BY u.id ORDER BY u.nome ASC");

    let mut stmt = conn
        .prepare(&sql)
        .map_err(|err| format!("Falha ao preparar listagem de usuários: {err}"))?;

    let rows = stmt
        .query_map(rusqlite::params_from_iter(values.iter()), row_to_json_map)
        .map_err(|err| format!("Falha ao executar listagem de usuários: {err}"))?;

    rows.collect::<Result<Vec<_>, _>>()
        .map_err(|err| format!("Falha ao mapear usuários: {err}"))
}

#[tauri::command]
pub fn user_get(
    state: State<'_, SharedState>,
    session_token: String,
    id: i64,
) -> Result<Map<String, Value>, String> {
    let db_path = state.db_path()?;
    let conn = open_connection(&db_path)?;
    let _ = require_session_by_token(&conn, &session_token)?;

    let mut record = conn
        .query_row(
            "SELECT id, nome, login, email, telefone, cargo, observacoes, photo_url, master_user, administrador, senha_provisoria, ativo, ultimo_login_em, created_at, updated_at
             FROM usuarios
             WHERE id = ?1
             LIMIT 1",
            [id],
            row_to_json_map,
        )
        .optional()
        .map_err(|err| format!("Falha ao consultar usuário: {err}"))?
        .ok_or_else(|| "Usuário não encontrado.".to_string())?;

    let profile_ids = conn
        .prepare(
            "SELECT perfil_id FROM usuarios_perfis WHERE usuario_id = ?1 ORDER BY perfil_id ASC",
        )
        .map_err(|err| format!("Falha ao preparar perfis do usuário: {err}"))?
        .query_map([id], |row| row.get::<_, i64>(0))
        .map_err(|err| format!("Falha ao consultar perfis do usuário: {err}"))?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|err| format!("Falha ao mapear perfis do usuário: {err}"))?;

    let empresa_ids = conn
        .prepare("SELECT empresa_id FROM usuarios_empresas WHERE usuario_id = ?1 ORDER BY empresa_id ASC")
        .map_err(|err| format!("Falha ao preparar empresas do usuário: {err}"))?
        .query_map([id], |row| row.get::<_, i64>(0))
        .map_err(|err| format!("Falha ao consultar empresas do usuário: {err}"))?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|err| format!("Falha ao mapear empresas do usuário: {err}"))?;

    record.insert(
        "profile_ids".to_string(),
        Value::Array(profile_ids.into_iter().map(Value::from).collect()),
    );
    record.insert(
        "empresa_ids".to_string(),
        Value::Array(empresa_ids.into_iter().map(Value::from).collect()),
    );
    Ok(record)
}

#[tauri::command]
pub fn user_save(
    state: State<'_, SharedState>,
    session_token: String,
    payload: Map<String, Value>,
) -> Result<Map<String, Value>, String> {
    let db_path = state.db_path()?;
    let conn = open_connection(&db_path)?;
    let actor_id = ensure_master(&conn, &session_token)?;
    let id = get_id(&payload);
    let now = Utc::now().to_rfc3339();

    let nome =
        get_string(&payload, "nome").ok_or_else(|| "Informe o nome do usuário.".to_string())?;
    let login = normalize_login(
        &get_string(&payload, "login").ok_or_else(|| "Informe o login do usuário.".to_string())?,
    );
    let email = get_string(&payload, "email");
    let telefone = get_string(&payload, "telefone");
    let cargo = get_string(&payload, "cargo");
    let observacoes = get_string(&payload, "observacoes");
    let photo_url = get_string(&payload, "photo_url");
    let master_user = get_bool(&payload, "master_user", false);
    let administrador = get_bool(&payload, "administrador", false);
    let senha_provisoria = get_bool(&payload, "senha_provisoria", false);
    let ativo = get_bool(&payload, "ativo", true);
    let password = get_string(&payload, "senha");
    let profile_ids = get_i64_array(&payload, "profile_ids");
    let empresa_ids = get_i64_array(&payload, "empresa_ids");
    let login_min_length = load_login_min_length(&conn)?;

    if login.len() < login_min_length as usize {
        return Err(format!(
            "O login deve conter ao menos {} caracteres.",
            login_min_length
        ));
    }

    if let Some(value) = email.as_deref() {
        if !validate_email(value) {
            return Err("O e-mail do usuário é inválido.".to_string());
        }
    }

    if let Some(existing_id) = id {
        if existing_id == actor_id && ativo == 0 {
            return Err(
                "O usuário master logado não pode ser inativado nesta operação.".to_string(),
            );
        }
    }

    let duplicate_id: Option<i64> = conn
        .query_row(
            "SELECT id FROM usuarios WHERE LOWER(login) = LOWER(?1) AND (?2 IS NULL OR id <> ?2) LIMIT 1",
            params![login, id],
            |row| row.get(0),
        )
        .optional()
        .map_err(|err| format!("Falha ao validar login do usuário: {err}"))?;

    if duplicate_id.is_some() {
        return Err("Já existe usuário com este login.".to_string());
    }

    if master_user != 1 {
        if profile_ids.is_empty() {
            return Err("Selecione ao menos um perfil de acesso para o usuário.".to_string());
        }
        if empresa_ids.is_empty() {
            return Err("Selecione ao menos uma empresa para o usuário.".to_string());
        }
    }

    for perfil_id in &profile_ids {
        let exists: Option<i64> = conn
            .query_row(
                "SELECT id FROM perfis_acesso WHERE id = ?1 LIMIT 1",
                [perfil_id],
                |row| row.get(0),
            )
            .optional()
            .map_err(|err| format!("Falha ao validar perfil do usuário: {err}"))?;
        if exists.is_none() {
            return Err(format!("Perfil inválido informado: {perfil_id}."));
        }
    }

    for empresa_id in &empresa_ids {
        let exists: Option<i64> = conn
            .query_row(
                "SELECT id FROM empresas WHERE id = ?1 LIMIT 1",
                [empresa_id],
                |row| row.get(0),
            )
            .optional()
            .map_err(|err| format!("Falha ao validar empresa do usuário: {err}"))?;
        if exists.is_none() {
            return Err(format!("Empresa inválida informada: {empresa_id}."));
        }
    }

    let record_id = if let Some(existing_id) = id {
        if let Some(raw_password) = password.as_deref() {
            if raw_password.trim().len() < 6 {
                return Err("A senha deve conter ao menos 6 caracteres.".to_string());
            }
            let password_hash = hash_password(raw_password.trim())?;
            conn.execute(
                "UPDATE usuarios
                 SET nome = ?1, login = ?2, email = ?3, telefone = ?4, cargo = ?5, observacoes = ?6, photo_url = ?7,
                     master_user = ?8, administrador = ?9, senha_provisoria = ?10, ativo = ?11,
                     senha_hash = ?12, updated_at = ?13
                 WHERE id = ?14",
                params![
                    nome,
                    login,
                    email,
                    telefone,
                    cargo,
                    observacoes,
                    photo_url.clone(),
                    master_user,
                    administrador,
                    senha_provisoria,
                    ativo,
                    password_hash,
                    now,
                    existing_id,
                ],
            )
            .map_err(|err| format!("Falha ao atualizar usuário: {err}"))?;
        } else {
            conn.execute(
                "UPDATE usuarios
                 SET nome = ?1, login = ?2, email = ?3, telefone = ?4, cargo = ?5, observacoes = ?6, photo_url = ?7,
                     master_user = ?8, administrador = ?9, senha_provisoria = ?10, ativo = ?11,
                     updated_at = ?12
                 WHERE id = ?13",
                params![
                    nome,
                    login,
                    email,
                    telefone,
                    cargo,
                    observacoes,
                    photo_url.clone(),
                    master_user,
                    administrador,
                    senha_provisoria,
                    ativo,
                    now,
                    existing_id,
                ],
            )
            .map_err(|err| format!("Falha ao atualizar usuário: {err}"))?;
        }
        existing_id
    } else {
        let raw_password =
            password.ok_or_else(|| "Informe a senha do novo usuário.".to_string())?;
        if raw_password.trim().len() < 6 {
            return Err("A senha deve conter ao menos 6 caracteres.".to_string());
        }
        let password_hash = hash_password(raw_password.trim())?;
        conn.execute(
            "INSERT INTO usuarios (
                nome, login, email, telefone, cargo, observacoes, photo_url, senha_hash,
                master_user, administrador, senha_provisoria, ativo, created_at, updated_at
             ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?13)",
            params![
                nome,
                login,
                email,
                telefone,
                cargo,
                observacoes,
                photo_url.clone(),
                password_hash,
                master_user,
                administrador,
                senha_provisoria,
                ativo,
                now,
            ],
        )
        .map_err(|err| format!("Falha ao inserir usuário: {err}"))?;
        conn.last_insert_rowid()
    };

    conn.execute(
        "DELETE FROM usuarios_perfis WHERE usuario_id = ?1",
        [record_id],
    )
    .map_err(|err| format!("Falha ao limpar perfis do usuário: {err}"))?;
    conn.execute(
        "DELETE FROM usuarios_empresas WHERE usuario_id = ?1",
        [record_id],
    )
    .map_err(|err| format!("Falha ao limpar empresas do usuário: {err}"))?;

    for perfil_id in profile_ids {
        conn.execute(
            "INSERT INTO usuarios_perfis (usuario_id, perfil_id, created_at) VALUES (?1, ?2, ?3)",
            params![record_id, perfil_id, now],
        )
        .map_err(|err| format!("Falha ao vincular perfil ao usuário: {err}"))?;
    }

    for empresa_id in empresa_ids {
        conn.execute(
            "INSERT INTO usuarios_empresas (usuario_id, empresa_id, created_at) VALUES (?1, ?2, ?3)",
            params![record_id, empresa_id, now],
        )
        .map_err(|err| format!("Falha ao vincular empresa ao usuário: {err}"))?;
    }

    let payload_json = json!({
        "id": record_id,
        "nome": nome,
        "login": login,
        "photo_url": photo_url,
        "master_user": master_user,
        "administrador": administrador,
        "ativo": ativo,
    });
    enqueue_sync(
        &conn,
        "usuarios",
        if id.is_some() { "update" } else { "insert" },
        Some(record_id),
        &payload_json,
    )?;
    write_audit(
        &conn,
        "usuarios",
        if id.is_some() { "update" } else { "insert" },
        Some(record_id),
        &json!({
            "actor_id": actor_id,
            "payload": payload_json
        }),
    )?;

    user_get(state, session_token, record_id)
}

#[tauri::command]
pub fn user_delete(
    state: State<'_, SharedState>,
    session_token: String,
    id: i64,
) -> Result<bool, String> {
    let db_path = state.db_path()?;
    let conn = open_connection(&db_path)?;
    let actor_id = ensure_master(&conn, &session_token)?;

    if actor_id == id {
        return Err("O usuário master logado não pode excluir a própria conta.".to_string());
    }

    let master_count: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM usuarios WHERE master_user = 1 AND ativo = 1",
            [],
            |row| row.get(0),
        )
        .map_err(|err| format!("Falha ao validar usuários master: {err}"))?;
    let target_is_master: i64 = conn
        .query_row(
            "SELECT COALESCE(master_user, 0) FROM usuarios WHERE id = ?1 LIMIT 1",
            [id],
            |row| row.get(0),
        )
        .optional()
        .map_err(|err| format!("Falha ao validar usuário alvo: {err}"))?
        .unwrap_or(0);

    if target_is_master == 1 && master_count <= 1 {
        return Err("Não é possível excluir o último usuário master ativo.".to_string());
    }

    conn.execute("DELETE FROM user_sessions WHERE usuario_id = ?1", [id])
        .map_err(|err| format!("Falha ao limpar sessões do usuário: {err}"))?;
    let affected = conn
        .execute("DELETE FROM usuarios WHERE id = ?1", [id])
        .map_err(|err| format!("Falha ao excluir usuário: {err}"))?;

    if affected == 0 {
        return Err("Usuário não encontrado.".to_string());
    }

    write_audit(
        &conn,
        "usuarios",
        "delete",
        Some(id),
        &json!({ "actor_id": actor_id }),
    )?;
    Ok(true)
}
