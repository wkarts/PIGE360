<script setup lang="ts">
defineProps<{ title: string; subtitle?: string; empty?: boolean }>();
</script>

<template>
  <section class="card chart-card">
    <header class="section-card-header"><div><h3>{{ title }}</h3><p v-if="subtitle" class="muted-text">{{ subtitle }}</p></div></header>
    <div v-if="empty" class="empty-state compact"><strong>Sem dados suficientes.</strong><p>Este bloco fica pronto para gráficos do projeto.</p></div>
    <div v-else class="chart-placeholder"><slot>Gráfico configurável</slot></div>
  </section>
</template>
