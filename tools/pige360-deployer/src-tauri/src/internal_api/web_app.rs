use std::{
    env, fs,
    path::{Component, Path, PathBuf},
    sync::OnceLock,
};

use axum::{
    extract::Path as AxumPath,
    http::{header, HeaderValue, StatusCode},
    response::{Html, IntoResponse, Response},
};

static DIST_DIR_CACHE: OnceLock<Option<PathBuf>> = OnceLock::new();

pub async fn web_index() -> Response {
    index_response("")
}

pub async fn web_asset(AxumPath(path): AxumPath<String>) -> Response {
    asset_response(path, "")
}

pub async fn root_assets(AxumPath(path): AxumPath<String>) -> Response {
    asset_response(format!("assets/{path}"), "")
}

pub async fn root_branding(AxumPath(path): AxumPath<String>) -> Response {
    asset_response(format!("branding/{path}"), "")
}

pub async fn root_icons(AxumPath(path): AxumPath<String>) -> Response {
    asset_response(format!("icons/{path}"), "")
}

pub async fn manifest() -> Response {
    asset_response("manifest.webmanifest".to_string(), "")
}

pub async fn disabled_service_worker() -> Response {
    let script = r#"self.addEventListener('install', event => { self.skipWaiting(); });
self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    if (self.registration) await self.registration.unregister();
    if (self.caches) {
      const keys = await caches.keys();
      await Promise.all(keys.map(key => caches.delete(key)));
    }
    const clientsList = await clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const client of clientsList) client.navigate(client.url);
  })());
});
self.addEventListener('fetch', () => {});
"#;
    let mut response = script.into_response();
    response.headers_mut().insert(
        header::CONTENT_TYPE,
        HeaderValue::from_static("application/javascript; charset=utf-8"),
    );
    response.headers_mut().insert(
        header::CACHE_CONTROL,
        HeaderValue::from_static("no-store, no-cache, must-revalidate"),
    );
    response
}

fn index_response(mount_path: &str) -> Response {
    let Some(dist_dir) = dist_dir() else {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Html(render_not_available(mount_path)),
        )
            .into_response();
    };

    let index_path = dist_dir.join("index.html");
    let Ok(html) = fs::read_to_string(&index_path) else {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Html(render_not_available(mount_path)),
        )
            .into_response();
    };

    let mut response = Html(rewrite_index_html(&html, mount_path)).into_response();
    response.headers_mut().insert(
        header::CACHE_CONTROL,
        HeaderValue::from_static("no-store, no-cache, must-revalidate"),
    );
    response
}

fn asset_response(path: String, mount_path: &str) -> Response {
    let Some(dist_dir) = dist_dir() else {
        return index_response(mount_path);
    };

    let Some(relative_path) = normalize_asset_path(&path) else {
        return (StatusCode::BAD_REQUEST, "Caminho de asset inválido.").into_response();
    };

    if relative_path.as_os_str().is_empty() || relative_path == Path::new("index.html") {
        return index_response(mount_path);
    }

    let asset_path = dist_dir.join(&relative_path);
    if !is_inside(&asset_path, &dist_dir) || !asset_path.is_file() {
        return index_response(mount_path);
    }

    let Ok(bytes) = fs::read(&asset_path) else {
        return (StatusCode::NOT_FOUND, "Asset não encontrado.").into_response();
    };

    let mut response = bytes.into_response();
    response.headers_mut().insert(
        header::CONTENT_TYPE,
        HeaderValue::from_static(content_type_for(&relative_path)),
    );
    let cache_control = if relative_path.starts_with("assets") {
        "public, max-age=31536000, immutable"
    } else {
        "public, max-age=3600"
    };
    response.headers_mut().insert(
        header::CACHE_CONTROL,
        HeaderValue::from_static(cache_control),
    );
    response
}

fn dist_dir() -> Option<PathBuf> {
    DIST_DIR_CACHE.get_or_init(resolve_dist_dir).clone()
}

