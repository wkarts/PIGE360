<script setup lang="ts">
defineProps<{ items: { label: string; value: string; status?: 'success' | 'warning' | 'error' | 'info' | 'neutral' }[] }>();
</script>

<template>
  <section class="card health-panel">
    <header class="section-card-header"><h3>Saúde do sistema</h3></header>
    <div class="health-list">
      <div v-for="item in items" :key="item.label" class="health-item" :class="item.status || 'neutral'">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
      </div>
    </div>
  </section>
</template>
