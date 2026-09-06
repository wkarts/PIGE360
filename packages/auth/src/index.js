import { isTauriRuntime } from "@pige360/app-manifest";
const WEB_KEY = "pige360.session.v1";
function invoke(command, args) {
    const fn = window.__TAURI__?.core?.invoke;
    if (typeof fn !== "function")
        return Promise.reject(new Error("Bridge Tauri indisponível"));
    return fn(command, args);
}
function decodeSegment(value) {
    const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
    return decodeURIComponent(Array.from(atob(padded), c => `%${c.charCodeAt(0).toString(16).padStart(2, "0")}`).join(""));
}
/** Decodifica claims somente para contexto local. A autorização continua sendo validada pelo backend. */
export function accessClaims(token) {
    const parts = token.split(".");
    const segment = parts[1];
    if (!segment)
        throw new Error("Access token malformado");
    const raw = JSON.parse(decodeSegment(segment));
    if (!raw.sub || !raw.email || !raw.plane || !raw.exp || !Array.isArray(raw.roles))
        throw new Error("Claims obrigatórias ausentes");
    return raw;
}
export async function saveSession(tokens, manifest) {
    if (isTauriRuntime()) {
        const claims = accessClaims(tokens.access_token);
        const tenantId = claims.tid ?? manifest?.tenant_id;
        if (!tenantId)
            throw new Error("Sessão nativa sem tenant fixado");
        if (manifest && manifest.tenant_id !== tenantId)
            throw new Error("Token pertence a outro tenant");
        await invoke("secure_session_put", { tenantId, userId: claims.sub, value: JSON.stringify(tokens) });
        return;
    }
    sessionStorage.setItem(WEB_KEY, JSON.stringify(tokens));
}
export async function loadSession(manifest) {
    if (isTauriRuntime()) {
        if (!manifest?.tenant_id)
            return null;
        const raw = await invoke("secure_session_get", { tenantId: manifest.tenant_id });
        if (!raw)
            return null;
        const tokens = JSON.parse(raw);
        const claims = accessClaims(tokens.access_token);
        if (claims.tid !== manifest.tenant_id) {
            await invoke("secure_session_delete", { tenantId: manifest.tenant_id });
            throw new Error("Sessão nativa rejeitada: tenant divergente");
        }
        return tokens;
    }
    const raw = sessionStorage.getItem(WEB_KEY);
    return raw ? JSON.parse(raw) : null;
}
export async function clearSession(manifest) {
    if (isTauriRuntime()) {
        if (manifest?.tenant_id)
            await invoke("secure_session_delete", { tenantId: manifest.tenant_id });
        return;
    }
    sessionStorage.removeItem(WEB_KEY);
}
export function sessionExpired(tokens, skewSeconds = 30) {
    return accessClaims(tokens.access_token).exp <= Math.floor(Date.now() / 1000) + skewSeconds;
}
export class Pige360SessionClient {
    manifest = null;
    tokens = null;
    basePath;
    constructor(basePath = "/api/v1") { this.basePath = basePath.replace(/\/$/, ""); }
    async initialize() {
        const { loadRuntimeManifest } = await import("@pige360/app-manifest");
        this.manifest = await loadRuntimeManifest();
        this.tokens = await loadSession(this.manifest);
    }
    url(path) {
        if (!path.startsWith("/"))
            throw new Error("Path da API inválido");
        const base = this.manifest?.api_url?.replace(/\/$/, "") ?? "";
        return `${base}${this.basePath}${path}`;
    }
    async login(email, password) {
        const response = await fetch(this.url("/auth/login"), {
            method: "POST",
            headers: { "Content-Type": "application/json", "Accept": "application/json" },
            body: JSON.stringify({ email, password }),
        });
        if (!response.ok)
            throw await apiError(response);
        const tokens = await response.json();
        if (this.manifest) {
            const claims = accessClaims(tokens.access_token);
            if (claims.tid !== this.manifest.tenant_id)
                throw new Error("Login rejeitado: token pertence a outro tenant");
        }
        this.tokens = tokens;
        await saveSession(tokens, this.manifest);
        return tokens;
    }
    async logout() {
        const tokens = this.tokens;
        try {
            if (tokens?.access_token) {
                await fetch(this.url("/auth/logout"), {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "Authorization": `Bearer ${tokens.access_token}`,
                    },
                    body: JSON.stringify({ refresh_token: tokens.refresh_token }),
                });
            }
        }
        catch {
            // A indisponibilidade da API não pode manter credenciais no dispositivo.
        }
        finally {
            this.tokens = null;
            await clearSession(this.manifest);
        }
    }
    async refresh() {
        if (!this.tokens?.refresh_token)
            return false;
        const response = await fetch(this.url("/auth/refresh"), {
            method: "POST", headers: { "Content-Type": "application/json", "Accept": "application/json" },
            body: JSON.stringify({ refresh_token: this.tokens.refresh_token }),
        });
        if (!response.ok) {
            await this.logout();
            return false;
        }
        const tokens = await response.json();
        this.tokens = tokens;
        await saveSession(tokens, this.manifest);
        return true;
    }
    async response(path, init = {}, retry = true) {
        if (this.tokens && sessionExpired(this.tokens) && !(await this.refresh()))
            throw new Error("Sessão expirada");
        const headers = new Headers(init.headers);
        headers.set("Accept", headers.get("Accept") ?? "application/json");
        if (this.tokens)
            headers.set("Authorization", `Bearer ${this.tokens.access_token}`);
        const response = await fetch(this.url(path), { ...init, headers });
        if (response.status === 401 && retry && this.tokens && await this.refresh())
            return this.response(path, init, false);
        if (!response.ok)
            throw await apiError(response);
        return response;
    }
    async request(path, init = {}, retry = true) {
        const response = await this.response(path, init, retry);
        if (response.status === 204)
            return undefined;
        const type = response.headers.get("content-type") ?? "";
        return (type.includes("json") ? await response.json() : await response.text());
    }
    claims() { return this.tokens ? accessClaims(this.tokens.access_token) : null; }
}
async function apiError(response) {
    const type = response.headers.get("content-type") ?? "";
    const body = type.includes("json") ? await response.json() : { detail: await response.text() };
    const error = new Error(body.detail || body.title || `Erro HTTP ${response.status}`);
    error.status = response.status;
    error.problem = body;
    return error;
}
