<script setup lang="ts">
import { onMounted, ref } from "vue";
import BasePage from "../components/base/BasePage.vue";
import BaseSectionCard from "../components/base/BaseSectionCard.vue";
import { getSystemInfo, type GenericRecord } from "../services/crud";
import { appFeatures, projectConfig } from "../config/projectConfig";

const info = ref<GenericRecord>({});
onMounted(async () => { try { info.value = await getSystemInfo(); } catch { info.value = {}; } });
</script>

<template>
  <BasePage title="Sobre" subtitle="Informações da aplicação, ambiente e stack técnica.">
    <div class="grid columns-2 mobile-columns-1">
      <BaseSectionCard title="Aplicação">
        <div class="info-grid compact-info">
          <div class="info-item"><strong>Nome</strong><code>{{ projectConfig.app.name }}</code></div>
          <div class="info-item"><strong>Versão</strong><code>{{ info.version || projectConfig.app.version }}</code></div>
          <div class="info-item"><strong>Build</strong><code>{{ info.build_hash || 'dev' }}</code></div>
          <div class="info-item"><strong>Identificador</strong><code>{{ projectConfig.app.identifier }}</code></div>
          <div class="info-item"><strong>Desenvolvedor</strong><code>{{ projectConfig.app.developer }}</code></div>
          <div class="info-item"><strong>Ambiente</strong><code>{{ projectConfig.app.mode }}</code></div>
        </div>
      </BaseSectionCard>
      <BaseSectionCard title="Stack técnica">
        <div class="module-chip-grid">
          <span class="module-chip enabled">Tauri 2</span><span class="module-chip enabled">Rust</span><span class="module-chip enabled">Vue 3</span><span class="module-chip enabled">TypeScript</span><span class="module-chip enabled">SQLite</span><span class="module-chip enabled">Pinia</span><span class="module-chip enabled">Vue Router</span>
        </div>
      </BaseSectionCard>
      <BaseSectionCard title="Dados locais">
        <div class="info-grid compact-info">
          <div class="info-item"><strong>Banco local</strong><code>{{ info.db_path || '-' }}</code></div>
          <div class="info-item"><strong>Dados</strong><code>{{ info.data_dir || '-' }}</code></div>
        </div>
      </BaseSectionCard>
      <BaseSectionCard title="Módulos">
        <div class="module-chip-grid">
          <span v-for="(enabled, key) in appFeatures" :key="key" class="module-chip" :class="enabled ? 'enabled' : 'disabled'">{{ key }}: {{ enabled ? 'ativo' : 'oculto' }}</span>
        </div>
      </BaseSectionCard>
    </div>
  </BasePage>
</template>
