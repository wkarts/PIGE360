use chrono::{DateTime, FixedOffset, Local, NaiveDateTime, TimeZone};
use reqwest::{Client, RequestBuilder, StatusCode};
use serde_json::{json, Value};

use crate::error::LicenseError;
use crate::models::{
    ApplicationLicenseRecord, CompanyRecord, DeviceRecord, LicenseApiResponse, LicenseCheckInput,
    LicenseConfig, LicenseDecision, LicenseRecord, OfflineDecision,
};

pub struct LicenseApiClient {
    config: LicenseConfig,
    http: Client,
}

impl LicenseApiClient {
    pub fn new(config: LicenseConfig) -> Self {
        Self {
            config,
            http: Client::new(),
        }
    }

    pub async fn resolve_activation(
        &self,
        input: &LicenseCheckInput,
    ) -> Result<LicenseDecision, LicenseError> {
        self.guard()?;

        let response = self
            .with_auth(
                self.http
                    .post(self.url(&self.config.resolve_activation_endpoint)),
            )
            .header("Accept", "application/json")
            .header("Content-Type", "application/json")
            .json(&self.resolve_payload(input))
            .send()
            .await
            .map_err(|e| LicenseError::Http(e.to_string()))?;

        if matches!(
            response.status(),
            StatusCode::NOT_FOUND | StatusCode::METHOD_NOT_ALLOWED
        ) {
            return Err(LicenseError::EndpointUnavailable(format!(
                "endpoint {} não disponível",
                self.config.resolve_activation_endpoint
            )));
        }

        let status = response.status();
        let value = response
            .json::<Value>()
            .await
            .map_err(|e| LicenseError::Serde(e.to_string()))?;

        if !status.is_success() {
            let message = value
                .get("message")
                .or_else(|| value.get("error"))
                .and_then(|v| v.as_str())
                .unwrap_or("falha ao resolver ativação");
            let step = value
                .get("step")
                .and_then(|v| v.as_str())
                .unwrap_or("resolve_activation");
            let reason_code = value
                .get("reason_code")
                .and_then(|v| v.as_str())
                .unwrap_or("ACTIVATION_RESOLVE_FAILED");

            return Err(LicenseError::Structured {
                step: step.to_string(),
                reason_code: reason_code.to_string(),
                message: format!("HTTP {} - {}", status, message),
            });
        }

        normalize_activation_decision(value)
    }

    pub async fn company_status(&self, document: &str) -> Result<LicenseApiResponse, LicenseError> {
        self.guard()?;

        let endpoint = self.config.status_endpoint.replace("{document}", document);

        let response = self
            .with_auth(self.http.get(self.url(&endpoint)))
            .header("Accept", "application/json")
            .send()
            .await
            .map_err(|e| LicenseError::Http(e.to_string()))?;

        if !response.status().is_success() {
            return Err(LicenseError::Http(format!("HTTP {}", response.status())));
        }

        let value = response
            .json::<Value>()
            .await
            .map_err(|e| LicenseError::Serde(e.to_string()))?;

        normalize_response(value)
    }

    pub async fn register_company(&self, input: &LicenseCheckInput) -> Result<(), LicenseError> {
        self.guard()?;

        let payload = json!({
            "DATACAD": Local::now().format("%Y-%m-%d %H:%M:%S").to_string(),
            "CNPJ": input.company_document,
            "EMP_EMAIL": input.company_email.clone().unwrap_or_default(),
            "RAZAOSOCIAL": input
                .company_legal_name
                .clone()
                .or_else(|| input.company_name.clone())
                .unwrap_or_default(),
            "EMP_NOMEFANTASIA": input.company_name.clone().unwrap_or_default(),
            "ATIVO": "S",
            "BLOQUEADO": "N",
            "QTD_MAQ": input.requested_licenses.unwrap_or(0),
            "N_MAQUINAS": input.requested_licenses.unwrap_or(0),
            "APP_INSTANCE": input.app_slug.clone().unwrap_or_else(|| input.app_id.clone()),
            "MODO_VALIDACAO": input.validation_mode.clone().unwrap_or_default(),
        });

        self.post_legacy(&self.config.register_company_endpoint, payload)
            .await
    }

