use axum::{
    extract::{Request, State},
    http::{header::HeaderName, StatusCode, Uri},
    middleware::{self, Next},
    response::{Html, IntoResponse, Redirect, Response},
    routing::{get, post},
    Json, Router,
};
use serde_json::{json, Value};
use tower_http::cors::{Any, CorsLayer};

use crate::{
    db::open_connection,
    internal_api::{app_commands, docs, state::InternalApiState},
};

fn runtime_app_name() -> String {
    std::env::var("PIGE360_DEPLOYER_NAME")
        .or_else(|_| std::env::var("APP_NAME"))
        .ok()
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| "PIGE360 Deployer".to_string())
}

fn runtime_app_identifier() -> String {
    std::env::var("PIGE360_DEPLOYER_IDENTIFIER")
        .or_else(|_| std::env::var("APP_IDENTIFIER"))
        .ok()
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| "br.com.pige360.deployer".to_string())
}

pub fn router(state: InternalApiState) -> Router {
    let protected = Router::new()
        .route("/api/command", post(app_commands::command))
        .route("/__internal_api/api/command", post(app_commands::command))
        .route("/version", get(version))
        .route("/__internal_api/version", get(version))
        .route("/status", get(status))
        .route("/__internal_api/status", get(status))
        .route("/app/meta", get(app_meta))
        .route("/__internal_api/app/meta", get(app_meta))
        .route("/features", get(features))
        .route("/__internal_api/features", get(features))
        .route("/logs", get(logs))
        .route("/__internal_api/logs", get(logs))
        .route_layer(middleware::from_fn_with_state(state.clone(), token_guard));

    let mut router = Router::new()
        .route("/", get(root))
        .route("/__internal_api/", get(root))
        .route("/health", get(health))
        .route("/__internal_api/health", get(health))
        .merge(protected)
        .with_state(state.clone());

    if state.config.expose_docs {
        let proxy_docs_path = format!("/__internal_api{}", state.config.docs.path);
        let docs_router = Router::new()
            .route("/openapi.json", get(openapi))
            .route("/__internal_api/openapi.json", get(openapi))
            .route(&state.config.docs.path, get(scalar_docs))
            .route(&proxy_docs_path, get(scalar_docs));

        router = if state.config.security.require_token
            && !state.config.docs_are_public_for_current_bind()
        {
            router.merge(
                docs_router
                    .route_layer(middleware::from_fn_with_state(state.clone(), token_guard))
                    .with_state(state.clone()),
            )
        } else {
            router.merge(docs_router.with_state(state.clone()))
        };
    }

    if state.config.security.cors_enabled {
        router.layer(
            CorsLayer::new()
                .allow_origin(Any)
                .allow_methods(Any)
                .allow_headers(Any),
        )
    } else {
        router
    }
}

async fn token_guard(
    State(state): State<InternalApiState>,
    request: Request,
    next: Next,
) -> Response {
    if !state.config.security.require_token {
        return next.run(request).await;
    }

    let configured_token = state
        .config
        .security
        .token
        .as_deref()
        .unwrap_or_default()
        .trim()
        .to_string();

    if configured_token.is_empty() {
        eprintln!("Token obrigatório não configurado");
        return (StatusCode::SERVICE_UNAVAILABLE, Json(json!({
            "error": "API token não configurado no servidor.",
            "hint": "Defina PIGE360_DEPLOYER_API_TOKEN ou desative PIGE360_DEPLOYER_API_REQUIRE_TOKEN apenas em ambiente local controlado."
        })))
        .into_response();
    }

    let header_name = match HeaderName::from_bytes(state.config.security.token_header.as_bytes()) {
        Ok(name) => name,
        Err(_) => {
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({
                    "error": "Nome do header de token inválido na configuração da API interna."
                })),
            )
                .into_response();
        }
    };

    let query_token = request.uri().query().and_then(|query| {
        query.split('&').find_map(|pair| {
            let mut parts = pair.splitn(2, '=');
            let key = parts.next().unwrap_or_default();
            let value = parts.next().unwrap_or_default();
            if matches!(key, "token" | "api_token" | "x-app-token") {
                Some(value.trim().to_string())
            } else {
                None
            }
        })
    });
    let header_token = request
        .headers()
        .get(header_name)
        .and_then(|value| value.to_str().ok())
        .unwrap_or_default()
        .trim()
        .to_string();
    let received = if header_token.is_empty() {
        query_token.unwrap_or_default()
    } else {
        header_token
    };

    if received != configured_token {
        eprintln!("Scalar/API bloqueado por autenticação");
        return (
            StatusCode::UNAUTHORIZED,
            Json(json!({ "error": "Token da API interna inválido ou ausente." })),
        )
            .into_response();
    }

    next.run(request).await
}

