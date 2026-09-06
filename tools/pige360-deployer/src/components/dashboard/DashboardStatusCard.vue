<script setup lang="ts">
defineProps<{ title: string; status: string; description?: string; tone?: 'success' | 'warning' | 'error' | 'info' | 'neutral' }>();
</script>

<template>
  <article class="card status-card" :class="tone || 'neutral'">
    <div class="status-dot" />
    <div>
      <strong>{{ title }}</strong>
      <span>{{ status }}</span>
      <p v-if="description" class="muted-text">{{ description }}</p>
    </div>
  </article>
</template>
