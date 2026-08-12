import { isTauriRuntime, type RuntimeAppManifest } from "@pige360/app-manifest";

export type AuthTokens = {
  token_type: string;
  access_token: string;
  expires_in: number;
  refresh_token: string;
  refresh_expires_at: string;
};

export type AccessClaims = {
  sub: string;
  tid: string | null;
  email: string;
  roles: string[];
  plane: "platform" | "tenant";
  exp: number;
  iat: number;
};

const WEB_KEY = "pige360.session.v1";

function invoke<T>(command: string, args?: Record<string, unknown>): Promise<T> {
  const fn = window.__TAURI__?.core?.invoke;
  if (typeof fn !== "function") return Promise.reject(new Error("Bridge Tauri indisponível"));
  return fn<T>(command, args);
}

function decodeSegment(value: string): string {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
  return decodeURIComponent(Array.from(atob(padded), c => `%${c.charCodeAt(0).toString(16).padStart(2, "0")}`).join(""));
}

/** Decodifica claims somente para contexto local. A autorização continua sendo validada pelo backend. */
export function accessClaims(token: string): AccessClaims {
  const parts = token.split(".");
  const segment = parts[1];
  if (!segment) throw new Error("Access token malformado");
  const raw = JSON.parse(decodeSegment(segment)) as Partial<AccessClaims>;
  if (!raw.sub || !raw.email || !raw.plane || !raw.exp || !Array.isArray(raw.roles)) throw new Error("Claims obrigatórias ausentes");
  return raw as AccessClaims;
}

export async function saveSession(tokens: AuthTokens, manifest: RuntimeAppManifest | null): Promise<void> {
  if (isTauriRuntime()) {
    const claims = accessClaims(tokens.access_token);
    const tenantId = claims.tid ?? manifest?.tenant_id;
    if (!tenantId) throw new Error("Sessão nativa sem tenant fixado");
    if (manifest && manifest.tenant_id !== tenantId) throw new Error("Token pertence a outro tenant");
    await invoke<void>("secure_session_put", { tenantId, userId: claims.sub, value: JSON.stringify(tokens) });
    return;
  }
  sessionStorage.setItem(WEB_KEY, JSON.stringify(tokens));
}

export async function loadSession(manifest: RuntimeAppManifest | null): Promise<AuthTokens | null> {
  if (isTauriRuntime()) {
    if (!manifest?.tenant_id) return null;
    const raw = await invoke<string | null>("secure_session_get", { tenantId: manifest.tenant_id });
    if (!raw) return null;
    const tokens = JSON.parse(raw) as AuthTokens;
    const claims = accessClaims(tokens.access_token);
    if (claims.tid !== manifest.tenant_id) {
      await invoke<void>("secure_session_delete", { tenantId: manifest.tenant_id });
      throw new Error("Sessão nativa rejeitada: tenant divergente");
    }
    return tokens;
  }
  const raw = sessionStorage.getItem(WEB_KEY);
  return raw ? JSON.parse(raw) as AuthTokens : null;
}

export async function clearSession(manifest: RuntimeAppManifest | null): Promise<void> {
  if (isTauriRuntime()) {
    if (manifest?.tenant_id) await invoke<void>("secure_session_delete", { tenantId: manifest.tenant_id });
    return;
  }
  sessionStorage.removeItem(WEB_KEY);
}

export function sessionExpired(tokens: AuthTokens, skewSeconds = 30): boolean {
  return accessClaims(tokens.access_token).exp <= Math.floor(Date.now() / 1000) + skewSeconds;
}

export type ApiProblem = { code?: string; title?: string; detail?: string; correlation_id?: string; errors?: Array<{ field:string; code:string; message:string }> };

export class Pige360SessionClient {
  manifest: RuntimeAppManifest | null = null;
  tokens: AuthTokens | null = null;
  readonly basePath: string;

  constructor(basePath = "/api/v1") { this.basePath = basePath.replace(/\/$/, ""); }

  async initialize(): Promise<void> {
    const { loadRuntimeManifest } = await import("@pige360/app-manifest");
    this.manifest = await loadRuntimeManifest();
    this.tokens = await loadSession(this.manifest);
  }

  url(path: string): string {
    if (!path.startsWith("/")) throw new Error("Path da API inválido");
    const base = this.manifest?.api_url?.replace(/\/$/, "") ?? "";
    return `${base}${this.basePath}${path}`;
  }

  async login(email: string, password: string): Promise<AuthTokens> {
    const response = await fetch(this.url("/auth/login"), {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!response.ok) throw await apiError(response);
    const tokens = await response.json() as AuthTokens;
    if (this.manifest) {
      const claims = accessClaims(tokens.access_token);
      if (claims.tid !== this.manifest.tenant_id) throw new Error("Login rejeitado: token pertence a outro tenant");
    }
    this.tokens = tokens;
    await saveSession(tokens, this.manifest);
    return tokens;
  }

  async logout(): Promise<void> {
    this.tokens = null;
    await clearSession(this.manifest);
  }

  async refresh(): Promise<boolean> {
    if (!this.tokens?.refresh_token) return false;
    const response = await fetch(this.url("/auth/refresh"), {
      method: "POST", headers: { "Content-Type": "application/json", "Accept":"application/json" },
      body: JSON.stringify({ refresh_token: this.tokens.refresh_token }),
    });
    if (!response.ok) { await this.logout(); return false; }
    const tokens = await response.json() as AuthTokens;
    this.tokens = tokens;
    await saveSession(tokens, this.manifest);
    return true;
  }

  async response(path: string, init: RequestInit = {}, retry = true): Promise<Response> {
    if (this.tokens && sessionExpired(this.tokens) && !(await this.refresh())) throw new Error("Sessão expirada");
    const headers = new Headers(init.headers);
    headers.set("Accept", headers.get("Accept") ?? "application/json");
    if (this.tokens) headers.set("Authorization", `Bearer ${this.tokens.access_token}`);
    const response = await fetch(this.url(path), { ...init, headers });
    if (response.status === 401 && retry && this.tokens && await this.refresh()) return this.response(path, init, false);
    if (!response.ok) throw await apiError(response);
    return response;
  }

  async request<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
    const response = await this.response(path, init, retry);
    if (response.status === 204) return undefined as T;
    const type = response.headers.get("content-type") ?? "";
    return (type.includes("json") ? await response.json() : await response.text()) as T;
  }

  claims(): AccessClaims | null { return this.tokens ? accessClaims(this.tokens.access_token) : null; }
}

async function apiError(response: Response): Promise<Error & { status:number; problem?:ApiProblem }> {
  const type = response.headers.get("content-type") ?? "";
  const body = type.includes("json") ? await response.json() as ApiProblem : { detail: await response.text() };
  const error = new Error(body.detail || body.title || `Erro HTTP ${response.status}`) as Error & { status:number; problem?:ApiProblem };
  error.status = response.status; error.problem = body; return error;
}
