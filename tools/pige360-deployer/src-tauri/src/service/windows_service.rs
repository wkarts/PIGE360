use serde_json::{json, Value};

pub fn service_status() -> Value {
    json!({
        "platform": "windows",
        "installed": false,
        "running": false,
        "manager": "available",
        "message": "Use o empacotamento final para ativar instalação real como serviço Windows."
    })
}
