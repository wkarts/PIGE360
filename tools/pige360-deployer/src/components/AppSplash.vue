<script setup lang="ts">
import { dismissSplash, splashState } from "../services/splash";
</script>

<template>
  <Teleport to="body">
    <div class="splash-stack" aria-live="polite" aria-atomic="true">
      <div
        v-for="item in splashState.messages"
        :key="item.id"
        class="splash-item"
        :class="`splash-${item.tone}`"
        role="status"
      >
        <span class="splash-text">{{ item.text }}</span>
        <button type="button" class="splash-close" @click="dismissSplash(item.id)">×</button>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.splash-stack {
  position: fixed;
  top: 14px;
  right: 16px;
  z-index: 2147483000;
  display: grid;
  gap: 10px;
  width: min(560px, calc(100vw - 24px));
  max-width: 100vw;
  pointer-events: none;
}

.splash-item {
  pointer-events: auto;
  border-radius: 10px;
  border: 1px solid transparent;
  padding: 10px 12px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.18);
  animation: splash-in 160ms ease-out;
  overflow: hidden;
}

.splash-text {
  flex: 1;
  min-width: 0;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.4;
}

.splash-success {
  background: #ecfdf5;
  border-color: #86efac;
  color: #14532d;
}

.splash-error {
  background: #fef2f2;
  border-color: #fca5a5;
  color: #7f1d1d;
}

.splash-info {
  background: #eff6ff;
  border-color: #93c5fd;
  color: #1e3a8a;
}

.splash-warning {
  background: #fffbeb;
  border-color: #fcd34d;
  color: #92400e;
}

.splash-close {
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 18px;
  line-height: 1;
  color: inherit;
  flex-shrink: 0;
  margin-top: 1px;
}

@keyframes splash-in {
  from {
    opacity: 0;
    transform: translateY(-6px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
