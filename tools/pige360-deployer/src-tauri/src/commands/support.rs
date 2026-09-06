use chrono::{Duration, Utc};
use rusqlite::{params, OptionalExtension};
use serde_json::{json, Map, Value};
use tauri::State;
use uuid::Uuid;

use crate::{
    app_state::SharedState,
    db::{open_connection, row_to_json_map, write_app_log, write_audit, AppLogInput},
    security::{
        build_otpauth_url, decrypt_text, encrypt_text, generate_recovery_codes,
        generate_support_secret, generate_totp_secret, hash_password, machine_key, verify_password,
        verify_totp_code,
    },
};

use super::auth::require_session_by_token;

fn ensure_master(conn: &rusqlite::Connection, session_token: &str) -> Result<i64, String> {
    let identity = require_session_by_token(conn, session_token)?;
    if !identity.master_user {
        return Err("Apenas usuário master pode acessar a proteção administrativa.".to_string());
    }
    Ok(identity.user_id)
}

fn guard_row(conn: &rusqlite::Connection) -> Result<Option<Map<String, Value>>, String> {
    conn.query_row(
        "SELECT id, support_secret_hash, totp_secret_encrypted, totp_enabled, recovery_codes_encrypted,
                licensing_protected, white_label_protected, created_at, updated_at, last_rotated_at
         FROM admin_guard WHERE id = 1 LIMIT 1",
        [],
        row_to_json_map,
    )
    .optional()
    .map_err(|err| format!("Falha ao consultar proteção administrativa: {err}"))
}

fn decrypt_guard_secret(row: &Map<String, Value>, field: &str) -> Result<Option<String>, String> {
    let value = row.get(field).and_then(Value::as_str).unwrap_or("");
    if value.trim().is_empty() {
        return Ok(None);
    }
    Ok(Some(decrypt_text(&machine_key(), value)?))
}

pub fn require_admin_unlock(
    conn: &rusqlite::Connection,
    user_id: i64,
    unlock_token: &str,
    scope: &str,
) -> Result<(), String> {
    let token = unlock_token.trim();
    if token.is_empty() {
        return Err("Autorização administrativa reforçada é obrigatória.".to_string());
    }
    let now = Utc::now().to_rfc3339();
    let found: Option<i64> = conn
        .query_row(
            "SELECT id FROM admin_unlock_sessions
             WHERE usuario_id = ?1 AND unlock_token = ?2 AND (scope = ?3 OR scope = 'global') AND expires_at > ?4
             LIMIT 1",
            params![user_id, token, scope, now],
            |row| row.get(0),
        )
        .optional()
        .map_err(|err| format!("Falha ao validar autorização administrativa: {err}"))?;
    if found.is_none() {
        return Err("Sessão administrativa reforçada ausente, inválida ou expirada.".to_string());
    }
    conn.execute(
        "UPDATE admin_unlock_sessions SET last_used_at = ?1 WHERE unlock_token = ?2",
        params![now, token],
    )
    .map_err(|err| format!("Falha ao atualizar uso da autorização administrativa: {err}"))?;
    Ok(())
}

#[tauri::command]
pub fn support_guard_status(
    state: State<'_, SharedState>,
    session_token: String,
) -> Result<Map<String, Value>, String> {
    let db_path = state.db_path()?;
    let conn = open_connection(&db_path)?;
    let user_id = ensure_master(&conn, &session_token)?;
    let mut result = guard_row(&conn)?.unwrap_or_default();
    let now = Utc::now().to_rfc3339();
    let unlocked: bool = conn
        .query_row(
            "SELECT COUNT(*) FROM admin_unlock_sessions WHERE usuario_id = ?1 AND expires_at > ?2",
            params![user_id, now],
            |row| row.get::<_, i64>(0),
        )
        .map_err(|err| format!("Falha ao consultar sessão administrativa: {err}"))?
        > 0;
    result.insert(
        "configured".to_string(),
        Value::from(
            result
                .get("support_secret_hash")
                .and_then(Value::as_str)
                .unwrap_or("")
                .len()
                > 10,
        ),
    );
    result.insert("unlocked".to_string(), Value::from(unlocked));
    result.insert("totp_uri".to_string(), Value::Null);
    Ok(result)
}

