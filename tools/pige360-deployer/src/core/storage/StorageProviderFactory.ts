import type { StorageProvider } from "./StorageProvider";
import { WebLocalStorageProvider } from "./WebLocalStorageProvider";
import { WebSessionStorageProvider } from "./WebSessionStorageProvider";

let localInstance: StorageProvider | null = null;
let sessionInstance: StorageProvider | null = null;

export function useLocalStorageProvider(): StorageProvider {
  if (!localInstance) {
    localInstance = new WebLocalStorageProvider();
  }
  return localInstance;
}

export function useSessionStorageProvider(): StorageProvider {
  if (!sessionInstance) {
    sessionInstance = new WebSessionStorageProvider();
  }
  return sessionInstance;
}

export function useStorageProvider(scope: "local" | "session" = "local"): StorageProvider {
  return scope === "session" ? useSessionStorageProvider() : useLocalStorageProvider();
}
