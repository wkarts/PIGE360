<script setup lang="ts">
import { appBranding } from "../config/appBranding";
</script>

<template>
  <div class="print-preview-shell">
    <div class="print-document">
      <header>
        <strong>{{ appBranding.appName }}</strong>
        <span>{{ new Date().toLocaleString() }}</span>
      </header>
      <main>
        <h1>Pré-visualização de impressão</h1>
        <p>Janela independente para relatórios e documentos. Fechar esta janela não fecha a aplicação principal.</p>
      </main>
      <footer>Documento gerado pela aplicação.</footer>
    </div>
  </div>
</template>