#[tauri::command]
pub fn support_guard_provision(
    state: State<'_, SharedState>,
    session_token: String,
    force_rotate: Option<bool>,
) -> Result<Map<String, Value>, String> {
    let db_path = state.db_path()?;
    let data_dir = state.data_dir()?;
    let conn = open_connection(&db_path)?;
    let user_id = ensure_master(&conn, &session_token)?;
    let existing = guard_row(&conn)?;
    if existing.is_some() && !force_rotate.unwrap_or(false) {
        return Err("A proteção administrativa já foi provisionada. Use rotação explícita para gerar novos segredos.".to_string());
    }

    let support_secret = generate_support_secret();
    let totp_secret = generate_totp_secret();
    let recovery_codes = generate_recovery_codes();
    let now = Utc::now().to_rfc3339();
    let support_secret_hash = hash_password(&support_secret)?;
    let recovery_json =
        Value::Array(recovery_codes.iter().cloned().map(Value::String).collect()).to_string();
    let totp_encrypted = encrypt_text(&machine_key(), &totp_secret);
    let recovery_encrypted = encrypt_text(&machine_key(), &recovery_json);

    conn.execute(
        "INSERT INTO admin_guard (
            id, support_secret_hash, totp_secret_encrypted, totp_enabled, recovery_codes_encrypted,
            licensing_protected, white_label_protected, created_at, updated_at, last_rotated_at
         ) VALUES (1, ?1, ?2, 0, ?3, 1, 1, ?4, ?4, ?4)
         ON CONFLICT(id) DO UPDATE SET
            support_secret_hash = excluded.support_secret_hash,
            totp_secret_encrypted = excluded.totp_secret_encrypted,
            totp_enabled = 0,
            recovery_codes_encrypted = excluded.recovery_codes_encrypted,
            updated_at = excluded.updated_at,
            last_rotated_at = excluded.last_rotated_at",
        params![support_secret_hash, totp_encrypted, recovery_encrypted, now],
    )
    .map_err(|err| format!("Falha ao provisionar proteção administrativa: {err}"))?;

    let payload = json!({
        "usuario_id": user_id,
        "rotated": existing.is_some(),
    });
    write_audit(&conn, "admin_guard", "provision", Some(1), &payload)?;
    let _ = write_app_log(
        &conn,
        &data_dir,
        AppLogInput {
            level: "warning",
            category: "support_guard",
            message: "Proteção administrativa provisionada/rotacionada.",
            source: Some("backend"),
            route: None,
            details: Some(&payload),
        },
    );

    let mut result = Map::new();
    result.insert("support_secret".to_string(), Value::from(support_secret));
    result.insert("totp_secret".to_string(), Value::from(totp_secret.clone()));
    result.insert(
        "otpauth_url".to_string(),
        Value::from(build_otpauth_url(
            &totp_secret,
            "PIGE360 Deployer:Suporte Admin",
            "PIGE360 Deployer",
        )),
    );
    result.insert(
        "recovery_codes".to_string(),
        Value::Array(recovery_codes.into_iter().map(Value::String).collect()),
    );
    result.insert("totp_enabled".to_string(), Value::from(false));
    Ok(result)
}

