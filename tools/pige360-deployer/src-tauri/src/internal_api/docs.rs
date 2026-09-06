pub fn scalar_html(docs_path: &str, token: Option<&str>) -> String {
    let openapi_path = if docs_path.starts_with("/__internal_api") {
        "/__internal_api/openapi.json"
    } else {
        "/openapi.json"
    };
    let openapi_url = token
        .map(|value| format!("{}?token={}", openapi_path, value))
        .unwrap_or_else(|| openapi_path.to_string());
    format!(
        r#"<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>PIGE360 Deployer API Docs</title>
  <style>
    :root {{ color-scheme: light only; }}
    html, body {{ margin:0; min-height:100%; background:#ffffff !important; color:#172033 !important; }}
    body {{ font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }}
    scalar-api-reference {{
      --scalar-background-1:#ffffff !important;
      --scalar-background-2:#f8fafc !important;
      --scalar-background-3:#eef2f7 !important;
      --scalar-color-1:#172033 !important;
      --scalar-color-2:#475569 !important;
      --scalar-color-3:#64748b !important;
      color-scheme: light only !important;
    }}
  </style>
</head>
<body>
  <script id="api-reference" data-url="{openapi_url}" data-theme="default"></script>
  <script src="https://cdn.jsdelivr.net/npm/@scalar/api-reference"></script>
</body>
</html>"#
    )
}

pub fn openapi_json(token_header: &str, require_token: bool, docs_path: &str) -> serde_json::Value {
    let protected_security = if require_token {
        serde_json::json!([{ "LocalToken": [] }])
    } else {
        serde_json::json!([])
    };
    serde_json::json!({
        "openapi": "3.0.3",
        "info": { "title": "PIGE360 Deployer Internal API", "version": env!("CARGO_PKG_VERSION") },
        "components": {
            "securitySchemes": {
                "LocalToken": {
                    "type": "apiKey",
                    "in": "header",
                    "name": token_header
                }
            }
        },
        "paths": {
            "/health": { "get": { "summary": "Health check público/local", "responses": { "200": { "description": "OK" } } } },
            "/version": { "get": { "security": protected_security.clone(), "summary": "Versão da aplicação", "responses": { "200": { "description": "OK" }, "401": { "description": "Token inválido" } } } },
            "/status": { "get": { "security": protected_security.clone(), "summary": "Status operacional", "responses": { "200": { "description": "OK" } } } },
            "/app/meta": { "get": { "security": protected_security.clone(), "summary": "Metadados da aplicação", "responses": { "200": { "description": "OK" } } } },
            "/features": { "get": { "security": protected_security.clone(), "summary": "Feature flags", "responses": { "200": { "description": "OK" } } } },
            "/logs": { "get": { "security": protected_security.clone(), "summary": "Últimos logs", "responses": { "200": { "description": "OK" } } } },
            "/openapi.json": { "get": { "summary": "OpenAPI", "responses": { "200": { "description": "JSON" } } } },
            docs_path: { "get": { "summary": "Documentação Scalar em tema claro fixo", "responses": { "200": { "description": "HTML" } } } }
        }
    })
}
