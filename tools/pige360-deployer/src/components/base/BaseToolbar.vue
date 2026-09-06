<script setup lang="ts">
defineProps<{ title?: string; subtitle?: string }>();
</script>

<template>
  <div class="toolbar base-toolbar">
    <div>
      <h2 v-if="title">{{ title }}</h2>
      <div v-if="subtitle" class="muted-text">{{ subtitle }}</div>
    </div>
    <div v-if="$slots.actions" class="actions"><slot name="actions" /></div>
  </div>
</template>
