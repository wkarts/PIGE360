import { projectConfig } from "../../config/projectConfig";
import { storageKey } from "../../config/appBranding";
import { entityConfigs } from "../../config/entities";
import { useDatabaseProvider } from "../database/DatabaseProviderFactory";
import type { TableRecord } from "../database/DatabaseTypes";
import { getPlatformInfo } from "../runtime/RuntimeProvider";
import type { CommandArgs, CommandProvider } from "./CommandProvider";

interface LoginResponse {
  success: boolean;
  session_token?: string;
  user?: Record<string, unknown>;
  message?: string;
}

const SESSION_PREFIX = "web-session-";
const permissionCatalog = [
  { key: "dashboard:view", descricao: "Visualizar dashboard", module: "Dashboard" },
  { key: "empresas:view", descricao: "Visualizar empresas", module: "Empresas" },
  { key: "empresas:manage", descricao: "Gerenciar empresas", module: "Empresas" },
  { key: "usuarios:view", descricao: "Visualizar usuários", module: "Usuários" },
  { key: "usuarios:manage", descricao: "Gerenciar usuários", module: "Usuários" },
  { key: "perfis:view", descricao: "Visualizar perfis", module: "Perfis" },
  { key: "perfis:manage", descricao: "Gerenciar perfis", module: "Perfis" },
  { key: "cadastros:view", descricao: "Visualizar cadastros", module: "Cadastros" },
  { key: "config:view", descricao: "Visualizar configurações", module: "Configurações" },
];

function asRecord(value: unknown): Record<string, unknown> {
  return Object.prototype.toString.call(value) === "[object Object]" ? (value as Record<string, unknown>) : {};
}

function getString(args: CommandArgs, key: string, fallback = ""): string {
  const value = asRecord(args)[key];
  return typeof value === "string" ? value : fallback;
}

function getNumber(args: CommandArgs, key: string): number {
  const value = asRecord(args)[key];
  const numberValue = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(numberValue)) throw new Error(`Parâmetro numérico inválido: ${key}`);
  return numberValue;
}

function payload(args: CommandArgs): TableRecord {
  return asRecord(asRecord(args).payload) as TableRecord;
}

function normalizeUser(row: TableRecord): Record<string, unknown> {
  return {
    id: row.id,
    login: row.login ?? row.email ?? "admin",
    name: row.name ?? row.nome ?? row.login ?? "Usuário",
    nome: row.nome ?? row.name ?? row.login ?? "Usuário",
    email: row.email ?? "",
    permissions: Array.isArray(row.permissions) ? row.permissions : ["*"],
    active_company_id: row.active_company_id ?? 1,
    photo_url: row.photo_url ?? row.avatar_url ?? null,
    empresas: row.empresas ?? row.empresa_ids ?? [1],
    profile_id: row.profile_id ?? row.perfil_id ?? 1,
    perfil_id: row.perfil_id ?? row.profile_id ?? 1,
    force_password_change: false,
  };
}

function publicRecord(row: TableRecord): TableRecord {
  const { password: _password, ...rest } = row;
  return rest;
}

function requireSession(token: string): Record<string, unknown> {
  if (!token || !token.startsWith(SESSION_PREFIX)) {
    throw new Error("Sessão inválida ou expirada.");
  }
  return { token };
}


function buildWebPorts(settings: Record<string, unknown>) {
  return [
    { key: "internal_api", label: "API interna", host: settings.internal_api_host, configured_port: settings.internal_api_port, effective_port: settings.internal_api_port, default_port: 61001, available: true, fallback_applied: false },
    { key: "local_web", label: "Servidor web local", host: settings.local_web_host, configured_port: settings.local_web_port, effective_port: settings.local_web_port, default_port: 61002, available: true, fallback_applied: false },
    { key: "auxiliary", label: "Webhook Service", host: settings.webhook_host ?? settings.auxiliary_host, configured_port: settings.webhook_port ?? settings.auxiliary_port, effective_port: settings.webhook_port ?? settings.auxiliary_port, default_port: 61003, available: true, fallback_applied: false },
    { key: "bridge_core", label: "WebSocket Service", host: settings.websocket_host ?? settings.bridge_core_host, configured_port: settings.websocket_port ?? settings.bridge_core_port, effective_port: settings.websocket_port ?? settings.bridge_core_port, default_port: 61004, available: true, fallback_applied: false },
  ];
}

