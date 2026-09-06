import { invokeAppCommand } from "../core/invoker/CommandProviderFactory";
import { showSplashError, showSplashInfo, showSplashWarning } from "./splash";

function toCamelCase(key: string): string {
  return key.replace(/_([a-z])/g, (_, char: string) => char.toUpperCase());
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return Object.prototype.toString.call(value) === "[object Object]";
}

function getRecordIdFromArgs(args?: Record<string, unknown>): number | null {
  if (!args || !isPlainObject(args)) return null;
  if (typeof args.id === "number" && Number.isFinite(args.id)) return Number(args.id);
  const payload = args.payload;
  if (isPlainObject(payload) && typeof payload.id === "number" && Number.isFinite(payload.id)) {
    return Number(payload.id);
  }
  return null;
}

function entityLabelFromCommand(command: string): string {
  const root = command.replace(/_(save|delete|import|export|clone)$/i, "");
  const map: Record<string, string> = {
    company: "Empresa",
    user: "Usuário",
    profile: "Perfil",
    entity: "Registro",
    support_guard: "Proteção administrativa",
    licensing: "Licenciamento",
  };
  return map[root] || "Registro";
}

function shouldAutoNotify(command: string): boolean {
  if (command === "app_log_write") return false;
  if (/_list$|_get$|_combo$|_status$|_check/.test(command)) return false;
  if (/^auth_(login|restore|logout)$/.test(command)) return false;
  return (
    command.endsWith("_save") ||
    command.endsWith("_delete") ||
    command.includes("_import") ||
    command.includes("_export") ||
    command.includes("_clone")
  );
}

function notifySuccess(command: string, args: Record<string, unknown> | undefined, result: unknown) {
  if (!shouldAutoNotify(command)) return;

  if (isPlainObject(result)) {
    const message = typeof result.message === "string" ? result.message.trim() : "";
    const warning = typeof result.warning === "string" ? result.warning.trim() : "";
    if (warning) {
      showSplashWarning(warning);
      return;
    }
    if (message) {
      showSplashInfo(message);
      return;
    }
  }

  const entity = entityLabelFromCommand(command);
  if (command.endsWith("_save")) {
    const isUpdate = getRecordIdFromArgs(args) !== null;
    showSplashInfo(isUpdate ? `${entity} atualizado com sucesso.` : `${entity} cadastrado com sucesso.`);
    return;
  }
  if (command.endsWith("_delete")) {
    showSplashInfo(`${entity} excluído com sucesso.`);
    return;
  }
  if (command.includes("_import")) {
    showSplashInfo("Importação concluída com sucesso.");
    return;
  }
  if (command.includes("_export")) {
    showSplashInfo("Exportação concluída com sucesso.");
    return;
  }
  if (command.endsWith("_clone")) {
    showSplashInfo(`${entity} clonado com sucesso.`);
  }
}

function withTauriArgAliases<T>(value: T): T {
  if (Array.isArray(value)) {
    return value.map((item) => withTauriArgAliases(item)) as T;
  }

  if (!isPlainObject(value)) {
    return value;
  }

  const result: Record<string, unknown> = {};
  for (const [key, raw] of Object.entries(value)) {
    const normalized = withTauriArgAliases(raw);
    result[key] = normalized;

    const camelKey = toCamelCase(key);
    if (camelKey !== key && !(camelKey in result)) {
      result[camelKey] = normalized;
    }
  }

  return result as T;
}

function isSessionInvalidError(message: string): boolean {
  const normalized = message.toLowerCase();
  return normalized.includes("sessão inválida")
    || normalized.includes("sessao invalida")
    || normalized.includes("sessão expirada")
    || normalized.includes("sessao expirada")
    || normalized.includes("session invalid")
    || normalized.includes("session expired");
}

async function forceLoginOnInvalidSession(message: string) {
  try {
    const [{ useSessionStore }, { default: router }] = await Promise.all([
      import("../stores/session"),
      import("../router"),
    ]);
    const session = useSessionStore();
    if (session.sessionToken || session.user) {
      session.clearAuthState();
    }
    showSplashWarning("Sua sessão foi encerrada porque houve novo acesso em outro dispositivo ou porque ela expirou. Faça login novamente.");
    if (router.currentRoute.value.path !== "/login") {
      await router.replace("/login");
    }
  } catch {
    showSplashWarning(message || "Sessão expirada. Faça login novamente.");
  }
}

export async function invokeCommand<T>(command: string, args?: Record<string, unknown>): Promise<T> {
  const normalizedArgs = withTauriArgAliases(args);
  try {
    const response = await invokeAppCommand<T>(command, normalizedArgs);
    notifySuccess(command, normalizedArgs, response);
    return response;
  } catch (error) {
    const errorText = error instanceof Error ? error.message : String(error);
    if (isSessionInvalidError(errorText)) {
      await forceLoginOnInvalidSession(errorText);
    } else if (errorText.includes("429 Too Many Requests") || errorText.toLowerCase().includes("rate limit")) {
      showSplashWarning("Limite temporário de consulta atingido nos serviços públicos. Aguarde alguns segundos e tente novamente.");
    } else {
      showSplashError(errorText);
    }
    if (command === "company_lookup_cnpj" || command === "company_lookup_ie") {
      showSplashInfo("A aplicação tenta fallback automático entre provedores quando disponível.");
    }
    if (command !== "app_log_write") {
      void import("./logger").then(({ logAppError, sanitizeForLog }) => {
        logAppError("invoke", `Falha ao executar comando ${command}.`, {
          command,
          args: sanitizeForLog(normalizedArgs),
          error: errorText,
        });
      });
    }
    throw error;
  }
}