    pub async fn register_device(&self, input: &LicenseCheckInput) -> Result<(), LicenseError> {
        self.guard()?;

        let payload = json!({
            "CNPJ": input.company_document,
            "CHAVE": input.device_key.clone().unwrap_or_default(),
            "NOME": input.station_name.clone().or_else(|| input.device_name.clone()).unwrap_or_default(),
            "NOMEMAQ": input.station_name.clone().or_else(|| input.device_name.clone()).unwrap_or_default(),
            "nome_compu": input.computer_name.clone().or_else(|| input.hostname.clone()).unwrap_or_default(),
            "BLOQUEADO": "N",
            "versaoexe": input.app_version,
            "observacao": input.app_name,
            "sistema_operacional": input.os_version.clone().or_else(|| input.os_name.clone()).unwrap_or_default(),
            "tipo": input.install_mode.clone().unwrap_or_default(),
            "Cod_ace_Remoto": input.domain_name.clone().unwrap_or_default(),
            "Prog_acesso": input.logged_user.clone().unwrap_or_default(),
            "tecnico_instalacao": input.logged_user.clone().unwrap_or_default(),
            "serial_number": input.serial_number.clone().unwrap_or_default(),
            "machine_guid": input.machine_guid.clone().unwrap_or_default(),
            "bios_serial": input.bios_serial.clone().unwrap_or_default(),
            "motherboard_serial": input.motherboard_serial.clone().unwrap_or_default(),
            "hostname": input.hostname.clone().unwrap_or_default(),
            "station_name": input.station_name.clone().unwrap_or_default(),
            "device_identifier": input.device_identifier.clone().unwrap_or_default(),
            "full_device_name": input.device_name.clone().unwrap_or_default(),
            "app_slug": input.app_slug.clone().unwrap_or_default(),
            "validation_mode": input.validation_mode.clone().unwrap_or_default(),
        });

        self.post_legacy(&self.config.register_device_endpoint, payload)
            .await
    }

    pub async fn update_device_name(
        &self,
        device_id: &str,
        input: &LicenseCheckInput,
    ) -> Result<(), LicenseError> {
        self.guard()?;

        let endpoint = self
            .config
            .update_device_endpoint
            .replace("{id}", device_id);

        let payload = json!({
            "NOME": input.station_name.clone().or_else(|| input.device_name.clone()).unwrap_or_default(),
            "NOMEMAQ": input.station_name.clone().or_else(|| input.device_name.clone()).unwrap_or_default(),
            "nome_compu": input.computer_name.clone().or_else(|| input.hostname.clone()).unwrap_or_default(),
            "versaoexe": input.app_version,
            "sistema_operacional": input.os_version.clone().or_else(|| input.os_name.clone()).unwrap_or_default(),
            "serial_number": input.serial_number.clone().unwrap_or_default(),
            "hostname": input.hostname.clone().unwrap_or_default(),
            "machine_guid": input.machine_guid.clone().unwrap_or_default(),
            "bios_serial": input.bios_serial.clone().unwrap_or_default(),
            "motherboard_serial": input.motherboard_serial.clone().unwrap_or_default(),
        });

        let response = self
            .with_auth(self.http.put(self.url(&endpoint)))
            .header("Accept", "application/json")
            .header("Content-Type", "application/json")
            .json(&payload)
            .send()
            .await
            .map_err(|e| LicenseError::Http(e.to_string()))?;

        if response.status().is_success() {
            Ok(())
        } else {
            Err(LicenseError::Http(format!("HTTP {}", response.status())))
        }
    }

