use chrono::Utc;

use crate::cache::OfflineCache;
use crate::client::LicenseApiClient;
use crate::device::enrich_input;
use crate::error::LicenseError;
use crate::models::{
    ApplicationLicenseRecord, DeviceRecord, DiagnosticItem, LicenseApiResponse, LicenseCheckInput,
    LicenseConfig, LicenseDecision, LicenseRecord, OfflineDecision,
};
use crate::registration::enrich_input_from_registration_file;

pub struct GenericLicenseService {
    config: LicenseConfig,
    api: LicenseApiClient,
    cache: OfflineCache,
}

impl GenericLicenseService {
    pub fn new(config: LicenseConfig) -> Self {
        let api = LicenseApiClient::new(config.clone());
        let cache = OfflineCache::new(config.cache_namespace.clone());

        Self { config, api, cache }
    }

    pub async fn check(
        &self,
        mut input: LicenseCheckInput,
    ) -> Result<LicenseDecision, LicenseError> {
        input.company_document = only_digits(&input.company_document);
        enrich_input(&mut input);
        let _ = enrich_input_from_registration_file(&self.config, &mut input)?;

        if input.company_document.is_empty() {
            return Err(LicenseError::Invalid(
                "documento da empresa não informado".to_string(),
            ));
        }

        if self.config.prefer_resolve_activation {
            match self.api.resolve_activation(&input).await {
                Ok(decision) => {
                    let _ = self
                        .cache
                        .put_decision(&input.company_document, &decision)
                        .await;
                    return Ok(decision);
                }
                Err(err) => {
                    if !self.config.allow_legacy_fallback {
                        return self
                            .try_offline_cache_or_fail(&input.company_document, err)
                            .await;
                    }
                }
            }
        }

        match self.api.company_status(&input.company_document).await {
            Ok(payload) => {
                let _ = self
                    .cache
                    .put_payload(&input.company_document, &payload)
                    .await;
                let decision = self.evaluate_legacy(payload, &input, false).await?;
                let _ = self
                    .cache
                    .put_decision(&input.company_document, &decision)
                    .await;
                Ok(decision)
            }
            Err(err) => {
                self.try_offline_cache_or_fail(&input.company_document, err)
                    .await
            }
        }
    }

    async fn try_offline_cache_or_fail(
        &self,
        document: &str,
        err: LicenseError,
    ) -> Result<LicenseDecision, LicenseError> {
        let cached = self.cache.get(document).await?;
        let cached = match cached {
            Some(value) => value,
            None => {
                return Err(LicenseError::Structured {
                    step: "offline_cache".to_string(),
                    reason_code: "ONLINE_VALIDATION_FAILED_NO_CACHE".to_string(),
                    message: format!(
                        "falha online ({}) e não existe cache offline para esta licença",
                        err
                    ),
                })
            }
        };

        let age_days = Utc::now()
            .signed_duration_since(cached.cached_at.with_timezone(&Utc))
            .num_days();

        if age_days > self.config.offline_max_age_days {
            return Err(LicenseError::Structured {
                step: "offline_cache".to_string(),
                reason_code: "OFFLINE_CACHE_EXPIRED".to_string(),
                message: "falha online e o cache offline expirou".to_string(),
            });
        }

        if let Some(mut decision) = cached.decision {
            decision.used_offline_cache = true;
            decision.source = "offline".to_string();
            if decision.reason_code.is_none() {
                decision.reason_code = Some("ONLINE_VALIDATION_FAILED_USING_CACHE".to_string());
            }
            return Ok(decision);
        }

        if let Some(payload) = cached.payload {
            let mut decision = self
                .evaluate_legacy(
                    payload,
                    &LicenseCheckInput {
                        company_document: document.to_string(),
                        company_name: None,
                        company_email: None,
                        company_legal_name: None,
                        app_id: String::new(),
                        app_name: String::new(),
                        app_version: String::new(),
                        app_slug: None,
                        device_key: None,
                        device_name: None,
                        station_name: None,
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
                        allow_company_auto_create: None,
                        allow_device_auto_create: None,
                        allow_device_auto_update: None,
                        requested_licenses: None,
                        device_identifier: None,
                        validation_mode: None,
                        interface_mode: None,
                        local_license_mode: None,
                        metadata: Default::default(),
                        login_context: false,
                    },
                    true,
                )
                .await?;
            decision.reason_code = Some("ONLINE_VALIDATION_FAILED_USING_CACHE".to_string());
            decision.source = "offline".to_string();
            return Ok(decision);
        }

        Err(err)
    }

