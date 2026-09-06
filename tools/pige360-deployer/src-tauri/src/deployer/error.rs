use std::fmt::{Display, Formatter};

#[derive(Debug)]
pub struct DeployError(pub String);

impl DeployError {
    pub fn msg(message: impl Into<String>) -> Self {
        Self(message.into())
    }
}

impl Display for DeployError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(&self.0)
    }
}

impl std::error::Error for DeployError {}

impl From<std::io::Error> for DeployError {
    fn from(error: std::io::Error) -> Self {
        Self(format!("Falha de entrada/saída: {error}"))
    }
}

impl From<serde_json::Error> for DeployError {
    fn from(error: serde_json::Error) -> Self {
        Self(format!("JSON inválido: {error}"))
    }
}

impl From<reqwest::Error> for DeployError {
    fn from(error: reqwest::Error) -> Self {
        Self(format!("Falha HTTP: {error}"))
    }
}

pub type Result<T> = std::result::Result<T, DeployError>;
