<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { getBootstrap } from "../services/crud";
import { appFeatures, dashboardConfig, projectConfig } from "../config/projectConfig";
import DashboardMetricCard from "../components/dashboard/DashboardMetricCard.vue";
import DashboardStatusCard from "../components/dashboard/DashboardStatusCard.vue";
import DashboardQuickActions from "../components/dashboard/DashboardQuickActions.vue";
import DashboardHealthPanel from "../components/dashboard/DashboardHealthPanel.vue";
import DashboardRecentEvents from "../components/dashboard/DashboardRecentEvents.vue";
import DashboardChartCard from "../components/dashboard/DashboardChartCard.vue";
import DashboardModuleStatus from "../components/dashboard/DashboardModuleStatus.vue";
import AppPageTitleBar from "../components/base/AppPageTitleBar.vue";

const loading = ref(false);
const stats = ref<Record<string, unknown>>({});
const error = ref("");
const dashboardCustomizerOpen = ref(false);
const dashboardWidgets = ref({
  metrics: true,
  health: true,
  quickActions: true,
  modules: true,
  recentEvents: true,
  charts: true,
});

function resetDashboardWidgets() {
  dashboardWidgets.value = {
    metrics: true,
    health: true,
    quickActions: true,
    modules: true,
    recentEvents: true,
    charts: true,
  };
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    stats.value = await getBootstrap();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao carregar dashboard.";
  } finally {
    loading.value = false;
  }
}

const modules = computed(() => [
  { label: "Licenciamento", enabled: appFeatures.licensing },
  { label: "API interna", enabled: appFeatures.internalApi },
  { label: "Integrações", enabled: appFeatures.integrations },
  { label: "Sincronização", enabled: appFeatures.sync },
  { label: "Serviço Windows", enabled: appFeatures.windowsService },
  { label: "Serviço Linux", enabled: appFeatures.linuxService },
  { label: "Tray", enabled: appFeatures.tray },
]);

const quickActions = computed(() => [
  { title: "Empresas", route: "/empresas", icon: "building" },
  { title: "Usuários", route: "/usuarios", icon: "users" },
  { title: "Perfis", route: "/perfis", icon: "shield" },
  { title: "Sistema", route: "/sistema", icon: "settings" },
  { title: "Logs", route: "/logs", icon: "clipboard", disabled: !appFeatures.logs },
  { title: "API Interna", route: "/api-interna", icon: "api", disabled: !appFeatures.internalApi },
].filter((item) => !item.disabled));

const recentEvents = computed(() => [
  { title: "Sistema inicializado", subtitle: `${projectConfig.app.mode} · Runtime ativo`, tone: "info" },
  { title: "API interna disponível", subtitle: appFeatures.internalApi ? "Serviço monitorado na topbar" : "Recurso desativado", tone: appFeatures.internalApi ? "success" : "neutral" },
  { title: "Preferências visuais carregadas", subtitle: "Tema e densidade aplicados por usuário", tone: "success" },
  { title: "Base local pronta", subtitle: `${projectConfig.database.driver.toUpperCase()} · ${String(stats.value.database_status || 'ok')}`, tone: "info" },
]);

onMounted(load);
</script>

