use chrono::{Duration, Utc};
use generic_license_tauri::{
    device::{collect_device_metadata, default_device_name, generate_device_key},
    models::{LicenseCheckInput, LicenseConfig, LicenseDecision},
    service::GenericLicenseService,
};
use rusqlite::{params, OptionalExtension};
use serde_json::{json, Map, Value};
use tauri::State;

use crate::{
    app_state::SharedState,
    db::{enqueue_sync, open_connection, row_to_json_map, write_app_log, write_audit, AppLogInput},
    security::{decrypt_text, encrypt_text, integrity_hash, machine_key},
};

use super::{auth::require_session_by_token, support::require_admin_unlock};

const LICENSE_SETTINGS_KEY: &str = "licensing_settings";
const LICENSING_FEATURE_ENABLED: bool = false;

fn company_seed(
    conn: &rusqlite::Connection,
    empresa_id: Option<i64>,
) -> Result<(i64, String, String, Option<String>), String> {
    let result = if let Some(empresa_id) = empresa_id {
        conn.query_row(
            "SELECT id, COALESCE(documento, ''), COALESCE(nome, ''), email FROM empresas WHERE id = ?1 LIMIT 1",
            [empresa_id],
            |row| Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?, row.get::<_, String>(2)?, row.get::<_, Option<String>>(3)?)),
        )
    } else {
        conn.query_row(
            "SELECT id, COALESCE(documento, ''), COALESCE(nome, ''), email FROM empresas ORDER BY id ASC LIMIT 1",
            [],
            |row| Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?, row.get::<_, String>(2)?, row.get::<_, Option<String>>(3)?)),
        )
    };

    result
        .optional()
        .map_err(|err| format!("Falha ao localizar empresa para licenciamento: {err}"))?
        .ok_or_else(|| "Cadastre ao menos uma empresa para utilizar o licenciamento.".to_string())
}

fn default_license_settings() -> Map<String, Value> {
    let mut map = Map::new();
    map.insert(
        "service_url".to_string(),
        Value::from(LicenseConfig::default().base_url),
    );
    map.insert("company_name".to_string(), Value::from(""));
    map.insert("company_document".to_string(), Value::from(""));
    map.insert("company_email".to_string(), Value::from(""));
    map.insert(
        "station_name".to_string(),
        Value::from(default_device_name()),
    );
    map.insert("machine_key".to_string(), Value::from(machine_key()));
    map.insert("app_instance".to_string(), Value::from("app-template"));
    map.insert("auto_register_machine".to_string(), Value::from(true));
    map.insert("auto_register_requested_licenses".to_string(), Value::Null);
    map.insert(
        "auto_register_validation_mode".to_string(),
        Value::from("standard"),
    );
    map.insert(
        "auto_register_interface_mode".to_string(),
        Value::from("interactive"),
    );
    map.insert(
        "auto_register_device_identifier".to_string(),
        Value::from(""),
    );
    map.insert("licensing_disabled".to_string(), Value::from(true));
    map
}

fn load_settings_from_db(conn: &rusqlite::Connection) -> Result<Map<String, Value>, String> {
    let existing: Option<String> = conn
        .query_row(
            "SELECT valor FROM configuracoes WHERE nome = ?1 LIMIT 1",
            [LICENSE_SETTINGS_KEY],
            |row| row.get(0),
        )
        .optional()
        .map_err(|err| format!("Falha ao consultar configuração de licenciamento: {err}"))?;

    let mut result = default_license_settings();
    if let Some(raw) = existing {
        if let Ok(Value::Object(saved)) = serde_json::from_str::<Value>(&raw) {
            for (k, v) in saved {
                result.insert(k, v);
            }
        }
    }
    Ok(result)
}

