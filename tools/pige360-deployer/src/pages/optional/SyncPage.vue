<script setup lang="ts">
import BasePage from "../../components/base/BasePage.vue";
import BaseSectionCard from "../../components/base/BaseSectionCard.vue";
</script>

<template>
  <BasePage title="Sincronização" subtitle="Estrutura opcional para filas, pendências, erros e reprocessamentos.">
    <div class="dashboard-metrics-grid">
      <div class="kpi"><strong>Pendências</strong><span>0</span></div>
      <div class="kpi"><strong>Erros</strong><span>0</span></div>
      <div class="kpi"><strong>Última sync</strong><span>—</span></div>
      <div class="kpi"><strong>Status</strong><span>Inativo</span></div>
    </div>
    <BaseSectionCard title="Fila de sincronização" subtitle="Nenhuma fila implementada neste template base.">
      <div class="empty-state"><strong>Nenhuma pendência.</strong><p>Projetos específicos podem plugar filas e workers sem alterar o core visual.</p></div>
    </BaseSectionCard>
  </BasePage>
</template>
