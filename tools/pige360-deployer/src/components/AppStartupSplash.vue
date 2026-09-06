<script setup lang="ts">
import splashLogo from "../assets/branding/splash-logo.png";
import { ref } from "vue";
import { appBranding } from "../config/appBranding";
import { logAppError } from "../services/logger";

const logoFailed = ref(false);

function handleLogoError() {
  logoFailed.value = true;
  logAppError("assets", "Falha ao carregar splash-logo.png; fallback visual aplicado.", { asset: "src/assets/branding/splash-logo.png" });
}

withDefaults(
  defineProps<{
    progress: number;
    message: string;
    detail?: string;
  }>(),
  {
    progress: 0,
    message: "Carregando aplicação...",
    detail: "Preparando ambiente local",
  }
);
</script>

<template>
  <section class="startup-splash" role="status" aria-live="polite" aria-busy="true">
    <div class="startup-splash-bg startup-splash-bg-a"></div>
    <div class="startup-splash-bg startup-splash-bg-b"></div>

    <main class="startup-splash-card">
      <img v-if="!logoFailed" :src="splashLogo" :alt="appBranding.appName" class="startup-splash-logo" @error="handleLogoError" />
      <div v-else class="startup-splash-logo fallback-logo">{{ appBranding.shortName.slice(0, 2).toUpperCase() }}</div>
      <h1>{{ appBranding.appName }}</h1>
      <p class="startup-splash-message">{{ message }}</p>

      <div class="startup-progress" aria-label="Progresso de carregamento">
        <div class="startup-progress-track">
          <div class="startup-progress-bar" :style="{ width: `${Math.min(100, Math.max(0, progress))}%` }"></div>
        </div>
        <strong>{{ Math.round(Math.min(100, Math.max(0, progress))) }}%</strong>
      </div>

      <span class="startup-splash-detail">{{ detail }}</span>
    </main>
  </section>
</template>
