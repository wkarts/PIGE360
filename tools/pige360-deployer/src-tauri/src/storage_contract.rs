use std::path::{Path, PathBuf};

/// Destino canônico; nunca é usado como origem legada.
pub const CURRENT_LOCAL_DATA_DIR: &str = "pige360-deployer";
pub const CURRENT_SQLITE_DATABASE_FILE_NAME: &str = "pige360-deployer.db";

/// Origens legadas conservadoras, parametrizadas na derivação.
pub const LEGACY_LOCAL_DATA_DIRS: &[&str] = &[];
pub const LEGACY_SQLITE_DATABASE_FILE_NAMES: &[&str] = &[];

/// Tabelas cujo número de linhas deve ser preservado na cópia legada.
pub const CRITICAL_MIGRATION_TABLES: &[&str] = &["usuarios", "empresas", "departamentos", "funcoes", "centro_custos", "clientes", "fornecedores", "produtos"];

pub fn sqlite_database_path(data_dir: &Path) -> PathBuf {
    data_dir.join(CURRENT_SQLITE_DATABASE_FILE_NAME)
}

pub fn legacy_database_candidates_in(data_dir: &Path) -> Vec<PathBuf> {
    LEGACY_SQLITE_DATABASE_FILE_NAMES.iter().map(|name| data_dir.join(name)).collect()
}

pub fn known_legacy_database_candidates(base_dir: &Path) -> Vec<PathBuf> {
    let mut candidates = Vec::new();
    for slug in LEGACY_LOCAL_DATA_DIRS {
        candidates.extend(legacy_database_candidates_in(&base_dir.join(slug)));
    }
    candidates
}
