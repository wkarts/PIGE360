export function isTauriRuntime() {
    return typeof window !== "undefined" && typeof window.__TAURI__?.core?.invoke === "function";
}
function validateUrl(value, allowedHosts, field) {
    const url = new URL(value);
    const local = url.hostname === "localhost" || url.hostname.endsWith(".localhost") || url.hostname === "127.0.0.1";
    if (url.protocol !== "https:" && !local)
        throw new Error(`${field}: HTTPS obrigatório`);
    if (!allowedHosts.has(url.hostname))
        throw new Error(`${field}: hostname fora da allowlist`);
    return url;
}
export function validateRuntimeManifest(input) {
    if (input.schema_version !== 1)
        throw new Error("Manifesto runtime incompatível");
    if (!input.tenant_id || !input.tenant_code || !input.app_product || !input.identifier)
        throw new Error("Manifesto runtime incompleto");
    const allowed = new Set(input.allowed_hosts.filter(Boolean));
    if (allowed.size === 0)
        throw new Error("Manifesto runtime sem hosts permitidos");
    validateUrl(input.api_url, allowed, "api_url");
    validateUrl(input.web_url, allowed, "web_url");
    validateUrl(input.update_url, allowed, "update_url");
    return Object.freeze({ ...input, allowed_hosts: Object.freeze([...allowed]) });
}
export async function loadRuntimeManifest() {
    if (typeof window === "undefined")
        return null;
    if (window.__PIGE360_RUNTIME_MANIFEST__)
        return validateRuntimeManifest(window.__PIGE360_RUNTIME_MANIFEST__);
    try {
        const response = await fetch("/tenant-app-manifest.json", { cache: "no-store", credentials: "same-origin" });
        if (response.ok)
            return validateRuntimeManifest(await response.json());
    }
    catch {
        // O PWA genérico pode operar same-origin sem manifesto de build dedicado.
    }
    if (isTauriRuntime())
        throw new Error("Aplicativo nativo sem manifesto de tenant assinado/configurado");
    return null;
}
export function apiBaseUrl(manifest) {
    if (manifest)
        return manifest.api_url.replace(/\/$/, "");
    return "";
}
export function apiUrl(manifest, path) {
    if (!path.startsWith("/"))
        throw new Error("O path da API deve iniciar com /");
    return `${apiBaseUrl(manifest)}${path}`;
}
