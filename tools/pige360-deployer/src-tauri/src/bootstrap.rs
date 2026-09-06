use rand::{distributions::Alphanumeric, rngs::OsRng, Rng};
use std::{
    fs::{self, OpenOptions},
    io::Write,
    path::{Path, PathBuf},
};

const BOOTSTRAP_FILE_NAME: &str = ".bootstrap-admin.local";

#[derive(Debug, Clone)]
pub struct BootstrapCredential {
    pub username: String,
    pub password: String,
}

pub fn load_or_create(db_path: &Path) -> Result<BootstrapCredential, String> {
    for path in candidate_paths(db_path)? {
        if path.is_file() {
            return read_credential(&path);
        }
    }

    let data_dir = db_path
        .parent()
        .ok_or_else(|| "Diretório do banco não pôde ser determinado.".to_string())?;
    fs::create_dir_all(data_dir)
        .map_err(|err| format!("Falha ao criar diretório do bootstrap: {err}"))?;
    let path = data_dir.join(BOOTSTRAP_FILE_NAME);
    let credential = BootstrapCredential {
        username: "admin".to_string(),
        password: OsRng
            .sample_iter(&Alphanumeric)
            .take(32)
            .map(char::from)
            .collect(),
    };

    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }

    match options.open(&path) {
        Ok(mut file) => {
            let contents = format!(
                "Usuario bootstrap: {}\nSenha bootstrap: {}\nTroque a senha no primeiro acesso.\n",
                credential.username, credential.password
            );
            match file
                .write_all(contents.as_bytes())
                .and_then(|_| file.sync_all())
            {
                Ok(()) => Ok(credential),
                Err(err) => {
                    drop(file);
                    let _ = fs::remove_file(&path);
                    Err(format!("Falha ao gravar credencial bootstrap local: {err}"))
                }
            }
        }
        Err(err) if err.kind() == std::io::ErrorKind::AlreadyExists => read_credential(&path),
        Err(err) => Err(format!("Falha ao criar credencial bootstrap local: {err}")),
    }
}

pub fn remove_after_password_change(db_path: &Path) -> Result<(), String> {
    for path in candidate_paths(db_path)? {
        if !path.is_file() {
            continue;
        }
        fs::remove_file(&path).map_err(|err| {
            format!(
                "Senha alterada, mas a credencial bootstrap local não pôde ser removida de {}: {err}",
                path.display()
            )
        })?;
    }
    Ok(())
}

fn candidate_paths(db_path: &Path) -> Result<Vec<PathBuf>, String> {
    let data_dir = db_path
        .parent()
        .ok_or_else(|| "Diretório do banco não pôde ser determinado.".to_string())?;
    Ok(vec![data_dir.join(BOOTSTRAP_FILE_NAME)])
}

fn read_credential(path: &Path) -> Result<BootstrapCredential, String> {
    let raw = fs::read_to_string(path)
        .map_err(|err| format!("Falha ao ler credencial bootstrap local: {err}"))?;
    let mut username = None;
    let mut password = None;
    for line in raw.lines() {
        let normalized = line.trim();
        if let Some(value) = normalized
            .strip_prefix("Usuario bootstrap:")
            .or_else(|| normalized.strip_prefix("Usuário bootstrap:"))
            .or_else(|| normalized.strip_prefix("BOOTSTRAP_ADMIN_USERNAME="))
        {
            username = Some(value.trim().to_string());
        }
        if let Some(value) = normalized
            .strip_prefix("Senha bootstrap:")
            .or_else(|| normalized.strip_prefix("BOOTSTRAP_ADMIN_PASSWORD="))
        {
            password = Some(value.trim().to_string());
        }
    }

    let username = username
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| "admin".to_string());
    let password = password
        .filter(|value| value.len() >= 16)
        .ok_or_else(|| "Arquivo bootstrap local inválido ou sem senha forte.".to_string())?;
    Ok(BootstrapCredential { username, password })
}
