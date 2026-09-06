use chrono::{Duration, Utc};
use rusqlite::{params, OptionalExtension};
#[cfg(any(feature = "desktop", feature = "mobile"))]
use tauri::State;
use uuid::Uuid;

use crate::{
    app_state::SharedState,
    bootstrap,
    db::{open_connection, write_app_log, AppLogInput},
    models::{AuthUser, LoginResponse, SessionIdentity},
    security::{hash_password, verify_password},
};

pub(crate) const PERMISSION_CATALOG: [(&str, &str); 17] = [
    ("dashboard:view", "Visualizar dashboard"),
    ("empresas:view", "Visualizar empresas"),
    ("empresas:manage", "Gerenciar empresas"),
    ("cadastros:view", "Visualizar cadastros genéricos"),
    ("cadastros:manage", "Gerenciar cadastros genéricos"),
    ("usuarios:view", "Visualizar usuários"),
    ("usuarios:manage", "Gerenciar usuários"),
    ("perfis:view", "Visualizar perfis de acesso"),
    ("perfis:manage", "Gerenciar perfis de acesso"),
    ("config:view", "Visualizar configurações"),
    ("config:manage", "Gerenciar configurações"),
    ("licenciamento:view", "Visualizar licenciamento"),
    ("licenciamento:manage", "Gerenciar licenciamento"),
    ("logs:view", "Visualizar logs"),
    ("logs:manage", "Gerenciar logs"),
    ("sync:view", "Visualizar fila de sincronização"),
    ("relatorios:export", "Exportar relatórios"),
];

pub(crate) fn all_permission_keys() -> Vec<String> {
    let mut keys = PERMISSION_CATALOG
        .iter()
        .map(|(key, _)| (*key).to_string())
        .collect::<Vec<_>>();
    keys.extend([]);
    keys.sort();
    keys.dedup();
    keys
}

pub(crate) fn build_auth_user(
    conn: &rusqlite::Connection,
    user_id: i64,
) -> Result<AuthUser, String> {
    let base = conn
        .query_row(
            "SELECT id, nome, login, email, telefone, cargo, photo_url, administrador, master_user, senha_provisoria, ativo
             FROM usuarios
             WHERE id = ?1
             LIMIT 1",
            [user_id],
            |row| {
                Ok((
                    row.get::<_, i64>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                    row.get::<_, Option<String>>(3)?,
                    row.get::<_, Option<String>>(4)?,
                    row.get::<_, Option<String>>(5)?,
                    row.get::<_, Option<String>>(6)?,
                    row.get::<_, i64>(7)?,
                    row.get::<_, i64>(8)?,
                    row.get::<_, i64>(9)?,
                    row.get::<_, i64>(10)?,
                ))
            },
        )
        .optional()
        .map_err(|err| format!("Falha ao carregar usuário autenticado: {err}"))?
        .ok_or_else(|| "Usuário da sessão não encontrado.".to_string())?;

    if base.10 == 0 {
        return Err("Usuário inativo.".to_string());
    }

    let mut stmt_profiles = conn
        .prepare(
            "SELECT p.nome
             FROM usuarios_perfis up
             INNER JOIN perfis_acesso p ON p.id = up.perfil_id
             WHERE up.usuario_id = ?1
             ORDER BY p.nome ASC",
        )
        .map_err(|err| format!("Falha ao preparar perfis do usuário: {err}"))?;

    let profile_names = stmt_profiles
        .query_map([user_id], |row| row.get::<_, String>(0))
        .map_err(|err| format!("Falha ao consultar perfis do usuário: {err}"))?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|err| format!("Falha ao mapear perfis do usuário: {err}"))?;

    let mut stmt_companies = conn
        .prepare(
            "SELECT e.id, e.nome
             FROM usuarios_empresas ue
             INNER JOIN empresas e ON e.id = ue.empresa_id
             WHERE ue.usuario_id = ?1
             ORDER BY e.nome ASC",
        )
        .map_err(|err| format!("Falha ao preparar empresas do usuário: {err}"))?;

    let company_rows = stmt_companies
        .query_map([user_id], |row| {
            Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
        })
        .map_err(|err| format!("Falha ao consultar empresas do usuário: {err}"))?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|err| format!("Falha ao mapear empresas do usuário: {err}"))?;

    let company_ids = company_rows.iter().map(|item| item.0).collect::<Vec<_>>();
    let company_names = company_rows
        .into_iter()
        .map(|item| item.1)
        .collect::<Vec<_>>();

    let permission_keys = if base.8 == 1 {
        all_permission_keys()
    } else {
        let mut stmt_permissions = conn
            .prepare(
                "SELECT DISTINCT pp.permissao_chave
                 FROM usuarios_perfis up
                 INNER JOIN perfis_permissoes pp ON pp.perfil_id = up.perfil_id
                 WHERE up.usuario_id = ?1
                 ORDER BY pp.permissao_chave ASC",
            )
            .map_err(|err| format!("Falha ao preparar permissões do usuário: {err}"))?;

        let mapped_rows = stmt_permissions
            .query_map([user_id], |row| row.get::<_, String>(0))
            .map_err(|err| format!("Falha ao consultar permissões do usuário: {err}"))?;
        let permission_rows = mapped_rows
            .collect::<Result<Vec<_>, _>>()
            .map_err(|err| format!("Falha ao mapear permissões do usuário: {err}"))?;
        permission_rows
    };

    Ok(AuthUser {
        id: base.0,
        nome: base.1,
        login: base.2,
        email: base.3,
        telefone: base.4,
        cargo: base.5,
        photo_url: base.6,
        administrador: base.7 == 1,
        master_user: base.8 == 1,
        senha_provisoria: base.9 == 1,
        permission_keys,
        profile_names,
        company_ids,
        company_names,
    })
}

