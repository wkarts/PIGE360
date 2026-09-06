<script setup lang="ts">
defineProps<{ title?: string }>();
</script>

<template>
  <section class="card filter-bar">
    <div v-if="title" class="filter-title">{{ title }}</div>
    <div class="filter-grid"><slot /></div>
    <div v-if="$slots.actions" class="actions filter-actions"><slot name="actions" /></div>
  </section>
</template>