fn save_settings_to_db(
    conn: &rusqlite::Connection,
    settings: &Map<String, Value>,
) -> Result<(), String> {
    let raw = Value::Object(settings.clone()).to_string();
    conn.execute(
        "INSERT INTO configuracoes (nome, valor, updated_at) VALUES (?1, ?2, datetime('now'))
         ON CONFLICT(nome) DO UPDATE SET valor = excluded.valor, updated_at = datetime('now')",
        params![LICENSE_SETTINGS_KEY, raw],
    )
    .map_err(|err| format!("Falha ao salvar configuração de licenciamento: {err}"))?;
    Ok(())
}
fn mask_protected_settings(settings: &Map<String, Value>) -> Map<String, Value> {
    let mut masked = settings.clone();
    for key in [
        "service_url",
        "app_instance",
        "auto_register_validation_mode",
        "auto_register_interface_mode",
        "auto_register_device_identifier",
        "auto_register_requested_licenses",
    ] {
        if masked.contains_key(key) {
            masked.insert(key.to_string(), Value::String("[protegido]".to_string()));
        }
    }
    masked.insert("protected".to_string(), Value::from(true));
    masked
}

fn get_bool(map: &Map<String, Value>, key: &str, default: bool) -> bool {
    match map.get(key) {
        Some(Value::Bool(flag)) => *flag,
        Some(Value::Number(number)) => number.as_i64().unwrap_or(0) != 0,
        Some(Value::String(text)) => matches!(
            text.trim().to_lowercase().as_str(),
            "1" | "true" | "sim" | "yes"
        ),
        _ => default,
    }
}

fn get_string(map: &Map<String, Value>, key: &str) -> Option<String> {
    map.get(key)
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
        .filter(|v| !v.is_empty())
}

fn build_check_input(
    settings: &Map<String, Value>,
    empresa_documento: String,
    empresa_nome: String,
    empresa_email: Option<String>,
) -> LicenseCheckInput {
    let mut input = LicenseCheckInput {
        company_document: get_string(settings, "company_document").unwrap_or(empresa_documento),
        company_name: get_string(settings, "company_name").or_else(|| Some(empresa_nome.clone())),
        company_email: get_string(settings, "company_email").or(empresa_email.clone()),
        company_legal_name: Some(empresa_nome),
        app_id: "pige360-deployer".to_string(),
        app_name: "PIGE360 Deployer".to_string(),
        app_version: env!("CARGO_PKG_VERSION").to_string(),
        app_slug: Some(
            get_string(settings, "app_instance").unwrap_or_else(|| "app-template".to_string()),
        ),
        device_key: None,
        device_name: None,
        station_name: get_string(settings, "station_name"),
        hostname: None,
        computer_name: None,
        serial_number: None,
        machine_guid: None,
        bios_serial: None,
        motherboard_serial: None,
        logged_user: None,
        os_name: None,
        os_version: None,
        os_arch: None,
        domain_name: None,
        mac_addresses: Vec::new(),
        install_mode: None,
        registration_file_content_b64: None,
        registration_file_path: None,
        registration_file_verified: None,
        allow_company_auto_create: Some(get_bool(settings, "auto_register_machine", true)),
        allow_device_auto_create: Some(get_bool(settings, "auto_register_machine", true)),
        allow_device_auto_update: Some(true),
        requested_licenses: map_requested_licenses(settings),
        device_identifier: get_string(settings, "auto_register_device_identifier"),
        validation_mode: get_string(settings, "auto_register_validation_mode"),
        interface_mode: get_string(settings, "auto_register_interface_mode"),
        local_license_mode: None,
        metadata: Default::default(),
        login_context: false,
    };
    input.device_key = Some(generate_device_key(&input));
    input
}

fn map_requested_licenses(settings: &Map<String, Value>) -> Option<u32> {
    settings
        .get("auto_register_requested_licenses")
        .and_then(|value| match value {
            Value::Number(number) => number.as_u64().map(|v| v as u32),
            Value::String(text) => text.trim().parse::<u32>().ok(),
            _ => None,
        })
}

