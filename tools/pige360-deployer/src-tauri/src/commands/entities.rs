use chrono::Utc;
use rusqlite::{params_from_iter, OptionalExtension};
use serde_json::{json, Map, Value};
#[cfg(any(feature = "desktop", feature = "mobile"))]
use tauri::State;

use crate::{
    app_state::SharedState,
    db::{enqueue_sync, open_connection, row_to_json_map, write_audit},
    models::ComboOption,
    security::hash_password,
};

struct EntityDefinition {
    table: &'static str,
    fields: &'static [&'static str],
    searchable: &'static [&'static str],
    required: &'static [&'static str],
    label_column: &'static str,
}

fn entity_definition(entity: &str) -> Option<EntityDefinition> {
    match entity {
        "empresas" | "companies" => Some(EntityDefinition {
            table: "empresas",
            fields: &[
                "nome",
                "nome_fantasia",
                "documento",
                "cidade",
                "estado",
                "ativo",
            ],
            searchable: &["nome", "nome_fantasia", "documento", "cidade"],
            required: &["nome"],
            label_column: "nome",
        }),
        "perfis" | "perfis_acesso" | "profiles" => Some(EntityDefinition {
            table: "perfis_acesso",
            fields: &["nome", "descricao", "perfil_master", "ativo"],
            searchable: &["nome", "descricao"],
            required: &["nome"],
            label_column: "nome",
        }),
        "usuarios" | "users" => Some(EntityDefinition {
            table: "usuarios",
            fields: &[
                "nome",
                "login",
                "email",
                "telefone",
                "cargo",
                "observacoes",
                "master_user",
                "administrador",
                "senha_provisoria",
                "ativo",
            ],
            searchable: &["nome", "login", "email"],
            required: &["nome", "login"],
            label_column: "nome",
        }),
        "departamentos" => Some(EntityDefinition {
            table: "departamentos",
            fields: &["descricao", "ativo"],
            searchable: &["descricao"],
            required: &["descricao"],
            label_column: "descricao",
        }),
        "funcoes" => Some(EntityDefinition {
            table: "funcoes",
            fields: &["descricao", "ativo"],
            searchable: &["descricao"],
            required: &["descricao"],
            label_column: "descricao",
        }),
        "centro_custos" => Some(EntityDefinition {
            table: "centro_custos",
            fields: &["codigo", "descricao", "ativo"],
            searchable: &["codigo", "descricao"],
            required: &["descricao"],
            label_column: "descricao",
        }),
        "clientes" => Some(EntityDefinition {
            table: "clientes",
            fields: &[
                "nome",
                "documento",
                "telefone",
                "email",
                "endereco",
                "cidade",
                "estado",
                "observacoes",
                "ativo",
            ],
            searchable: &["nome", "documento", "email"],
            required: &["nome"],
            label_column: "nome",
        }),
        "fornecedores" => Some(EntityDefinition {
            table: "fornecedores",
            fields: &[
                "nome",
                "documento",
                "telefone",
                "email",
                "endereco",
                "cidade",
                "estado",
                "observacoes",
                "ativo",
            ],
            searchable: &["nome", "documento", "email"],
            required: &["nome"],
            label_column: "nome",
        }),
        "produtos" => Some(EntityDefinition {
            table: "produtos",
            fields: &["codigo", "descricao", "tipo", "unidade", "valor", "ativo"],
            searchable: &["codigo", "descricao", "tipo"],
            required: &["descricao"],
            label_column: "descricao",
        }),
        _ => None,
    }
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

fn normalize_value(payload: &Map<String, Value>, field: &str) -> Value {
    let value = payload.get(field).cloned().unwrap_or(Value::Null);

    match field {
        "empresa_id"
        | "departamento_id"
        | "funcao_id"
        | "centro_custo_id"
        | "horario_id"
        | "escala_id"
        | "numero"
        | "porta"
        | "carga_horaria_minutos"
        | "tolerancia_minutos"
        | "ativo"
        | "administrador"
        | "impacta_banco_horas"
        | "abono"
        | "banco_horas_ativo"
        | "permite_hora_extra"
        | "compensa_atraso_com_extra"
        | "usa_banco_para_excedente" => match value {
            Value::String(v) if v.trim().is_empty() => Value::Null,
            Value::String(v) => v.parse::<i64>().map(Value::from).unwrap_or(Value::Null),
            other => other,
        },
        _ => value,
    }
}

#[cfg(any(feature = "desktop", feature = "mobile"))]
#[tauri::command]
pub fn entity_list(
    state: State<'_, SharedState>,
    entity: String,
    search: String,
) -> Result<Vec<Map<String, Value>>, String> {
    let definition =
        entity_definition(&entity).ok_or_else(|| "Entidade não permitida.".to_string())?;
    let db_path = state.db_path()?;
    let conn = open_connection(&db_path)?;

    let mut sql = format!(
        "SELECT id, {} FROM {}",
        definition.fields.join(", "),
        definition.table
    );
    let mut params: Vec<rusqlite::types::Value> = Vec::new();

    if !search.trim().is_empty() {
        let clauses = definition
            .searchable
            .iter()
            .map(|column| format!("{} LIKE ?", column))
            .collect::<Vec<_>>()
            .join(" OR ");
        sql.push_str(&format!(" WHERE ({clauses})"));
        for _ in definition.searchable {
            params.push(rusqlite::types::Value::Text(format!("%{}%", search.trim())));
        }
    }

    sql.push_str(" ORDER BY id DESC");

    let mut stmt = conn
        .prepare(&sql)
        .map_err(|err| format!("Falha ao preparar listagem de {}: {err}", definition.table))?;

    let mapped = stmt
        .query_map(params_from_iter(params.iter()), row_to_json_map)
        .map_err(|err| format!("Falha ao executar listagem de {}: {err}", definition.table))?;

    let rows: Result<Vec<_>, _> = mapped.collect();
    rows.map_err(|err| format!("Falha ao mapear listagem de {}: {err}", definition.table))
}

#[cfg(any(feature = "desktop", feature = "mobile"))]
#[tauri::command]
pub fn combo_list(
    state: State<'_, SharedState>,
    entity: String,
) -> Result<Vec<ComboOption>, String> {
    let definition =
        entity_definition(&entity).ok_or_else(|| "Entidade não permitida.".to_string())?;
    let db_path = state.db_path()?;
    let conn = open_connection(&db_path)?;
    let sql = format!(
        "SELECT id, COALESCE({}, '[sem descrição]') AS label FROM {} ORDER BY label ASC",
        definition.label_column, definition.table
    );

    let mut stmt = conn
        .prepare(&sql)
        .map_err(|err| format!("Falha ao preparar combo de {}: {err}", definition.table))?;

    let rows = stmt
        .query_map([], |row| {
            Ok(ComboOption {
                id: row.get(0)?,
                label: row.get(1)?,
            })
        })
        .map_err(|err| format!("Falha ao executar combo de {}: {err}", definition.table))?;

    let result: Result<Vec<_>, _> = rows.collect();
    result.map_err(|err| format!("Falha ao mapear combo de {}: {err}", definition.table))
}

#[cfg(any(feature = "desktop", feature = "mobile"))]
#[tauri::command]
pub fn entity_save(
    state: State<'_, SharedState>,
    entity: String,
    payload: Map<String, Value>,
) -> Result<Map<String, Value>, String> {
    let definition =
        entity_definition(&entity).ok_or_else(|| "Entidade não permitida.".to_string())?;
    let db_path = state.db_path()?;
    let conn = open_connection(&db_path)?;
    let now = Utc::now().to_rfc3339();
    let id = payload.get("id").and_then(|v| {
        v.as_i64()
            .or_else(|| v.as_str().and_then(|s| s.parse::<i64>().ok()))
    });

    for required in definition.required {
        let raw = payload
            .get(*required)
            .and_then(|v| v.as_str())
            .map(|s| s.trim().to_string())
            .unwrap_or_default();
        if raw.is_empty() {
            return Err(format!("O campo {} é obrigatório.", required));
        }
    }

    let mut columns: Vec<String> = Vec::new();
    let mut values: Vec<Value> = Vec::new();

    for field in definition.fields {
        if entity == "usuarios" && *field == "senha_hash" {
            if let Some(password) = payload.get("senha").and_then(|v| v.as_str()) {
                if !password.trim().is_empty() {
                    columns.push((*field).to_string());
                    values.push(Value::String(hash_password(password)?));
                } else if id.is_none() {
                    return Err("Senha é obrigatória para novo usuário.".to_string());
                }
            } else if id.is_none() {
                return Err("Senha é obrigatória para novo usuário.".to_string());
            }
            continue;
        }

        columns.push((*field).to_string());
        values.push(normalize_value(&payload, field));
    }

    let record_id = if let Some(existing_id) = id {
        let set_clause = columns
            .iter()
            .map(|col| format!("{} = ?", col))
            .chain(std::iter::once("updated_at = ?".to_string()))
            .collect::<Vec<_>>()
            .join(", ");

        let sql = format!(
            "UPDATE {} SET {} WHERE id = ?",
            definition.table, set_clause
        );
        let mut sql_values: Vec<rusqlite::types::Value> =
            values.iter().map(json_to_sql_value).collect();
        sql_values.push(rusqlite::types::Value::Text(now.clone()));
        sql_values.push(rusqlite::types::Value::Integer(existing_id));

        conn.execute(&sql, params_from_iter(sql_values.iter()))
            .map_err(|err| format!("Falha ao atualizar {}: {err}", definition.table))?;
        existing_id
    } else {
        let mut insert_columns = columns.clone();
        insert_columns.push("created_at".to_string());
        insert_columns.push("updated_at".to_string());

        let placeholders = std::iter::repeat_n("?", insert_columns.len())
            .collect::<Vec<_>>()
            .join(", ");

        let sql = format!(
            "INSERT INTO {} ({}) VALUES ({})",
            definition.table,
            insert_columns.join(", "),
            placeholders
        );

        let mut sql_values: Vec<rusqlite::types::Value> =
            values.iter().map(json_to_sql_value).collect();
        sql_values.push(rusqlite::types::Value::Text(now.clone()));
        sql_values.push(rusqlite::types::Value::Text(now.clone()));

        conn.execute(&sql, params_from_iter(sql_values.iter()))
            .map_err(|err| format!("Falha ao inserir em {}: {err}", definition.table))?;
        conn.last_insert_rowid()
    };

    let select_sql = format!(
        "SELECT id, {} FROM {} WHERE id = ?1",
        definition.fields.join(", "),
        definition.table
    );
    let saved = conn
        .query_row(&select_sql, [record_id], row_to_json_map)
        .optional()
        .map_err(|err| {
            format!(
                "Falha ao reler registro salvo em {}: {err}",
                definition.table
            )
        })?
        .ok_or_else(|| "Registro salvo não encontrado.".to_string())?;

    let action_name = if id.is_some() { "update" } else { "create" };
    let payload_value = Value::Object(saved.clone());
    write_audit(&conn, &entity, action_name, Some(record_id), &payload_value)?;
    enqueue_sync(&conn, &entity, action_name, Some(record_id), &payload_value)?;

    Ok(saved)
}

#[cfg(any(feature = "desktop", feature = "mobile"))]
#[tauri::command]
pub fn entity_delete(
    state: State<'_, SharedState>,
    entity: String,
    id: i64,
) -> Result<bool, String> {
    let definition =
        entity_definition(&entity).ok_or_else(|| "Entidade não permitida.".to_string())?;
    let db_path = state.db_path()?;
    let conn = open_connection(&db_path)?;

    let sql = format!("DELETE FROM {} WHERE id = ?1", definition.table);
    let affected = conn
        .execute(&sql, [id])
        .map_err(|err| format!("Falha ao excluir de {}: {err}", definition.table))?;

    if affected > 0 {
        let payload = json!({ "id": id, "entity": entity });
        write_audit(&conn, &entity, "delete", Some(id), &payload)?;
        enqueue_sync(&conn, &entity, "delete", Some(id), &payload)?;
    }

    Ok(affected > 0)
}

fn db_value_from_json(value: Value) -> crate::core::database::provider::types::DbValue {
    crate::core::database::provider::types::DbValue::from(value)
}

fn current_provider_driver() -> String {
    std::env::var("PIGE360_DEPLOYER_DATABASE_DRIVER")
        .or_else(|_| std::env::var("PIGE360_DEPLOYER_DB_DRIVER"))
        .unwrap_or_else(|_| "sqlite".to_string())
        .trim()
        .to_ascii_lowercase()
}

fn active_provider(
    state: &SharedState,
) -> Result<crate::core::database::provider::ActiveDatabaseProvider, String> {
    use crate::core::database::{config::DatabaseConfig, provider::ActiveDatabaseProvider};

    let driver = current_provider_driver();
    let db_path = state.db_path()?;
    let config = DatabaseConfig::from_env_with_driver(&driver);
    ActiveDatabaseProvider::from_config(config, &db_path)
}

fn select_columns(definition: &EntityDefinition) -> String {
    format!("id, {}", definition.fields.join(", "))
}

fn placeholders(
    provider: &dyn crate::core::database::provider::DatabaseProvider,
    start: usize,
    count: usize,
) -> Vec<String> {
    (start..start + count)
        .map(|index| provider.placeholder(index))
        .collect()
}

pub fn provider_list_with_database(
    provider: &dyn crate::core::database::provider::DatabaseProvider,
    entity: &str,
    search: &str,
) -> Result<Vec<Map<String, Value>>, String> {
    let definition =
        entity_definition(entity).ok_or_else(|| "Entidade não permitida.".to_string())?;
    let mut sql = format!(
        "SELECT {} FROM {}",
        select_columns(&definition),
        definition.table
    );
    let mut params = Vec::new();

    if !search.trim().is_empty() {
        let clauses = definition
            .searchable
            .iter()
            .enumerate()
            .map(|(index, column)| format!("{column} LIKE {}", provider.placeholder(index + 1)))
            .collect::<Vec<_>>()
            .join(" OR ");
        sql.push_str(&format!(" WHERE ({clauses})"));
        for _ in definition.searchable {
            params.push(crate::core::database::provider::types::DbValue::Text(
                format!("%{}%", search.trim()),
            ));
        }
    }

    sql.push_str(" ORDER BY id DESC");
    provider.query(&sql, &params)
}

pub(crate) fn provider_get_with_database(
    provider: &dyn crate::core::database::provider::DatabaseProvider,
    entity: &str,
    id: i64,
) -> Result<Option<Map<String, Value>>, String> {
    let definition =
        entity_definition(entity).ok_or_else(|| "Entidade não permitida.".to_string())?;
    let sql = format!(
        "SELECT {} FROM {} WHERE id = {}",
        select_columns(&definition),
        definition.table,
        provider.placeholder(1)
    );
    provider.query_one(
        &sql,
        &[crate::core::database::provider::types::DbValue::Integer(id)],
    )
}

fn provider_insert_audit(
    provider: &dyn crate::core::database::provider::DatabaseProvider,
    entity: &str,
    action: &str,
    record_id: Option<i64>,
    payload: &Value,
    now: &str,
) -> Result<(), String> {
    let sql = format!(
        "INSERT INTO audit_logs (entity_name, action_name, record_id, payload_json, created_at) VALUES ({}, {}, {}, {}, {})",
        provider.placeholder(1),
        provider.placeholder(2),
        provider.placeholder(3),
        provider.placeholder(4),
        provider.placeholder(5)
    );
    provider.execute(
        &sql,
        &[
            crate::core::database::provider::types::DbValue::Text(entity.to_string()),
            crate::core::database::provider::types::DbValue::Text(action.to_string()),
            record_id
                .map(crate::core::database::provider::types::DbValue::Integer)
                .unwrap_or(crate::core::database::provider::types::DbValue::Null),
            crate::core::database::provider::types::DbValue::Text(payload.to_string()),
            crate::core::database::provider::types::DbValue::Text(now.to_string()),
        ],
    )?;
    Ok(())
}

fn provider_enqueue_sync(
    provider: &dyn crate::core::database::provider::DatabaseProvider,
    entity: &str,
    action: &str,
    record_id: Option<i64>,
    payload: &Value,
    now: &str,
) -> Result<(), String> {
    let sql = format!(
        "INSERT INTO sync_queue (entity_name, action_name, record_id, payload_json, status, created_at, updated_at) VALUES ({}, {}, {}, {}, {}, {}, {})",
        provider.placeholder(1),
        provider.placeholder(2),
        provider.placeholder(3),
        provider.placeholder(4),
        provider.placeholder(5),
        provider.placeholder(6),
        provider.placeholder(7)
    );
    provider.execute(
        &sql,
        &[
            crate::core::database::provider::types::DbValue::Text(entity.to_string()),
            crate::core::database::provider::types::DbValue::Text(action.to_string()),
            record_id
                .map(crate::core::database::provider::types::DbValue::Integer)
                .unwrap_or(crate::core::database::provider::types::DbValue::Null),
            crate::core::database::provider::types::DbValue::Text(payload.to_string()),
            crate::core::database::provider::types::DbValue::Text("pending".to_string()),
            crate::core::database::provider::types::DbValue::Text(now.to_string()),
            crate::core::database::provider::types::DbValue::Text(now.to_string()),
        ],
    )?;
    Ok(())
}

pub(crate) fn provider_save_with_database(
    provider: &dyn crate::core::database::provider::DatabaseProvider,
    entity: String,
    payload: Map<String, Value>,
) -> Result<Map<String, Value>, String> {
    use crate::core::database::{config::DatabaseDriver, provider::types::DbValue};

    let definition =
        entity_definition(&entity).ok_or_else(|| "Entidade não permitida.".to_string())?;
    let now = Utc::now().to_rfc3339();
    let id = payload.get("id").and_then(|value| {
        value
            .as_i64()
            .or_else(|| value.as_str().and_then(|text| text.parse::<i64>().ok()))
    });

    for required in definition.required {
        let raw = payload
            .get(*required)
            .and_then(|value| value.as_str())
            .map(|value| value.trim().to_string())
            .unwrap_or_default();
        if raw.is_empty() {
            return Err(format!("O campo {required} é obrigatório."));
        }
    }

    let mut columns = Vec::new();
    let mut values = Vec::new();
    for field in definition.fields {
        columns.push((*field).to_string());
        values.push(db_value_from_json(normalize_value(&payload, field)));
    }

    let record_id = if let Some(existing_id) = id {
        let set_clause = columns
            .iter()
            .enumerate()
            .map(|(index, column)| format!("{column} = {}", provider.placeholder(index + 1)))
            .chain(std::iter::once(format!(
                "updated_at = {}",
                provider.placeholder(columns.len() + 1)
            )))
            .collect::<Vec<_>>()
            .join(", ");
        let sql = format!(
            "UPDATE {} SET {} WHERE id = {}",
            definition.table,
            set_clause,
            provider.placeholder(columns.len() + 2)
        );
        values.push(DbValue::Text(now.clone()));
        values.push(DbValue::Integer(existing_id));
        provider.execute(&sql, &values)?;
        existing_id
    } else {
        let mut insert_columns = columns.clone();
        insert_columns.push("created_at".to_string());
        insert_columns.push("updated_at".to_string());
        values.push(DbValue::Text(now.clone()));
        values.push(DbValue::Text(now.clone()));
        let value_placeholders = placeholders(provider, 1, insert_columns.len()).join(", ");
        let returning = if provider.driver() == DatabaseDriver::Postgres {
            " RETURNING id"
        } else {
            ""
        };
        let sql = format!(
            "INSERT INTO {} ({}) VALUES ({}){}",
            definition.table,
            insert_columns.join(", "),
            value_placeholders,
            returning
        );
        if provider.driver() == DatabaseDriver::Postgres {
            let row = provider
                .query_one(&sql, &values)?
                .ok_or_else(|| "Falha ao obter id retornado pelo PostgreSQL.".to_string())?;
            row.get("id")
                .and_then(|value| {
                    value
                        .as_i64()
                        .or_else(|| value.as_str()?.parse::<i64>().ok())
                })
                .ok_or_else(|| "Id retornado pelo provider é inválido.".to_string())?
        } else {
            provider.execute(&sql, &values)?;
            let row = provider
                .query_one(provider.last_insert_id_sql(), &[])?
                .ok_or_else(|| "Falha ao obter último id inserido pelo provider.".to_string())?;
            row.get("id")
                .and_then(|value| {
                    value
                        .as_i64()
                        .or_else(|| value.as_str()?.parse::<i64>().ok())
                })
                .ok_or_else(|| "Id retornado pelo provider é inválido.".to_string())?
        }
    };

    let saved = provider_get_with_database(provider, &entity, record_id)?
        .ok_or_else(|| "Registro salvo não encontrado pelo provider.".to_string())?;
    let action = if id.is_some() { "update" } else { "create" };
    let payload_value = Value::Object(saved.clone());
    provider_insert_audit(
        provider,
        &entity,
        action,
        Some(record_id),
        &payload_value,
        &now,
    )?;
    provider_enqueue_sync(
        provider,
        &entity,
        action,
        Some(record_id),
        &payload_value,
        &now,
    )?;
    Ok(saved)
}

pub(crate) fn provider_delete_with_database(
    provider: &dyn crate::core::database::provider::DatabaseProvider,
    entity: String,
    id: i64,
) -> Result<bool, String> {
    let definition =
        entity_definition(&entity).ok_or_else(|| "Entidade não permitida.".to_string())?;
    let sql = format!(
        "DELETE FROM {} WHERE id = {}",
        definition.table,
        provider.placeholder(1)
    );
    let affected = provider.execute(
        &sql,
        &[crate::core::database::provider::types::DbValue::Integer(id)],
    )?;
    if affected > 0 {
        let now = Utc::now().to_rfc3339();
        let payload = json!({ "id": id, "entity": entity });
        provider_insert_audit(provider, &entity, "delete", Some(id), &payload, &now)?;
        provider_enqueue_sync(provider, &entity, "delete", Some(id), &payload, &now)?;
    }
    Ok(affected > 0)
}

#[cfg(any(feature = "desktop", feature = "mobile"))]
#[tauri::command]
pub fn entity_provider_list(
    state: State<'_, SharedState>,
    entity: String,
    search: String,
) -> Result<Vec<Map<String, Value>>, String> {
    let provider = active_provider(&state)?;
    provider_list_with_database(&provider, &entity, &search)
}

#[cfg(any(feature = "desktop", feature = "mobile"))]
#[tauri::command]
pub fn provider_entity_list(
    state: State<'_, SharedState>,
    entity: String,
    search: String,
) -> Result<Vec<Map<String, Value>>, String> {
    entity_provider_list(state, entity, search)
}

#[cfg(any(feature = "desktop", feature = "mobile"))]
#[tauri::command]
pub fn provider_entity_get(
    state: State<'_, SharedState>,
    entity: String,
    id: i64,
) -> Result<Option<Map<String, Value>>, String> {
    let provider = active_provider(&state)?;
    provider_get_with_database(&provider, &entity, id)
}

#[cfg(any(feature = "desktop", feature = "mobile"))]
#[tauri::command]
pub fn provider_entity_create(
    state: State<'_, SharedState>,
    entity: String,
    payload: Map<String, Value>,
) -> Result<Map<String, Value>, String> {
    let provider = active_provider(&state)?;
    provider_save_with_database(&provider, entity, payload)
}

#[cfg(any(feature = "desktop", feature = "mobile"))]
#[tauri::command]
pub fn provider_entity_update(
    state: State<'_, SharedState>,
    entity: String,
    payload: Map<String, Value>,
) -> Result<Map<String, Value>, String> {
    if payload.get("id").is_none() {
        return Err(
            "Campo id é obrigatório para atualização via provider_entity_update.".to_string(),
        );
    }
    let provider = active_provider(&state)?;
    provider_save_with_database(&provider, entity, payload)
}

#[cfg(any(feature = "desktop", feature = "mobile"))]
#[tauri::command]
pub fn provider_entity_delete(
    state: State<'_, SharedState>,
    entity: String,
    id: i64,
) -> Result<bool, String> {
    let provider = active_provider(&state)?;
    provider_delete_with_database(&provider, entity, id)
}