pub(crate) fn load_session_identity(
    conn: &rusqlite::Connection,
    session_token: &str,
) -> Result<SessionIdentity, String> {
    let token = session_token.trim();
    if token.is_empty() {
        return Err("Sessão inválida ou expirada.".to_string());
    }

    let now = Utc::now().to_rfc3339();

    let session = conn
        .query_row(
            "SELECT us.usuario_id, u.master_user, u.ativo, u.senha_provisoria
             FROM user_sessions us
             INNER JOIN usuarios u ON u.id = us.usuario_id
             WHERE us.session_token = ?1 AND us.expires_at > ?2
             LIMIT 1",
            params![token, now],
            |row| {
                Ok((
                    row.get::<_, i64>(0)?,
                    row.get::<_, i64>(1)?,
                    row.get::<_, i64>(2)?,
                    row.get::<_, i64>(3)?,
                ))
            },
        )
        .optional()
        .map_err(|err| format!("Falha ao validar sessão: {err}"))?
        .ok_or_else(|| "Sessão inválida ou expirada.".to_string())?;

    if session.2 == 0 {
        return Err("Usuário inativo.".to_string());
    }

    conn.execute(
        "UPDATE user_sessions SET last_activity_at = ?1 WHERE session_token = ?2",
        params![now, token],
    )
    .map_err(|err| format!("Falha ao atualizar atividade da sessão: {err}"))?;

    Ok(SessionIdentity {
        user_id: session.0,
        master_user: session.1 == 1,
        senha_provisoria: session.3 == 1,
    })
}

pub(crate) fn require_session_by_token(
    conn: &rusqlite::Connection,
    session_token: &str,
) -> Result<SessionIdentity, String> {
    let identity = load_session_identity(conn, session_token)?;
    if identity.senha_provisoria {
        return Err("Troque a senha provisória antes de acessar este recurso.".to_string());
    }
    Ok(identity)
}

#[cfg(any(feature = "desktop", feature = "mobile"))]
#[tauri::command]
pub fn auth_login(
    state: State<'_, SharedState>,
    login: String,
    senha: String,
) -> Result<LoginResponse, String> {
    let db_path = state.db_path()?;
    let data_dir = state.data_dir()?;
    let conn = open_connection(&db_path)?;
    let normalized_login = login.trim().to_lowercase();

    let row = conn
        .query_row(
            "SELECT id, nome, login, senha_hash, administrador, ativo
             FROM usuarios
             WHERE LOWER(login) = ?1
             LIMIT 1",
            [normalized_login],
            |row| {
                Ok((
                    row.get::<_, i64>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                    row.get::<_, String>(3)?,
                    row.get::<_, i64>(4)?,
                    row.get::<_, i64>(5)?,
                ))
            },
        )
        .optional()
        .map_err(|err| format!("Falha ao consultar usuário: {err}"))?;

    let Some(row) = row else {
        return Ok(LoginResponse {
            success: false,
            message: "Credenciais inválidas.".to_string(),
            session_token: None,
            user: None,
        });
    };

    if row.5 == 0 {
        return Ok(LoginResponse {
            success: false,
            message: "Credenciais inválidas.".to_string(),
            session_token: None,
            user: None,
        });
    }

    let password_ok = verify_password(&senha, &row.3)?;
    if !password_ok {
        return Ok(LoginResponse {
            success: false,
            message: "Credenciais inválidas.".to_string(),
            session_token: None,
            user: None,
        });
    }

    let now = Utc::now();
    let session_token = Uuid::new_v4().to_string();
    let expires_at = (now + Duration::days(7)).to_rfc3339();
    let now_str = now.to_rfc3339();

    conn.execute(
        "DELETE FROM user_sessions WHERE usuario_id = ?1 OR expires_at <= ?2",
        params![row.0, now_str],
    )
    .map_err(|err| format!("Falha ao limpar sessões antigas: {err}"))?;

    conn.execute(
        "INSERT INTO user_sessions (usuario_id, session_token, created_at, expires_at, last_activity_at)
         VALUES (?1, ?2, ?3, ?4, ?3)",
        params![row.0, session_token, now_str, expires_at],
    )
    .map_err(|err| format!("Falha ao criar sessão: {err}"))?;

    conn.execute(
        "UPDATE usuarios SET ultimo_login_em = ?1 WHERE id = ?2",
        params![Utc::now().to_rfc3339(), row.0],
    )
    .map_err(|err| format!("Falha ao atualizar último login: {err}"))?;

    let user = build_auth_user(&conn, row.0)?;
    let _ = write_app_log(
        &conn,
        &data_dir,
        AppLogInput {
            level: "info",
            category: "auth",
            message: "Login efetuado com sucesso.",
            source: Some("backend"),
            route: None,
            details: Some(&serde_json::json!({"usuario_id": row.0, "login": row.2})),
        },
    );

    Ok(LoginResponse {
        success: true,
        message: if user.senha_provisoria {
            "Login efetuado com sucesso. Este usuário está com senha provisória.".to_string()
        } else {
            "Login efetuado com sucesso.".to_string()
        },
        session_token: Some(session_token),
        user: Some(user),
    })
}