fn trial_license_row(
    conn: &rusqlite::Connection,
    empresa_id: i64,
) -> Result<Option<Map<String, Value>>, String> {
    conn.query_row(
        "SELECT id, empresa_id, cnpj, license_kind, status, issued_at, expires_at, fingerprint, payload_encrypted, integrity_hash, created_at, updated_at
         FROM local_licenses WHERE empresa_id = ?1 LIMIT 1",
        [empresa_id],
        row_to_json_map,
    )
    .optional()
    .map_err(|err| format!("Falha ao consultar licença local: {err}"))
}

fn attach_decrypted_payload(mut row: Map<String, Value>, cnpj: &str) -> Map<String, Value> {
    let encrypted = row
        .get("payload_encrypted")
        .and_then(Value::as_str)
        .unwrap_or("");
    let decrypted = if encrypted.is_empty() {
        None
    } else {
        decrypt_text(cnpj, encrypted).ok()
    };
    row.insert(
        "payload_decrypted".to_string(),
        decrypted.map(Value::from).unwrap_or(Value::Null),
    );
    row.insert(
        "is_trial".to_string(),
        Value::from(row.get("license_kind").and_then(Value::as_str) == Some("trial")),
    );
    row
}

#[tauri::command]
pub fn licensing_load_settings(
    state: State<'_, SharedState>,
    session_token: String,
    admin_unlock_token: Option<String>,
) -> Result<Map<String, Value>, String> {
    if !LICENSING_FEATURE_ENABLED {
        return Err("Licenciamento desativado na configuração desta aplicação.".to_string());
    }
    let db_path = state.db_path()?;
    let conn = open_connection(&db_path)?;
    let identity = require_session_by_token(&conn, &session_token)?;
    let settings = load_settings_from_db(&conn)?;
    if identity.master_user {
        if let Some(token) = admin_unlock_token {
            if require_admin_unlock(&conn, identity.user_id, &token, "licensing").is_ok() {
                return Ok(settings);
            }
        }
        return Ok(mask_protected_settings(&settings));
    }
    Ok(mask_protected_settings(&settings))
}

#[tauri::command]
pub fn licensing_save_settings(
    state: State<'_, SharedState>,
    session_token: String,
    admin_unlock_token: String,
    payload: Map<String, Value>,
) -> Result<Map<String, Value>, String> {
    if !LICENSING_FEATURE_ENABLED {
        return Err("Licenciamento desativado na configuração desta aplicação.".to_string());
    }
    let db_path = state.db_path()?;
    let data_dir = state.data_dir()?;
    let conn = open_connection(&db_path)?;
    let identity = require_session_by_token(&conn, &session_token)?;
    if !identity.master_user {
        return Err(
            "Apenas usuário master pode alterar configurações de licenciamento.".to_string(),
        );
    }
    require_admin_unlock(&conn, identity.user_id, &admin_unlock_token, "licensing")?;
    let mut settings = default_license_settings();
    for (k, v) in payload {
        settings.insert(k, v);
    }
    save_settings_to_db(&conn, &settings)?;
    let value = Value::Object(settings.clone());
    write_audit(&conn, "licensing_settings", "update", None, &value)?;
    let _ = write_app_log(
        &conn,
        &data_dir,
        AppLogInput {
            level: "warning",
            category: "licensing",
            message: "Configurações sensíveis de licenciamento atualizadas.",
            source: Some("backend"),
            route: None,
            details: Some(&json!({"usuario_id": identity.user_id})),
        },
    );
    Ok(settings)
}

#[tauri::command]
pub fn licensing_device_info(
    state: State<'_, SharedState>,
    session_token: String,
) -> Result<Map<String, Value>, String> {
    if !LICENSING_FEATURE_ENABLED {
        return Err("Licenciamento desativado na configuração desta aplicação.".to_string());
    }
    let db_path = state.db_path()?;
    let conn = open_connection(&db_path)?;
    let _ = require_session_by_token(&conn, &session_token)?;
    let info = collect_device_metadata();
    let value = serde_json::to_value(info)
        .map_err(|err| format!("Falha ao serializar informações do dispositivo: {err}"))?;
    match value {
        Value::Object(mut map) => {
            map.insert("device_key".to_string(), Value::from(machine_key()));
            Ok(map)
        }
        _ => Err("Falha ao montar payload do dispositivo.".to_string()),
    }
}

