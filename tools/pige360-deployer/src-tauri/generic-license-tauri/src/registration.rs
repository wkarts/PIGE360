use base64::engine::general_purpose::STANDARD as BASE64;
use base64::Engine;
use directories::{BaseDirs, ProjectDirs};
use ed25519_dalek::{Signature, Verifier, VerifyingKey};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::env;
use std::fs;
use std::path::PathBuf;

use crate::error::LicenseError;
use crate::models::{LicenseCheckInput, LicenseConfig};

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct RegistrationFileDiscovery {
    pub searched_paths: Vec<String>,
    pub file_path: Option<String>,
    pub content_b64: Option<String>,
    pub verified: Option<bool>,
    pub payload: Option<Value>,
    pub message: Option<String>,
}

pub fn enrich_input_from_registration_file(
    config: &LicenseConfig,
    input: &mut LicenseCheckInput,
) -> Result<Option<RegistrationFileDiscovery>, LicenseError> {
    if input.registration_file_content_b64.is_some() || !config.enable_registration_file_lookup {
        return Ok(None);
    }

    let discovered = discover_registration_file(config)?;

    if let Some(content_b64) = &discovered.content_b64 {
        input.registration_file_content_b64 = Some(content_b64.clone());
        input.registration_file_path = discovered.file_path.clone();
        input.registration_file_verified = discovered.verified;

        if input.company_document.trim().is_empty() {
            if let Some(document) = discovered
                .payload
                .as_ref()
                .and_then(|v| v.get("company"))
                .and_then(|v| v.get("document"))
                .and_then(|v| v.as_str())
            {
                input.company_document = document.to_string();
            }
        }

        if input.company_email.is_none() {
            input.company_email = discovered
                .payload
                .as_ref()
                .and_then(|v| v.get("company"))
                .and_then(|v| v.get("email"))
                .and_then(|v| v.as_str())
                .map(|v| v.to_string());
        }

        if input.company_legal_name.is_none() {
            input.company_legal_name = discovered
                .payload
                .as_ref()
                .and_then(|v| v.get("company"))
                .and_then(|v| v.get("legal_name"))
                .and_then(|v| v.as_str())
                .map(|v| v.to_string());
        }

        if input.app_slug.is_none() {
            input.app_slug = discovered
                .payload
                .as_ref()
                .and_then(|v| v.get("application"))
                .and_then(|v| v.get("slug"))
                .and_then(|v| v.as_str())
                .map(|v| v.to_string());
        }
    }

    Ok(Some(discovered))
}

pub fn discover_registration_file(
    config: &LicenseConfig,
) -> Result<RegistrationFileDiscovery, LicenseError> {
    let mut searched_paths = Vec::new();

    for candidate in candidate_paths(config) {
        searched_paths.push(candidate.to_string_lossy().to_string());
        if !candidate.exists() {
            continue;
        }

        let bytes =
            fs::read(&candidate).map_err(|e| LicenseError::RegistrationFile(e.to_string()))?;
        let content_b64 = BASE64.encode(&bytes);
        let payload = serde_json::from_slice::<Value>(&bytes).ok();
        let verified = match (&payload, &config.registration_public_key_base64) {
            (Some(payload), Some(pub_key)) if !pub_key.trim().is_empty() => {
                Some(verify_signature(payload, pub_key)?)
            }
            _ => None,
        };

        return Ok(RegistrationFileDiscovery {
            searched_paths,
            file_path: Some(candidate.to_string_lossy().to_string()),
            content_b64: Some(content_b64),
            verified,
            payload,
            message: Some("arquivo de registro localizado automaticamente".to_string()),
        });
    }

    Ok(RegistrationFileDiscovery {
        searched_paths,
        file_path: None,
        content_b64: None,
        verified: None,
        payload: None,
        message: Some("nenhum arquivo de registro foi localizado".to_string()),
    })
}

fn candidate_paths(config: &LicenseConfig) -> Vec<PathBuf> {
    let mut roots: Vec<PathBuf> = Vec::new();

    if let Ok(exe) = env::current_exe() {
        if let Some(parent) = exe.parent() {
            roots.push(parent.to_path_buf());
        }
    }

    if let Ok(current_dir) = env::current_dir() {
        roots.push(current_dir);
    }

    if let Some(base_dirs) = BaseDirs::new() {
        roots.push(base_dirs.data_dir().to_path_buf());
        roots.push(base_dirs.config_dir().to_path_buf());
    }

    if let Some(project_dirs) = ProjectDirs::from("br", "WWSoftwares", "IntegraDesktop") {
        roots.push(project_dirs.data_dir().to_path_buf());
        roots.push(project_dirs.config_dir().to_path_buf());
    }

    if let Ok(program_data) = env::var("PROGRAMDATA") {
        roots.push(
            PathBuf::from(program_data)
                .join("WWSoftwares")
                .join("IntegraDesktop"),
        );
    }

    for path in &config.registration_file_extra_paths {
        if !path.trim().is_empty() {
            roots.push(PathBuf::from(path));
        }
    }

    let mut candidates = Vec::new();
    for root in roots {
        for name in &config.registration_file_names {
            candidates.push(root.join(name));
        }
    }

    candidates
}

fn verify_signature(payload: &Value, public_key_b64: &str) -> Result<bool, LicenseError> {
    let obj = payload.as_object().ok_or_else(|| {
        LicenseError::RegistrationFile("payload do arquivo de registro inválido".to_string())
    })?;

    let signature_value = obj
        .get("signature")
        .and_then(|v| v.get("value"))
        .and_then(|v| v.as_str())
        .ok_or_else(|| {
            LicenseError::RegistrationFile(
                "assinatura não encontrada no arquivo de registro".to_string(),
            )
        })?;

    let mut unsigned = payload.clone();
    if let Some(map) = unsigned.as_object_mut() {
        map.remove("signature");
    }

    let message = serde_json::to_vec(&unsigned).map_err(|e| LicenseError::Serde(e.to_string()))?;
    let public_key_bytes = BASE64
        .decode(public_key_b64)
        .map_err(|e| LicenseError::RegistrationFile(format!("chave pública inválida: {}", e)))?;
    let signature_bytes = BASE64
        .decode(signature_value)
        .map_err(|e| LicenseError::RegistrationFile(format!("assinatura inválida: {}", e)))?;

    let public_key_array: [u8; 32] = public_key_bytes.try_into().map_err(|_| {
        LicenseError::RegistrationFile("a chave pública Ed25519 deve conter 32 bytes".to_string())
    })?;
    let signature_array: [u8; 64] = signature_bytes.try_into().map_err(|_| {
        LicenseError::RegistrationFile("a assinatura Ed25519 deve conter 64 bytes".to_string())
    })?;

    let verifying_key = VerifyingKey::from_bytes(&public_key_array)
        .map_err(|e| LicenseError::RegistrationFile(e.to_string()))?;
    let signature = Signature::from_bytes(&signature_array);

    Ok(verifying_key.verify(&message, &signature).is_ok())
}