#[cfg(any(feature = "desktop", feature = "mobile"))]
#[tauri::command]
pub fn auth_restore(
    state: State<'_, SharedState>,
    session_token: String,
) -> Result<LoginResponse, String> {
    let db_path = state.db_path()?;
    let data_dir = state.data_dir()?;
    let conn = open_connection(&db_path)?;
    let identity = match load_session_identity(&conn, &session_token) {
        Ok(identity) => identity,
        Err(_) => {
            let _ = write_app_log(
                &conn,
                &data_dir,
                AppLogInput {
                    level: "warning",
                    category: "session",
                    message: "Falha ao restaurar sessão expirada ou inválida.",
                    source: Some("backend"),
                    route: None,
                    details: None,
                },
            );
            return Ok(LoginResponse {
                success: false,
                message: "Sessão inválida ou expirada.".to_string(),
                session_token: None,
                user: None,
            });
        }
    };

    let user = build_auth_user(&conn, identity.user_id)?;
    let _ = write_app_log(
        &conn,
        &data_dir,
        AppLogInput {
            level: "info",
            category: "session",
            message: "Sessão restaurada com sucesso.",
            source: Some("backend"),
            route: None,
            details: Some(&serde_json::json!({"usuario_id": identity.user_id})),
        },
    );
    Ok(LoginResponse {
        success: true,
        message: "Sessão restaurada com sucesso.".to_string(),
        session_token: Some(session_token),
        user: Some(user),
    })
}

#[cfg(any(feature = "desktop", feature = "mobile"))]
#[tauri::command]
pub fn auth_logout(state: State<'_, SharedState>, session_token: String) -> Result<bool, String> {
    let db_path = state.db_path()?;
    let data_dir = state.data_dir()?;
    let conn = open_connection(&db_path)?;
    conn.execute(
        "DELETE FROM user_sessions WHERE session_token = ?1",
        [session_token],
    )
    .map_err(|err| format!("Falha ao encerrar sessão: {err}"))?;
    let _ = write_app_log(
        &conn,
        &data_dir,
        AppLogInput {
            level: "info",
            category: "session",
            message: "Sessão encerrada.",
            source: Some("backend"),
            route: None,
            details: None,
        },
    );
    Ok(true)
}

#[cfg(any(feature = "desktop", feature = "mobile"))]
#[tauri::command]
pub fn auth_change_password(
    state: State<'_, SharedState>,
    session_token: String,
    current_password: String,
    new_password: String,
) -> Result<bool, String> {
    let db_path = state.db_path()?;
    let data_dir = state.data_dir()?;
    let conn = open_connection(&db_path)?;
    let identity = load_session_identity(&conn, &session_token)?;

    let new_password = new_password.trim();
    if new_password.len() < 12
        || !new_password.chars().any(|value| value.is_ascii_lowercase())
        || !new_password.chars().any(|value| value.is_ascii_uppercase())
        || !new_password.chars().any(|value| value.is_ascii_digit())
        || !new_password.chars().any(|value| !value.is_alphanumeric())
    {
        return Err(
            "A nova senha deve ter ao menos 12 caracteres, com maiúscula, minúscula, número e símbolo."
                .to_string(),
        );
    }

    let current_hash: String = conn
        .query_row(
            "SELECT senha_hash FROM usuarios WHERE id = ?1 LIMIT 1",
            [identity.user_id],
            |row| row.get(0),
        )
        .map_err(|err| format!("Falha ao consultar senha atual: {err}"))?;

    if !verify_password(current_password.trim(), &current_hash)? {
        return Err("A senha atual informada está incorreta.".to_string());
    }

    let new_hash = hash_password(new_password)?;
    conn.execute(
        "UPDATE usuarios SET senha_hash = ?1, senha_provisoria = 0, updated_at = ?2 WHERE id = ?3",
        params![new_hash, Utc::now().to_rfc3339(), identity.user_id],
    )
    .map_err(|err| format!("Falha ao atualizar senha: {err}"))?;
    if identity.master_user {
        bootstrap::remove_after_password_change(&db_path)?;
    }
    let _ = write_app_log(
        &conn,
        &data_dir,
        AppLogInput {
            level: "info",
            category: "auth",
            message: "Senha alterada com sucesso.",
            source: Some("backend"),
            route: None,
            details: Some(&serde_json::json!({"usuario_id": identity.user_id})),
        },
    );

    Ok(true)
}
