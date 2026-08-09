<script setup lang="ts">
import type { NavigationItem } from "./index";
defineProps<{ title: string; items: NavigationItem[]; tenantSurface?: boolean }>();
</script>
<template>
  <div class="app-shell" :data-tenant-surface="tenantSurface ? 'true' : 'false'">
    <aside><slot name="brand"/><nav><a v-for="item in items" :key="item.route" :href="item.route">{{ item.label }}</a></nav></aside>
    <main><header><h1>{{ title }}</h1><slot name="actions"/></header><slot/></main>
  </div>
</template>
