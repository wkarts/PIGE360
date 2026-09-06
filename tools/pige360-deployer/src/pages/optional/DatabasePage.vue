<script setup lang="ts">
import { onMounted, ref } from "vue";
import BasePage from "../../components/base/BasePage.vue";
import BaseSectionCard from "../../components/base/BaseSectionCard.vue";
import { getSystemInfo, type GenericRecord } from "../../services/crud";
import { databaseConfig } from "../../config/projectConfig";

const info = ref<GenericRecord>({});
const error = ref("");
async function load() { try { info.value = await getSystemInfo(); error.value = ""; } catch (err) { error.value = err instanceof Error ? err.message : "Falha ao consultar banco."; } }
onMounted(load);
</script>

<template>
  <BasePage title="Banco de dados" subtitle="Status e configuração de banco, mantendo SQLite como padrão do template.">
    <template #actions><button class="secondary" @click="load">Testar/atualizar</button></template>
    <div v-if="error" class="alert error">{{ error }}</div>
    <BaseSectionCard title="Conexão atual">
      <div class="info-grid compact-info">
        <div class="info-item"><strong>Driver</strong><code>{{ databaseConfig.driver }}</code></div>
        <div class="info-item"><strong>Status</strong><code>Disponível via comandos locais</code></div>
        <div class="info-item"><strong>Caminho SQLite</strong><code>{{ info.db_path || databaseConfig.sqlite.path }}</code></div>
        <div class="info-item"><strong>Diretório de dados</strong><code>{{ info.data_dir || '-' }}</code></div>
      </div>
    </BaseSectionCard>
    <BaseSectionCard title="Drivers de banco suportados">
      <div class="module-chip-grid">
        <span class="module-chip enabled">SQLite padrão funcional</span>
        <span class="module-chip enabled">MySQL/MariaDB por feature Rust mysql-db</span>
        <span class="module-chip enabled">PostgreSQL por feature Rust postgres-db</span>
        <span class="module-chip disabled">Firebird fora do escopo por compatibilidade</span>
      </div>
    </BaseSectionCard>
  </BasePage>
</template>
