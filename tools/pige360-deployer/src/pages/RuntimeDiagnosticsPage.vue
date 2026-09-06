<script setup lang="ts">
import { onMounted, ref } from "vue";
import BasePage from "../components/base/BasePage.vue";
import { collectRuntimeDiagnostics, type RuntimeDiagnosticItem } from "../core/diagnostics/RuntimeDiagnostics";

const loading = ref(true);
const items = ref<RuntimeDiagnosticItem[]>([]);

async function loadDiagnostics() {
  loading.value = true;
  try {
    items.value = await collectRuntimeDiagnostics();
  } finally {
    loading.value = false;
  }
}

onMounted(loadDiagnostics);
</script>

<template>
  <BasePage title="Diagnóstico do Runtime" subtitle="Validação do mesmo projeto em Web, PWA e Tauri.">
    <template #actions>
      <button class="btn primary" type="button" @click="loadDiagnostics">Atualizar</button>
    </template>

    <div class="diagnostics-grid">
      <article v-for="item in items" :key="item.key" class="diagnostic-card" :class="{ ok: item.ok, fail: !item.ok }">
        <span class="diagnostic-label">{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
      </article>
    </div>

    <p v-if="loading" class="muted-text">Carregando diagnóstico...</p>
  </BasePage>
</template>

<style scoped>
.diagnostics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 14px;
}

.diagnostic-card {
  border: 1px solid var(--border-color, #d9e2ec);
  border-radius: 16px;
  padding: 16px;
  background: #fff;
  box-shadow: 0 8px 24px rgb(15 23 42 / 6%);
}

.diagnostic-card.ok {
  border-color: #bbf7d0;
}

.diagnostic-card.fail {
  border-color: #fecaca;
}

.diagnostic-label {
  display: block;
  color: #64748b;
  font-size: 0.85rem;
  margin-bottom: 6px;
}
</style>
