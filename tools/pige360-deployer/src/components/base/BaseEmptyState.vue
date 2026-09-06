<script setup lang="ts">
defineProps<{ title?: string; message?: string; icon?: string }>();
</script>

<template>
  <div class="empty-state">
    <div class="empty-icon">{{ icon || '∅' }}</div>
    <strong>{{ title || 'Nenhum registro encontrado' }}</strong>
    <p>{{ message || 'Ajuste os filtros ou cadastre um novo registro.' }}</p>
    <slot />
  </div>
</template>
