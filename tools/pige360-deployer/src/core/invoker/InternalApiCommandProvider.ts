import type { CommandArgs, CommandProvider } from "./CommandProvider";

interface ApiCommandResponse<T> {
  ok: boolean;
  result?: T;
  error?: string;
}

type TemplateRuntimeWindow = Window & {
  __TAURI_INTERNALS__?: unknown;
  PIGE360_DEPLOYER_WEB_RUNTIME?: boolean;
  PIGE360_DEPLOYER_INTERNAL_API_WEB_RUNTIME?: boolean;
  PIGE360_DEPLOYER_COMMAND_PROXY_BASE?: string;
  PIGE360_DEPLOYER_API_BASE_URL?: string;
};

function runtimeWindow(): TemplateRuntimeWindow | null {
  if (typeof window === "undefined") return null;
  return window as TemplateRuntimeWindow;
}

function trimRightSlash(value: string): string {
  return value.replace(/\/+$/, "");
}

function apiBaseUrl(): string {
  const win = runtimeWindow();
  if (!win) return "/__internal_api";

  const proxyBase = win.PIGE360_DEPLOYER_COMMAND_PROXY_BASE;
  if (proxyBase && proxyBase.trim()) {
    return trimRightSlash(proxyBase.trim());
  }

  const configured = win.PIGE360_DEPLOYER_API_BASE_URL;
  if (configured && configured.trim()) {
    return trimRightSlash(configured.trim());
  }

  // Quando a aplicação está publicada pelo webport/proxy, use sempre o proxy
  // same-origin. Assim o navegador não depende de CORS, token manual nem porta
  // exposta diretamente para executar os mesmos comandos do desktop.
  return "/__internal_api";
}

export function isInternalApiWebRuntime(): boolean {
  const win = runtimeWindow();
  if (!win) return false;
  if (win.__TAURI_INTERNALS__) return false;

  const port = win.location.port;
  return Boolean(win.PIGE360_DEPLOYER_INTERNAL_API_WEB_RUNTIME || win.PIGE360_DEPLOYER_WEB_RUNTIME || port === "61002");
}

export class InternalApiCommandProvider implements CommandProvider {
  providerName(): string {
    return "internal-api-web";
  }

  async invoke<T>(command: string, args?: CommandArgs): Promise<T> {
    const response = await fetch(`${apiBaseUrl()}/api/command`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify({ command, args: args ?? {} }),
    });

    const rawPayload = await response.text();
    let payload: ApiCommandResponse<T>;
    try {
      payload = JSON.parse(rawPayload) as ApiCommandResponse<T>;
    } catch {
      const snippet = rawPayload.replace(/\s+/g, " ").trim().slice(0, 220);
      throw new Error(`Falha ao interpretar resposta da API interna para ${command}. Resposta recebida: ${snippet || "vazia"}`);
    }

    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || `Falha ao executar ${command} pela API interna.`);
    }

    return payload.result as T;
  }
}