    async fn post_legacy(&self, endpoint: &str, payload: Value) -> Result<(), LicenseError> {
        let response = self
            .with_auth(self.http.post(self.url(endpoint)))
            .header("Accept", "application/json")
            .header("Content-Type", "application/json")
            .json(&payload)
            .send()
            .await
            .map_err(|e| LicenseError::Http(e.to_string()))?;

        if response.status().is_success() {
            Ok(())
        } else {
            Err(LicenseError::Http(format!("HTTP {}", response.status())))
        }
    }

    fn resolve_payload(&self, input: &LicenseCheckInput) -> Value {
        json!({
            "app": {
                "slug": input.app_slug.clone().unwrap_or_else(|| input.app_id.clone()),
                "app_id": input.app_id,
                "name": input.app_name,
                "version": input.app_version,
            },
            "company": {
                "document": input.company_document,
                "email": input.company_email,
                "legal_name": input.company_legal_name.clone().or_else(|| input.company_name.clone()),
                "trade_name": input.company_name,
            },
            "device": {
                "fingerprint": input.device_key,
                "station_name": input.station_name.clone().or_else(|| input.device_name.clone()),
                "hostname": input.hostname,
                "computer_name": input.computer_name,
                "serial_number": input.serial_number,
                "machine_guid": input.machine_guid,
                "bios_serial": input.bios_serial,
                "motherboard_serial": input.motherboard_serial,
                "logged_user": input.logged_user,
                "os_name": input.os_name,
                "os_version": input.os_version,
                "os_arch": input.os_arch,
                "domain_name": input.domain_name,
                "mac_addresses": input.mac_addresses,
                "install_mode": input.install_mode,
            },
            "registration_file": {
                "present": input.registration_file_content_b64.is_some(),
                "file_path": input.registration_file_path,
                "content_b64": input.registration_file_content_b64,
                "verified": input.registration_file_verified,
            },
            "options": {
                "allow_company_auto_create": input
                    .allow_company_auto_create
                    .unwrap_or(self.config.auto_register_company_on_missing),
                "allow_device_auto_create": input
                    .allow_device_auto_create
                    .unwrap_or(self.config.auto_register_device_on_missing),
                "allow_device_auto_update": input
                    .allow_device_auto_update
                    .unwrap_or(self.config.auto_update_device_name),
                "requested_licenses": input.requested_licenses,
                "validation_mode": input.validation_mode,
                "interface_mode": input.interface_mode,
                "local_license_mode": input.local_license_mode,
                "device_identifier": input.device_identifier,
            },
            "metadata": input.metadata,
        })
    }

    fn with_auth(&self, builder: RequestBuilder) -> RequestBuilder {
        if let Some(token) = &self.config.api_token {
            if token.trim().is_empty() {
                builder
            } else {
                builder.bearer_auth(token)
            }
        } else {
            builder
        }
    }

    fn url(&self, endpoint: &str) -> String {
        format!(
            "{}/{}",
            self.config.base_url.trim_end_matches('/'),
            endpoint.trim_start_matches('/')
        )
    }

    fn guard(&self) -> Result<(), LicenseError> {
        if self.config.base_url.trim().is_empty() {
            return Err(LicenseError::Config(
                "base_url da licença não informada".to_string(),
            ));
        }

        Ok(())
    }
}

