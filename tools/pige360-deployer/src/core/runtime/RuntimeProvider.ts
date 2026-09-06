import { projectConfig } from "../../config/projectConfig";
import type { NativePlatform, PlatformInfo, RuntimeMode } from "./RuntimeTypes";

declare global {
  interface Window {
    __TAURI_INTERNALS__?: unknown;
  }
}

export function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && !!window.__TAURI_INTERNALS__;
}

export function isPwaRuntime(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia?.("(display-mode: standalone)").matches ||
    (navigator as Navigator & { standalone?: boolean }).standalone === true;
}

export function getNativePlatform(): NativePlatform {
  if (typeof navigator === "undefined") return "unknown";
  const descriptor = `${navigator.userAgent} ${navigator.platform}`.toLowerCase();
  if (/android/.test(descriptor)) return "android";
  if (/iphone|ipad|ipod/.test(descriptor) || (/mac/.test(descriptor) && navigator.maxTouchPoints > 1)) return "ios";
  if (isTauriRuntime()) return "desktop";
  return "web";
}

export function isNativeMobileRuntime(): boolean {
  const platform = getNativePlatform();
  return isTauriRuntime() && (platform === "android" || platform === "ios");
}

export function getRuntimeMode(): RuntimeMode {
  if (isTauriRuntime()) return "tauri";
  if (isPwaRuntime()) return "pwa";
  return "web";
}

export function getPlatformInfo(): PlatformInfo {
  const mode = getRuntimeMode();
  const nativePlatform = getNativePlatform();
  const isMobile = nativePlatform === "android" || nativePlatform === "ios";
  return {
    mode,
    nativePlatform,
    isTauri: mode === "tauri",
    isPwa: mode === "pwa",
    isWeb: mode === "web",
    isMobile,
    isNativeMobile: mode === "tauri" && isMobile,
    userAgent: navigator.userAgent,
    platform: navigator.platform,
    online: navigator.onLine,
    appVersion: projectConfig.app.version,
  };
}

export function assertWebCompatibleFeature(feature: string, available: boolean): void {
  if (!available) {
    throw new Error(`${feature} não está disponível neste runtime.`);
  }
}
