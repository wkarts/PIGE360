<script setup lang="ts">
defineProps<{ title?: string; subtitle?: string; compact?: boolean }>();
</script>

<template>
  <section class="card section-card" :class="{ compact }">
    <header v-if="title || subtitle || $slots.actions" class="section-card-header">
      <div>
        <h3 v-if="title">{{ title }}</h3>
        <p v-if="subtitle" class="muted-text">{{ subtitle }}</p>
      </div>
      <div v-if="$slots.actions" class="actions"><slot name="actions" /></div>
    </header>
    <slot />
  </section>
</template>