fn normalize_activation_decision(value: Value) -> Result<LicenseDecision, LicenseError> {
    let obj = value
        .as_object()
        .ok_or_else(|| LicenseError::Serde("resposta inválida da API de ativação".to_string()))?;

    Ok(LicenseDecision {
        allowed: obj
            .get("success")
            .map(parse_bool)
            .unwrap_or_else(|| obj.get("allowed").map(parse_bool).unwrap_or(false)),
        decision: obj
            .get("decision")
            .and_then(|v| v.as_str())
            .unwrap_or_else(|| {
                if obj.get("allowed").map(parse_bool).unwrap_or(false) {
                    "allowed"
                } else {
                    "denied"
                }
            })
            .to_string(),
        reason_code: obj
            .get("reason_code")
            .and_then(|v| v.as_str())
            .map(|v| v.to_string()),
        step: obj
            .get("step")
            .and_then(|v| v.as_str())
            .map(|v| v.to_string()),
        message: obj
            .get("message")
            .and_then(|v| v.as_str())
            .unwrap_or("resposta recebida da API de ativação")
            .to_string(),
        used_offline_cache: false,
        warning: obj
            .get("warning")
            .and_then(|v| v.as_str())
            .map(|v| v.to_string()),
        license: obj.get("license").map(normalize_license),
        application_license: obj
            .get("application_license")
            .map(normalize_application_license),
        company: obj.get("company").map(normalize_company),
        device: obj.get("device").map(normalize_device),
        offline: obj.get("offline").map(normalize_offline),
        diagnostics: Vec::new(),
        source: "online".to_string(),
    })
}

fn normalize_response(value: Value) -> Result<LicenseApiResponse, LicenseError> {
    let obj = value
        .as_object()
        .ok_or_else(|| LicenseError::Serde("resposta inválida da API de licença".to_string()))?;

    if obj.contains_key("license") || obj.contains_key("status") {
        let status = obj.get("status").and_then(|v| v.as_i64()).unwrap_or(0) as i32;
        let message = obj
            .get("message")
            .and_then(|v| v.as_str())
            .map(|v| v.to_string());
        let license = obj
            .get("license")
            .map(normalize_license)
            .unwrap_or_else(|| normalize_license(&value));

        return Ok(LicenseApiResponse {
            status,
            message,
            license,
        });
    }

    let status = obj.get("STATUS").and_then(|v| v.as_i64()).unwrap_or(0) as i32;
    let message = obj
        .get("MESSAGE")
        .and_then(|v| v.as_str())
        .map(|v| v.to_string());

    Ok(LicenseApiResponse {
        status,
        message,
        license: normalize_license(&value),
    })
}

fn normalize_license(value: &Value) -> LicenseRecord {
    let obj = match value.as_object() {
        Some(obj) => obj,
        None => return LicenseRecord::default(),
    };

    let devices: Vec<DeviceRecord> = obj
        .get("devices")
        .or_else(|| obj.get("computers"))
        .or_else(|| obj.get("COMPUTADORES"))
        .or_else(|| obj.get("maquinas"))
        .or_else(|| obj.get("MAQUINAS"))
        .and_then(|v| v.as_array())
        .map(|items| items.iter().map(normalize_device).collect())
        .unwrap_or_default();

    let max_devices = obj
        .get("max_devices")
        .and_then(|v| v.as_u64())
        .map(|v| v as u32)
        .or_else(|| {
            obj.get("QTD_MAQ")
                .and_then(|v| v.as_u64())
                .map(|v| v as u32)
        })
        .or_else(|| {
            obj.get("n_maquinas")
                .and_then(|v| v.as_u64())
                .map(|v| v as u32)
        });

    let devices_in_use = obj
        .get("devices_in_use")
        .and_then(|v| v.as_u64())
        .map(|v| v as u32)
        .or_else(|| Some(devices.len() as u32));

    let devices_available = match (max_devices, devices_in_use) {
        (Some(max), Some(used)) if max >= used => Some(max - used),
        _ => None,
    };

    LicenseRecord {
        document: obj
            .get("document")
            .or_else(|| obj.get("CNPJ"))
            .and_then(|v| v.as_str())
            .map(|v| v.to_string()),
        company_name: obj
            .get("company_name")
            .or_else(|| obj.get("RAZAO"))
            .or_else(|| obj.get("RAZAOSOCIAL"))
            .and_then(|v| v.as_str())
            .map(|v| v.to_string()),
        company_email: obj
            .get("company_email")
            .or_else(|| obj.get("EMP_EMAIL"))
            .and_then(|v| v.as_str())
            .map(|v| v.to_string()),
        blocked: obj
            .get("blocked")
            .map(parse_bool)
            .or_else(|| obj.get("BLOQUEADO").map(parse_bool))
            .unwrap_or(false),
        active: obj
            .get("active")
            .map(parse_bool)
            .or_else(|| obj.get("ATIVO").map(parse_bool))
            .unwrap_or(true),
        expires_at: obj
            .get("expires_at")
            .or_else(|| obj.get("DATA_VAL_LIC"))
            .and_then(parse_datetime),
        max_devices,
        devices_in_use,
        devices_available,
        application_slug: obj
            .get("application_slug")
            .or_else(|| obj.get("app_slug"))
            .and_then(|v| v.as_str())
            .map(|v| v.to_string()),
        devices,
    }
}