fn resolve_dist_dir() -> Option<PathBuf> {
    let mut candidates: Vec<PathBuf> = Vec::new();

    if let Ok(value) = env::var("PIGE360_DEPLOYER_WEB_DIST_DIR") {
        let trimmed = value.trim();
        if !trimmed.is_empty() {
            candidates.push(PathBuf::from(trimmed));
        }
    }

    if let Ok(current_dir) = env::current_dir() {
        candidates.push(current_dir.join("dist"));
        candidates.push(current_dir.join("src-tauri/dist"));
        candidates.push(current_dir.join("../dist"));
        candidates.push(current_dir.join("../../dist"));
    }

    if let Ok(exe_path) = env::current_exe() {
        if let Some(exe_dir) = exe_path.parent() {
            candidates.push(exe_dir.join("dist"));
            candidates.push(exe_dir.join("resources/dist"));
            candidates.push(exe_dir.join("../dist"));
            candidates.push(exe_dir.join("../Resources/dist"));
            candidates.push(exe_dir.join("../share/pige360-deployer/dist"));
        }
    }

    candidates.push(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("dist"));
    candidates.push(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../dist"));

    candidates
        .into_iter()
        .filter_map(|candidate| candidate.canonicalize().ok())
        .find(|candidate| candidate.join("index.html").is_file())
}

fn normalize_asset_path(path: &str) -> Option<PathBuf> {
    let trimmed = path.trim_start_matches('/').replace('\\', "/");
    let mut output = PathBuf::new();
    for component in Path::new(&trimmed).components() {
        match component {
            Component::Normal(value) => output.push(value),
            Component::CurDir => {}
            Component::Prefix(_) | Component::RootDir | Component::ParentDir => return None,
        }
    }
    Some(output)
}

fn is_inside(path: &Path, root: &Path) -> bool {
    let Ok(path) = path.canonicalize() else {
        return false;
    };
    let Ok(root) = root.canonicalize() else {
        return false;
    };
    path.starts_with(root)
}

fn rewrite_index_html(html: &str, mount_path: &str) -> String {
    let base = if mount_path.is_empty() {
        "/".to_string()
    } else {
        format!("{mount_path}/")
    };
    let runtime_script = r#"<script>
window.PIGE360_DEPLOYER_WEB_RUNTIME = true;
window.PIGE360_DEPLOYER_INTERNAL_API_WEB_RUNTIME = true;
window.PIGE360_DEPLOYER_COMMAND_PROXY_BASE = '/__internal_api';
</script>"#;

    let mut output = html
        .replace("href=\"/", &format!("href=\"{mount_path}/"))
        .replace("src=\"/", &format!("src=\"{mount_path}/"))
        .replace("href='/", &format!("href='{mount_path}/"))
        .replace("src='/", &format!("src='{mount_path}/"))
        .replace("url(/", &format!("url({mount_path}/"));
    if !output.contains("<base ") {
        output = output.replace("<head>", &format!("<head>\n    <base href=\"{base}\" />"));
    }
    if !output.contains("PIGE360_DEPLOYER_INTERNAL_API_WEB_RUNTIME") {
        if output.contains("</head>") {
            output = output.replace("</head>", &format!("    {runtime_script}\n</head>"));
        } else {
            output = format!("{runtime_script}\n{output}");
        }
    }
    output
}

fn content_type_for(path: &Path) -> &'static str {
    match path
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase()
        .as_str()
    {
        "html" => "text/html; charset=utf-8",
        "js" | "mjs" => "application/javascript; charset=utf-8",
        "css" => "text/css; charset=utf-8",
        "json" | "webmanifest" => "application/json; charset=utf-8",
        "svg" => "image/svg+xml",
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        "gif" => "image/gif",
        "ico" => "image/x-icon",
        "wasm" => "application/wasm",
        "txt" => "text/plain; charset=utf-8",
        "woff" => "font/woff",
        "woff2" => "font/woff2",
        "ttf" => "font/ttf",
        _ => "application/octet-stream",
    }
}

fn render_not_available(mount_path: &str) -> String {
    format!(
        r#"<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PIGE360 Deployer</title>
  <style>
    body{{font-family:Inter,Segoe UI,Arial,sans-serif;background:#f8fafc;color:#172033;margin:0}}
    main{{max-width:860px;margin:80px auto;padding:24px}}
    .card{{background:white;border:1px solid #dbe4f0;border-radius:18px;padding:28px;box-shadow:0 12px 34px rgba(15,23,42,.08)}}
    code{{background:#eef2ff;border-radius:8px;padding:2px 7px}}
  </style>
</head>
<body>
  <main><section class="card">
    <h1>Aplicação web não encontrada</h1>
    <p>O endpoint <code>{}</code> publica a mesma interface web gerada pelo Vite, sem incorporar os arquivos no binário.</p>
    <p>Execute <code>npm run build:web</code> antes do build Tauri, ou defina <code>PIGE360_DEPLOYER_WEB_DIST_DIR</code> apontando para a pasta <code>dist</code>.</p>
  </section></main>
</body>
</html>"#,
        mount_path
    )
}
