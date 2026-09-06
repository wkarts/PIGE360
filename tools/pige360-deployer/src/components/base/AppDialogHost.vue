<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import type { AppDialogRequest } from "../../services/dialog";
import IconSymbol from "./IconSymbol.vue";

const queue = ref<AppDialogRequest[]>([]);
const current = computed(() => queue.value[0] || null);

function onDialogRequest(event: Event) {
  const detail = (event as CustomEvent<AppDialogRequest>).detail;
  if (!detail?.resolve) return;
  queue.value.push(detail);
}

function close(value: boolean) {
  const item = current.value;
  if (!item) return;
  item.resolve(value);
  queue.value.shift();
}

function handleKeydown(event: KeyboardEvent) {
  if (!current.value) return;
  if (event.key === "Escape") {
    event.preventDefault();
    close(false);
  }
}

onMounted(() => {
  window.addEventListener("pige360-deployer:dialog", onDialogRequest as EventListener);
  window.addEventListener("keydown", handleKeydown);
});

onBeforeUnmount(() => {
  window.removeEventListener("pige360-deployer:dialog", onDialogRequest as EventListener);
  window.removeEventListener("keydown", handleKeydown);
});
</script>

<template>
  <Teleport to="body">
    <div v-if="current" class="app-dialog-overlay" @click.self="close(false)">
      <section class="app-dialog-card" :class="{ danger: current.danger }" role="dialog" aria-modal="true">
        <header class="app-dialog-header">
          <span class="app-dialog-icon" :class="{ danger: current.danger }">
            <IconSymbol :name="current.danger ? 'warning' : current.kind === 'confirm' ? 'alert' : 'info'" :size="20" />
          </span>
          <div>
            <h3>{{ current.title }}</h3>
            <p v-if="current.detail">{{ current.detail }}</p>
          </div>
        </header>

        <div class="app-dialog-body">
          <p>{{ current.message }}</p>
        </div>

        <footer class="app-dialog-footer">
          <button v-if="current.kind === 'confirm'" class="secondary" type="button" @click="close(false)">
            {{ current.cancelText }}
          </button>
          <button :class="current.danger ? 'danger' : 'primary'" type="button" autofocus @click="close(true)">
            {{ current.confirmText }}
          </button>
        </footer>
      </section>
    </div>
  </Teleport>
</template>
