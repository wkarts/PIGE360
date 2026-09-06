export type RuntimeMode = "web" | "pwa" | "tauri";
export type NativePlatform = "android" | "ios" | "desktop" | "web" | "unknown";

export interface PlatformInfo {
  mode: RuntimeMode;
  nativePlatform: NativePlatform;
  isTauri: boolean;
  isPwa: boolean;
  isWeb: boolean;
  isMobile: boolean;
  isNativeMobile: boolean;
  userAgent: string;
  platform: string;
  online: boolean;
  appVersion: string;
}
