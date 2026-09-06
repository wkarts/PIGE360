<script setup lang="ts">
defineProps<{ open: boolean; title: string; subtitle?: string; size?: 'sm' | 'md' | 'lg' | 'xl' }>();
const emit = defineEmits<{ close: []; save: [] }>();
</script>

<template>
  <div v-if="open" class="app-modal-overlay" @click.self="emit('close')">
    <div class="app-modal-card" :class="`app-modal-${size || 'md'}`">
      <header class="app-modal-header">
        <div>
          <h3>{{ title }}</h3>
          <p v-if="subtitle" class="muted-text">{{ subtitle }}</p>
        </div>
        <button class="icon-button" @click="emit('close')">×</button>
      </header>
      <div class="app-modal-body"><slot /></div>
      <footer class="app-modal-footer">
        <button class="secondary" @click="emit('close')">Cancelar</button>
        <button class="primary" @click="emit('save')">Salvar</button>
      </footer>
    </div>
  </div>
</template>