#[tauri::command]
pub fn support_guard_enable_totp(
    state: State<'_, SharedState>,
    session_token: String,
    current_password: String,
    support_secret: String,
    totp_code: String,
) -> Result<bool, String> {
    let db_path = state.db_path()?;
    let data_dir = state.data_dir()?;
    let conn = open_connection(&db_path)?;
    let user_id = ensure_master(&conn, &session_token)?;
    let row = guard_row(&conn)?
        .ok_or_else(|| "Proteção administrativa ainda não provisionada.".to_string())?;
    let support_hash = row
        .get("support_secret_hash")
        .and_then(Value::as_str)
        .unwrap_or("");
    if !verify_password(&support_secret, support_hash)? {
        return Err("Secret de suporte inválido.".to_string());
    }
    let password_hash: String = conn
        .query_row(
            "SELECT senha_hash FROM usuarios WHERE id = ?1 LIMIT 1",
            [user_id],
            |row| row.get(0),
        )
        .map_err(|err| format!("Falha ao consultar senha do usuário master: {err}"))?;
    if !verify_password(current_password.trim(), &password_hash)? {
        return Err("Senha atual inválida.".to_string());
    }
    let totp_secret = decrypt_guard_secret(&row, "totp_secret_encrypted")?
        .ok_or_else(|| "Secret TOTP não encontrado para provisionamento.".to_string())?;
    if !verify_totp_code(&totp_secret, &totp_code)? {
        return Err("Código TOTP inválido.".to_string());
    }
    conn.execute(
        "UPDATE admin_guard SET totp_enabled = 1, updated_at = ?1 WHERE id = 1",
        [Utc::now().to_rfc3339()],
    )
    .map_err(|err| format!("Falha ao ativar TOTP administrativo: {err}"))?;
    let _ = write_app_log(
        &conn,
        &data_dir,
        AppLogInput {
            level: "info",
            category: "support_guard",
            message: "TOTP administrativo ativado.",
            source: Some("backend"),
            route: None,
            details: Some(&json!({"usuario_id": user_id})),
        },
    );
    Ok(true)
}

#[tauri::command]
pub fn support_guard_unlock(
    state: State<'_, SharedState>,
    session_token: String,
    current_password: String,
    support_secret: String,
    totp_code: Option<String>,
    scope: Option<String>,
) -> Result<Map<String, Value>, String> {
    let db_path = state.db_path()?;
    let data_dir = state.data_dir()?;
    let conn = open_connection(&db_path)?;
    let user_id = ensure_master(&conn, &session_token)?;
    let row = guard_row(&conn)?
        .ok_or_else(|| "Proteção administrativa ainda não provisionada.".to_string())?;

    let password_hash: String = conn
        .query_row(
            "SELECT senha_hash FROM usuarios WHERE id = ?1 LIMIT 1",
            [user_id],
            |row| row.get(0),
        )
        .map_err(|err| format!("Falha ao consultar senha do usuário master: {err}"))?;
    if !verify_password(current_password.trim(), &password_hash)? {
        return Err("Senha atual inválida.".to_string());
    }

    let support_hash = row
        .get("support_secret_hash")
        .and_then(Value::as_str)
        .unwrap_or("");
    if !verify_password(&support_secret, support_hash)? {
        return Err("Secret de suporte inválido.".to_string());
    }

    if row.get("totp_enabled").and_then(Value::as_i64).unwrap_or(0) == 1 {
        let code = totp_code.unwrap_or_default();
        let totp_secret = decrypt_guard_secret(&row, "totp_secret_encrypted")?
            .ok_or_else(|| "Secret TOTP não configurado.".to_string())?;
        if !verify_totp_code(&totp_secret, &code)? {
            return Err("Código TOTP inválido.".to_string());
        }
    }

    let scope_value = scope.unwrap_or_else(|| "global".to_string());
    let unlock_token = Uuid::new_v4().to_string();
    let created_at = Utc::now().to_rfc3339();
    let expires_at = (Utc::now() + Duration::minutes(15)).to_rfc3339();
    conn.execute(
        "INSERT INTO admin_unlock_sessions (usuario_id, scope, unlock_token, expires_at, created_at, last_used_at)
         VALUES (?1, ?2, ?3, ?4, ?5, ?5)",
        params![user_id, scope_value, unlock_token, expires_at, created_at],
    )
    .map_err(|err| format!("Falha ao criar sessão administrativa reforçada: {err}"))?;

    let _ = write_app_log(
        &conn,
        &data_dir,
        AppLogInput {
            level: "warning",
            category: "support_guard",
            message: "Acesso administrativo reforçado liberado.",
            source: Some("backend"),
            route: None,
            details: Some(
                &json!({"usuario_id": user_id, "scope": scope_value, "expires_at": expires_at}),
            ),
        },
    );

    let mut result = Map::new();
    result.insert("unlock_token".to_string(), Value::from(unlock_token));
    result.insert("expires_at".to_string(), Value::from(expires_at));
    result.insert("scope".to_string(), Value::from(scope_value));
    Ok(result)
}
