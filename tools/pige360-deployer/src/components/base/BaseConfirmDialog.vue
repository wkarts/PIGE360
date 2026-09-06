<script setup lang="ts">
defineProps<{ open: boolean; title?: string; message?: string; danger?: boolean }>();
const emit = defineEmits<{ confirm: []; cancel: [] }>();
</script>

<template>
  <div v-if="open" class="app-modal-overlay" @click.self="emit('cancel')">
    <div class="app-modal-card app-modal-sm">
      <header class="app-modal-header">
        <h3>{{ title || 'Confirmar ação' }}</h3>
      </header>
      <div class="app-modal-body">
        <p>{{ message || 'Deseja continuar?' }}</p>
      </div>
      <footer class="app-modal-footer">
        <button class="secondary" @click="emit('cancel')">Cancelar</button>
        <button :class="danger ? 'danger' : 'primary'" @click="emit('confirm')">Confirmar</button>
      </footer>
    </div>
  </div>
</template>
