import { invokeAppCommand } from "../core/invoker/CommandProviderFactory";

export type AppLogLevel = "debug" | "info" | "warning" | "error";

export interface AppLogPayload {
  level?: AppLogLevel;
  category: string;
  message: string;
  source?: string;
  route?: string;
  details?: unknown;
}

const SENSITIVE_KEY_MARKERS = [
  "senha",
  "password",
  "confirm_password",
  "password_confirmation",
  "token",
  "secret",
  "api_key",
  "apikey",
  "authorization",
];

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return Object.prototype.toString.call(value) === "[object Object]";
}

function isSensitiveKey(key: string): boolean {
  const normalized = key.trim().toLowerCase();
  return SENSITIVE_KEY_MARKERS.some((marker) => normalized.includes(marker));
}

export function sanitizeForLog(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => sanitizeForLog(item));
  }
  if (isPlainObject(value)) {
    const sanitized: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(value)) {
      sanitized[key] = isSensitiveKey(key) ? "***" : sanitizeForLog(item);
    }
    return sanitized;
  }
  return value;
}

export async function writeAppLog(payload: AppLogPayload): Promise<void> {
  const normalized = {
    level: payload.level ?? "info",
    category: payload.category,
    message: payload.message,
    source: payload.source ?? "frontend",
    route: payload.route ?? window.location.hash,
    details: sanitizeForLog(payload.details ?? null),
  };
  try {
    await invokeAppCommand<boolean>("app_log_write", { payload: normalized });
  } catch (error) {
    console.error("Falha ao gravar log da aplicação", sanitizeForLog(normalized), error);
  }
}

export function logAppError(category: string, message: string, details?: unknown) {
  void writeAppLog({ level: "error", category, message, details, source: "frontend" });
}

export function logAppInfo(category: string, message: string, details?: unknown) {
  void writeAppLog({ level: "info", category, message, details, source: "frontend" });
}

export function logAppWarning(category: string, message: string, details?: unknown) {
  void writeAppLog({ level: "warning", category, message, details, source: "frontend" });
}
