<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, watch } from 'vue';

const props = defineProps<{
  open: boolean;
  title: string;
  subtitle?: string;
  width?: 'sm' | 'md' | 'lg' | 'xl';
  closeOnBackdrop?: boolean;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
}>();

const widthClass = computed(() => `app-modal-${props.width || 'lg'}`);

function close() {
  emit('close');
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && props.open) {
    close();
  }
}

function toggleBodyLock(locked: boolean) {
  if (typeof document === 'undefined') return;
  document.body.style.overflow = locked ? 'hidden' : '';
}

watch(
  () => props.open,
  (value) => toggleBodyLock(value),
  { immediate: true }
);

onMounted(() => {
  window.addEventListener('keydown', onKeydown);
});

onBeforeUnmount(() => {
  toggleBodyLock(false);
  window.removeEventListener('keydown', onKeydown);
});
</script>

<template>
  <teleport to="body">
    <div v-if="open" class="app-modal-overlay" @click="closeOnBackdrop !== false ? close() : undefined">
      <div class="app-modal-card" :class="widthClass" @click.stop>
        <div class="app-modal-header">
          <div>
            <div class="app-modal-title">{{ title }}</div>
            <div v-if="subtitle" class="app-modal-subtitle">{{ subtitle }}</div>
          </div>
          <button class="secondary app-modal-close" type="button" @click="close">Fechar</button>
        </div>
        <div class="app-modal-body">
          <slot />
        </div>
      </div>
    </div>
  </teleport>
</template>
