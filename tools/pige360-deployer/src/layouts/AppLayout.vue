<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { RouterLink, RouterView, useRoute, useRouter } from "vue-router";
import { getAppMeta, getInternalApiStatus } from "../services/crud";
import { useSessionStore } from "../stores/session";
import logoMark from "../assets/branding/logo-mark.png";
import { logAppError, logAppInfo } from "../services/logger";
import AppSwitch from "../components/AppSwitch.vue";
import IconSymbol from "../components/base/IconSymbol.vue";
import { invokeCommand } from "../services/tauri";
import { appConfirm } from "../services/dialog";
import { projectConfig, sidebarConfig, workspaceConfig } from "../config/projectConfig";
import { appBranding, storageKey } from "../config/appBranding";
import { findMenuItemByRoute, visibleMenuItems, type MenuSection } from "../config/navigation";
import {
  applyVisualPreferences,
  defaultVisualPreferences,
  findThemePreset,
  loadCustomVisualThemes,
  loadVisualPreferences,
  MAX_CUSTOM_THEMES_PER_USER,
  saveCustomVisualThemes,
  saveVisualPreferences,
  visualThemePresets,
  type ThemeDensity,
  type ThemeMode,
  type UserCustomVisualTheme,
  type UserVisualPreferences,
  type VisualThemePreset,
} from "../visual-core/theme";

const session = useSessionStore();
const router = useRouter();
const route = useRoute();

const meta = reactive({ version: projectConfig.app.version, build_hash: "dev" });
const now = ref(new Date());
const isDarkMode = ref(false);
const desktopSidebarOpen = ref(sidebarConfig.defaultState === "expanded");
const mobileSidebarOpen = ref(false);
const sidebarOpen = computed({
  get: () => isMobileViewport.value ? mobileSidebarOpen.value : desktopSidebarOpen.value,
  set: (value: boolean) => {
    if (isMobileViewport.value) mobileSidebarOpen.value = value;
    else desktopSidebarOpen.value = value;
  },
});
const brandLogoFailed = ref(false);
const refreshToken = ref(0);
const tabScrollRef = ref<HTMLElement | null>(null);
const canScrollTabsLeft = ref(false);
const canScrollTabsRight = ref(false);
const isMobileViewport = ref(false);
const workspaceTabsEnabled = ref(workspaceConfig.tabsMode === "enabled");
const userMenuOpen = ref(false);
const globalSearch = ref("");
const globalSearchFocused = ref(false);
const globalSearchInputRef = ref<HTMLInputElement | null>(null);
const userMenuRef = ref<HTMLElement | null>(null);
const visualMode = ref<ThemeMode>(defaultVisualPreferences.mode);
const visualPreset = ref(defaultVisualPreferences.preset);
const visualDensity = ref<ThemeDensity>(defaultVisualPreferences.density);
const customThemes = ref<UserCustomVisualTheme[]>([]);
const customThemeName = ref("Meu tema");
const customPrimaryColor = ref("#2563eb");
const customAccentColor = ref("#0891b2");
const customSidebarStartColor = ref("#ffffff");
const customSidebarEndColor = ref("#eef6ff");
const customFontFamily = ref("Inter, Segoe UI, Arial, sans-serif");
const customFontScale = ref(1);
const customTitleScale = ref(1);
const customTextColor = ref("#0f172a");
const customMutedColor = ref("#64748b");
const customThemeActive = ref(true);
const themeImportInputRef = ref<HTMLInputElement | null>(null);
const themeManagerOpen = ref(false);
const editingCustomThemeId = ref<string | null>(null);
const themeManagerMessage = ref("");

type ServiceKey = "api" | "webhook" | "websocket";
interface TopbarServiceStatus {
  key: ServiceKey;
  label: string;
  running: boolean;
  host?: string;
  port?: number | string;
  path?: string;
  hint: string;
}

const serviceStatuses = reactive<Record<ServiceKey, TopbarServiceStatus>>({
  api: { key: "api", label: "API", running: false, hint: "API Interna: aguardando leitura do status." },
  webhook: { key: "webhook", label: "Webhook", running: false, hint: "Webhook Service: aguardando leitura do status." },
  websocket: { key: "websocket", label: "WebSocket", running: false, hint: "WebSocket Service: aguardando leitura do status." },
});

interface WorkspaceTab {
  key: string;
  route: string;
  fullPath: string;
  title: string;
  eyebrow: string;
  description: string;
  pinned?: boolean;
}

const workspaceTabs = ref<WorkspaceTab[]>([]);
let timer: number | undefined;
let tabStateTimer: number | undefined;
let serviceStatusTimer: number | undefined;
let sessionMonitorTimer: number | undefined;
let sessionMonitorBusy = false;

const MENU_STATE_KEY = storageKey("menu-state");
const WORKSPACE_TABS_KEY = storageKey("workspace-tabs");
const WORKSPACE_TABS_ENABLED_KEY = storageKey("workspace-tabs-enabled");



function iconNameForRoute(routePath: string): string {
  const normalized = canonicalTabKey(routePath);
  const icons: Record<string, string> = {
    "/": "home",
    "/empresas": "building",
    "/departamentos": "department",
    "/funcoes": "briefcase",
    "/centros-custo": "target",
    "/clientes": "customer",
    "/fornecedores": "supplier",
    "/produtos": "package",
    "/usuarios": "users",
    "/perfis": "shield",
    "/logs": "clipboard",
    "/sistema": "settings",
    "/banco-dados": "database",
    "/sistema/banco": "database",
    "/licenciamento": "key",
    "/runtime": "activity",
    "/diagnosticos": "activity",
    "/api-interna": "api",
    "/documentacao/scalar": "docs",
    "/webhooks": "webhook",
    "/websocket": "websocket",
    "/integracoes": "plug",
    "/sincronizacao": "sync",
    "/ficha-tecnica": "file",
    "/sobre": "info",
    "/documentacao/guia": "book",
  };
  return icons[normalized] || "circle";
}


function readMenuState() {
  if (!sidebarConfig.persistUserMenuState || typeof window === "undefined") return null;
  try { return JSON.parse(window.localStorage.getItem(MENU_STATE_KEY) || "null"); } catch { return null; }
}
function readWorkspaceTabsPreference(): boolean {
  if (typeof window === "undefined") return workspaceConfig.tabsMode === "enabled";
  const stored = window.localStorage.getItem(WORKSPACE_TABS_ENABLED_KEY);
  if (stored === "enabled") return true;
  if (stored === "disabled") return false;
  return workspaceConfig.tabsMode === "enabled";
}
function persistWorkspaceTabsPreference(enabled: boolean) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(WORKSPACE_TABS_ENABLED_KEY, enabled ? "enabled" : "disabled");
}
function updateViewportMode() {
  if (typeof window === "undefined") {
    isMobileViewport.value = false;
    return;
  }

  const wasMobile = isMobileViewport.value;
  const nextMobile = window.innerWidth <= workspaceConfig.mobileBreakpoint;
  isMobileViewport.value = nextMobile;

  // O estado do drawer mobile não contamina o estado expandido/colapsado do desktop.
  // Ao entrar em telas pequenas, o menu começa fechado; ao voltar para desktop,
  // a escolha anterior do usuário no desktop é preservada.
  if (nextMobile && !wasMobile) {
    mobileSidebarOpen.value = false;
  }
}

