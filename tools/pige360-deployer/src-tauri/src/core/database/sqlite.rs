use std::path::Path;

use rusqlite::{params_from_iter, Connection, OptionalExtension};

pub fn connect(path: &Path) -> Result<Connection, String> {
    crate::db::open_connection(path)
}

pub fn health(path: &Path) -> Result<bool, String> {
    let conn = connect(path)?;
    conn.query_row("SELECT 1", [], |row| row.get::<_, i64>(0))
        .map(|value| value == 1)
        .map_err(|err| format!("Falha no health check SQLite: {err}"))
}

#[derive(Debug, Clone)]
pub struct SqliteProvider {
    db_path: std::path::PathBuf,
}

impl SqliteProvider {
    pub fn new(db_path: std::path::PathBuf) -> Self {
        Self { db_path }
    }
}

fn to_rusqlite_value(value: &super::provider::types::DbValue) -> rusqlite::types::Value {
    match value {
        super::provider::types::DbValue::Null => rusqlite::types::Value::Null,
        super::provider::types::DbValue::Bool(value) => {
            rusqlite::types::Value::Integer(if *value { 1 } else { 0 })
        }
        super::provider::types::DbValue::Integer(value) => rusqlite::types::Value::Integer(*value),
        super::provider::types::DbValue::Real(value) => rusqlite::types::Value::Real(*value),
        super::provider::types::DbValue::Text(value) => rusqlite::types::Value::Text(value.clone()),
        super::provider::types::DbValue::Json(value) => {
            rusqlite::types::Value::Text(value.to_string())
        }
    }
}

impl super::provider::DatabaseProvider for SqliteProvider {
    fn driver(&self) -> super::config::DatabaseDriver {
        super::config::DatabaseDriver::Sqlite
    }

    fn health(&self) -> Result<super::provider::ProviderStatus, String> {
        let ok = health(&self.db_path)?;
        Ok(super::provider::ProviderStatus {
            driver: "sqlite".to_string(),
            available: ok,
            message: if ok {
                "SQLite funcional.".to_string()
            } else {
                "SQLite indisponível.".to_string()
            },
        })
    }

    fn migrate(&self) -> Result<(), String> {
        crate::migrations::migrate(&self.db_path)
    }

    fn execute(
        &self,
        sql: &str,
        params: &[super::provider::types::DbValue],
    ) -> Result<u64, String> {
        let conn = connect(&self.db_path)?;
        let values = params.iter().map(to_rusqlite_value).collect::<Vec<_>>();
        conn.execute(sql, params_from_iter(values.iter()))
            .map(|affected| affected as u64)
            .map_err(|err| format!("Falha ao executar SQL SQLite pelo provider: {err}"))
    }

    fn query(
        &self,
        sql: &str,
        params: &[super::provider::types::DbValue],
    ) -> Result<Vec<super::provider::types::DbRow>, String> {
        let conn = connect(&self.db_path)?;
        let values = params.iter().map(to_rusqlite_value).collect::<Vec<_>>();
        let mut stmt = conn
            .prepare(sql)
            .map_err(|err| format!("Falha ao preparar query SQLite pelo provider: {err}"))?;
        let rows = stmt
            .query_map(params_from_iter(values.iter()), crate::db::row_to_json_map)
            .map_err(|err| format!("Falha ao executar query SQLite pelo provider: {err}"))?;
        rows.collect::<Result<Vec<_>, _>>()
            .map_err(|err| format!("Falha ao mapear query SQLite pelo provider: {err}"))
    }

    fn query_one(
        &self,
        sql: &str,
        params: &[super::provider::types::DbValue],
    ) -> Result<Option<super::provider::types::DbRow>, String> {
        let conn = connect(&self.db_path)?;
        let values = params.iter().map(to_rusqlite_value).collect::<Vec<_>>();
        let mut stmt = conn
            .prepare(sql)
            .map_err(|err| format!("Falha ao preparar query_one SQLite pelo provider: {err}"))?;
        stmt.query_row(params_from_iter(values.iter()), crate::db::row_to_json_map)
            .optional()
            .map_err(|err| format!("Falha ao executar query_one SQLite pelo provider: {err}"))
    }

    fn list_entities(
        &self,
        entity: &str,
        search: &str,
    ) -> Result<Vec<serde_json::Map<String, serde_json::Value>>, String> {
        let allowed = match entity {
            "departamentos" => (
                "departamentos",
                &["descricao", "ativo"][..],
                &["descricao"][..],
            ),
            "funcoes" => ("funcoes", &["descricao", "ativo"][..], &["descricao"][..]),
            "centro_custos" => (
                "centro_custos",
                &["codigo", "descricao", "ativo"][..],
                &["codigo", "descricao"][..],
            ),
            "clientes" => (
                "clientes",
                &[
                    "nome",
                    "documento",
                    "telefone",
                    "email",
                    "endereco",
                    "cidade",
                    "estado",
                    "observacoes",
                    "ativo",
                ][..],
                &["nome", "documento", "email"][..],
            ),
            "fornecedores" => (
                "fornecedores",
                &[
                    "nome",
                    "documento",
                    "telefone",
                    "email",
                    "endereco",
                    "cidade",
                    "estado",
                    "observacoes",
                    "ativo",
                ][..],
                &["nome", "documento", "email"][..],
            ),
            "produtos" => (
                "produtos",
                &["codigo", "descricao", "tipo", "unidade", "valor", "ativo"][..],
                &["codigo", "descricao", "tipo"][..],
            ),
            _ => return Err("Entidade não permitida para o provider SQLite.".to_string()),
        };

        let conn = connect(&self.db_path)?;
        let mut sql = format!("SELECT id, {} FROM {}", allowed.1.join(", "), allowed.0);
        let mut values: Vec<rusqlite::types::Value> = Vec::new();
        if !search.trim().is_empty() {
            let clauses = allowed
                .2
                .iter()
                .map(|column| format!("{column} LIKE ?"))
                .collect::<Vec<_>>()
                .join(" OR ");
            sql.push_str(&format!(" WHERE ({clauses})"));
            for _ in allowed.2 {
                values.push(rusqlite::types::Value::Text(format!("%{}%", search.trim())));
            }
        }
        sql.push_str(" ORDER BY id DESC");
        let mut stmt = conn
            .prepare(&sql)
            .map_err(|err| format!("Falha ao preparar CRUD provider SQLite: {err}"))?;
        let rows = stmt
            .query_map(params_from_iter(values.iter()), crate::db::row_to_json_map)
            .map_err(|err| format!("Falha ao listar via CRUD provider SQLite: {err}"))?;
        rows.collect::<Result<Vec<_>, _>>()
            .map_err(|err| format!("Falha ao mapear CRUD provider SQLite: {err}"))
    }
}
