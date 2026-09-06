<script setup lang="ts">
defineProps<{ modules: { label: string; enabled: boolean }[] }>();
</script>

<template>
  <section class="card module-status-card">
    <header class="section-card-header"><h3>Módulos do projeto</h3></header>
    <div class="module-chip-grid">
      <span v-for="module in modules" :key="module.label" class="module-chip" :class="module.enabled ? 'enabled' : 'disabled'">
        {{ module.label }}: {{ module.enabled ? 'ativo' : 'oculto' }}
      </span>
    </div>
  </section>
</template>
