import { projectConfig } from "./projectConfig";

function slugify(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-zA-Z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .toLowerCase() || "app";
}

function envValue(key: string, fallback: string): string {
  const value = import.meta.env[key] as string | undefined;
  return value && value.trim() ? value.trim() : fallback;
}

const configuredName = envValue("VITE_APP_NAME", projectConfig.app.name);
const configuredIdentifier = envValue("VITE_APP_IDENTIFIER", projectConfig.app.identifier);
const configuredLocalDataDir = envValue("VITE_APP_LOCAL_DATA_DIR", projectConfig.app.localDataDir || slugify(configuredIdentifier || configuredName));
const configuredStoragePrefix = envValue("VITE_APP_STORAGE_PREFIX", projectConfig.app.storagePrefix || slugify(configuredIdentifier || configuredName).replace(/_/g, "-"));

export const appBranding = {
  appName: configuredName,
  shortName: envValue("VITE_APP_SHORT_NAME", projectConfig.app.shortName),
  productName: envValue("VITE_APP_PRODUCT_NAME", projectConfig.app.productName || configuredName),
  windowTitle: envValue("VITE_APP_WINDOW_TITLE", projectConfig.app.windowTitle || configuredName),
  subtitle: envValue("VITE_APP_SUBTITLE", projectConfig.app.subtitle),
  description: envValue("VITE_APP_DESCRIPTION", projectConfig.app.description),
  developer: envValue("VITE_APP_DEVELOPER", projectConfig.app.developer),
  identifier: configuredIdentifier,
  localDataDir: configuredLocalDataDir,
  storagePrefix: configuredStoragePrefix,
  logoLight: envValue("VITE_APP_LOGO_LIGHT", ""),
  logoDark: envValue("VITE_APP_LOGO_DARK", ""),
  logoMark: envValue("VITE_APP_LOGO_MARK", ""),
};

export function storageKey(key: string): string {
  return `${appBranding.storagePrefix}:${key}`;
}

export function appDbName(suffix = "desktop_web"): string {
  return `${appBranding.localDataDir}_${suffix}`.replace(/[^a-zA-Z0-9_]/g, "_");
}