function tableForEntity(entity: string): string {
  const normalized = (entity || "entity").trim().toLowerCase();
  const aliases: Record<string, string> = {
    empresas: "companies",
    empresa: "companies",
    companies: "companies",
    perfis: "profiles",
    perfis_acesso: "profiles",
    profiles: "profiles",
    usuarios: "users",
    users: "users",
  };
  return aliases[normalized] ?? normalized;
}

export class WebCommandProvider implements CommandProvider {
  providerName(): string {
    return "web";
  }

  async invoke<T>(command: string, args?: CommandArgs): Promise<T> {
    const db = useDatabaseProvider();
    await db.bootstrap();

    switch (command) {
      case "app_bootstrap":
        return { ok: true, runtime: getPlatformInfo(), database: db.providerName() } as T;

      case "app_meta":
        return {
          name: projectConfig.app.name,
          short_name: projectConfig.app.shortName,
          version: projectConfig.app.version,
          identifier: projectConfig.app.identifier,
          runtime: getPlatformInfo().mode,
        } as T;

      case "system_info":
        return {
          runtime: getPlatformInfo(),
          database_provider: db.providerName(),
          online: navigator.onLine,
          language: navigator.language,
          user_agent: navigator.userAgent,
        } as T;

      case "system_set_data_dir":
        return { ok: true, warning: "No modo Web/PWA os dados são armazenados no IndexedDB do navegador." } as T;

      case "auth_login": {
        const login = getString(args, "login") || getString(args, "username");
        const password = getString(args, "password") || getString(args, "senha");
        const users = await db.list<TableRecord>("users");
        const user = users.find((item) => String(item.login ?? item.email) === login && String(item.password ?? "") === password);
        if (!user) {
          throw new Error("Usuário ou senha inválidos.");
        }
        const sessionToken = `${SESSION_PREFIX}${Date.now()}-${Math.random().toString(36).slice(2)}`;
        window.localStorage.setItem(storageKey("web-session-token"), sessionToken);
        window.localStorage.setItem(storageKey("web-session-user"), JSON.stringify(normalizeUser(user)));
        return { success: true, session_token: sessionToken, user: normalizeUser(user) } satisfies LoginResponse as T;
      }

      case "auth_restore": {
        const sessionToken = getString(args, "session_token");
        requireSession(sessionToken);
        const stored = window.localStorage.getItem(storageKey("web-session-user"));
        if (!stored) return { success: false, message: "Sessão não encontrada." } as T;
        return { success: true, session_token: sessionToken, user: JSON.parse(stored) } satisfies LoginResponse as T;
      }

      case "auth_logout":
        window.localStorage.removeItem(storageKey("web-session-token"));
        window.localStorage.removeItem(storageKey("web-session-user"));
        return true as T;

      case "auth_change_password":
        return true as T;

      case "permission_catalog":
        return permissionCatalog as T;

      case "profile_list":
        requireSession(getString(args, "session_token"));
        return db.list("profiles", getString(asRecord(args).filters as CommandArgs, "search")) as T;

      case "profile_get":
        requireSession(getString(args, "session_token"));
        return (await db.get("profiles", getNumber(args, "id"))) as T;

      case "profile_save":
        requireSession(getString(args, "session_token"));
        return db.save("profiles", payload(args)) as T;

      case "profile_delete":
        requireSession(getString(args, "session_token"));
        return db.delete("profiles", getNumber(args, "id")) as T;

      case "user_policy_get":
        requireSession(getString(args, "session_token"));
        return { password_min_length: 6, require_strong_password: false, session_timeout_minutes: 480 } as T;

      case "user_policy_save":
        requireSession(getString(args, "session_token"));
        return payload(args) as T;

      case "user_list":
        requireSession(getString(args, "session_token"));
        return (await db.list<TableRecord>("users")).map(publicRecord) as T;

      case "user_get":
        requireSession(getString(args, "session_token"));
        return publicRecord((await db.get("users", getNumber(args, "id"))) ?? {}) as T;

      case "user_save":
        requireSession(getString(args, "session_token"));
        return publicRecord(await db.save("users", payload(args))) as T;

      case "user_delete":
        requireSession(getString(args, "session_token"));
        return db.delete("users", getNumber(args, "id")) as T;

      case "company_list": {
        const filters = asRecord(asRecord(args).filters);
        return db.list("companies", String(filters.search ?? ""), ["razao_social", "nome_fantasia", "documento", "cidade", "estado"]) as T;
      }

      case "company_get":
        return (await db.get("companies", getNumber(args, "id"))) as T;

      case "company_save":
        return db.save("companies", payload(args)) as T;

      case "company_delete":
        return db.delete("companies", getNumber(args, "id")) as T;

      case "company_lookup_cnpj":
      case "company_lookup_ie":
        return { warning: "Consulta pública não disponível no modo Web offline. Use API remota ou Tauri para consulta real." } as T;

      case "entity_list": {
        const entity = tableForEntity(getString(args, "entity"));
        const cfg = entityConfigs[entity];
        return db.list(entity, getString(args, "search"), cfg?.columns ?? []) as T;
      }

      case "entity_save":
        return db.save(tableForEntity(getString(args, "entity")), payload(args)) as T;

      case "entity_delete":
        return db.delete(tableForEntity(getString(args, "entity")), getNumber(args, "id")) as T;

      case "combo_list": {
        const rows = await db.list<TableRecord>(tableForEntity(getString(args, "entity")));
        return rows.map((row) => ({ id: row.id, label: String(row.descricao ?? row.nome ?? row.razao_social ?? row.name ?? row.id) })) as T;
      }

      case "app_log_write": {
        await db.save("app_logs", { ...(payload(args) as TableRecord), created_at: new Date().toISOString() });
        return true as T;
      }

      case "app_log_list":
        requireSession(getString(args, "session_token"));
        return db.list("app_logs") as T;

      case "app_log_clear":
        requireSession(getString(args, "session_token"));
        await db.clear("app_logs");
        return true as T;

      case "licensing_load_settings":
      case "licensing_status":
        return { enabled: false, status: "disabled", message: "Licenciamento desativado no template Web." } as T;

      case "licensing_save_settings":
        return payload(args) as T;

      case "licensing_device_info":
        return { device_id: "web-browser", runtime: getPlatformInfo().mode, platform: navigator.platform } as T;

      case "licensing_check_runtime":
        return { ok: true, status: "disabled" } as T;

      case "licensing_start_trial":
        return { ok: true, status: "trial-local" } as T;

      case "integration_list":
        return db.list("integrations") as T;

      case "integration_save":
        return db.save("integrations", payload(args)) as T;

      case "integration_delete":
        return db.delete("integrations", getNumber(args, "id")) as T;

      case "integration_test":
        return { ok: true, message: "Teste simulado no modo Web/PWA." } as T;

      case "integration_logs":
        return db.list("app_logs", "integration") as T;

      case "sync_queue_list":
        return db.list("sync_queue") as T;

      case "sync_queue_mark_synced": {
        const id = getNumber(args, "id");
        const row = (await db.get("sync_queue", id)) ?? { id };
        await db.save("sync_queue", { ...row, status: "sincronizado", synced_at: new Date().toISOString() });
        return true as T;
      }

      case "support_guard_status":
        return { provisioned: false, locked: false, runtime: getPlatformInfo().mode } as T;

      case "support_guard_provision":
      case "support_guard_enable_totp":
      case "support_guard_unlock":
        return { ok: true, runtime: getPlatformInfo().mode } as T;

      case "runtime_settings_load": {
        const raw = window.localStorage.getItem(storageKey("runtime-settings"));
        const settings = raw ? JSON.parse(raw) : {
          internal_api_host: projectConfig.api.host,
          internal_api_port: projectConfig.api.port,
          internal_api_auto_start: projectConfig.api.autoStart,
          internal_api_base_url: projectConfig.api.baseUrl,
          internal_api_docs_url: projectConfig.api.scalarUrl,
          internal_api_restart_on_config_change: projectConfig.api.restartOnConfigChange,
          internal_api_require_token: projectConfig.api.security.requireToken,
          internal_api_allow_public_network: projectConfig.api.security.allowPublicNetwork ?? false,
          internal_api_cors_enabled: projectConfig.api.security.corsEnabled ?? false,
          internal_api_token_header: projectConfig.api.security.tokenHeader,
          internal_api_token: "",
          internal_api_docs_public_local: projectConfig.api.security.docsPublicLocal,
          internal_api_open_scalar_after_start: projectConfig.api.openScalarAfterStart,
          internal_api_timeout_ms: projectConfig.api.timeoutMs,
          internal_api_log_mode: projectConfig.api.logMode,
          internal_api_docs_enabled: projectConfig.api.docs,
          internal_api_docs_path: projectConfig.api.docsPath,
          local_web_enabled: true,
          local_web_auto_start: true,
          local_web_host: "0.0.0.0",
          local_web_port: 61002,
          auxiliary_host: "0.0.0.0",
          auxiliary_port: 61003,
          bridge_core_host: "0.0.0.0",
          bridge_core_port: 61004,
          webhook_enabled: false,
          webhook_auto_start: false,
          webhook_host: "0.0.0.0",
          webhook_port: 61003,
          webhook_base_path: "/webhooks",
          webhook_token_required: true,
          webhook_token_header: "X-Webhook-Token",
          webhook_token: "",
          webhook_allow_lan: true,
          webhook_allow_external: false,
          websocket_enabled: false,
          websocket_auto_start: false,
          websocket_host: "0.0.0.0",
          websocket_port: 61004,
          websocket_path: "/ws",
          websocket_token_required: true,
          websocket_token_query: "token",
          websocket_token_header: "X-WebSocket-Token",
          websocket_token: "",
          websocket_allow_lan: true,
          websocket_allow_external: false,
          websocket_heartbeat_seconds: 30,
          tray_enabled: projectConfig.tray.enabled,
          minimize_to_tray: projectConfig.tray.minimizeToTray,
          close_to_tray: projectConfig.tray.closeToTray,
          start_with_windows: false,
          services_auto_start: false,
          app_service_name: "Pige360DeployerServer",
        };
        return { env_path: "localStorage:runtime-settings", settings, ports: buildWebPorts(settings), warnings: ["Modo Web/PWA: portas e tray são simulados; use API remota/Tauri para serviços reais."] } as T;
      }

      case "runtime_settings_save": {
        const settings = asRecord(asRecord(args).settings || {});
        window.localStorage.setItem(storageKey("runtime-settings"), JSON.stringify(settings));
        return { env_path: "localStorage:runtime-settings", settings, ports: buildWebPorts(settings), warnings: ["Modo Web/PWA: configuração persistida no navegador."] } as T;
      }

      case "webhook_status": {
        const raw = window.localStorage.getItem(storageKey("webhook-status"));
        return (raw ? JSON.parse(raw) : { running: false, runtime: "web", host: "0.0.0.0", port: 61003, base_path: "/webhooks", events_count: 0, message: "Webhook Service real depende do runtime Tauri/headless." }) as T;
      }

      case "webhook_start": {
        const status = { running: false, simulated: true, runtime: "web", host: "0.0.0.0", port: 61003, url: "http://127.0.0.1:61003", base_path: "/webhooks", events_count: 0, message: "Modo Web não inicia Webhook Service local. Use Tauri/headless para serviço real." };
        window.localStorage.setItem(storageKey("webhook-status"), JSON.stringify(status));
        return status as T;
      }

      case "webhook_stop": {
        const status = { running: false, simulated: true, runtime: "web", host: "0.0.0.0", port: 61003, base_path: "/webhooks", events_count: 0, message: "Webhook Service simulado parado no modo Web." };
        window.localStorage.setItem(storageKey("webhook-status"), JSON.stringify(status));
        return status as T;
      }

      case "webhook_restart":
        return this.invoke("webhook_start", args) as T;

      case "webhook_list_events": {
        const raw = window.localStorage.getItem(storageKey("webhook-events"));
        return { items: raw ? JSON.parse(raw) : [] } as T;
      }

      case "webhook_clear_events":
        window.localStorage.removeItem(storageKey("webhook-events"));
        return true as T;

      case "webhook_test_receive": {
        const record = {
          id: Date.now(),
          provider: getString(args, "provider", "manual"),
          event: getString(args, "event", "test"),
          status: "received",
          payload_json: asRecord(args).payload ?? { message: "Teste Web/PWA" },
          received_at: new Date().toISOString(),
        };
        const raw = window.localStorage.getItem(storageKey("webhook-events"));
        const events = raw ? JSON.parse(raw) : [];
        events.unshift(record);
        window.localStorage.setItem(storageKey("webhook-events"), JSON.stringify(events.slice(0, 100)));
        return { ok: true, event: record } as T;
      }

      case "websocket_status": {
        const raw = window.localStorage.getItem(storageKey("websocket-status"));
        return (raw ? JSON.parse(raw) : { running: false, runtime: "web", host: "0.0.0.0", port: 61004, path: "/ws", clients_count: 0, message: "WebSocket Service real depende do runtime Tauri/headless." }) as T;
      }

      case "websocket_start": {
        const status = { running: false, simulated: true, runtime: "web", host: "0.0.0.0", port: 61004, url: "ws://127.0.0.1:61004/ws", path: "/ws", clients_count: 0, message: "Modo Web não inicia WebSocket Service local. Use Tauri/headless para serviço real." };
        window.localStorage.setItem(storageKey("websocket-status"), JSON.stringify(status));
        return status as T;
      }

      case "websocket_stop": {
        const status = { running: false, simulated: true, runtime: "web", host: "0.0.0.0", port: 61004, path: "/ws", clients_count: 0, message: "WebSocket Service simulado parado no modo Web." };
        window.localStorage.setItem(storageKey("websocket-status"), JSON.stringify(status));
        return status as T;
      }

      case "websocket_restart":
        return this.invoke("websocket_start", args) as T;

      case "websocket_list_clients":
        return { items: [] } as T;

      case "websocket_broadcast_test":
        return { ok: true, sent: 0, simulated: true, payload: { type: "template.broadcast.test", message: getString(args, "message", "Teste Web/PWA"), sent_at: new Date().toISOString() } } as T;

      case "startup_with_windows_set":
        return { implemented: false, runtime: getPlatformInfo().mode, message: "Inicialização com Windows indisponível no navegador." } as T;

      case "internal_api_status": {
        const raw = window.localStorage.getItem(storageKey("internal-api-status"));
        return (raw ? JSON.parse(raw) : { running: false, runtime: "web", host: projectConfig.api.host, port: projectConfig.api.port, message: "No navegador a API interna depende do backend remoto/Tauri." }) as T;
      }

      case "web_proxy_status":
        return { running: false, runtime: "web", host: "127.0.0.1", port: 61002, message: "Webport real é iniciado pelo runtime Tauri, não pelo navegador puro." } as T;

      case "web_proxy_start":
      case "web_proxy_stop":
      case "web_proxy_restart":
        return { running: false, simulated: true, runtime: "web", message: "Modo Web puro não inicia serviços locais. No Tauri desktop o webport inicia internamente sem cmd/PowerShell." } as T;

      case "internal_api_start": {
        const host = getString(args, "host", projectConfig.api.host);
        const port = Number(asRecord(args).port || projectConfig.api.port);
        const status = { running: false, simulated: true, runtime: "web", host, port, url: `http://${host}:${port}`, docs_url: `http://${host}:${port}/docs`, message: "Modo Web não inicia servidor local. Use Tauri/headless para API real." };
        window.localStorage.setItem(storageKey("internal-api-status"), JSON.stringify(status));
        return status as T;
      }

      case "internal_api_stop": {
        const status = { running: false, simulated: true, runtime: "web", host: projectConfig.api.host, port: projectConfig.api.port, message: "API simulada parada no modo Web." };
        window.localStorage.setItem(storageKey("internal-api-status"), JSON.stringify(status));
        return status as T;
      }

      case "internal_api_restart": {
        const host = getString(args, "host", projectConfig.api.host);
        const port = Number(asRecord(args).port || projectConfig.api.port);
        const status = { running: false, simulated: true, runtime: "web", host, port, url: `http://${host}:${port}`, docs_url: `http://${host}:${port}/docs`, message: "Restart simulado no modo Web. Use Tauri/headless para API real." };
        window.localStorage.setItem(storageKey("internal-api-status"), JSON.stringify(status));
        return status as T;
      }

      case "app_service_install":
      case "app_service_uninstall":
      case "app_service_start":
      case "app_service_stop":
      case "app_service_restart":
        return { ok: false, warning: "Recurso nativo indisponível no navegador. Configure API remota para execução real." } as T;

      case "app_service_status":
        return { running: false, installed: false, available: false, runtime: getPlatformInfo().mode, message: "Serviço nativo indisponível no navegador." } as T;

      case "tray_status":
        return { enabled: false, available: false, runtime: getPlatformInfo().mode, message: "Tray icon é recurso desktop/Tauri." } as T;

      case "open_print_preview":
        window.print();
        return true as T;

      case "tray_restore_window":
      case "tray_exit_app":
        return true as T;

      case "entity_provider_list":
      case "provider_list_with_database":
        return [{ id: "indexeddb", name: "IndexedDB Web", runtime: getPlatformInfo().mode }] as T;

      case "provider_entity_list":
        return db.list(tableForEntity(getString(args, "entity"))) as T;

      case "provider_entity_get":
        return db.get(tableForEntity(getString(args, "entity")), getNumber(args, "id")) as T;

      case "provider_entity_create":
      case "provider_entity_update":
        return db.save(tableForEntity(getString(args, "entity")), payload(args)) as T;

      case "provider_entity_delete":
        return db.delete(tableForEntity(getString(args, "entity")), getNumber(args, "id")) as T;

      default:
        throw new Error(`Comando '${command}' ainda não possui implementação Web. Crie fallback em WebCommandProvider.`);
    }
  }
}
