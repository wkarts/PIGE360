<script setup lang="ts">
import IconSymbol from "./IconSymbol.vue";

withDefaults(defineProps<{
  title: string;
  subtitle?: string;
  eyebrow?: string;
  icon?: string;
  iconSize?: number;
}>(), {
  subtitle: "",
  eyebrow: "PIGE360 Deployer",
  icon: "file",
  iconSize: 20,
});
</script>

<template>
  <div class="app-page-titlebar dashboard-command-center">
    <div class="dashboard-command-title">
      <div class="dashboard-command-icon">
        <IconSymbol :name="icon" :size="iconSize" />
      </div>
      <div>
        <p v-if="eyebrow" class="eyebrow">{{ eyebrow }}</p>
        <h2>{{ title }}</h2>
        <p v-if="subtitle">{{ subtitle }}</p>
      </div>
    </div>
    <div v-if="$slots.actions" class="actions">
      <slot name="actions" />
    </div>
  </div>
</template>
