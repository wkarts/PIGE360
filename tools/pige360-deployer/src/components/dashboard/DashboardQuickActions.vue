<script setup lang="ts">
import IconSymbol from "../base/IconSymbol.vue";

defineProps<{ actions: { title: string; route?: string; icon?: string; disabled?: boolean }[] }>();
</script>

<template>
  <section class="card quick-actions-card">
    <header class="section-card-header"><h3>Atalhos rápidos</h3></header>
    <div class="quick-actions-grid">
      <RouterLink v-for="action in actions" :key="action.title" :to="action.route || '/'" class="quick-action" :class="{ disabled: action.disabled }">
        <span class="quick-action-icon"><IconSymbol :name="action.icon || 'circle'" :size="20" /></span>
        <strong>{{ action.title }}</strong>
      </RouterLink>
    </div>
  </section>
</template>
