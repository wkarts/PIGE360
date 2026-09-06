import { defineStore } from "pinia";
import { invokeCommand } from "../services/tauri";
import { logAppError, logAppInfo, logAppWarning } from "../services/logger";
import { storageKey } from "../config/appBranding";

export interface AuthUser {
  id: number;
  nome: string;
  login: string;
  email?: string | null;
  telefone?: string | null;
  cargo?: string | null;
  administrador: boolean;
  master_user: boolean;
  senha_provisoria: boolean;
  permission_keys: string[];
  profile_names: string[];
  company_ids: number[];
  company_names: string[];
  photo_url?: string | null;
}

interface LoginResponse {
  success: boolean;
  message: string;
  session_token?: string | null;
  user?: AuthUser;
}

const STORAGE_KEY = storageKey("session");
const ACTIVE_COMPANY_KEY = storageKey("active-company");

function sessionStore() {
  if (typeof window === "undefined") return null;
  return window.sessionStorage;
}

function readStorage(): string | null {
  return sessionStore()?.getItem(STORAGE_KEY) ?? null;
}

function writeStorage(value: string | null) {
  const store = sessionStore();
  if (!store) return;
  if (!value) {
    store.removeItem(STORAGE_KEY);
    return;
  }
  store.setItem(STORAGE_KEY, value);
}

function readActiveCompany(): number | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(ACTIVE_COMPANY_KEY);
  if (!raw) return null;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : null;
}

function writeActiveCompany(value: number | null) {
  if (typeof window === "undefined") return;
  if (value == null) {
    window.localStorage.removeItem(ACTIVE_COMPANY_KEY);
    return;
  }
  window.localStorage.setItem(ACTIVE_COMPANY_KEY, String(value));
}

