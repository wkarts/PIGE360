<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";
import AppPageTitleBar from "./AppPageTitleBar.vue";

const props = defineProps<{
  title: string;
  subtitle?: string;
  eyebrow?: string;
  icon?: string;
}>();

const route = useRoute();

function iconNameForRoute(routePath: string): string {
  const normalized = ((routePath || "/").split("?")[0].split("#")[0].replace(/\/+$/, "") || "/");
  const icons: Record<string, string> = {
    "/empresas": "building",
    "/departamentos": "department",
    "/funcoes": "briefcase",
    "/centros-custo": "target",
    "/clientes": "customer",
    "/fornecedores": "supplier",
    "/produtos": "package",
    "/usuarios": "users",
    "/perfis": "shield",
    "/logs": "clipboard",
    "/sistema": "settings",
    "/sistema/banco": "database",
    "/licenciamento": "key",
    "/runtime": "activity",
    "/api-interna": "api",
    "/documentacao/scalar": "docs",
    "/webhooks": "webhook",
    "/websocket": "websocket",
    "/integracoes": "plug",
    "/sincronizacao": "sync",
    "/ficha-tecnica": "file",
    "/sobre": "info",
    "/documentacao/guia": "book",
  };
  return icons[normalized] || "file";
}

const pageIcon = computed(() => props.icon || iconNameForRoute(route.path));
</script>

<template>
  <section class="base-page page-content-scroll">
    <AppPageTitleBar
      class="page-header-card"
      :title="title"
      :subtitle="subtitle"
      :eyebrow="eyebrow || 'PIGE360 Deployer'"
      :icon="pageIcon"
    >
      <template v-if="$slots.actions" #actions>
        <slot name="actions" />
      </template>
    </AppPageTitleBar>
    <div class="base-page-body">
      <slot />
    </div>
  </section>
</template>
