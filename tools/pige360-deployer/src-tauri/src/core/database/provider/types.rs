use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(untagged)]
pub enum DbValue {
    Null,
    Bool(bool),
    Integer(i64),
    Real(f64),
    Text(String),
    Json(Value),
}

pub type DbRow = Map<String, Value>;

impl From<Value> for DbValue {
    fn from(value: Value) -> Self {
        match value {
            Value::Null => Self::Null,
            Value::Bool(value) => Self::Bool(value),
            Value::Number(value) => {
                if let Some(integer) = value.as_i64() {
                    Self::Integer(integer)
                } else if let Some(real) = value.as_f64() {
                    Self::Real(real)
                } else {
                    Self::Null
                }
            }
            Value::String(value) => Self::Text(value),
            other => Self::Json(other),
        }
    }
}

impl DbValue {
    pub fn to_json_value(&self) -> Value {
        match self {
            Self::Null => Value::Null,
            Self::Bool(value) => Value::Bool(*value),
            Self::Integer(value) => Value::from(*value),
            Self::Real(value) => Value::from(*value),
            Self::Text(value) => Value::String(value.clone()),
            Self::Json(value) => value.clone(),
        }
    }
}
