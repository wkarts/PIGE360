import { createRouter, createWebHashHistory, RouteRecordRaw } from "vue-router";
import AppLayout from "../layouts/AppLayout.vue";
import DeploymentPage from "../pages/DeploymentPage.vue";
import EntityPage from "../pages/EntityPage.vue";
import EmpresaPage from "../pages/EmpresaPage.vue";
import UsuarioPage from "../pages/UsuarioPage.vue";
import PerfilPage from "../pages/PerfilPage.vue";
import LoginPage from "../pages/LoginPage.vue";
import FirstAccessPage from "../pages/FirstAccessPage.vue";
import SystemPage from "../pages/SystemPage.vue";
import LicensingPage from "../pages/LicensingPage.vue";
import AboutPage from "../pages/AboutPage.vue";
import AppLogsPage from "../pages/AppLogsPage.vue";
import UserGuidePage from "../pages/UserGuidePage.vue";
import TechnicalSheetPage from "../pages/optional/TechnicalSheetPage.vue";
import SyncPage from "../pages/optional/SyncPage.vue";
import InternalApiPage from "../pages/optional/InternalApiPage.vue";
import ScalarDocsPage from "../pages/optional/ScalarDocsPage.vue";
import WebhookServicePage from "../pages/optional/WebhookServicePage.vue";
import WebSocketServicePage from "../pages/optional/WebSocketServicePage.vue";
import DatabasePage from "../pages/optional/DatabasePage.vue";
import IntegrationPage from "../pages/optional/IntegrationPage.vue";
import PrintPreviewPage from "../pages/PrintPreviewPage.vue";
import RuntimeDiagnosticsPage from "../pages/RuntimeDiagnosticsPage.vue";
import { entityConfigs } from "../config/entities";
import { appFeatures } from "../config/projectConfig";
import { isFeatureEnabled } from "../config/navigation";
import { useSessionStore } from "../stores/session";
import { logAppError, logAppInfo, logAppWarning } from "../services/logger";
import { isNativeMobileRuntime } from "../core/runtime/RuntimeProvider";

const permissionByEntity: Record<string, string> = {
  departamentos: "cadastros:view",
  funcoes: "cadastros:view",
  centro_custos: "cadastros:view",
  clientes: "cadastros:view",
  fornecedores: "cadastros:view",
  produtos: "cadastros:view"
};

const genericEntityRoutes: RouteRecordRaw[] = Object.values(entityConfigs).map((entity) => ({
  path: entity.route.replace(/^\//, ""),
  component: EntityPage,
  props: { entityKey: entity.key },
  meta: { permission: permissionByEntity[entity.key] ?? "cadastros:view", feature: "genericEntities" }
}));

const routes: RouteRecordRaw[] = [
  { path: "/login", component: LoginPage },
  { path: "/primeiro-acesso", component: FirstAccessPage },
  { path: "/print-preview", component: PrintPreviewPage, meta: { desktopOnly: true } },
  {
    path: "/",
    component: AppLayout,
    children: [
      { path: "", component: DeploymentPage, meta: { permission: "dashboard:view" } },
      { path: "empresas", component: EmpresaPage, meta: { permission: "empresas:view" } },
      { path: "usuarios", component: UsuarioPage, meta: { permission: "usuarios:view" } },
      { path: "perfis", component: PerfilPage, meta: { permission: "perfis:view" } },
      ...genericEntityRoutes,
      { path: "sistema", component: SystemPage, meta: { permission: "config:view", feature: "systemSettings", desktopOnly: true } },
      { path: "sistema/banco", component: DatabasePage, meta: { permission: "config:view", feature: "databaseSettings" } },
      { path: "licenciamento", component: LicensingPage, meta: { permission: "config:view", feature: "licensing" } },
      { path: "sobre", component: AboutPage, meta: { feature: "about" } },
      { path: "logs", component: AppLogsPage, meta: { permission: "config:view", feature: "logs" } },
      { path: "runtime", component: RuntimeDiagnosticsPage, meta: { permission: "config:view", desktopOnly: true } },
      { path: "documentacao/guia", component: UserGuidePage, meta: { feature: "userGuide" } },
      { path: "ficha-tecnica", component: TechnicalSheetPage, meta: { permission: "config:view", feature: "technicalSheet" } },
      { path: "sincronizacao", component: SyncPage, meta: { permission: "config:view", feature: "sync" } },
      { path: "api-interna", component: InternalApiPage, meta: { permission: "config:view", feature: "internalApi", desktopOnly: true } },
      { path: "documentacao/scalar", component: ScalarDocsPage, meta: { permission: "config:view", feature: "scalarDocs", desktopOnly: true } },
      { path: "webhooks", component: WebhookServicePage, meta: { permission: "config:view", feature: "webhookService", desktopOnly: true } },
      { path: "websocket", component: WebSocketServicePage, meta: { permission: "config:view", feature: "websocketService", desktopOnly: true } },
      { path: "integracoes", component: IntegrationPage, meta: { permission: "config:view", feature: "integrations" } },
    ]
  }
];

const router = createRouter({ history: createWebHashHistory(), routes });

router.beforeEach(async (to) => {
  const session = useSessionStore();
  if (!session.initialized) {
    try {
      await session.restore();
    } catch (error) {
      logAppError("router", "Falha ao restaurar sessão durante navegação.", {
        to: to.fullPath,
        error: error instanceof Error ? error.message : String(error),
      });
      session.clearAuthState();
    }
  }

  const publicPaths = ["/login"];
  if (!publicPaths.includes(to.path) && !session.isAuthenticated) {
    logAppWarning("router", "Navegação bloqueada por ausência de autenticação.", { to: to.fullPath });
    return "/login";
  }
  if (to.path === "/login" && session.isAuthenticated) return "/";
  if (session.isAuthenticated && session.user?.senha_provisoria && to.path !== "/primeiro-acesso") {
    return "/primeiro-acesso";
  }
  if (to.path === "/primeiro-acesso" && session.isAuthenticated && !session.user?.senha_provisoria) {
    return "/";
  }

  if (to.meta?.desktopOnly === true && isNativeMobileRuntime()) {
    logAppWarning("router", "Rota exclusiva do runtime desktop bloqueada no mobile nativo.", {
      to: to.fullPath,
    });
    return "/";
  }

  const requiredFeature = to.meta?.feature as keyof typeof appFeatures | undefined;
  if (!isFeatureEnabled(requiredFeature)) {
    logAppWarning("router", "Rota bloqueada porque o módulo está desativado.", { to: to.fullPath, feature: requiredFeature });
    return "/";
  }

  const requiredPermission = to.meta?.permission as string | undefined;
  if (requiredPermission && !session.can(requiredPermission)) {
    logAppWarning("router", "Navegação bloqueada por permissão insuficiente.", {
      to: to.fullPath,
      permission: requiredPermission,
      user: session.user?.login,
    });
    return "/";
  }

  return true;
});

router.afterEach((to) => {
  const session = useSessionStore();
  logAppInfo("navigation", "Rota carregada.", {
    to: to.fullPath,
    authenticated: session.isAuthenticated,
    user: session.user?.login ?? null,
  });
});

router.onError((error) => {
  logAppError("router", "Erro interno de roteamento.", {
    error: error instanceof Error ? error.message : String(error),
  });
});

export default router;
