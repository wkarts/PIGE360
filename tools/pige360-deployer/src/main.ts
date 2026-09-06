import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import { registerServiceWorker } from "./core/pwa/registerServiceWorker";
import router from "./router";
import "./styles.css";
import { useSessionStore } from "./stores/session";
import { logAppError, logAppInfo } from "./services/logger";
import { showSplashError, showSplashWarning } from "./services/splash";


function renderBootFallback(title: string, message: string) {
  const target = document.querySelector('#app');
  if (!target) return;
  target.innerHTML = `
    <div class="pige360-deployer-boot-fallback">
      <main class="pige360-deployer-boot-card">
        <div class="pige360-deployer-boot-logo"></div>
        <h1>${title}</h1>
        <p>${message}</p>
        <div class="pige360-deployer-boot-error" style="display:block">${message}</div>
      </main>
    </div>`;
}

function notifyBootFallback(message: string) {
  const fallback = (window as Window & { __pige360DeployerBootError?: (message: string) => void }).__pige360DeployerBootError;
  if (fallback) fallback(message);
}

function resolveComponentName(instance: unknown): string | null {
  const raw = instance as { type?: { name?: string }; $options?: { name?: string } } | null;
  return raw?.type?.name ?? raw?.$options?.name ?? null;
}

async function bootstrap() {
  const app = createApp(App);
  const pinia = createPinia();
  app.use(pinia);
  app.use(router);

  app.config.errorHandler = (error, instance, info) => {
    logAppError("vue", "Erro global capturado pelo Vue.", {
      info,
      component: resolveComponentName(instance),
      error: error instanceof Error ? error.message : String(error),
    });
    console.error(error);
    showSplashError(error instanceof Error ? error.message : String(error));
  };

  window.addEventListener("error", (event) => {
    logAppError("window", "Erro global de janela.", { message: event.message, file: event.filename, line: event.lineno, column: event.colno });
    showSplashError(event.message || "Erro global da aplicação.");
  });

  window.addEventListener("unhandledrejection", (event) => {
    logAppError("promise", "Promise rejeitada sem tratamento.", { reason: event.reason instanceof Error ? event.reason.message : String(event.reason) });
    showSplashWarning(event.reason instanceof Error ? event.reason.message : String(event.reason));
  });

  useSessionStore(pinia);

  const target = document.querySelector("#app");
  if (!target) {
    notifyBootFallback("Elemento #app não foi encontrado no HTML de inicialização.");
    return;
  }
  app.mount("#app");
  document.body.dataset.pige360DeployerMounted = "true";
  logAppInfo("bootstrap", "Aplicação montada imediatamente para evitar tela branca no primeiro carregamento.");

  router.isReady().catch((error) => {
    logAppError("router", "Router demorou ou falhou após montagem inicial.", { error: error instanceof Error ? error.message : String(error) });
  });
}

bootstrap().catch((error) => {
  const message = error instanceof Error ? error.message : String(error);
  console.error(error);
  notifyBootFallback(message);
  renderBootFallback("Falha ao carregar a interface", message);
});
void registerServiceWorker();
