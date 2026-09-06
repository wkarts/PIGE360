<script setup lang="ts">
import BasePage from "../components/base/BasePage.vue";
import BaseSectionCard from "../components/base/BaseSectionCard.vue";
import { appFeatures } from "../config/projectConfig";
</script>

<template>
  <BasePage title="Guia do usuário" subtitle="Guia funcional ajustado aos módulos ativos neste projeto.">
    <div class="grid columns-2 mobile-columns-1">
      <BaseSectionCard title="Primeiro acesso">
        <ul class="summary-list">
          <li>Acesse com o usuário inicial documentado para implantação.</li>
          <li>Troque a senha no primeiro uso operacional.</li>
          <li>Cadastre empresas e vincule usuários aos perfis corretos.</li>
        </ul>
      </BaseSectionCard>
      <BaseSectionCard title="Controle de acesso">
        <ul class="summary-list">
          <li>Usuários controlam credenciais e vínculos.</li>
          <li>Perfis organizam permissões por função.</li>
          <li>Menus respeitam permissões e módulos ativos.</li>
        </ul>
      </BaseSectionCard>
      <BaseSectionCard v-if="appFeatures.licensing" title="Licenciamento">
        <p class="muted-text">O licenciamento pode operar local/offline e pode ser ocultado em projetos que não usam licença.</p>
      </BaseSectionCard>
      <BaseSectionCard v-if="appFeatures.logs" title="Logs">
        <p class="muted-text">Use logs para auditoria técnica, diagnóstico de sessão, navegação e falhas administrativas.</p>
      </BaseSectionCard>
      <BaseSectionCard v-if="appFeatures.internalApi" title="API interna">
        <p class="muted-text">A API interna expõe health check, versão, status e endpoints próprios do projeto quando habilitada.</p>
      </BaseSectionCard>
      <BaseSectionCard v-if="appFeatures.tray" title="Tray icon">
        <p class="muted-text">O tray pode controlar restauração da janela, API interna e serviços quando o projeto habilitar esses recursos.</p>
      </BaseSectionCard>
    </div>
  </BasePage>
</template>
