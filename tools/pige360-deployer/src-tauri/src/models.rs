use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

#[derive(Debug, Serialize)]
pub struct LoginResponse {
    pub success: bool,
    pub message: String,
    pub session_token: Option<String>,
    pub user: Option<AuthUser>,
}

#[derive(Debug, Serialize, Clone)]
pub struct AuthUser {
    pub id: i64,
    pub nome: String,
    pub login: String,
    pub email: Option<String>,
    pub telefone: Option<String>,
    pub cargo: Option<String>,
    pub photo_url: Option<String>,
    pub administrador: bool,
    pub master_user: bool,
    pub senha_provisoria: bool,
    pub permission_keys: Vec<String>,
    pub profile_names: Vec<String>,
    pub company_ids: Vec<i64>,
    pub company_names: Vec<String>,
}

#[derive(Debug, Clone)]
pub struct SessionIdentity {
    pub user_id: i64,
    pub master_user: bool,
    pub senha_provisoria: bool,
}

#[derive(Debug, Serialize)]
pub struct ComboOption {
    pub id: i64,
    pub label: String,
}

#[allow(dead_code)]
#[derive(Debug, Deserialize)]
pub struct GenericEntityPayload {
    pub entity: String,
    pub payload: Map<String, Value>,
}
