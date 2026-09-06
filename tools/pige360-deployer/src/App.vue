<script setup lang="ts">
import { onErrorCaptured, onMounted, reactive, ref } from "vue";
import { logAppError } from "./services/logger";
import AppSplash from "./components/AppSplash.vue";
import AppStartupSplash from "./components/AppStartupSplash.vue";
import AppDialogHost from "./components/base/AppDialogHost.vue";
import { showSplashError, showSplashWarning } from "./services/splash";
import { runApplicationStartup, type StartupState } from "./services/startup";

const startupVisible = ref(true);
const nonBlockingError = ref("");
const startupState = reactive<StartupState>({ progress: 0, message: "Inicializando aplicação...", detail: "Preparando ambiente local" });
let startupFallbackTimer: number | undefined;
const STARTUP_REALTIME_MIN_VISIBLE_MS = 1100;

function bootStartedAt(): number {
  const raw = (window as Window & { __pige360DeployerBootStartedAt?: number }).__pige360DeployerBootStartedAt;
  return typeof raw === "number" && raw > 0 ? raw : Date.now();
}

function wait(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function resolveComponentName(instance: unknown): string | null {
  const raw = instance as { type?: { name?: string }; $options?: { name?: string } } | null;
  return raw?.type?.name ?? raw?.$options?.name ?? null;
}

async function finishStartup() {
  if (startupFallbackTimer) window.clearTimeout(startupFallbackTimer);
  const remaining = STARTUP_REALTIME_MIN_VISIBLE_MS - (Date.now() - bootStartedAt());
  if (remaining > 0) {
    startupState.progress = Math.max(startupState.progress, 98);
    startupState.message = startupState.message || "Finalizando inicialização...";
    startupState.detail = "Finalizando abertura";
    await wait(remaining);
  }
  startupState.progress = 100;
  startupVisible.value = false;
}

onMounted(async () => {
  startupFallbackTimer = window.setTimeout(() => {
    nonBlockingError.value = "A inicialização excedeu o tempo seguro; a interface foi liberada para evitar tela branca.";
    showSplashWarning(nonBlockingError.value);
    void finishStartup();
  }, 12000);

  try {
    await runApplicationStartup((state) => {
      startupState.progress = state.progress;
      startupState.message = state.message;
      startupState.detail = state.detail;
    });
  } catch (error) {
    nonBlockingError.value = error instanceof Error ? error.message : "Falha ao inicializar aplicação.";
    showSplashError(nonBlockingError.value);
  } finally {
    await finishStartup();
  }
});

onErrorCaptured((error, instance, info) => {
  nonBlockingError.value = error instanceof Error ? error.message : "Falha inesperada na interface.";
  logAppError("vue", "Erro capturado no componente raiz.", { info, component: resolveComponentName(instance), error: nonBlockingError.value });
  showSplashError(nonBlockingError.value);
  return false;
});
</script>

<template>
  <!--
    A interface principal fica sempre montada atrás do splash.
    Isso preserva a tela de abertura e impede janela branca caso algum serviço
    de rede demore, falhe ou esteja ocupado por outra instância.
  -->
  <AppSplash />
  <div v-if="nonBlockingError" class="startup-recovery-banner">
    {{ nonBlockingError }}
  </div>
  <router-view />

  <AppDialogHost />

  <AppStartupSplash
    v-if="startupVisible"
    class="startup-splash-overlay"
    :progress="startupState.progress"
    :message="startupState.message"
    :detail="startupState.detail"
  />
</template>
