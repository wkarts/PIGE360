<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import BasePage from "../../components/base/BasePage.vue";
import BaseSectionCard from "../../components/base/BaseSectionCard.vue";
import { getSystemInfo, type GenericRecord } from "../../services/crud";
import { appFeatures, projectConfig } from "../../config/projectConfig";

const info = ref<GenericRecord>({});
const error = ref("");
const activeModules = computed(() => Object.entries(appFeatures).filter(([, enabled]) => enabled).map(([key]) => key));
const inactiveModules = computed(() => Object.entries(appFeatures).filter(([, enabled]) => !enabled).map(([key]) => key));

onMounted(async () => {
  try { info.value = await getSystemInfo(); } catch (err) { error.value = err instanceof Error ? err.message : "Falha ao carregar ficha técnica."; }
});
</script>

<template>
  <BasePage title="Ficha técnica" subtitle="Informações técnicas úteis para suporte, sem exposição de segredos.">
    <div v-if="error" class="alert error">{{ error }}</div>
    <div class="grid columns-2 mobile-columns-1">
      <BaseSectionCard title="Aplicação">
        <div class="info-grid compact-info">
          <div class="info-item"><strong>Nome</strong><code>{{ projectConfig.app.name }}</code></div>
          <div class="info-item"><strong>Versão</strong><code>{{ info.version || projectConfig.app.version }}</code></div>
          <div class="info-item"><strong>Build</strong><code>{{ info.build_hash || 'dev' }}</code></div>
          <div class="info-item"><strong>Modo</strong><code>{{ projectConfig.app.mode }}</code></div>
        </div>
      </BaseSectionCard>
      <BaseSectionCard title="Ambiente local">
        <div class="info-grid compact-info">
          <div class="info-item"><strong>Banco</strong><code>{{ projectConfig.database.driver }}</code></div>
          <div class="info-item"><strong>DB Path</strong><code>{{ info.db_path || '-' }}</code></div>
          <div class="info-item"><strong>Dados</strong><code>{{ info.data_dir || '-' }}</code></div>
          <div class="info-item"><strong>Logs</strong><code>{{ info.log_file || '-' }}</code></div>
        </div>
      </BaseSectionCard>
    </div>
    <BaseSectionCard title="Módulos ativos e ocultos">
      <div class="grid columns-2 mobile-columns-1">
        <div><h4>Ativos</h4><div class="module-chip-grid"><span v-for="item in activeModules" :key="item" class="module-chip enabled">{{ item }}</span></div></div>
        <div><h4>Ocultos</h4><div class="module-chip-grid"><span v-for="item in inactiveModules" :key="item" class="module-chip disabled">{{ item }}</span></div></div>
      </div>
    </BaseSectionCard>
  </BasePage>
</template>