async fn root(State(state): State<InternalApiState>) -> impl IntoResponse {
    if state.config.expose_docs {
        Redirect::temporary(&state.config.docs.path).into_response()
    } else {
        Json(json!({
            "ok": true,
            "service": "internal-api",
            "version": env!("CARGO_PKG_VERSION"),
            "health": "/health"
        }))
        .into_response()
    }
}

async fn health(State(state): State<InternalApiState>) -> Json<Value> {
    let database_ok = open_connection(&state.db_path).is_ok();
    Json(json!({
        "ok": true,
        "database": database_ok,
        "version": env!("CARGO_PKG_VERSION"),
        "docs_exposed": state.config.expose_docs,
        "token_required": state.config.security.require_token,
        "bind_host": state.config.security.bind_host,
    }))
}

async fn version() -> Json<Value> {
    Json(
        json!({ "version": env!("CARGO_PKG_VERSION"), "build": option_env!("BUILD_HASH").unwrap_or("dev") }),
    )
}

async fn status(State(state): State<InternalApiState>) -> Json<Value> {
    Json(json!({
        "runtime": "headless-api",
        "host": state.host,
        "port": state.port,
        "started_at": state.started_at,
        "database_path": state.db_path.to_string_lossy(),
        "data_dir": state.data_dir.to_string_lossy(),
        "security": {
            "require_token": state.config.security.require_token,
            "token_header": state.config.security.token_header,
            "allow_public_network": state.config.security.allow_public_network,
            "cors_enabled": state.config.security.cors_enabled,
            "expose_docs": state.config.expose_docs,
            "docs_public": state.config.security.docs_public
        }
    }))
}

async fn app_meta() -> Json<Value> {
    Json(json!({
        "name": runtime_app_name(),
        "identifier": runtime_app_identifier(),
        "version": env!("CARGO_PKG_VERSION"),
        "environment": option_env!("APP_ENV").unwrap_or("production")
    }))
}

async fn features(State(state): State<InternalApiState>) -> Json<Value> {
    Json(json!({
        "licensing": false,
        "logs": true,
        "systemSettings": true,
        "internalApi": true,
        "scalarDocs": state.config.expose_docs,
        "integrations": true,
        "tray": true,
        "windowsService": cfg!(target_os = "windows"),
        "linuxService": cfg!(target_os = "linux"),
        "mysql": cfg!(feature = "mysql-db"),
        "postgres": cfg!(feature = "postgres-db"),
        "firebird": false,
        "headlessMode": true
    }))
}

async fn logs(State(state): State<InternalApiState>) -> Json<Value> {
    let result = open_connection(&state.db_path).and_then(|conn| {
        let mut stmt = conn
            .prepare("SELECT id, level, category, message, source, route, created_at FROM app_logs ORDER BY id DESC LIMIT 100")
            .map_err(|err| err.to_string())?;
        let rows = stmt
            .query_map([], |row| {
                Ok(json!({
                    "id": row.get::<_, i64>(0)?,
                    "level": row.get::<_, String>(1)?,
                    "category": row.get::<_, String>(2)?,
                    "message": row.get::<_, String>(3)?,
                    "source": row.get::<_, Option<String>>(4)?,
                    "route": row.get::<_, Option<String>>(5)?,
                    "created_at": row.get::<_, String>(6)?,
                }))
            })
            .map_err(|err| err.to_string())?;
        let mut items = Vec::new();
        for row in rows {
            items.push(row.map_err(|err| err.to_string())?);
        }
        Ok(items)
    });
    Json(json!({ "items": result.unwrap_or_default() }))
}

async fn openapi(State(state): State<InternalApiState>) -> Json<Value> {
    Json(docs::openapi_json(
        &state.config.security.token_header,
        state.config.security.require_token,
        &state.config.docs.path,
    ))
}

async fn scalar_docs(State(_state): State<InternalApiState>, uri: Uri) -> impl IntoResponse {
    eprintln!("Scalar acessado");
    let token = uri.query().and_then(|query| {
        query.split('&').find_map(|pair| {
            let mut parts = pair.splitn(2, '=');
            let key = parts.next().unwrap_or_default();
            let value = parts.next().unwrap_or_default();
            if matches!(key, "token" | "api_token" | "x-app-token") {
                Some(value.to_string())
            } else {
                None
            }
        })
    });
    Html(docs::scalar_html(uri.path(), token.as_deref()))
}