const savedMenuState = readMenuState();
const groupState = reactive<Record<MenuSection, boolean>>({
  dashboard: savedMenuState?.dashboard ?? true,
  cadastro: savedMenuState?.cadastro ?? true,
  sistema: savedMenuState?.sistema ?? true,
  ferramentas: savedMenuState?.ferramentas ?? false,
  documentacao: savedMenuState?.documentacao ?? false,
});

const sections: { key: MenuSection; title: string; subtitle: string }[] = [
  { key: "dashboard", title: "Dashboard", subtitle: "visão geral" },
  { key: "cadastro", title: "Cadastro", subtitle: "dados base" },
  { key: "sistema", title: "Sistema", subtitle: "segurança e parâmetros" },
  { key: "ferramentas", title: "Ferramentas", subtitle: "runtime e integrações" },
  { key: "documentacao", title: "Documentação", subtitle: "apoio ao usuário" },
];

const menuBySection = computed(() => {
  const items = visibleMenuItems().filter((item) => !item.permission || session.can(item.permission));
  return sections.map((section) => ({ ...section, items: items.filter((item) => item.section === section.key) })).filter((section) => section.items.length);
});

const currentMenuItem = computed(() => findMenuItemByRoute(route.path));
const pageTitle = computed(() => currentMenuItem.value?.title || appBranding.appName);
const pageEyebrow = computed(() => currentMenuItem.value?.eyebrow || appBranding.appName);
const pageDescription = computed(() => currentMenuItem.value?.description || appBranding.description);
function capitalizePt(value: string) {
  return value ? value.charAt(0).toUpperCase() + value.slice(1) : value;
}
const longDateLabel = computed(() => new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "long", year: "numeric" }).format(now.value));
const shortDateLabel = computed(() => new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" }).format(now.value));
const timeLabel = computed(() => new Intl.DateTimeFormat("pt-BR", { timeStyle: "medium" }).format(now.value));
const weekdayLabel = computed(() => capitalizePt(new Intl.DateTimeFormat("pt-BR", { weekday: "long" }).format(now.value)));
const monthLabel = computed(() => capitalizePt(new Intl.DateTimeFormat("pt-BR", { month: "long" }).format(now.value)));
const fullDateTimeLabel = computed(() => `${longDateLabel.value} às ${timeLabel.value}`);
const activeCompanyLabel = computed(() => session.activeCompanyName || "Empresa geral");
const activeTabKey = computed(() => canonicalTabKey(route.path));
const showWorkspaceTabs = computed(() => route.path !== "/login" && workspaceTabsEnabled.value && (workspaceConfig.mobileTabs || !isMobileViewport.value));
const userVisualKey = computed(() => session.user?.id ?? session.user?.login ?? "anonymous");
const activeCustomThemes = computed(() => customThemes.value.filter((item) => item.active !== false).slice(0, MAX_CUSTOM_THEMES_PER_USER));
const availableThemePresets = computed<VisualThemePreset[]>(() => [...visualThemePresets, ...activeCustomThemes.value]);
const selectedThemePreset = computed(() => findThemePreset(visualPreset.value, customThemes.value));
const isSelectedCustomTheme = computed(() => selectedThemePreset.value.custom === true);
const canCreateAnotherCustomTheme = computed(() => true);
const searchableMenuItems = computed(() => visibleMenuItems().filter((item) => !item.permission || session.can(item.permission)));
const globalSearchResults = computed(() => {
  const term = globalSearch.value.trim().toLowerCase();
  if (!term) return [];
  return searchableMenuItems.value
    .filter((item) => `${item.title} ${item.route} ${item.description || ""}`.toLowerCase().includes(term))
    .slice(0, 8);
});
const showGlobalSearchResults = computed(() => globalSearchFocused.value && (globalSearch.value.trim().length > 0));
const visualPreferences = computed<UserVisualPreferences>(() => ({
  mode: visualMode.value,
  preset: visualPreset.value,
  density: visualDensity.value,
}));

function syncCustomThemeDraftFromPreset() {
  const preset = selectedThemePreset.value;
  customThemeName.value = preset.custom ? preset.name : "Meu tema";
  customPrimaryColor.value = preset.colors.primary;
  customAccentColor.value = preset.colors.accent;
  customSidebarStartColor.value = preset.colors.sidebarStart;
  customSidebarEndColor.value = preset.colors.sidebarEnd;
  customFontFamily.value = preset.typography?.fontFamily || "Inter, Segoe UI, Arial, sans-serif";
  customFontScale.value = preset.typography?.fontScale || 1;
  customTitleScale.value = preset.typography?.titleScale || 1;
  customTextColor.value = preset.typography?.textColor || "#0f172a";
  customMutedColor.value = preset.typography?.mutedColor || "#64748b";
  customThemeActive.value = preset.custom ? preset.active !== false : customThemes.value.filter((item) => item.active !== false).length < MAX_CUSTOM_THEMES_PER_USER;
}

function restoreVisualPreferences() {
  customThemes.value = loadCustomVisualThemes(userVisualKey.value);
  const preferences = loadVisualPreferences(userVisualKey.value);
  visualMode.value = preferences.mode;
  visualPreset.value = findThemePreset(preferences.preset, customThemes.value).id;
  visualDensity.value = preferences.density;
  isDarkMode.value = preferences.mode === "dark";
  applyVisualPreferences({ ...preferences, preset: visualPreset.value }, customThemes.value);
  syncCustomThemeDraftFromPreset();
}

function persistVisualPreferences() {
  const preferences = visualPreferences.value;
  isDarkMode.value = preferences.mode === "dark";
  applyVisualPreferences(preferences, customThemes.value);
  saveVisualPreferences(userVisualKey.value, preferences);
}

function resetVisualPreferences() {
  visualMode.value = defaultVisualPreferences.mode;
  visualPreset.value = defaultVisualPreferences.preset;
  visualDensity.value = defaultVisualPreferences.density;
  persistVisualPreferences();
  syncCustomThemeDraftFromPreset();
}

function loadCustomThemeDraft(theme: VisualThemePreset) {
  customThemeName.value = theme.custom ? theme.name : `Meu tema ${Math.min(customThemes.value.length + 1, MAX_CUSTOM_THEMES_PER_USER)}`;
  customPrimaryColor.value = theme.colors.primary;
  customAccentColor.value = theme.colors.accent;
  customSidebarStartColor.value = theme.colors.sidebarStart;
  customSidebarEndColor.value = theme.colors.sidebarEnd;
  customFontFamily.value = theme.typography?.fontFamily || "Inter, Segoe UI, Arial, sans-serif";
  customFontScale.value = theme.typography?.fontScale || 1;
  customTitleScale.value = theme.typography?.titleScale || 1;
  customTextColor.value = theme.typography?.textColor || "#0f172a";
  customMutedColor.value = theme.typography?.mutedColor || "#64748b";
  customThemeActive.value = theme.custom ? theme.active !== false : customThemes.value.filter((item) => item.active !== false).length < MAX_CUSTOM_THEMES_PER_USER;
}

function openThemeManager() {
  themeManagerOpen.value = true;
  themeManagerMessage.value = "";
  editingCustomThemeId.value = isSelectedCustomTheme.value ? visualPreset.value : null;
  loadCustomThemeDraft(selectedThemePreset.value);
}

function closeThemeManager() {
  themeManagerOpen.value = false;
  editingCustomThemeId.value = null;
  themeManagerMessage.value = "";
}

function startNewCustomTheme() {
  editingCustomThemeId.value = null;
  themeManagerMessage.value = "";
  loadCustomThemeDraft(selectedThemePreset.value);
  customThemeName.value = `Meu tema ${customThemes.value.length + 1}`;
  customThemeActive.value = customThemes.value.filter((item) => item.active !== false).length < MAX_CUSTOM_THEMES_PER_USER;
}

function editCustomTheme(theme: UserCustomVisualTheme) {
  editingCustomThemeId.value = theme.id;
  themeManagerMessage.value = "";
  visualPreset.value = theme.id;
  loadCustomThemeDraft(theme);
}

function saveCustomTheme() {
  const editingIndex = editingCustomThemeId.value
    ? customThemes.value.findIndex((item) => item.id === editingCustomThemeId.value)
    : customThemes.value.findIndex((item) => item.id === visualPreset.value && item.custom);

  const activeCountWithoutCurrent = customThemes.value.filter((item, index) => index !== editingIndex && item.active !== false).length;
  const shouldBeActive = customThemeActive.value && activeCountWithoutCurrent < MAX_CUSTOM_THEMES_PER_USER;
  if (customThemeActive.value && !shouldBeActive) {
    themeManagerMessage.value = `Tema salvo, mas ficou inativo porque já existem ${MAX_CUSTOM_THEMES_PER_USER} temas próprios ativos no menu rápido.`;
  }

  const name = customThemeName.value.trim() || `Meu tema ${customThemes.value.length + 1}`;
  const base = selectedThemePreset.value;
  const theme: UserCustomVisualTheme = {
    id: editingIndex >= 0 ? customThemes.value[editingIndex].id : `custom:${Date.now()}`,
    name,
    description: "Tema personalizado do usuário.",
    custom: true,
    active: shouldBeActive,
    colors: {
      primary: customPrimaryColor.value,
      primaryHover: customPrimaryColor.value,
      primarySoft: base.colors.primarySoft,
      accent: customAccentColor.value,
      sidebarStart: customSidebarStartColor.value,
      sidebarEnd: customSidebarEndColor.value,
      sidebarAccent: customPrimaryColor.value,
    },
    typography: {
      fontFamily: customFontFamily.value || "Inter, Segoe UI, Arial, sans-serif",
      fontScale: Number(customFontScale.value) || 1,
      titleScale: Number(customTitleScale.value) || 1,
      textColor: customTextColor.value,
      mutedColor: customMutedColor.value,
    },
  };

  if (editingIndex >= 0) customThemes.value.splice(editingIndex, 1, theme);
  else customThemes.value.push(theme);

  saveCustomVisualThemes(userVisualKey.value, customThemes.value);
  editingCustomThemeId.value = theme.id;
  if (theme.active !== false) {
    visualPreset.value = theme.id;
  }
  persistVisualPreferences();
  themeManagerMessage.value = `Tema "${theme.name}" salvo para este usuário.`;
}

function toggleCustomThemeActive(themeId: string) {
  const theme = customThemes.value.find((item) => item.id === themeId);
  if (!theme) return;
  const activeCount = customThemes.value.filter((item) => item.id !== themeId && item.active !== false).length;
  if (theme.active === false && activeCount >= MAX_CUSTOM_THEMES_PER_USER) {
    themeManagerMessage.value = `Só é possível manter ${MAX_CUSTOM_THEMES_PER_USER} temas personalizados ativos no menu do usuário.`;
    return;
  }
  theme.active = theme.active === false;
  saveCustomVisualThemes(userVisualKey.value, customThemes.value);
  if (visualPreset.value === themeId && theme.active === false) {
    visualPreset.value = defaultVisualPreferences.preset;
    persistVisualPreferences();
  }
  themeManagerMessage.value = theme.active === false ? "Tema desativado do menu rápido." : "Tema ativado no menu rápido.";
}

function exportCustomThemes() {
  const data = JSON.stringify({ version: 1, exported_at: new Date().toISOString(), themes: customThemes.value }, null, 2);
  const blob = new Blob([data], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `pige360-deployer-temas-${userVisualKey.value || "usuario"}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

function triggerImportThemes() {
  themeImportInputRef.value?.click();
}

async function importCustomThemes(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  try {
    const raw = await file.text();
    const parsed = JSON.parse(raw);
    const imported = Array.isArray(parsed) ? parsed : Array.isArray(parsed.themes) ? parsed.themes : [];
    if (!imported.length) throw new Error("Nenhum tema encontrado no arquivo.");
    const currentIds = new Set(customThemes.value.map((item) => item.id));
    let activeSlots = Math.max(0, MAX_CUSTOM_THEMES_PER_USER - customThemes.value.filter((item) => item.active !== false).length);
    for (const item of imported) {
      const id = `custom:${Date.now()}:${Math.random().toString(16).slice(2)}`;
      const importedTheme: UserCustomVisualTheme = {
        id: currentIds.has(String(item.id)) ? id : String(item.id || id).replace(/^custom:/, "custom:"),
        name: String(item.name || "Tema importado").slice(0, 48),
        description: String(item.description || "Tema importado pelo usuário."),
        custom: true,
        active: activeSlots > 0 && item.active !== false,
        colors: {
          primary: item.colors?.primary || "#2563eb",
          primaryHover: item.colors?.primaryHover || item.colors?.primary || "#1d4ed8",
          primarySoft: item.colors?.primarySoft || "#dbeafe",
          accent: item.colors?.accent || "#0891b2",
          sidebarStart: item.colors?.sidebarStart || "#ffffff",
          sidebarEnd: item.colors?.sidebarEnd || "#eef6ff",
          sidebarAccent: item.colors?.sidebarAccent || item.colors?.primary || "#2563eb",
        },
        typography: {
          fontFamily: item.typography?.fontFamily || "Inter, Segoe UI, Arial, sans-serif",
          fontScale: Number(item.typography?.fontScale) || 1,
          titleScale: Number(item.typography?.titleScale) || 1,
          textColor: item.typography?.textColor || "#0f172a",
          mutedColor: item.typography?.mutedColor || "#64748b",
        },
      };
      if (importedTheme.active) activeSlots -= 1;
      customThemes.value.push(importedTheme);
    }
    saveCustomVisualThemes(userVisualKey.value, customThemes.value);
    themeManagerMessage.value = `${imported.length} tema(s) importado(s).`;
  } catch (error) {
    themeManagerMessage.value = error instanceof Error ? error.message : "Falha ao importar temas.";
  } finally {
    input.value = "";
  }
}

async function deleteCustomTheme(themeId: string) {
  const theme = customThemes.value.find((item) => item.id === themeId);
  if (!theme) return;
  if (!(await appConfirm({ title: "Excluir tema", message: `Excluir o tema "${theme.name}" deste usuário?`, danger: true, confirmText: "Excluir" }))) return;
  customThemes.value = customThemes.value.filter((item) => item.id !== themeId);
  saveCustomVisualThemes(userVisualKey.value, customThemes.value);
  if (visualPreset.value === themeId) {
    visualPreset.value = defaultVisualPreferences.preset;
    persistVisualPreferences();
  }
  editingCustomThemeId.value = null;
  syncCustomThemeDraftFromPreset();
  themeManagerMessage.value = "Tema excluído.";
}

async function deleteSelectedCustomTheme() {
  if (!isSelectedCustomTheme.value) return;
  await deleteCustomTheme(visualPreset.value);
}

function toggleVisualMode() {
  visualMode.value = visualMode.value === "dark" ? "light" : "dark";
}

function toggleUserMenu() {
  userMenuOpen.value = !userMenuOpen.value;
}

function serviceHint(service: TopbarServiceStatus): string {
  const address = service.port ? `${service.host || "0.0.0.0"}:${service.port}` : service.host || "sem porta";
  return `${service.label}: ${service.running ? "em execução" : "parado"} — ${address}${service.path ? service.path : ""}`;
}

async function monitorActiveSession() {
  if (route.path === "/login" || !session.sessionToken || sessionMonitorBusy) return;
  sessionMonitorBusy = true;
  try {
    const active = await session.validateCurrentSession();
    if (!active) {
      userMenuOpen.value = false;
      globalSearchFocused.value = false;
      await router.replace("/login");
    }
  } finally {
    sessionMonitorBusy = false;
  }
}

function applyServiceStatus(key: ServiceKey, payload: Record<string, any>) {
  const target = serviceStatuses[key];
  target.running = Boolean(payload.running);
  target.host = String(payload.host || payload.effective_host || payload.bind_host || "0.0.0.0");
  target.port = payload.port || payload.effective_port || payload.configured_port || (key === "api" ? 61001 : key === "webhook" ? 61003 : 61004);
  target.path = String(payload.path || payload.base_path || (key === "websocket" ? "/ws" : key === "webhook" ? "/webhooks" : "/docs"));
  target.hint = serviceHint(target);
}

function browserReachableHost(host?: string) {
  const value = String(host || "").trim();
  if (!value || value === "0.0.0.0" || value === "::" || value === "[::]" || value === "127.0.0.1" || value === "localhost") {
    return typeof window !== "undefined" ? window.location.hostname || "127.0.0.1" : "127.0.0.1";
  }
  return value;
}

async function probePublishedService(key: Exclude<ServiceKey, "api">) {
  const service = serviceStatuses[key];
  const port = Number(service.port || (key === "webhook" ? 61003 : 61004));
  if (!Number.isFinite(port) || port <= 0) return;
  const host = browserReachableHost(service.host);
  const url = `http://${host}:${port}/health`;
  try {
    await fetch(url, { method: "GET", mode: "no-cors", cache: "no-store" });
    service.running = true;
    service.host = host;
    service.port = port;
    service.hint = `${service.label}: acessível via rede — ${host}:${port}${service.path || ""}`;
  } catch {
    service.hint = serviceHint(service);
  }
}

async function loadTopbarServiceStatuses() {
  try {
    applyServiceStatus("api", await getInternalApiStatus());
  } catch (error) {
    serviceStatuses.api.running = false;
    serviceStatuses.api.hint = `API: falha ao consultar status (${error instanceof Error ? error.message : String(error)})`;
  }
  try {
    applyServiceStatus("webhook", await invokeCommand<Record<string, any>>("webhook_status"));
  } catch (error) {
    serviceStatuses.webhook.running = false;
    serviceStatuses.webhook.hint = `Webhook: falha ao consultar status (${error instanceof Error ? error.message : String(error)})`;
  }
  try {
    applyServiceStatus("websocket", await invokeCommand<Record<string, any>>("websocket_status"));
  } catch (error) {
    serviceStatuses.websocket.running = false;
    serviceStatuses.websocket.hint = `WebSocket: falha ao consultar status (${error instanceof Error ? error.message : String(error)})`;
  }

  await Promise.all([probePublishedService("webhook"), probePublishedService("websocket")]);
}

function focusGlobalSearch() {
  nextTick(() => globalSearchInputRef.value?.focus());
}

function openSearchResult(item: { route: string }) {
  router.push(item.route);
  globalSearch.value = "";
  globalSearchFocused.value = false;
}

function handleGlobalSearchKeydown(event: KeyboardEvent) {
  if (event.key === "Enter" && globalSearchResults.value[0]) {
    event.preventDefault();
    openSearchResult(globalSearchResults.value[0]);
  }
  if (event.key === "Escape") {
    globalSearch.value = "";
    globalSearchFocused.value = false;
    globalSearchInputRef.value?.blur();
  }
}

function handleGlobalShortcut(event: KeyboardEvent) {
  if (event.key === "Escape") {
    if (userMenuOpen.value) {
      userMenuOpen.value = false;
      event.preventDefault();
    }
    if (themeManagerOpen.value) {
      closeThemeManager();
      event.preventDefault();
    }
    if (globalSearchFocused.value || globalSearch.value) {
      globalSearch.value = "";
      globalSearchFocused.value = false;
      globalSearchInputRef.value?.blur();
    }
    return;
  }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    focusGlobalSearch();
  }
}

function handleDocumentPointerDown(event: PointerEvent) {
  if (!userMenuOpen.value) return;
  const target = event.target as Node | null;
  if (target && userMenuRef.value?.contains(target)) return;
  userMenuOpen.value = false;
}

function canonicalTabKey(path: string): string {
  const cleanPath = (path || "/").split("?")[0].split("#")[0].replace(/\/+$/, "") || "/";
  if (["/app", "/template"].includes(cleanPath)) return "/";
  return cleanPath;
}

function dashboardTab(): WorkspaceTab {
  return {
    key: "/",
    route: "/",
    fullPath: "/",
    title: "Dashboard",
    eyebrow: "Visão geral",
    description: "Resumo operacional.",
    pinned: true,
  };
}

function dedupeTabs(tabs: WorkspaceTab[]): WorkspaceTab[] {
  const byKey = new Map<string, WorkspaceTab>();
  for (const tab of tabs) {
    const key = canonicalTabKey(tab.key || tab.route || tab.fullPath || "/");
    const normalized: WorkspaceTab = {
      ...tab,
      key,
      route: key,
      fullPath: tab.fullPath || key,
      pinned: key === "/" || tab.pinned,
    };
    byKey.set(key, normalized);
  }
  if (!byKey.has("/")) byKey.set("/", dashboardTab());
  const items = Array.from(byKey.values());
  return [
    ...items.filter((tab) => tab.key === "/"),
    ...items.filter((tab) => tab.key !== "/"),
  ];
}

function normalizeStoredTabs(value: unknown): WorkspaceTab[] {
  if (!Array.isArray(value)) return [];
  const normalized = value
    .filter((item) => item && typeof item === "object" && typeof (item as WorkspaceTab).fullPath === "string")
    .map((item) => {
      const tab = item as WorkspaceTab;
      const key = canonicalTabKey(tab.key || tab.route || tab.fullPath || "/");
      return {
        key,
        route: key,
        fullPath: tab.fullPath || key,
        title: tab.title || "Página",
        eyebrow: tab.eyebrow || appBranding.appName,
        description: tab.description || "",
        pinned: key === "/" || tab.pinned,
      };
    });
  return dedupeTabs(normalized).slice(0, 12);
}
function restoreWorkspaceTabs() {
  if (typeof window === "undefined" || !workspaceConfig.persistTabs) return;
  try {
    const stored = normalizeStoredTabs(JSON.parse(window.localStorage.getItem(WORKSPACE_TABS_KEY) || "[]"));
    workspaceTabs.value = stored.length ? dedupeTabs(stored) : [dashboardTab()];
  } catch {
    workspaceTabs.value = [dashboardTab()];
  }
}

function persistWorkspaceTabs() {
  if (typeof window !== "undefined" && workspaceConfig.persistTabs) window.localStorage.setItem(WORKSPACE_TABS_KEY, JSON.stringify(dedupeTabs(workspaceTabs.value)));
}

function upsertCurrentTab() {
  if (!showWorkspaceTabs.value) return;
  const key = canonicalTabKey(route.path);
  const existingIndex = workspaceTabs.value.findIndex((tab) => tab.key === key);
  const tab: WorkspaceTab = {
    key,
    route: key,
    fullPath: route.fullPath,
    title: pageTitle.value,
    eyebrow: pageEyebrow.value,
    description: pageDescription.value,
    pinned: key === "/",
  };
  if (existingIndex >= 0) {
    workspaceTabs.value[existingIndex] = { ...workspaceTabs.value[existingIndex], ...tab };
  } else {
    workspaceTabs.value.push(tab);
  }
  workspaceTabs.value = dedupeTabs(workspaceTabs.value);
  if (workspaceTabs.value.length > workspaceConfig.maxTabs) {
    const active = workspaceTabs.value.find((item) => item.key === key);
    const pinned = workspaceTabs.value.find((item) => item.pinned);
    const others = workspaceTabs.value.filter((item) => item.key !== active?.key && !item.pinned).slice(-(workspaceConfig.maxTabs - 2));
    workspaceTabs.value = [pinned, ...others, active].filter(Boolean) as WorkspaceTab[];
  }
  persistWorkspaceTabs();
}

function activateTab(tab: WorkspaceTab) {
  if (tab.fullPath !== route.fullPath) router.push(tab.fullPath);
}

function closeTab(tab: WorkspaceTab, event?: MouseEvent) {
  event?.stopPropagation();
  if (tab.pinned && workspaceTabs.value.length === 1) return;
  const index = workspaceTabs.value.findIndex((item) => item.key === tab.key);
  if (index < 0) return;
  const wasActive = tab.key === activeTabKey.value;
  workspaceTabs.value.splice(index, 1);
  if (!workspaceTabs.value.length) {
    workspaceTabs.value.push(dashboardTab());
  }
  persistWorkspaceTabs();
  if (wasActive) {
    const next = workspaceTabs.value[Math.max(0, index - 1)] || workspaceTabs.value[0];
    router.push(next.fullPath);
  }
}

function closeOtherTabs(tab: WorkspaceTab) {
  workspaceTabs.value = dedupeTabs(workspaceTabs.value).filter((item) => item.key === tab.key || item.pinned);
  persistWorkspaceTabs();
  activateTab(tab);
}

function openDashboardTab() {
  router.push("/");
}

function updateTabScrollState() {
  const el = tabScrollRef.value;
  if (!el) {
    canScrollTabsLeft.value = false;
    canScrollTabsRight.value = false;
    return;
  }
  const maxScroll = Math.max(0, el.scrollWidth - el.clientWidth);
  canScrollTabsLeft.value = el.scrollLeft > 4;
  canScrollTabsRight.value = el.scrollLeft < maxScroll - 4;
}

function scheduleTabScrollStateUpdate() {
  if (typeof window === "undefined") return;
  if (tabStateTimer) window.clearTimeout(tabStateTimer);
  tabStateTimer = window.setTimeout(updateTabScrollState, 60);
}

function scrollWorkspaceTabs(direction: "left" | "right") {
  const el = tabScrollRef.value;
  if (!el) return;
  const distance = Math.max(220, Math.floor(el.clientWidth * 0.55));
  el.scrollBy({ left: direction === "left" ? -distance : distance, behavior: "smooth" });
  scheduleTabScrollStateUpdate();
}

function toggleGroup(key: MenuSection) {
  if (sidebarConfig.menuBehavior === "single-open" && sidebarConfig.collapsePreviousOnNewSelection) {
    for (const section of sections) groupState[section.key] = section.key === key ? !groupState[key] : false;
    return;
  }
  groupState[key] = !groupState[key];
}

async function logout() {
  await session.logout();
  router.push("/login");
}
function closeSidebarOnMobile() { if (window.innerWidth <= workspaceConfig.mobileBreakpoint) mobileSidebarOpen.value = false; }
function refreshCurrentPage() {
  refreshToken.value += 1;
  window.dispatchEvent(new CustomEvent("template:refresh-page", { detail: { route: route.fullPath } }));
  logAppInfo("layout", "Atualização manual solicitada na barra superior.", { route: route.fullPath });
}
function handleBrandLogoError() {
  brandLogoFailed.value = true;
  logAppError("assets", "Falha ao carregar logo-mark.png; fallback visual aplicado.", { asset: "src/assets/branding/logo-mark.png" });
}

function ensureActiveGroup() {
  const current = visibleMenuItems().find((item) => item.route === route.path);
  if (current && sidebarConfig.keepActiveParentExpanded) groupState[current.section] = true;
}

watch(() => route.fullPath, () => {
  ensureActiveGroup();
  closeSidebarOnMobile();
  upsertCurrentTab();
});
watch(groupState, (value) => {
  if (sidebarConfig.persistUserMenuState) localStorage.setItem(MENU_STATE_KEY, JSON.stringify(value));
}, { deep: true });
watch(workspaceTabs, () => scheduleTabScrollStateUpdate(), { deep: true });
watch(workspaceTabsEnabled, (enabled) => {
  persistWorkspaceTabsPreference(enabled);
  if (enabled && !isMobileViewport.value) {
    restoreWorkspaceTabs();
    upsertCurrentTab();
  }
});
watch(isMobileViewport, (mobile) => {
  if (!mobile && workspaceTabsEnabled.value) {
    restoreWorkspaceTabs();
    upsertCurrentTab();
    scheduleTabScrollStateUpdate();
  }
});
function handleWorkspacePreferenceChanged(event: Event) {
  const detail = (event as CustomEvent<{ enabled?: boolean }>).detail;
  if (typeof detail?.enabled === "boolean") workspaceTabsEnabled.value = detail.enabled;
}

watch(isDarkMode, (enabled) => {
  const nextMode = enabled ? "dark" : "light";
  if (visualMode.value !== nextMode) visualMode.value = nextMode;
});
watch([visualMode, visualPreset, visualDensity], () => persistVisualPreferences());
watch(visualPreset, () => syncCustomThemeDraftFromPreset());
watch(userVisualKey, () => restoreVisualPreferences());
watch(() => route.fullPath, () => { userMenuOpen.value = false; globalSearchFocused.value = false; });

onMounted(async () => {
  updateViewportMode();
  workspaceTabsEnabled.value = readWorkspaceTabsPreference();
  restoreWorkspaceTabs();
  restoreVisualPreferences();
  await loadTopbarServiceStatuses();
  serviceStatusTimer = window.setInterval(loadTopbarServiceStatuses, 10000);
  sessionMonitorTimer = window.setInterval(() => { void monitorActiveSession(); }, 10000);
  window.addEventListener("keydown", handleGlobalShortcut);
  window.addEventListener("pointerdown", handleDocumentPointerDown);
  window.addEventListener("focus", () => { void monitorActiveSession(); });
  try {
    const payload = await getAppMeta();
    meta.version = String(payload.version || meta.version);
    meta.build_hash = String(payload.build_hash || meta.build_hash);
  } catch (error) {
    logAppError("layout", "Falha ao carregar metadados da aplicação.", { error: error instanceof Error ? error.message : String(error) });
  }
  timer = window.setInterval(() => { now.value = new Date(); }, 1000);
  window.addEventListener("resize", updateViewportMode);
  window.addEventListener("resize", scheduleTabScrollStateUpdate);
  window.addEventListener("template:workspace-tabs-preference-changed", handleWorkspacePreferenceChanged as EventListener);
  ensureActiveGroup();
  closeSidebarOnMobile();
  upsertCurrentTab();
  scheduleTabScrollStateUpdate();
  logAppInfo("layout", "Shell principal montado.");
});

onBeforeUnmount(() => {
  if (timer) window.clearInterval(timer);
  if (tabStateTimer) window.clearTimeout(tabStateTimer);
  if (serviceStatusTimer) window.clearInterval(serviceStatusTimer);
  if (sessionMonitorTimer) window.clearInterval(sessionMonitorTimer);
  if (typeof window !== "undefined") {
    window.removeEventListener("keydown", handleGlobalShortcut);
    window.removeEventListener("pointerdown", handleDocumentPointerDown);
    window.removeEventListener("resize", updateViewportMode);
    window.removeEventListener("resize", scheduleTabScrollStateUpdate);
    window.removeEventListener("template:workspace-tabs-preference-changed", handleWorkspacePreferenceChanged as EventListener);
  }
});
</script>

<template>
  <div class="shell-root professional-shell" :class="{ 'sidebar-collapsed': !sidebarOpen }">
    <div v-if="sidebarOpen" class="shell-overlay" @click="sidebarOpen = false" />

    <aside class="sidebar professional-sidebar" :class="{ open: sidebarOpen }">
      <div class="brand-box professional-brand">
        <img v-if="!brandLogoFailed" :src="logoMark" :alt="appBranding.appName" class="brand-mark" @error="handleBrandLogoError" />
        <div v-else class="brand-mark fallback-logo">{{ appBranding.shortName.slice(0, 2).toUpperCase() }}</div>
        <div class="brand-copy">
          <h1>{{ appBranding.appName }}</h1>
          <div class="muted-light">{{ appBranding.subtitle }}</div>
        </div>
      </div>

      <div class="sidebar-scroll professional-menu-scroll">
        <div v-for="section in menuBySection" :key="section.key" class="menu-group professional-menu-group">
          <button class="menu-group-button professional-menu-group-button" @click="toggleGroup(section.key)">
            <span>{{ section.title }}</span>
            <small>{{ groupState[section.key] ? '−' : '+' }}</small>
          </button>
          <div v-show="groupState[section.key]" class="menu-links submenu-links professional-menu-links" :class="`submenu-${sidebarConfig.submenuVisualMode}`">
            <RouterLink v-for="item in section.items" :key="item.route" :to="item.route" :title="item.title">
              <span class="menu-link-icon" aria-hidden="true"><IconSymbol :name="iconNameForRoute(item.route)" :size="15" /></span>
              <span class="menu-link-label">{{ item.title }}</span>
            </RouterLink>
          </div>
        </div>
      </div>

      <div class="sidebar-footer-fixed professional-sidebar-footer">
        <div v-if="isMobileViewport" class="mobile-sidebar-context">
          <label class="sidebar-company-selector">
            <span>Empresa ativa</span>
            <select :value="session.activeCompanyId ?? ''" @change="session.setActiveCompany(Number(($event.target as HTMLSelectElement).value) || null)">
              <option v-if="session.isMaster" value="">Todas / geral</option>
              <option v-for="company in session.user?.company_ids || []" :key="company" :value="company">
                {{ session.user?.company_names?.[session.user.company_ids.indexOf(company)] || `Empresa ${company}` }}
              </option>
            </select>
          </label>

          <div class="sidebar-service-status-list" aria-label="Status dos serviços internos">
            <RouterLink
              v-for="service in serviceStatuses"
              :key="`sidebar-${service.key}`"
              :to="service.key === 'api' ? '/api-interna' : service.key === 'webhook' ? '/webhooks' : '/websocket'"
              class="sidebar-service-status"
              :title="service.hint"
            >
              <span class="service-dot" :class="{ online: service.running, offline: !service.running }" />
              <strong>{{ service.label }}</strong>
            </RouterLink>
          </div>
        </div>

        <div class="sidebar-footer-actions">
          <RouterLink class="footer-icon-button" to="/sistema" title="Configurações"><IconSymbol name="settings" :size="16" /></RouterLink>
          <button class="footer-icon-button" type="button" title="Sair" @click="logout"><IconSymbol name="logout" :size="16" /></button>
        </div>
      </div>
    </aside>

    <div class="shell-main professional-main">
      <header class="topbar professional-topbar">
        <div class="topbar-left professional-topbar-left">
          <button v-if="sidebarConfig.allowCollapse" class="icon-button topbar-menu-button" type="button" :title="sidebarOpen ? 'Recolher menu lateral' : 'Exibir menu lateral'" @click="sidebarOpen = !sidebarOpen">
            <IconSymbol name="menu" :size="18" />
          </button>
          <div class="global-search-wrap">
            <label class="global-search-box" title="Buscar páginas e módulos do sistema">
              <IconSymbol name="search" :size="15" />
              <input
                ref="globalSearchInputRef"
                v-model="globalSearch"
                type="search"
                placeholder="Buscar páginas, módulos e rotas... (Ctrl + K)"
                @focus="globalSearchFocused = true"
                @keydown="handleGlobalSearchKeydown"
              />
            </label>
            <div v-if="showGlobalSearchResults" class="global-search-results">
              <button
                v-for="item in globalSearchResults"
                :key="item.route"
                type="button"
                class="global-search-result"
                @mousedown.prevent="openSearchResult(item)"
              >
                <span class="menu-link-icon"><IconSymbol :name="iconNameForRoute(item.route)" :size="15" /></span>
                <span><strong>{{ item.title }}</strong><small>{{ item.route }}</small></span>
              </button>
              <div v-if="!globalSearchResults.length" class="global-search-empty">Nenhum módulo encontrado.</div>
            </div>
          </div>
        </div>

        <div class="topbar-right professional-topbar-right">
          <label class="company-selector topbar-company-selector">
            <span>Empresa ativa</span>
            <select :value="session.activeCompanyId ?? ''" @change="session.setActiveCompany(Number(($event.target as HTMLSelectElement).value) || null)">
              <option v-if="session.isMaster" value="">Todas / geral</option>
              <option v-for="company in session.user?.company_ids || []" :key="company" :value="company">
                {{ session.user?.company_names?.[session.user.company_ids.indexOf(company)] || `Empresa ${company}` }}
              </option>
            </select>
          </label>

          <div class="topbar-services" title="Status dos serviços publicados">
            <RouterLink
              v-for="service in serviceStatuses"
              :key="service.key"
              :to="service.key === 'api' ? '/api-interna' : service.key === 'webhook' ? '/webhooks' : '/websocket'"
              class="service-led-pill"
              :title="service.hint"
            >
              <span class="service-dot" :class="{ online: service.running, offline: !service.running }" />
              <strong>{{ service.label }}</strong>
            </RouterLink>
          </div>

          <div class="topbar-clock topbar-date-time" :title="fullDateTimeLabel" aria-label="Data e hora completas">
            <div class="topbar-date-copy">
              <strong>{{ weekdayLabel }}</strong>
              <small>{{ monthLabel }}</small>
            </div>
            <div class="topbar-time-copy">
              <strong>{{ timeLabel }}</strong>
              <small>{{ shortDateLabel }}</small>
            </div>
          </div>

          <button class="topbar-icon-button" type="button" title="Atualizar tela" @click="refreshCurrentPage"><IconSymbol name="refresh" :size="16" /></button>
          <button class="topbar-icon-button" type="button" title="Alternar tema claro/escuro" @click="toggleVisualMode"><IconSymbol :name="visualMode === 'dark' ? 'moon' : 'sun'" :size="16" /></button>
          <button class="topbar-icon-button" type="button" title="Notificações"><IconSymbol name="bell" :size="16" /></button>

          <div ref="userMenuRef" class="topbar-user-menu" :class="{ 'with-workspace-tabs': showWorkspaceTabs }">
            <button class="user-menu-trigger" type="button" @click="toggleUserMenu">
              <img v-if="session.user?.photo_url" :src="session.user.photo_url" class="user-avatar-img" alt="Foto do usuário" />
              <span v-else class="user-avatar compact-avatar">{{ (session.user?.nome || session.user?.login || 'U').slice(0, 1).toUpperCase() }}</span>
              <span class="user-menu-copy">
                <strong>{{ session.user?.nome || "Sem usuário" }}</strong>
                <small>{{ session.user?.login || activeCompanyLabel }}</small>
              </span>
              <IconSymbol class="user-menu-caret" name="chevronDown" :size="15" />
            </button>

            <div v-if="userMenuOpen" class="user-dropdown-panel" :class="{ 'with-workspace-tabs': showWorkspaceTabs }">
              <div class="user-dropdown-header">
                <strong>{{ session.user?.nome || "Sem usuário" }}</strong>
                <small>{{ activeCompanyLabel }}</small>
              </div>

              <div class="appearance-panel">
                <div class="appearance-title">Aparência do usuário</div>
                <label class="field compact-field">
                  <span>Tema</span>
                  <select v-model="visualPreset">
                    <option v-for="preset in availableThemePresets" :key="preset.id" :value="preset.id">{{ preset.custom ? '★ ' : '' }}{{ preset.name }}</option>
                  </select>
                </label>
                <label class="field compact-field">
                  <span>Modo</span>
                  <select v-model="visualMode">
                    <option value="light">Claro</option>
                    <option value="dark">Escuro</option>
                  </select>
                </label>
                <label class="field compact-field">
                  <span>Densidade</span>
                  <select v-model="visualDensity">
                    <option value="comfortable">Confortável</option>
                    <option value="compact">Compacto</option>
                    <option value="dense">Denso</option>
                  </select>
                </label>
                <div class="theme-preview-row">
                  <span class="theme-preview-dot" :style="{ background: selectedThemePreset.colors.primary }" />
                  <span class="theme-preview-dot" :style="{ background: selectedThemePreset.colors.accent }" />
                  <span class="theme-preview-dot" :style="{ background: selectedThemePreset.colors.sidebarStart }" />
                  <small>{{ activeCustomThemes.length }}/{{ MAX_CUSTOM_THEMES_PER_USER }} temas ativos</small>
                </div>

                <button class="secondary full-button" type="button" @click="openThemeManager">Gerenciar temas próprios</button>
                <button class="secondary full-button" type="button" @click="resetVisualPreferences">Restaurar padrão</button>
              </div>

              <div class="user-dropdown-actions">
                <RouterLink class="dropdown-action" to="/sistema">Configurações</RouterLink>
                <button class="dropdown-action danger-link" type="button" @click="logout">Sair</button>
              </div>
            </div>
          </div>
        </div>
      </header>

      <section v-if="showWorkspaceTabs" class="workspace-tabs-bar professional-tabs-bar" aria-label="Guias abertas">
        <button
          type="button"
          class="workspace-tab-nav previous"
          :class="{ visible: canScrollTabsLeft }"
          title="Mover guias para a esquerda"
          aria-label="Mover guias para a esquerda"
          @click="scrollWorkspaceTabs('left')"
        >
          <IconSymbol name="chevronDown" :size="14" />
        </button>

        <div class="workspace-tabs-viewport">
          <div ref="tabScrollRef" class="workspace-tabs-scroll" @scroll="updateTabScrollState">
            <button
              v-for="tab in workspaceTabs"
              :key="tab.key"
              type="button"
              class="workspace-tab"
              :class="{ active: tab.key === activeTabKey, pinned: tab.pinned }"
              :title="tab.description || tab.title"
              @click="activateTab(tab)"
              @dblclick="closeOtherTabs(tab)"
            >
              <span class="workspace-tab-dot" />
              <span class="workspace-tab-copy"><strong>{{ tab.title }}</strong></span>
              <span v-if="tab.pinned" class="workspace-tab-pin"><IconSymbol name="home" :size="12" /></span>
              <span v-else class="workspace-tab-close" role="button" aria-label="Fechar guia" @click="closeTab(tab, $event)"><IconSymbol name="close" :size="12" /></span>
            </button>
            <button type="button" class="workspace-tab-add" title="Abrir Dashboard em uma guia" @click="openDashboardTab"><IconSymbol name="plus" :size="15" /></button>
          </div>
        </div>

        <button
          type="button"
          class="workspace-tab-nav next"
          :class="{ visible: canScrollTabsRight }"
          title="Mover guias para a direita"
          aria-label="Mover guias para a direita"
          @click="scrollWorkspaceTabs('right')"
        >
          <IconSymbol name="chevronDown" :size="14" />
        </button>
      </section>

      <main class="content-area workspace-content-area professional-content-area">
        <RouterView v-slot="{ Component }">
          <KeepAlive v-if="showWorkspaceTabs" :max="workspaceConfig.maxTabs">
            <component :is="Component" :key="`${route.fullPath}:${refreshToken}`" />
          </KeepAlive>
          <component v-else :is="Component" :key="`${route.fullPath}:${refreshToken}`" />
        </RouterView>
      </main>
    </div>
    <div v-if="themeManagerOpen" class="theme-manager-overlay" @click.self="closeThemeManager">
      <section class="theme-manager-panel" role="dialog" aria-modal="true" aria-label="Personalização de temas do usuário">
        <header class="theme-manager-header">
          <div>
            <p class="eyebrow">Aparência do usuário</p>
            <h2>Temas próprios</h2>
            <p>Crie, importe, edite, exporte e exclua temas. Vários temas podem existir; somente {{ MAX_CUSTOM_THEMES_PER_USER }} ficam ativos no menu rápido do usuário.</p>
          </div>
          <button class="secondary" type="button" @click="closeThemeManager">Fechar</button>
        </header>

        <div class="theme-manager-body">
          <aside class="theme-manager-list">
            <div class="theme-manager-list-head">
              <strong>Meus temas</strong>
              <small>{{ activeCustomThemes.length }}/{{ MAX_CUSTOM_THEMES_PER_USER }} ativos · {{ customThemes.length }} salvos</small>
            </div>
            <button class="primary full-button" type="button" @click="startNewCustomTheme">
              Novo tema
            </button>
            <div class="theme-manager-import-export">
              <button class="secondary" type="button" @click="exportCustomThemes">Exportar</button>
              <button class="secondary" type="button" @click="triggerImportThemes">Importar</button>
              <input ref="themeImportInputRef" type="file" accept="application/json,.json" hidden @change="importCustomThemes" />
            </div>
            <div class="theme-list-scroll">
              <div
                v-for="theme in customThemes"
                :key="theme.id"
                class="custom-theme-list-item"
                :class="{ active: editingCustomThemeId === theme.id }"
                role="button"
                tabindex="0"
                @click="editCustomTheme(theme)"
                @keydown.enter="editCustomTheme(theme)"
              >
                <span class="custom-theme-swatch" :style="{ background: `linear-gradient(135deg, ${theme.colors.primary}, ${theme.colors.accent})` }" />
                <span><strong>{{ theme.name }}</strong><small>{{ theme.description }}</small></span>
                <button class="custom-theme-active-toggle" type="button" :class="{ active: theme.active !== false }" @click.stop="toggleCustomThemeActive(theme.id)">
                  {{ theme.active === false ? 'Inativo' : 'Ativo' }}
                </button>
              </div>
              <div v-if="!customThemes.length" class="theme-manager-empty">Nenhum tema próprio criado.</div>
            </div>
          </aside>

          <div class="theme-manager-editor">
            <div class="theme-editor-preview" :style="{ background: `linear-gradient(135deg, ${customSidebarStartColor}, ${customSidebarEndColor})` }">
              <div class="theme-editor-preview-card">
                <span :style="{ background: customPrimaryColor }" />
                <strong>{{ customThemeName || 'Meu tema' }}</strong>
                <small>Prévia da sidebar e cor principal</small>
              </div>
            </div>

            <div class="theme-editor-grid">
              <label class="field compact-field full-span">
                <span>Nome do tema</span>
                <input v-model="customThemeName" maxlength="32" placeholder="Meu tema" />
              </label>
              <label class="theme-color-field"><span>Primária</span><input v-model="customPrimaryColor" type="color" /></label>
              <label class="theme-color-field"><span>Destaque</span><input v-model="customAccentColor" type="color" /></label>
              <label class="theme-color-field"><span>Sidebar topo/background</span><input v-model="customSidebarStartColor" type="color" /></label>
              <label class="theme-color-field"><span>Sidebar base/background</span><input v-model="customSidebarEndColor" type="color" /></label>
              <label class="field compact-field full-span"><span>Fonte</span><select v-model="customFontFamily"><option value="Inter, Segoe UI, Arial, sans-serif">Inter / Segoe UI</option><option value="Segoe UI, Arial, sans-serif">Segoe UI</option><option value="Arial, sans-serif">Arial</option><option value="Roboto, Segoe UI, Arial, sans-serif">Roboto</option><option value="Verdana, Geneva, sans-serif">Verdana</option></select></label>
              <label class="theme-color-field"><span>Tamanho texto</span><input v-model.number="customFontScale" type="number" min="0.86" max="1.18" step="0.01" /></label>
              <label class="theme-color-field"><span>Tamanho títulos</span><input v-model.number="customTitleScale" type="number" min="0.88" max="1.22" step="0.01" /></label>
              <label class="theme-color-field"><span>Cor do texto</span><input v-model="customTextColor" type="color" /></label>
              <label class="theme-color-field"><span>Texto secundário</span><input v-model="customMutedColor" type="color" /></label>
              <label class="checkbox-line full-span theme-active-line"><input v-model="customThemeActive" type="checkbox" /> <span>Manter ativo no menu rápido do usuário</span></label>
            </div>

            <div v-if="themeManagerMessage" class="theme-manager-message">{{ themeManagerMessage }}</div>

            <div class="theme-manager-actions">
              <button class="secondary" type="button" @click="startNewCustomTheme">Limpar para novo</button>
              <button v-if="editingCustomThemeId" class="danger" type="button" @click="deleteCustomTheme(editingCustomThemeId)">Excluir tema</button>
              <button class="primary" type="button" :disabled="!canCreateAnotherCustomTheme && !editingCustomThemeId" @click="saveCustomTheme">
                {{ editingCustomThemeId ? 'Atualizar tema' : 'Salvar novo tema' }}
              </button>
            </div>
          </div>
        </div>
      </section>
    </div>

  </div>
</template>