fn normalize_company(value: &Value) -> CompanyRecord {
    let obj = match value.as_object() {
        Some(obj) => obj,
        None => return CompanyRecord::default(),
    };

    CompanyRecord {
        id: obj.get("id").map(stringify_value),
        document: obj
            .get("document")
            .or_else(|| obj.get("CNPJ"))
            .and_then(|v| v.as_str())
            .map(|v| v.to_string()),
        legal_name: obj
            .get("legal_name")
            .or_else(|| obj.get("RAZAOSOCIAL"))
            .or_else(|| obj.get("RAZAO"))
            .and_then(|v| v.as_str())
            .map(|v| v.to_string()),
        email: obj
            .get("email")
            .or_else(|| obj.get("EMP_EMAIL"))
            .and_then(|v| v.as_str())
            .map(|v| v.to_string()),
        reused_existing: obj.get("reused_existing").map(parse_bool).unwrap_or(false),
    }
}

fn normalize_application_license(value: &Value) -> ApplicationLicenseRecord {
    let obj = match value.as_object() {
        Some(obj) => obj,
        None => return ApplicationLicenseRecord::default(),
    };

    ApplicationLicenseRecord {
        application_slug: obj
            .get("application_slug")
            .or_else(|| obj.get("slug"))
            .and_then(|v| v.as_str())
            .map(|v| v.to_string()),
        status: obj
            .get("status")
            .and_then(|v| v.as_str())
            .map(|v| v.to_string()),
        max_devices: obj
            .get("max_devices")
            .and_then(|v| v.as_u64())
            .map(|v| v as u32),
        devices_in_use: obj
            .get("devices_in_use")
            .and_then(|v| v.as_u64())
            .map(|v| v as u32),
        devices_available: obj
            .get("devices_available")
            .and_then(|v| v.as_u64())
            .map(|v| v as u32),
        expires_at: obj.get("expires_at").and_then(parse_datetime),
    }
}

fn normalize_offline(value: &Value) -> OfflineDecision {
    let obj = match value.as_object() {
        Some(obj) => obj,
        None => return OfflineDecision::default(),
    };

    OfflineDecision {
        cache_allowed_until: obj.get("cache_allowed_until").and_then(parse_datetime),
    }
}