    async fn evaluate_legacy(
        &self,
        payload: LicenseApiResponse,
        input: &LicenseCheckInput,
        used_offline_cache: bool,
    ) -> Result<LicenseDecision, LicenseError> {
        let mut diagnostics = Vec::new();

        if payload.status == 0 {
            if input
                .allow_company_auto_create
                .unwrap_or(self.config.auto_register_company_on_missing)
            {
                if let Err(err) = self.api.register_company(input).await {
                    diagnostics.push(diag(
                        "register_company",
                        "COMPANY_AUTO_CREATE_FAILED",
                        err.to_string(),
                    ));
                } else if let Ok(registered_payload) =
                    self.api.company_status(&input.company_document).await
                {
                    let _ = self
                        .cache
                        .put_payload(&input.company_document, &registered_payload)
                        .await;
                    return Box::pin(self.evaluate_legacy(
                        registered_payload,
                        input,
                        used_offline_cache,
                    ))
                    .await;
                }
            }

            return Ok(LicenseDecision {
                allowed: false,
                decision: "denied".to_string(),
                reason_code: Some("COMPANY_NOT_FOUND".to_string()),
                step: Some("resolve_company".to_string()),
                message: payload.message.unwrap_or_else(|| {
                    "empresa não cadastrada no serviço de licenciamento".to_string()
                }),
                used_offline_cache,
                warning: None,
                license: Some(payload.license.clone()),
                application_license: Some(application_from_legacy(&payload.license)),
                company: Some(company_from_legacy(&payload.license)),
                device: None,
                offline: Some(OfflineDecision::default()),
                diagnostics,
                source: source_label(used_offline_cache),
            });
        }

        let license = payload.license.clone();

        if license.blocked && self.config.block_on_company_blocked {
            return Ok(deny(
                "empresa bloqueada no serviço de licenciamento",
                "COMPANY_BLOCKED",
                "validate_company",
                used_offline_cache,
                license,
                None,
                diagnostics,
            ));
        }

        if let Some(expires_at) = license.expires_at.clone() {
            if expires_at.with_timezone(&Utc) < Utc::now() && self.config.block_on_expired {
                return Ok(deny(
                    "licença expirada",
                    "LICENSE_EXPIRED",
                    "validate_license",
                    used_offline_cache,
                    payload.license,
                    None,
                    diagnostics,
                ));
            }
        }

        let device_key = input.device_key.clone().unwrap_or_default();
        let device_name = input
            .station_name
            .clone()
            .or_else(|| input.device_name.clone())
            .unwrap_or_default();
        let device = find_device(&license, &device_key);

        if device.is_none() {
            if input
                .allow_device_auto_create
                .unwrap_or(self.config.auto_register_device_on_missing)
            {
                if let Err(err) = self.api.register_device(input).await {
                    diagnostics.push(diag(
                        "register_device",
                        "DEVICE_AUTO_CREATE_FAILED",
                        err.to_string(),
                    ));
                } else if let Ok(registered_payload) =
                    self.api.company_status(&input.company_document).await
                {
                    let _ = self
                        .cache
                        .put_payload(&input.company_document, &registered_payload)
                        .await;
                    return Box::pin(self.evaluate_legacy(
                        registered_payload,
                        input,
                        used_offline_cache,
                    ))
                    .await;
                }
            }

            if self.config.block_on_device_missing {
                return Ok(deny(
                    "dispositivo não autorizado para esta licença",
                    "DEVICE_NOT_FOUND",
                    "resolve_device",
                    used_offline_cache,
                    payload.license,
                    None,
                    diagnostics,
                ));
            }
        }

        if let Some(current_device) = &device {
            if current_device.blocked && self.config.block_on_device_blocked {
                return Ok(deny(
                    "dispositivo bloqueado para esta licença",
                    "DEVICE_BLOCKED",
                    "validate_device",
                    used_offline_cache,
                    payload.license,
                    Some(current_device.clone()),
                    diagnostics,
                ));
            }

            if input
                .allow_device_auto_update
                .unwrap_or(self.config.auto_update_device_name)
            {
                if let (Some(id), Some(name)) = (&current_device.id, &current_device.device_name) {
                    if name != &device_name {
                        if let Err(err) = self.api.update_device_name(id, input).await {
                            diagnostics.push(diag(
                                "update_device",
                                "DEVICE_AUTO_UPDATE_FAILED",
                                err.to_string(),
                            ));
                        }
                    }
                }
            }
        }

        let warning = license.expires_at.clone().and_then(|expires_at| {
            let days_left = expires_at
                .with_timezone(&Utc)
                .signed_duration_since(Utc::now())
                .num_days();

            if days_left >= 0 && days_left <= self.config.warn_before_expiration_in_days {
                Some(format!("A licença vence em {} dia(s).", days_left))
            } else {
                None
            }
        });

        Ok(LicenseDecision {
            allowed: true,
            decision: "allowed".to_string(),
            reason_code: Some(if used_offline_cache {
                "ONLINE_VALIDATION_FAILED_USING_CACHE".to_string()
            } else {
                "LICENSE_VALID".to_string()
            }),
            step: Some("validate_license".to_string()),
            message: if used_offline_cache {
                "licença validada com cache offline".to_string()
            } else {
                "licença validada com sucesso".to_string()
            },
            used_offline_cache,
            warning,
            license: Some(payload.license.clone()),
            application_license: Some(application_from_legacy(&payload.license)),
            company: Some(company_from_legacy(&payload.license)),
            device,
            offline: Some(OfflineDecision::default()),
            diagnostics,
            source: source_label(used_offline_cache),
        })
    }
}

