export type ThemeMode = "light" | "dark";
export type ThemeDensity = "comfortable" | "compact" | "dense";

export interface VisualThemeColors {
  primary: string;
  primaryHover: string;
  primarySoft: string;
  accent: string;
  sidebarStart: string;
  sidebarEnd: string;
  sidebarAccent: string;
}

export interface VisualThemeTypography {
  fontFamily: string;
  fontScale: number;
  titleScale: number;
  textColor: string;
  mutedColor: string;
}

export interface VisualThemePreset {
  id: string;
  name: string;
  description: string;
  colors: VisualThemeColors;
  typography?: VisualThemeTypography;
  custom?: boolean;
  active?: boolean;
}

export interface UserVisualPreferences {
  mode: ThemeMode;
  preset: string;
  density: ThemeDensity;
}

export type UserCustomVisualTheme = VisualThemePreset & { custom: true; active: boolean; typography: VisualThemeTypography };

// Regra de UX: o usuário pode ter vários temas salvos/importados,
// porém somente 5 ficam ativos no menu rápido para evitar lista extensa.
export const MAX_CUSTOM_THEMES_PER_USER = 5;

export const defaultThemeTypography: VisualThemeTypography = {
  fontFamily: "Inter, Segoe UI, Arial, sans-serif",
  fontScale: 1,
  titleScale: 1,
  textColor: "#0f172a",
  mutedColor: "#64748b",
};

export const visualThemePresets: VisualThemePreset[] = [
  {
    id: "brand-primary",
    name: "Marca PIGE360 Deployer",
    description: "Tema principal alinhado à identidade do produto.",
    colors: {
      primary: "#006D77",
      primaryHover: "#005962",
      primarySoft: "#DBEBEC",
      accent: "#0D1B2A",
      sidebarStart: "#ffffff",
      sidebarEnd: "#eef6ff",
      sidebarAccent: "#006D77",
    },
  },
  {
    id: "sky-clean",
    name: "Azul clean",
    description: "Visual claro com azul mais leve.",
    colors: {
      primary: "#0284c7",
      primaryHover: "#0369a1",
      primarySoft: "#e0f2fe",
      accent: "#06b6d4",
      sidebarStart: "#ffffff",
      sidebarEnd: "#f0f9ff",
      sidebarAccent: "#0284c7",
    },
  },
  {
    id: "financial-green",
    name: "Verde financeiro",
    description: "Boa opção para sistemas financeiros e operacionais.",
    colors: {
      primary: "#059669",
      primaryHover: "#047857",
      primarySoft: "#d1fae5",
      accent: "#10b981",
      sidebarStart: "#ffffff",
      sidebarEnd: "#ecfdf5",
      sidebarAccent: "#059669",
    },
  },
  {
    id: "modern-purple",
    name: "Roxo moderno",
    description: "Identidade visual moderna para produtos SaaS.",
    colors: {
      primary: "#7c3aed",
      primaryHover: "#6d28d9",
      primarySoft: "#ede9fe",
      accent: "#a855f7",
      sidebarStart: "#ffffff",
      sidebarEnd: "#f5f3ff",
      sidebarAccent: "#7c3aed",
    },
  },
  {
    id: "operational-orange",
    name: "Laranja operacional",
    description: "Destaque visual para rotinas operacionais e chão de loja.",
    colors: {
      primary: "#ea580c",
      primaryHover: "#c2410c",
      primarySoft: "#ffedd5",
      accent: "#f97316",
      sidebarStart: "#ffffff",
      sidebarEnd: "#fff7ed",
      sidebarAccent: "#ea580c",
    },
  },
  {
    id: "executive-graphite",
    name: "Grafite executivo",
    description: "Visual sóbrio com sidebar clara e acento grafite.",
    colors: {
      primary: "#334155",
      primaryHover: "#1e293b",
      primarySoft: "#e2e8f0",
      accent: "#64748b",
      sidebarStart: "#ffffff",
      sidebarEnd: "#f8fafc",
      sidebarAccent: "#334155",
    },
  },

  {
    id: "classic-blue-dark",
    name: "Azul clássico escuro",
    description: "Tema clássico com background azul escuro na sidebar, semelhante ao visual anterior.",
    colors: {
      primary: "#2563eb",
      primaryHover: "#1d4ed8",
      primarySoft: "#dbeafe",
      accent: "#38bdf8",
      sidebarStart: "#0f2747",
      sidebarEnd: "#081827",
      sidebarAccent: "#60a5fa",
    },
  },
  {
    id: "ocean-blue",
    name: "Azul oceano",
    description: "Background de menu em azul petróleo com destaque cyan.",
    colors: {
      primary: "#0ea5e9",
      primaryHover: "#0284c7",
      primarySoft: "#e0f2fe",
      accent: "#22d3ee",
      sidebarStart: "#063b5c",
      sidebarEnd: "#082f49",
      sidebarAccent: "#67e8f9",
    },
  },
  {
    id: "emerald-dark",
    name: "Verde escuro",
    description: "Background verde corporativo para sistemas financeiros e operacionais.",
    colors: {
      primary: "#059669",
      primaryHover: "#047857",
      primarySoft: "#d1fae5",
      accent: "#34d399",
      sidebarStart: "#064e3b",
      sidebarEnd: "#022c22",
      sidebarAccent: "#6ee7b7",
    },
  },
  {
    id: "purple-dark",
    name: "Roxo escuro",
    description: "Background roxo/índigo com aparência SaaS moderna.",
    colors: {
      primary: "#7c3aed",
      primaryHover: "#6d28d9",
      primarySoft: "#ede9fe",
      accent: "#c084fc",
      sidebarStart: "#312e81",
      sidebarEnd: "#1e1b4b",
      sidebarAccent: "#c4b5fd",
    },
  },
  {
    id: "graphite-dark",
    name: "Grafite escuro",
    description: "Background grafite executivo, sóbrio e compacto.",
    colors: {
      primary: "#334155",
      primaryHover: "#1e293b",
      primarySoft: "#e2e8f0",
      accent: "#94a3b8",
      sidebarStart: "#1f2937",
      sidebarEnd: "#0f172a",
      sidebarAccent: "#cbd5e1",
    },
  },
  {
    id: "orange-dark",
    name: "Laranja escuro",
    description: "Tema anterior com sidebar/background laranja escuro, preservado para compatibilidade visual.",
    colors: {
      primary: "#ea580c",
      primaryHover: "#c2410c",
      primarySoft: "#ffedd5",
      accent: "#fb923c",
      sidebarStart: "#7c2d12",
      sidebarEnd: "#431407",
      sidebarAccent: "#fdba74",
    },
  },
  {
    id: "dark-navy",
    name: "Azul escuro",
    description: "Preset escuro opcional para usuários que preferem alto contraste.",
    colors: {
      primary: "#3b82f6",
      primaryHover: "#2563eb",
      primarySoft: "#1e3a8a",
      accent: "#38bdf8",
      sidebarStart: "#0f2747",
      sidebarEnd: "#081827",
      sidebarAccent: "#60a5fa",
    },
  },
];