fn normalize_device(value: &Value) -> DeviceRecord {
    let obj = match value.as_object() {
        Some(obj) => obj,
        None => return DeviceRecord::default(),
    };

    DeviceRecord {
        id: obj
            .get("id")
            .or_else(|| obj.get("IDMAQ"))
            .or_else(|| obj.get("IDMAQUINA"))
            .or_else(|| obj.get("idmaquina"))
            .map(stringify_value),
        device_key: obj
            .get("device_key")
            .or_else(|| obj.get("fingerprint"))
            .or_else(|| obj.get("key"))
            .or_else(|| obj.get("chave"))
            .or_else(|| obj.get("CHAVE"))
            .and_then(|v| v.as_str())
            .map(|v| v.to_string()),
        device_name: obj
            .get("device_name")
            .or_else(|| obj.get("NOME"))
            .or_else(|| obj.get("NOMEMAQ"))
            .or_else(|| obj.get("nome_compu"))
            .and_then(|v| v.as_str())
            .map(|v| v.to_string()),
        station_name: obj
            .get("station_name")
            .and_then(|v| v.as_str())
            .map(|v| v.to_string()),
        hostname: obj
            .get("hostname")
            .and_then(|v| v.as_str())
            .map(|v| v.to_string()),
        computer_name: obj
            .get("computer_name")
            .and_then(|v| v.as_str())
            .map(|v| v.to_string()),
        serial_number: obj
            .get("serial_number")
            .and_then(|v| v.as_str())
            .map(|v| v.to_string()),
        machine_guid: obj
            .get("machine_guid")
            .and_then(|v| v.as_str())
            .map(|v| v.to_string()),
        bios_serial: obj
            .get("bios_serial")
            .and_then(|v| v.as_str())
            .map(|v| v.to_string()),
        motherboard_serial: obj
            .get("motherboard_serial")
            .and_then(|v| v.as_str())
            .map(|v| v.to_string()),
        logged_user: obj
            .get("logged_user")
            .and_then(|v| v.as_str())
            .map(|v| v.to_string()),
        os_name: obj
            .get("os_name")
            .and_then(|v| v.as_str())
            .map(|v| v.to_string()),
        os_version: obj
            .get("os_version")
            .and_then(|v| v.as_str())
            .map(|v| v.to_string()),
        os_arch: obj
            .get("os_arch")
            .and_then(|v| v.as_str())
            .map(|v| v.to_string()),
        domain_name: obj
            .get("domain_name")
            .and_then(|v| v.as_str())
            .map(|v| v.to_string()),
        mac_addresses: obj
            .get("mac_addresses")
            .and_then(|v| v.as_array())
            .map(|items| {
                items
                    .iter()
                    .filter_map(|item| item.as_str().map(|v| v.to_string()))
                    .collect()
            })
            .unwrap_or_default(),
        install_mode: obj
            .get("install_mode")
            .and_then(|v| v.as_str())
            .map(|v| v.to_string()),
        blocked: obj
            .get("blocked")
            .map(parse_bool)
            .or_else(|| obj.get("BLOQUEADO").map(parse_bool))
            .unwrap_or(false),
        reused_existing: obj.get("reused_existing").map(parse_bool).unwrap_or(false),
        bound: obj.get("bound").map(parse_bool).unwrap_or(false),
    }
}

fn parse_bool(value: &Value) -> bool {
    match value {
        Value::Bool(v) => *v,
        Value::Number(v) => v.as_i64().unwrap_or(0) != 0,
        Value::String(v) => matches!(
            v.trim().to_uppercase().as_str(),
            "1" | "TRUE" | "T" | "Y" | "YES" | "S" | "SIM" | "ALLOWED"
        ),
        _ => false,
    }
}

fn parse_datetime(value: &Value) -> Option<DateTime<FixedOffset>> {
    let raw = value.as_str()?;

    if let Ok(dt) = DateTime::parse_from_rfc3339(raw) {
        return Some(dt);
    }

    if let Ok(dt) = DateTime::parse_from_str(raw, "%Y-%m-%d %H:%M:%S%:z") {
        return Some(dt);
    }

    for fmt in ["%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d"] {
        if let Ok(naive) = NaiveDateTime::parse_from_str(raw, fmt) {
            if let Some(local_dt) = Local.from_local_datetime(&naive).single() {
                return Some(local_dt.fixed_offset());
            }
        }
    }

    None
}

fn stringify_value(value: &Value) -> String {
    match value {
        Value::String(v) => v.clone(),
        Value::Number(v) => v.to_string(),
        Value::Bool(v) => {
            if *v {
                "true".to_string()
            } else {
                "false".to_string()
            }
        }
        _ => String::new(),
    }
}
