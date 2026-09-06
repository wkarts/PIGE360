import { useCommandProvider } from "../invoker/CommandProviderFactory";
import { useDatabaseProvider } from "../database/DatabaseProviderFactory";
import { useFileProvider } from "../filesystem/FileProviderFactory";
import { useNotificationProvider } from "../notifications/NotificationProviderFactory";
import { usePrintProvider } from "../printer/PrintProviderFactory";
import { getPlatformInfo } from "../runtime/RuntimeProvider";
import { useLocalStorageProvider, useSessionStorageProvider } from "../storage/StorageProviderFactory";

export interface RuntimeDiagnosticItem {
  key: string;
  label: string;
  value: string;
  ok: boolean;
}

export async function collectRuntimeDiagnostics(): Promise<RuntimeDiagnosticItem[]> {
  const platform = getPlatformInfo();
  const command = useCommandProvider();
  const db = useDatabaseProvider();
  await db.bootstrap();
  const localStorageProvider = useLocalStorageProvider();
  const sessionStorageProvider = useSessionStorageProvider();

  return [
    { key: "runtime", label: "Runtime", value: platform.mode, ok: true },
    { key: "tauri", label: "Tauri detectado", value: platform.isTauri ? "Sim" : "Não", ok: true },
    { key: "pwa", label: "PWA/standalone", value: platform.isPwa ? "Sim" : "Não", ok: true },
    { key: "online", label: "Conectividade", value: platform.online ? "Online" : "Offline", ok: true },
    { key: "command", label: "Command Provider", value: command.providerName(), ok: true },
    { key: "database", label: "Database Provider", value: db.providerName(), ok: true },
    { key: "filesystem", label: "File Provider", value: useFileProvider().providerName(), ok: true },
    { key: "notification", label: "Notification Provider", value: useNotificationProvider().providerName(), ok: true },
    { key: "printer", label: "Print Provider", value: usePrintProvider().providerName(), ok: true },
    { key: "indexeddb", label: "IndexedDB", value: "indexedDB" in window ? "Disponível" : "Indisponível", ok: "indexedDB" in window },
    { key: "localstorage", label: "LocalStorage", value: localStorageProvider.isAvailable() ? "Disponível" : "Indisponível", ok: localStorageProvider.isAvailable() },
    { key: "sessionstorage", label: "SessionStorage", value: sessionStorageProvider.isAvailable() ? "Disponível" : "Indisponível", ok: sessionStorageProvider.isAvailable() },
    { key: "serviceworker", label: "Service Worker", value: "serviceWorker" in navigator ? "Disponível" : "Indisponível", ok: "serviceWorker" in navigator },
  ];
}