export const defaultVisualPreferences: UserVisualPreferences = {
  mode: "light",
  preset: "brand-primary",
  density: "compact",
};

export function getVisualPreferenceKey(userKey?: string | number | null) {
  const normalized = String(userKey || "anonymous").replace(/[^a-zA-Z0-9_.-]/g, "_");
  return `pige360-deployer:user-visual-preferences:${normalized}`;
}

export function getCustomVisualThemesKey(userKey?: string | number | null) {
  const normalized = String(userKey || "anonymous").replace(/[^a-zA-Z0-9_.-]/g, "_");
  return `pige360-deployer:user-custom-visual-themes:${normalized}`;
}

export function loadCustomVisualThemes(userKey?: string | number | null): UserCustomVisualTheme[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(getCustomVisualThemesKey(userKey));
    const parsed = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((item) => item && typeof item === "object" && typeof item.id === "string" && typeof item.name === "string" && item.colors)
      .map((item) => ({
        id: item.id.startsWith("custom:") ? item.id : `custom:${item.id}`,
        name: item.name,
        description: item.description || "Tema personalizado do usuário.",
        custom: true,
        active: item.active !== false,
        colors: normalizeThemeColors(item.colors),
        typography: normalizeThemeTypography(item.typography),
      }));
  } catch {
    return [];
  }
}

export function saveCustomVisualThemes(userKey: string | number | null | undefined, themes: UserCustomVisualTheme[]) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(getCustomVisualThemesKey(userKey), JSON.stringify(themes));
}

export function findThemePreset(id: string, customThemes: VisualThemePreset[] = []): VisualThemePreset {
  return [...customThemes, ...visualThemePresets].find((item) => item.id === id) || visualThemePresets[0];
}