#[tauri::command]
pub async fn licensing_check_runtime(
    state: State<'_, SharedState>,
    session_token: String,
    empresa_id: Option<i64>,
) -> Result<Map<String, Value>, String> {
    if !LICENSING_FEATURE_ENABLED {
        let mut result = Map::new();
        result.insert("mode".to_string(), Value::from("disabled"));
        result.insert("allowed".to_string(), Value::from(true));
        result.insert("status".to_string(), Value::from("disabled"));
        return Ok(result);
    }
    let db_path = state.db_path()?;
    let conn = open_connection(&db_path)?;
    let _identity = require_session_by_token(&conn, &session_token)?;
    let settings = load_settings_from_db(&conn)?;
    let (empresa_id_resolved, documento, empresa_nome, empresa_email) =
        company_seed(&conn, empresa_id)?;

    let mut result = Map::new();
    result.insert("empresa_id".to_string(), Value::from(empresa_id_resolved));
    result.insert(
        "empresa_nome".to_string(),
        Value::from(empresa_nome.clone()),
    );
    result.insert("cnpj".to_string(), Value::from(documento.clone()));
    result.insert("machine_key".to_string(), Value::from(machine_key()));
    result.insert(
        "settings".to_string(),
        Value::Object(mask_protected_settings(&settings)),
    );

    if let Some(local) = trial_license_row(&conn, empresa_id_resolved)? {
        result.insert(
            "local_license".to_string(),
            Value::Object(attach_decrypted_payload(local, &documento)),
        );
    } else {
        result.insert("local_license".to_string(), Value::Null);
    }

    if get_bool(&settings, "licensing_disabled", false) {
        result.insert("mode".to_string(), Value::from("disabled"));
        result.insert("allowed".to_string(), Value::from(true));
        result.insert(
            "decision".to_string(),
            json!({
                "allowed": true,
                "decision": "allowed",
                "reason_code": "LICENSING_DISABLED",
                "step": "settings",
                "message": "Licenciamento desabilitado na configuração da aplicação.",
                "source": "settings"
            }),
        );
        return Ok(result);
    }

    let input = build_check_input(&settings, documento.clone(), empresa_nome, empresa_email);
    let mut config = LicenseConfig {
        cache_namespace: format!("app-template-{}", empresa_id_resolved),
        ..LicenseConfig::default()
    };
    if let Some(service_url) = get_string(&settings, "service_url") {
        config.base_url = service_url;
    }
    let service = GenericLicenseService::new(config);
    let decision: LicenseDecision = service.check(input).await.map_err(|err| err.to_string())?;
    let decision_value = serde_json::to_value(&decision)
        .map_err(|err| format!("Falha ao serializar decisão de licença: {err}"))?;
    result.insert("mode".to_string(), Value::from("generic-license-tauri"));
    result.insert("allowed".to_string(), Value::from(decision.allowed));
    result.insert("decision".to_string(), decision_value);
    Ok(result)
}

