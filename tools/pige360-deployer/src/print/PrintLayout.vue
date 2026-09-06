<script setup lang="ts">
import { appBranding } from "../config/appBranding";

defineProps<{ title: string; company?: string; generatedAt?: string }>();
</script>

<template>
  <article class="print-document">
    <header class="print-header">
      <div>
        <h1>{{ title }}</h1>
        <p>{{ company || appBranding.appName }}</p>
      </div>
      <span>{{ generatedAt || new Date().toLocaleString('pt-BR') }}</span>
    </header>
    <main class="print-body"><slot /></main>
    <footer class="print-footer">Documento gerado pelo {{ appBranding.appName }}</footer>
  </article>
</template>