export function loadVisualPreferences(userKey?: string | number | null): UserVisualPreferences {
  if (typeof window === "undefined") return { ...defaultVisualPreferences };
  try {
    const raw = window.localStorage.getItem(getVisualPreferenceKey(userKey));
    if (!raw) return { ...defaultVisualPreferences };
    const parsed = JSON.parse(raw) as Partial<UserVisualPreferences>;
    const preset = typeof parsed.preset === "string" && parsed.preset.trim() ? String(parsed.preset) : defaultVisualPreferences.preset;
    const mode = parsed.mode === "dark" ? "dark" : "light";
    const density = parsed.density === "comfortable" || parsed.density === "dense" ? parsed.density : "compact";
    return { mode, preset, density };
  } catch {
    return { ...defaultVisualPreferences };
  }
}

export function saveVisualPreferences(userKey: string | number | null | undefined, preferences: UserVisualPreferences) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(getVisualPreferenceKey(userKey), JSON.stringify(preferences));
}

function normalizeThemeColors(colors: Partial<VisualThemeColors>): VisualThemeColors {
  const fallback = visualThemePresets[0].colors;
  return {
    primary: safeHex(colors.primary, fallback.primary),
    primaryHover: safeHex(colors.primaryHover, colors.primary || fallback.primaryHover),
    primarySoft: safeHex(colors.primarySoft, fallback.primarySoft),
    accent: safeHex(colors.accent, fallback.accent),
    sidebarStart: safeHex(colors.sidebarStart, fallback.sidebarStart),
    sidebarEnd: safeHex(colors.sidebarEnd, fallback.sidebarEnd),
    sidebarAccent: safeHex(colors.sidebarAccent, colors.primary || fallback.sidebarAccent),
  };
}

function safeNumber(value: unknown, fallback: number, min: number, max: number): number {
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return fallback;
  return Math.min(max, Math.max(min, n));
}

function normalizeThemeTypography(typography?: Partial<VisualThemeTypography>): VisualThemeTypography {
  return {
    fontFamily: typeof typography?.fontFamily === "string" && typography.fontFamily.trim()
      ? typography.fontFamily.trim()
      : defaultThemeTypography.fontFamily,
    fontScale: safeNumber(typography?.fontScale, defaultThemeTypography.fontScale, 0.86, 1.18),
    titleScale: safeNumber(typography?.titleScale, defaultThemeTypography.titleScale, 0.88, 1.22),
    textColor: safeHex(typography?.textColor, defaultThemeTypography.textColor),
    mutedColor: safeHex(typography?.mutedColor, defaultThemeTypography.mutedColor),
  };
}

function safeHex(value: unknown, fallback: string): string {
  return typeof value === "string" && /^#[0-9a-fA-F]{6}$/.test(value) ? value : fallback;
}

function isDarkSidebar(hex: string): boolean {
  const normalized = safeHex(hex, "#ffffff").slice(1);
  const r = parseInt(normalized.slice(0, 2), 16);
  const g = parseInt(normalized.slice(2, 4), 16);
  const b = parseInt(normalized.slice(4, 6), 16);
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return luminance < 0.42;
}


function hexToRgb(hex: string, fallback = "#0f172a") {
  const normalized = safeHex(hex, fallback).slice(1);
  return {
    r: parseInt(normalized.slice(0, 2), 16),
    g: parseInt(normalized.slice(2, 4), 16),
    b: parseInt(normalized.slice(4, 6), 16),
  };
}

function rgbToHex(r: number, g: number, b: number): string {
  const toHex = (value: number) => Math.round(Math.min(255, Math.max(0, value))).toString(16).padStart(2, "0");
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
}

function mixHex(a: string, b: string, weightA = 0.5): string {
  const first = hexToRgb(a);
  const second = hexToRgb(b);
  const wa = Math.min(1, Math.max(0, weightA));
  const wb = 1 - wa;
  return rgbToHex(first.r * wa + second.r * wb, first.g * wa + second.g * wb, first.b * wa + second.b * wb);
}