#[tauri::command]
pub fn licensing_status(
    state: State<'_, SharedState>,
    session_token: String,
    empresa_id: Option<i64>,
) -> Result<Map<String, Value>, String> {
    if !LICENSING_FEATURE_ENABLED {
        let mut result = Map::new();
        result.insert("mode".to_string(), Value::from("disabled"));
        result.insert("allowed".to_string(), Value::from(true));
        result.insert("status".to_string(), Value::from("disabled"));
        return Ok(result);
    }
    let db_path = state.db_path()?;
    let conn = open_connection(&db_path)?;
    let _identity = require_session_by_token(&conn, &session_token)?;
    let settings = load_settings_from_db(&conn)?;
    let (empresa_id_resolved, documento, empresa_nome, _) = company_seed(&conn, empresa_id)?;

    let mut result = Map::new();
    result.insert("empresa_id".to_string(), Value::from(empresa_id_resolved));
    result.insert("empresa_nome".to_string(), Value::from(empresa_nome));
    result.insert("cnpj".to_string(), Value::from(documento.clone()));
    result.insert("machine_key".to_string(), Value::from(machine_key()));
    result.insert(
        "settings".to_string(),
        Value::Object(mask_protected_settings(&settings)),
    );

    if let Some(row) = trial_license_row(&conn, empresa_id_resolved)? {
        result.insert(
            "license".to_string(),
            Value::Object(attach_decrypted_payload(row, &documento)),
        );
    } else {
        result.insert("license".to_string(), Value::Null);
    }

    Ok(result)
}

#[tauri::command]
pub fn licensing_start_trial(
    state: State<'_, SharedState>,
    session_token: String,
    empresa_id: Option<i64>,
) -> Result<Map<String, Value>, String> {
    if !LICENSING_FEATURE_ENABLED {
        return Err("Licenciamento desativado na configuração desta aplicação.".to_string());
    }
    let db_path = state.db_path()?;
    let conn = open_connection(&db_path)?;
    let _identity = require_session_by_token(&conn, &session_token)?;
    let now = Utc::now();
    let (empresa_id_resolved, documento, empresa_nome, _) = company_seed(&conn, empresa_id)?;
    let cnpj = documento.trim().to_string();
    if cnpj.is_empty() {
        return Err("A licença de teste exige CNPJ/CPF cadastrado na empresa ativa.".to_string());
    }

    let existing = trial_license_row(&conn, empresa_id_resolved)?;
    if let Some(row) = existing {
        return Ok(attach_decrypted_payload(row, &cnpj));
    }

    let expires_at = (now + Duration::days(45)).to_rfc3339();
    let issued_at = now.to_rfc3339();
    let payload = json!({
        "empresa_id": empresa_id_resolved,
        "empresa_nome": empresa_nome,
        "cnpj": cnpj,
        "kind": "trial",
        "issued_at": issued_at,
        "expires_at": expires_at,
        "machine_key": machine_key(),
        "days": 45,
    });
    let payload_str = payload.to_string();
    let payload_encrypted = encrypt_text(&cnpj, &payload_str);
    let payload_hash = integrity_hash(&cnpj, &payload_str);

    conn.execute(
        "INSERT INTO local_licenses (
            empresa_id, cnpj, license_kind, status, issued_at, expires_at, fingerprint,
            payload_encrypted, integrity_hash, created_at, updated_at
        ) VALUES (?1, ?2, 'trial', 'active', ?3, ?4, ?5, ?6, ?7, ?3, ?3)",
        params![
            empresa_id_resolved,
            cnpj,
            issued_at,
            expires_at,
            machine_key(),
            payload_encrypted,
            payload_hash,
        ],
    )
    .map_err(|err| format!("Falha ao gravar licença de teste: {err}"))?;

    let id = conn.last_insert_rowid();
    let saved = conn
        .query_row(
            "SELECT id, empresa_id, cnpj, license_kind, status, issued_at, expires_at, fingerprint, payload_encrypted, integrity_hash, created_at, updated_at
             FROM local_licenses WHERE id = ?1",
            [id],
            row_to_json_map,
        )
        .map_err(|err| format!("Falha ao reler licença salva: {err}"))?;

    let payload_value = Value::Object(saved.clone());
    write_audit(
        &conn,
        "local_licenses",
        "create_trial",
        Some(id),
        &payload_value,
    )?;
    enqueue_sync(
        &conn,
        "local_licenses",
        "create_trial",
        Some(id),
        &payload_value,
    )?;
    Ok(attach_decrypted_payload(saved, &documento))
}
