export type RuntimeMode = "desktop" | "headless-api" | "windows-service" | "linux-service" | "cli" | "worker";
export type SidebarDefaultState = "expanded" | "collapsed";
export type MenuBehavior = "single-open" | "multi-open" | "free";
export type SubmenuVisualMode = "default" | "tree" | "compact" | "indented";
export type DatabaseDriver = "sqlite" | "mysql" | "postgres";
export type WorkspaceTabsMode = "enabled" | "disabled";

export const projectConfig = {
  app: {
    name: "PIGE360 Deployer",
    shortName: "PIGE360",
    productName: "PIGE360 Deployer",
    windowTitle: "PIGE360 Deployer",
    subtitle: "ARGWS • Tauri • Rust • SSH • Docker",
    description: "Implantador multiplataforma para distribuições develop, prerelease e stable do PIGE360",
    version: "1.1.2",
    mode: "desktop" as RuntimeMode,
    identifier: "br.com.pige360.deployer",
    developer: "ARGWS",
    localDataDir: "pige360-deployer",
    storagePrefix: "pige360-deployer",
    supportUrl: "https://pige360.com.br",
    documentationUrl: "",
  },
  features: {
    licensing: false,
    about: true,
    userGuide: true,
    logs: true,
    systemSettings: false,
    genericEntities: false,
    technicalSheet: false,
    sync: false,
    internalApi: false,
    scalarDocs: false,
    webhookService: false,
    websocketService: false,
    databaseSettings: false,
    integrations: false,
    tray: true,
    windowsService: false,
    linuxService: false,
    autoStartWithWindows: false,
    headlessMode: false,
    printPreview: false,
  },
  defaultAdmin: {
    enabled: true,
    username: "admin",
    bootstrapFile: ".bootstrap-admin.local",
    forcePasswordChangeOnFirstLogin: true,
  },
  database: {
    driver: "sqlite" as DatabaseDriver,
    sqlite: { path: "pige360-deployer.db" },
    mysql: { host: "127.0.0.1", port: 3306, database: "pige360_deployer", username: "root", password: "" },
    postgres: { host: "127.0.0.1", port: 5432, database: "pige360_deployer", username: "postgres", password: "" },
    firebird: {
      supported: false,
      scope: "out-of-scope",
      note: "Firebird ignorado por compatibilidade nesta etapa.",
    },
  },
  dashboard: {
    enabled: false,
    demoMode: false,
    showSystemCards: true,
    showBusinessCards: true,
    showIntegrationCards: true,
    showCharts: true,
    blocks: {
      systemHealth: true,
      userStats: true,
      companyStats: true,
      licensingStatus: false,
      internalApiStatus: true,
      integrationStatus: true,
      syncStatus: true,
      financialSummary: false,
      customBusinessCards: false,
    },
  },
  api: {
    enabled: false,
    autoStart: false,
    restartOnConfigChange: true,
    host: "127.0.0.1",
    port: 61001,
    baseUrl: "http://127.0.0.1:61001",
    scalarUrl: "http://127.0.0.1:61001/docs",
    docsPath: "/docs",
    timeoutMs: 8000,
    logMode: "normal",
    openScalarAfterStart: false,
    docs: true,
    docsProvider: "scalar" as const,
    security: {
      bindHost: "127.0.0.1",
      allowPublicNetwork: false,
      requireToken: false,
      tokenHeader: "X-App-Token",
      corsEnabled: false,
      rateLimitEnabled: false,
      docsPublic: false,
      docsPublicLocal: true,
    },
  },
  sidebar: {
    defaultState: "expanded" as SidebarDefaultState,
    allowCollapse: true,
    menuBehavior: "single-open" as MenuBehavior,
    keepActiveParentExpanded: true,
    collapsePreviousOnNewSelection: true,
    persistUserMenuState: false,
    showSubmenuTreeLine: true,
    submenuVisualMode: "tree" as SubmenuVisualMode,
  },
  workspace: {
    tabsMode: "enabled" as WorkspaceTabsMode,
    persistTabs: true,
    maxTabs: 12,
    mobileTabs: false,
    mobileBreakpoint: 1180,
  },
  mobile: {
    enabled: false,
    frontend: "local-bundled" as const,
    localDatabase: "sqlite" as const,
    standaloneSupported: false,
    restClientSupported: false,
    remoteWebView: false,
    synchronization: "product-defined" as const,
  },
  services: {
    webhook: {
      enabled: false,
      host: "0.0.0.0",
      port: 61003,
      basePath: "/webhooks",
      tokenRequired: true,
      tokenHeader: "X-Webhook-Token",
    },
    websocket: {
      enabled: false,
      host: "0.0.0.0",
      port: 61004,
      path: "/ws",
      tokenRequired: true,
      tokenQuery: "token",
      tokenHeader: "X-WebSocket-Token",
    },
  },
  tray: {
    enabled: true,
    minimizeToTray: true,
    closeToTray: false,
    alwaysUseTray: false,
    askBeforeExit: true,
    showServiceControls: true,
    showInternalApiStatus: true,
  },
  startup: {
    enabled: false,
    mode: "disabled" as "disabled" | "user-login" | "machine-startup",
  },
  integrations: {
    enabled: false,
    allowExternalApis: false,
    allowWebhooks: false,
    allowTokens: false,
    allowRequestLogs: false,
    allowRetryQueue: false,
  },
};

export const appFeatures = projectConfig.features;
export const sidebarConfig = projectConfig.sidebar;
export const workspaceConfig = projectConfig.workspace;
export const dashboardConfig = projectConfig.dashboard;
export const internalApiConfig = projectConfig.api;
export const serviceConfig = projectConfig.services;
export const databaseConfig = projectConfig.database;

export const trayConfig = projectConfig.tray;
export const startupConfig = projectConfig.startup;
export const integrationsConfig = projectConfig.integrations;
