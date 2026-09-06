use serde::Serialize;
use thiserror::Error;

#[derive(Debug, Error, Clone)]
pub enum LicenseError {
    #[error("configuração inválida: {0}")]
    Config(String),

    #[error("erro HTTP: {0}")]
    Http(String),

    #[error("licença inválida: {0}")]
    Invalid(String),

    #[error("erro de serialização: {0}")]
    Serde(String),

    #[error("erro de IO: {0}")]
    Io(String),

    #[error("endpoint indisponível: {0}")]
    EndpointUnavailable(String),

    #[error("erro no arquivo de registro: {0}")]
    RegistrationFile(String),

    #[error("falha na etapa {step} ({reason_code}): {message}")]
    Structured {
        step: String,
        reason_code: String,
        message: String,
    },
}

impl LicenseError {
    pub fn step(&self) -> String {
        match self {
            Self::Structured { step, .. } => step.clone(),
            Self::RegistrationFile(_) => "registration_file".to_string(),
            Self::EndpointUnavailable(_) => "resolve_activation".to_string(),
            Self::Config(_) => "config".to_string(),
            Self::Http(_) => "http".to_string(),
            Self::Invalid(_) => "validation".to_string(),
            Self::Serde(_) => "serialization".to_string(),
            Self::Io(_) => "io".to_string(),
        }
    }

    pub fn reason_code(&self) -> String {
        match self {
            Self::Structured { reason_code, .. } => reason_code.clone(),
            Self::RegistrationFile(_) => "REGISTRATION_FILE_ERROR".to_string(),
            Self::EndpointUnavailable(_) => "ENDPOINT_UNAVAILABLE".to_string(),
            Self::Config(_) => "INVALID_CONFIG".to_string(),
            Self::Http(_) => "HTTP_ERROR".to_string(),
            Self::Invalid(_) => "INVALID_LICENSE".to_string(),
            Self::Serde(_) => "SERDE_ERROR".to_string(),
            Self::Io(_) => "IO_ERROR".to_string(),
        }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct SerializableLicenseError {
    pub step: String,
    pub reason_code: String,
    pub message: String,
}

impl From<LicenseError> for SerializableLicenseError {
    fn from(value: LicenseError) -> Self {
        Self {
            step: value.step(),
            reason_code: value.reason_code(),
            message: value.to_string(),
        }
    }
}