export const useSessionStore = defineStore("session", {
  state: () => ({
    user: null as AuthUser | null,
    sessionToken: readStorage() as string | null,
    activeCompanyId: readActiveCompany() as number | null,
    loading: false,
    restoring: false,
    initialized: false,
    lastError: "",
  }),
  getters: {
    isAuthenticated: (state) => Boolean(state.user && state.sessionToken),
    isMaster: (state) => Boolean(state.user?.master_user),
    permissionKeys: (state) => state.user?.permission_keys || [],
    activeCompanyName(state): string {
      const user = state.user;
      if (!user || state.activeCompanyId == null) return "Todas as empresas";
      const index = user.company_ids.findIndex((id) => id === state.activeCompanyId);
      return index >= 0 ? user.company_names[index] : "Empresa ativa";
    }
  },
  actions: {
    clearAuthState() {
      this.user = null;
      this.sessionToken = null;
      this.activeCompanyId = null;
      this.lastError = "";
      writeStorage(null);
      writeActiveCompany(null);
    },
    can(permission: string) {
      if (!permission) return true;
      if (this.user?.master_user) return true;
      return this.permissionKeys.includes(permission);
    },
    ensureActiveCompany() {
      if (!this.user) {
        this.activeCompanyId = null;
        writeActiveCompany(null);
        return;
      }
      const available = this.user.company_ids || [];
      if (!available.length) {
        this.activeCompanyId = null;
        writeActiveCompany(null);
        return;
      }
      if (this.activeCompanyId && available.includes(this.activeCompanyId)) {
        writeActiveCompany(this.activeCompanyId);
        return;
      }
      this.activeCompanyId = available[0];
      writeActiveCompany(this.activeCompanyId);
    },
    setActiveCompany(companyId: number | null) {
      if (!this.user) {
        this.activeCompanyId = null;
        writeActiveCompany(null);
        return;
      }
      if (companyId == null) {
        this.activeCompanyId = null;
        writeActiveCompany(null);
        logAppInfo("tenant", "Empresa ativa redefinida para contexto geral.");
        return;
      }
      if (!this.user.master_user && !this.user.company_ids.includes(companyId)) {
        logAppWarning("tenant", "Tentativa de selecionar empresa sem vínculo.", { companyId });
        return;
      }
      this.activeCompanyId = companyId;
      writeActiveCompany(companyId);
      logAppInfo("tenant", "Empresa ativa alterada.", { companyId });
    },
    async login(login: string, senha: string) {
      this.loading = true;
      this.lastError = "";
      try {
        const response = await invokeCommand<LoginResponse>("auth_login", { login, senha });
        if (!response.success || !response.user || !response.session_token) {
          throw new Error(response.message || "Falha ao autenticar.");
        }
        this.user = response.user;
        this.sessionToken = response.session_token;
        writeStorage(response.session_token);
        this.ensureActiveCompany();
        this.initialized = true;
        logAppInfo("auth", "Login concluído no frontend.", { usuario: response.user.login });
        return response;
      } catch (error) {
        this.lastError = error instanceof Error ? error.message : "Falha ao autenticar.";
        logAppError("auth", "Erro durante login no frontend.", { error: this.lastError, login });
        throw error;
      } finally {
        this.loading = false;
      }
    },
    async restore() {
      if (this.initialized || this.restoring) return;
      this.restoring = true;
      this.lastError = "";
      try {
        if (!this.sessionToken) {
          this.user = null;
          return;
        }
        const response = await invokeCommand<LoginResponse>("auth_restore", {
          session_token: this.sessionToken
        });
        if (!response.success || !response.user || !response.session_token) {
          logAppWarning("session", "Sessão não pôde ser restaurada; limpeza do estado local.");
          this.clearAuthState();
          return;
        }
        this.user = response.user;
        this.sessionToken = response.session_token;
        writeStorage(response.session_token);
        this.ensureActiveCompany();
        logAppInfo("session", "Sessão restaurada com sucesso no frontend.", {
          usuario: response.user.login,
        });
      } catch (error) {
        this.lastError = error instanceof Error ? error.message : "Falha ao restaurar sessão.";
        this.clearAuthState();
        logAppError("session", "Erro ao restaurar sessão no frontend.", {
          error: this.lastError,
        });
      } finally {
        this.initialized = true;
        this.restoring = false;
      }
    },
    async validateCurrentSession() {
      if (!this.sessionToken) return false;
      try {
        const response = await invokeCommand<LoginResponse>("auth_restore", {
          session_token: this.sessionToken,
        });
        if (!response.success || !response.user || !response.session_token) {
          logAppWarning("session", "Sessão expirada ou derrubada por novo login.");
          this.clearAuthState();
          return false;
        }
        this.user = response.user;
        this.sessionToken = response.session_token;
        writeStorage(response.session_token);
        this.ensureActiveCompany();
        return true;
      } catch (error) {
        this.lastError = error instanceof Error ? error.message : "Sessão inválida ou expirada.";
        logAppWarning("session", "Sessão invalidada durante monitoramento ativo.", { error: this.lastError });
        this.clearAuthState();
        return false;
      }
    },
    async changePassword(currentPassword: string, newPassword: string) {
      if (!this.sessionToken) throw new Error("Sessão não encontrada.");
      this.loading = true;
      this.lastError = "";
      try {
        await invokeCommand<boolean>("auth_change_password", {
          session_token: this.sessionToken,
          current_password: currentPassword,
          new_password: newPassword,
        });
        if (this.user) this.user.senha_provisoria = false;
        logAppInfo("auth", "Senha inicial alterada e acesso definitivo liberado.");
      } catch (error) {
        this.lastError = error instanceof Error ? error.message : "Falha ao alterar senha.";
        throw error;
      } finally {
        this.loading = false;
      }
    },
    async logout({ silent = false }: { silent?: boolean } = {}) {
      const currentToken = this.sessionToken;
      const currentUser = this.user?.login ?? null;
      this.clearAuthState();
      this.initialized = true;
      if (currentToken) {
        try {
          await invokeCommand<boolean>("auth_logout", { session_token: currentToken });
        } catch (error) {
          if (!silent) {
            logAppWarning("session", "Falha ao encerrar sessão no backend durante logout.", {
              error: error instanceof Error ? error.message : String(error),
            });
          }
        }
      }
      if (!silent) {
        logAppInfo("session", "Logout executado no frontend.", { usuario: currentUser });
      }
    }
  }
});