export function applyVisualPreferences(preferences: UserVisualPreferences, customThemes: VisualThemePreset[] = []) {
  if (typeof document === "undefined") return;
  const preset = findThemePreset(preferences.preset, customThemes);
  const root = document.documentElement;
  const darkSidebar = isDarkSidebar(preset.colors.sidebarStart) || isDarkSidebar(preset.colors.sidebarEnd) || (preferences.mode === "dark" && preset.id === "dark-navy");
  const typography = normalizeThemeTypography(preset.typography);
  const adaptiveDarkStart = darkSidebar ? preset.colors.sidebarStart : mixHex(preset.colors.primaryHover, "#020617", 0.58);
  const adaptiveDarkEnd = darkSidebar ? preset.colors.sidebarEnd : mixHex(preset.colors.primary, "#020617", 0.38);
  const adaptiveDarkPage = mixHex(adaptiveDarkEnd, "#020617", 0.62);
  const adaptiveDarkSurface = mixHex(adaptiveDarkStart, "#111827", 0.36);
  const adaptiveDarkCard = mixHex(adaptiveDarkStart, "#0f172a", 0.28);
  const adaptiveDarkMuted = mixHex(adaptiveDarkStart, "#1f2937", 0.22);
  const adaptiveDarkBorder = mixHex(preset.colors.sidebarAccent || preset.colors.primary, "#334155", 0.22);

  root.setAttribute("data-theme", preferences.mode);
  root.setAttribute("data-density", preferences.density);
  root.setAttribute("data-theme-preset", preset.id);
  root.style.setProperty("--primary", preset.colors.primary);
  root.style.setProperty("--primary-hover", preset.colors.primaryHover);
  root.style.setProperty("--primary-soft", preset.colors.primarySoft);
  root.style.setProperty("--accent", preset.colors.accent);
  root.style.setProperty("--sidebar-start", preset.colors.sidebarStart);
  root.style.setProperty("--sidebar-end", preset.colors.sidebarEnd);
  root.style.setProperty("--sidebar-accent", preset.colors.sidebarAccent);
  root.style.setProperty("--sidebar-bg", `linear-gradient(180deg, ${preset.colors.sidebarStart} 0%, ${preset.colors.sidebarEnd} 100%)`);
  root.style.setProperty("--sidebar-text", darkSidebar ? "#f8fafc" : "#0f172a");
  root.style.setProperty("--sidebar-muted", darkSidebar ? "rgba(226,232,240,.78)" : "#64748b");
  root.style.setProperty("--sidebar-link", darkSidebar ? "#dbeafe" : "#334155");
  root.style.setProperty("--sidebar-hover-bg", darkSidebar ? "rgba(255,255,255,.08)" : "rgba(37,99,235,.075)");
  root.style.setProperty("--sidebar-active-bg", preset.colors.primary);
  root.style.setProperty("--sidebar-active-text", "#ffffff");
  root.style.setProperty("--sidebar-border", darkSidebar ? "rgba(255,255,255,.10)" : "rgba(148,163,184,.24)");
  root.style.setProperty("--sidebar-footer-bg", darkSidebar ? "rgba(2,6,23,.10)" : "rgba(255,255,255,.72)");
  root.style.setProperty("--sidebar-brand-text", darkSidebar ? "#f8fafc" : "#0f172a");
  root.style.setProperty("--sidebar-brand-muted", darkSidebar ? "rgba(226,232,240,.82)" : "#64748b");
  root.style.setProperty("--sidebar-brand-bg", darkSidebar ? "rgba(2,6,23,.18)" : "rgba(255,255,255,.58)");
  root.style.setProperty("--sidebar-brand-logo-filter", darkSidebar ? "drop-shadow(0 6px 12px rgba(0,0,0,.30))" : "drop-shadow(0 8px 18px rgba(37,99,235,.18))");
  root.style.setProperty("--adaptive-dark-page-bg", adaptiveDarkPage);
  root.style.setProperty("--adaptive-dark-surface-bg", adaptiveDarkSurface);
  root.style.setProperty("--adaptive-dark-card-bg", adaptiveDarkCard);
  root.style.setProperty("--adaptive-dark-muted-bg", adaptiveDarkMuted);
  root.style.setProperty("--adaptive-dark-border", adaptiveDarkBorder);
  root.style.setProperty("--adaptive-dark-text", "#f8fafc");
  root.style.setProperty("--adaptive-dark-muted", "#c6d0dd");
  root.style.setProperty("--adaptive-dark-hero", `linear-gradient(135deg, ${mixHex(adaptiveDarkSurface, preset.colors.primary, 0.78)}, ${mixHex(adaptiveDarkPage, preset.colors.accent, 0.88)})`);
  root.style.setProperty("--app-font-family", typography.fontFamily);
  root.style.setProperty("--app-font-scale", String(typography.fontScale));
  root.style.setProperty("--app-title-scale", String(typography.titleScale));
  if (preset.custom) {
    root.style.setProperty("--text-color", preferences.mode === "dark" ? "#e5edf8" : typography.textColor);
    root.style.setProperty("--text-muted", preferences.mode === "dark" ? "#aab7c8" : typography.mutedColor);
  }

}
