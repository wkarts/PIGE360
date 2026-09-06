import { invokeCommand } from "./tauri";
import { invokeAppCommand } from "../core/invoker/CommandProviderFactory";
import { useSessionStore } from "../stores/session";
import { logAppError, logAppInfo } from "./logger";
import { isNativeMobileRuntime } from "../core/runtime/RuntimeProvider";

export interface StartupState {
  progress: number;
  message: string;
  detail: string;
}

export type StartupUpdate = (state: StartupState) => void;

const STARTUP_MIN_VISIBLE_MS = 1100;
const STARTUP_STEP_TIMEOUT_MS = 2500;

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function emit(update: StartupUpdate, progress: number, message: string, detail: string) {
  update({ progress, message, detail });
}

async function withStartupTimeout<T>(label: string, task: Promise<T>): Promise<T> {
  let timeoutId: number | undefined;
  try {
    return await Promise.race([
      task,
      new Promise<T>((_, reject) => {
        timeoutId = window.setTimeout(() => reject(new Error(`${label} excedeu o tempo limite de inicialização.`)), STARTUP_STEP_TIMEOUT_MS);
      }),
    ]);
  } finally {
    if (timeoutId) window.clearTimeout(timeoutId);
  }
}

export async function runApplicationStartup(update: StartupUpdate) {
  const startedAt = Date.now();
  const session = useSessionStore();

  emit(update, 8, "Inicializando aplicação...", "Carregando interface e recursos visuais");
  await sleep(120);

  try {
    emit(update, 26, "Preparando ambiente local...", "Validando banco, diretórios e configurações");
    try {
      await withStartupTimeout("Bootstrap da aplicação", invokeCommand("app_bootstrap"));
    } catch (error) {
      logAppError("startup", "Bootstrap falhou, mas a interface será aberta para recuperação.", { error: error instanceof Error ? error.message : String(error) });
    }

    if (isNativeMobileRuntime()) {
      emit(update, 42, "Preparando modo mobile...", "Usando interface, dashboards e SQLite locais no dispositivo");
    } else {
      emit(update, 42, "Validando webport local...", "Consultando serviço publicado pelo runtime nativo");
      try {
        await withStartupTimeout("Consulta de status do webport/proxy local", invokeAppCommand("web_proxy_status"));
      } catch (error) {
        logAppInfo("startup", "Status do webport/proxy indisponível no startup; a interface continuará normalmente.", { error: error instanceof Error ? error.message : String(error) });
      }
    }

    emit(update, 54, "Restaurando sessão...", "Verificando usuário autenticado neste dispositivo");
    try {
      await withStartupTimeout("Restauração da sessão", session.restore());
    } catch (error) {
      logAppError("startup", "Restauração de sessão falhou, seguindo para login.", { error: error instanceof Error ? error.message : String(error) });
      session.clearAuthState();
    }

    emit(update, 86, "Aplicando configurações...", "Preparando permissões, tema e contexto da aplicação");
    await sleep(120);

    emit(update, 96, "Finalizando carregamento...", "Abrindo tela inicial da aplicação");
    const elapsed = Date.now() - startedAt;
    if (STARTUP_MIN_VISIBLE_MS > 0 && elapsed < STARTUP_MIN_VISIBLE_MS) {
      await sleep(STARTUP_MIN_VISIBLE_MS - elapsed);
    }

    emit(update, 100, "Pronto", "Aplicação carregada com sucesso");
    logAppInfo("startup", "Aplicação inicializada pelo splash screen.", {
      authenticated: session.isAuthenticated,
      user: session.user?.login ?? null,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Falha ao carregar aplicação.";
    emit(update, 100, "Falha ao carregar aplicação", message);
    logAppError("startup", "Falha durante inicialização pelo splash screen.", { error: message });
    throw error;
  }
}
