<script setup lang="ts">
defineProps<{ rows: { title: string; subtitle?: string; tone?: string }[] }>();
</script>

<template>
  <section class="card recent-events-card">
    <header class="section-card-header"><h3>Últimos eventos</h3></header>
    <div v-if="rows.length" class="recent-list">
      <div v-for="row in rows" :key="row.title + row.subtitle" class="recent-row">
        <strong>{{ row.title }}</strong>
        <span>{{ row.subtitle }}</span>
      </div>
    </div>
    <div v-else class="empty-state compact"><strong>Nenhum evento recente.</strong></div>
  </section>
</template>