fn deny(
    message: &str,
    reason_code: &str,
    step: &str,
    used_offline_cache: bool,
    license: LicenseRecord,
    device: Option<DeviceRecord>,
    diagnostics: Vec<DiagnosticItem>,
) -> LicenseDecision {
    LicenseDecision {
        allowed: false,
        decision: "denied".to_string(),
        reason_code: Some(reason_code.to_string()),
        step: Some(step.to_string()),
        message: message.to_string(),
        used_offline_cache,
        warning: None,
        application_license: Some(application_from_legacy(&license)),
        company: Some(company_from_legacy(&license)),
        license: Some(license),
        device,
        offline: Some(OfflineDecision::default()),
        diagnostics,
        source: source_label(used_offline_cache),
    }
}

fn application_from_legacy(license: &LicenseRecord) -> ApplicationLicenseRecord {
    ApplicationLicenseRecord {
        application_slug: license.application_slug.clone(),
        status: Some(
            if license.blocked {
                "blocked"
            } else if license.active {
                "active"
            } else {
                "inactive"
            }
            .to_string(),
        ),
        max_devices: license.max_devices,
        devices_in_use: license.devices_in_use,
        devices_available: license.devices_available,
        expires_at: license.expires_at.clone(),
    }
}

fn company_from_legacy(license: &LicenseRecord) -> crate::models::CompanyRecord {
    crate::models::CompanyRecord {
        id: None,
        document: license.document.clone(),
        legal_name: license.company_name.clone(),
        email: license.company_email.clone(),
        reused_existing: false,
    }
}

fn source_label(used_offline_cache: bool) -> String {
    if used_offline_cache {
        "offline".to_string()
    } else {
        "online".to_string()
    }
}

fn find_device(license: &LicenseRecord, device_key: &str) -> Option<DeviceRecord> {
    license
        .devices
        .iter()
        .find(|device| device.device_key.as_deref().unwrap_or("") == device_key)
        .cloned()
}

fn only_digits(value: &str) -> String {
    value.chars().filter(|c| c.is_ascii_digit()).collect()
}

fn diag(step: &str, code: &str, message: String) -> DiagnosticItem {
    DiagnosticItem {
        step: step.to_string(),
        code: code.to_string(),
        message,
    }
}