<template>
  <div class="page-content-scroll dashboard-page">
    <AppPageTitleBar
      title="Dashboard"
      subtitle="Visão geral do sistema, serviços, módulos e indicadores principais."
      eyebrow="PIGE360 Deployer"
      icon="chart"
    >
      <template #actions>
        <button class="secondary" type="button" @click="dashboardCustomizerOpen = !dashboardCustomizerOpen">Personalizar dashboard</button>
        <button class="primary" :disabled="loading" @click="load">{{ loading ? "Atualizando..." : "Atualizar" }}</button>
      </template>
    </AppPageTitleBar>

    <section v-if="dashboardCustomizerOpen" class="dashboard-customizer-panel">
      <div>
        <p class="eyebrow">Personalização da dashboard</p>
        <h3>Widgets visíveis</h3>
        <p>Preferência visual local para organizar a tela inicial sem alterar regras de negócio.</p>
      </div>
      <div class="dashboard-customizer-options">
        <label><input v-model="dashboardWidgets.metrics" type="checkbox" /> Indicadores</label>
        <label><input v-model="dashboardWidgets.health" type="checkbox" /> Saúde do sistema</label>
        <label><input v-model="dashboardWidgets.quickActions" type="checkbox" /> Atalhos rápidos</label>
        <label><input v-model="dashboardWidgets.modules" type="checkbox" /> Módulos do projeto</label>
        <label><input v-model="dashboardWidgets.recentEvents" type="checkbox" /> Últimos eventos</label>
        <label><input v-model="dashboardWidgets.charts" type="checkbox" /> Gráficos</label>
      </div>
      <div class="dashboard-customizer-actions">
        <button class="secondary" type="button" @click="resetDashboardWidgets">Restaurar padrão</button>
        <button class="primary" type="button" @click="dashboardCustomizerOpen = false">Aplicar</button>
      </div>
    </section>

    <div v-if="error" class="alert error">{{ error }}</div>
    <div v-if="loading" class="muted-text">Carregando indicadores reais...</div>

    <section v-if="dashboardWidgets.metrics" class="dashboard-metrics-grid">
      <DashboardMetricCard v-if="dashboardConfig.blocks.companyStats" title="Empresas" :value="Number(stats.empresas || 0)" subtitle="Empresas cadastradas" icon="building" status="info" />
      <DashboardMetricCard v-if="dashboardConfig.blocks.userStats" title="Usuários" :value="Number(stats.usuarios || 0)" subtitle="Usuários locais" icon="user" status="success" />
      <DashboardMetricCard title="Perfis" :value="Number(stats.perfis || 0)" subtitle="Perfis de acesso" icon="lock" status="neutral" />
      <DashboardMetricCard v-if="appFeatures.sync" title="Sync pendente" :value="Number(stats.sync_pendente || 0)" subtitle="Fila de sincronização" icon="sync" status="warning" />
      <DashboardMetricCard v-if="appFeatures.logs" title="Logs de erro hoje" :value="Number(stats.logs_error_today || 0)" subtitle="Erros e críticos registrados hoje" icon="alert" :status="Number(stats.logs_error_today || 0) > 0 ? 'warning' : 'success'" />
      <DashboardMetricCard v-if="appFeatures.integrations" title="Integrações ativas" :value="Number(stats.integrations_active || 0)" :subtitle="`${Number(stats.integrations_total || 0)} integração(ões) cadastrada(s)`" icon="plug" status="info" />
    </section>

    <section class="dashboard-grid-main">
      <DashboardHealthPanel
        v-if="dashboardWidgets.health"
        :items="[
          { label: 'Banco de dados', value: `${projectConfig.database.driver.toUpperCase()} / ${String(stats.database_status || 'ok')}`, status: 'info' },
          { label: 'Modo de execução', value: projectConfig.app.mode, status: 'info' },
          { label: 'API interna', value: appFeatures.internalApi ? String(stats.internal_api_status || 'ativável') : 'desativada neste projeto', status: appFeatures.internalApi ? 'success' : 'neutral' },
          { label: 'Licenciamento', value: appFeatures.licensing ? 'ativo no template' : 'não utilizado', status: appFeatures.licensing ? 'info' : 'neutral' }
        ]"
      />
      <DashboardQuickActions v-if="dashboardWidgets.quickActions" :actions="quickActions" />
      <DashboardModuleStatus v-if="dashboardWidgets.modules" :modules="modules" />
      <DashboardRecentEvents v-if="dashboardWidgets.recentEvents" :rows="recentEvents" />
    </section>

    <section v-if="dashboardConfig.showCharts && dashboardWidgets.charts" class="dashboard-chart-grid">
      <DashboardChartCard title="Eventos por dia" subtitle="Últimos 7 dias">
        <div class="demo-bars-chart" aria-label="Prévia visual de eventos por dia">
          <span style="--h: 44%"><small>27/05</small></span>
          <span style="--h: 58%"><small>28/05</small></span>
          <span style="--h: 82%"><small>29/05</small></span>
          <span style="--h: 63%"><small>30/05</small></span>
          <span style="--h: 54%"><small>31/05</small></span>
          <span style="--h: 76%"><small>01/06</small></span>
          <span style="--h: 36%"><small>02/06</small></span>
        </div>
      </DashboardChartCard>
      <DashboardChartCard title="Logs por severidade" subtitle="Distribuição visual pronta para dados reais">
        <div class="demo-donut-chart">
          <div class="demo-donut"><strong>{{ Number(stats.logs_total || 156) }}</strong><small>total</small></div>
          <ul>
            <li><span class="dot info"></span> Informação <strong>78%</strong></li>
            <li><span class="dot warning"></span> Aviso <strong>13%</strong></li>
            <li><span class="dot error"></span> Erro <strong>5%</strong></li>
            <li><span class="dot critical"></span> Crítico <strong>3%</strong></li>
          </ul>
        </div>
      </DashboardChartCard>
    </section>
  </div>
</template>
