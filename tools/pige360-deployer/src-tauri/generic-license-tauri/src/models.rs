use chrono::{DateTime, FixedOffset};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LicenseApiResponse {
    pub status: i32,
    pub message: Option<String>,
    #[serde(default)]
    pub license: LicenseRecord,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct LicenseRecord {
    pub document: Option<String>,
    pub company_name: Option<String>,
    pub company_email: Option<String>,
    #[serde(default)]
    pub blocked: bool,
    #[serde(default)]
    pub active: bool,
    pub expires_at: Option<DateTime<FixedOffset>>,
    pub max_devices: Option<u32>,
    pub devices_in_use: Option<u32>,
    pub devices_available: Option<u32>,
    pub application_slug: Option<String>,
    #[serde(default)]
    pub devices: Vec<DeviceRecord>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct CompanyRecord {
    pub id: Option<String>,
    pub document: Option<String>,
    pub legal_name: Option<String>,
    pub email: Option<String>,
    #[serde(default)]
    pub reused_existing: bool,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ApplicationLicenseRecord {
    pub application_slug: Option<String>,
    pub status: Option<String>,
    pub max_devices: Option<u32>,
    pub devices_in_use: Option<u32>,
    pub devices_available: Option<u32>,
    pub expires_at: Option<DateTime<FixedOffset>>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct DeviceRecord {
    pub id: Option<String>,
    pub device_key: Option<String>,
    pub device_name: Option<String>,
    pub station_name: Option<String>,
    pub hostname: Option<String>,
    pub computer_name: Option<String>,
    pub serial_number: Option<String>,
    pub machine_guid: Option<String>,
    pub bios_serial: Option<String>,
    pub motherboard_serial: Option<String>,
    pub logged_user: Option<String>,
    pub os_name: Option<String>,
    pub os_version: Option<String>,
    pub os_arch: Option<String>,
    pub domain_name: Option<String>,
    #[serde(default)]
    pub mac_addresses: Vec<String>,
    pub install_mode: Option<String>,
    #[serde(default)]
    pub blocked: bool,
    #[serde(default)]
    pub reused_existing: bool,
    #[serde(default)]
    pub bound: bool,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct OfflineDecision {
    pub cache_allowed_until: Option<DateTime<FixedOffset>>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct DiagnosticItem {
    pub step: String,
    pub code: String,
    pub message: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CachedLicenseFile {
    pub cached_at: DateTime<FixedOffset>,
    #[serde(default)]
    pub decision: Option<LicenseDecision>,
    #[serde(default)]
    pub payload: Option<LicenseApiResponse>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LicenseCheckInput {
    pub company_document: String,
    pub company_name: Option<String>,
    #[serde(default)]
    pub company_email: Option<String>,
    #[serde(default)]
    pub company_legal_name: Option<String>,
    pub app_id: String,
    pub app_name: String,
    pub app_version: String,
    #[serde(default)]
    pub app_slug: Option<String>,
    #[serde(default)]
    pub device_key: Option<String>,
    #[serde(default)]
    pub device_name: Option<String>,
    #[serde(default)]
    pub station_name: Option<String>,
    #[serde(default)]
    pub hostname: Option<String>,
    #[serde(default)]
    pub computer_name: Option<String>,
    #[serde(default)]
    pub serial_number: Option<String>,
    #[serde(default)]
    pub machine_guid: Option<String>,
    #[serde(default)]
    pub bios_serial: Option<String>,
    #[serde(default)]
    pub motherboard_serial: Option<String>,
    #[serde(default)]
    pub logged_user: Option<String>,
    #[serde(default)]
    pub os_name: Option<String>,
    #[serde(default)]
    pub os_version: Option<String>,
    #[serde(default)]
    pub os_arch: Option<String>,
    #[serde(default)]
    pub domain_name: Option<String>,
    #[serde(default)]
    pub mac_addresses: Vec<String>,
    #[serde(default)]
    pub install_mode: Option<String>,
    #[serde(default)]
    pub registration_file_content_b64: Option<String>,
    #[serde(default)]
    pub registration_file_path: Option<String>,
    #[serde(default)]
    pub registration_file_verified: Option<bool>,
    #[serde(default)]
    pub allow_company_auto_create: Option<bool>,
    #[serde(default)]
    pub allow_device_auto_create: Option<bool>,
    #[serde(default)]
    pub allow_device_auto_update: Option<bool>,
    #[serde(default)]
    pub requested_licenses: Option<u32>,
    #[serde(default)]
    pub device_identifier: Option<String>,
    #[serde(default)]
    pub validation_mode: Option<String>,
    #[serde(default)]
    pub interface_mode: Option<String>,
    #[serde(default)]
    pub local_license_mode: Option<String>,
    #[serde(default)]
    pub metadata: BTreeMap<String, String>,
    #[serde(default)]
    pub login_context: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LicenseDecision {
    pub allowed: bool,
    pub decision: String,
    pub reason_code: Option<String>,
    pub step: Option<String>,
    pub message: String,
    pub used_offline_cache: bool,
    pub warning: Option<String>,
    pub license: Option<LicenseRecord>,
    pub application_license: Option<ApplicationLicenseRecord>,
    pub company: Option<CompanyRecord>,
    pub device: Option<DeviceRecord>,
    pub offline: Option<OfflineDecision>,
    #[serde(default)]
    pub diagnostics: Vec<DiagnosticItem>,
    pub source: String,
}

impl LicenseDecision {
    pub fn deny(
        message: impl Into<String>,
        reason_code: impl Into<String>,
        step: impl Into<String>,
    ) -> Self {
        Self {
            allowed: false,
            decision: "denied".to_string(),
            reason_code: Some(reason_code.into()),
            step: Some(step.into()),
            message: message.into(),
            used_offline_cache: false,
            warning: None,
            license: None,
            application_license: None,
            company: None,
            device: None,
            offline: None,
            diagnostics: Vec::new(),
            source: "online".to_string(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LicenseConfig {
    pub base_url: String,
    pub api_token: Option<String>,
    pub resolve_activation_endpoint: String,
    pub status_endpoint: String,
    pub register_company_endpoint: String,
    pub register_device_endpoint: String,
    pub update_device_endpoint: String,
    pub offline_max_age_days: i64,
    pub warn_before_expiration_in_days: i64,
    pub auto_register_company_on_missing: bool,
    pub auto_register_device_on_missing: bool,
    pub auto_update_device_name: bool,
    pub block_on_company_blocked: bool,
    pub block_on_device_blocked: bool,
    pub block_on_device_missing: bool,
    pub block_on_expired: bool,
    pub cache_namespace: String,
    pub prefer_resolve_activation: bool,
    pub allow_legacy_fallback: bool,
    pub enable_registration_file_lookup: bool,
    pub registration_file_names: Vec<String>,
    pub registration_file_extra_paths: Vec<String>,
    pub registration_public_key_base64: Option<String>,
}

impl Default for LicenseConfig {
    fn default() -> Self {
        Self {
            base_url: "https://api.rest.wwsoftwares.com.br/api/v1".to_string(),
            api_token: None,
            resolve_activation_endpoint: "/licensing/activation/resolve".to_string(),
            status_endpoint: "81b3767f-7bc5-4275-9453-a6a921010a17/86d7b2bee439957e040b72be6fea5fc2/cliente/{document}".to_string(),
            register_company_endpoint: "81b3767f-7bc5-4275-9453-a6a921010a17/86d7b2bee439957e040b72be6fea5fc2/clientes".to_string(),
            register_device_endpoint: "81b3767f-7bc5-4275-9453-a6a921010a17/86d7b2bee439957e040b72be6fea5fc2/maquinas".to_string(),
            update_device_endpoint: "81b3767f-7bc5-4275-9453-a6a921010a17/86d7b2bee439957e040b72be6fea5fc2/maquinas/IDMAQUINA/{id}".to_string(),
            offline_max_age_days: 15,
            warn_before_expiration_in_days: 5,
            auto_register_company_on_missing: false,
            auto_register_device_on_missing: false,
            auto_update_device_name: true,
            block_on_company_blocked: true,
            block_on_device_blocked: true,
            block_on_device_missing: true,
            block_on_expired: true,
            cache_namespace: "default".to_string(),
            prefer_resolve_activation: true,
            allow_legacy_fallback: true,
            enable_registration_file_lookup: true,
            registration_file_names: vec!["wwreg.json".to_string(), "wwreg.lic".to_string()],
            registration_file_extra_paths: Vec::new(),
            registration_public_key_base64: None,
        }
    }
}
