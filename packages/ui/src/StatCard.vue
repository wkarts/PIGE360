<script setup lang="ts">
defineProps<{ label: string; value: string | number; variation?: string; state?: 'normal'|'warning'|'critical' }>();
</script>
<template><article class="stat-card" :data-state="state || 'normal'"><span>{{ label }}</span><strong>{{ value }}</strong><small v-if="variation">{{ variation }}</small></article></template>
