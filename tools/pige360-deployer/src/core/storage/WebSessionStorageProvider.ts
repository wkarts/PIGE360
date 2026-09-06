import type { StorageProvider, StorageScope } from "./StorageProvider";
import { cloneStorageValue } from "./StorageProvider";
import { appBranding } from "../../config/appBranding";

export class WebSessionStorageProvider implements StorageProvider {
  private readonly namespace: string;

  constructor(namespace = appBranding.storagePrefix) {
    this.namespace = namespace;
  }

  providerName(): string {
    return "web-session-storage";
  }

  scope(): StorageScope {
    return "session";
  }

  isAvailable(): boolean {
    try {
      if (typeof window === "undefined" || !window.sessionStorage) return false;
      const key = `${this.namespace}:__storage_check__`;
      window.sessionStorage.setItem(key, "1");
      window.sessionStorage.removeItem(key);
      return true;
    } catch {
      return false;
    }
  }

  async get<T>(key: string, fallback?: T): Promise<T | null> {
    if (!this.isAvailable()) return fallback ?? null;
    const raw = window.sessionStorage.getItem(this.key(key));
    if (raw == null) return fallback ?? null;
    try {
      return JSON.parse(raw) as T;
    } catch {
      return raw as T;
    }
  }

  async set<T>(key: string, value: T): Promise<void> {
    if (!this.isAvailable()) return;
    window.sessionStorage.setItem(this.key(key), JSON.stringify(cloneStorageValue(value)));
  }

  async remove(key: string): Promise<void> {
    if (!this.isAvailable()) return;
    window.sessionStorage.removeItem(this.key(key));
  }

  async clear(prefix = ""): Promise<void> {
    if (!this.isAvailable()) return;
    const keys = await this.keys(prefix);
    keys.forEach((key) => window.sessionStorage.removeItem(this.key(key)));
  }

  async keys(prefix = ""): Promise<string[]> {
    if (!this.isAvailable()) return [];
    const ns = `${this.namespace}:`;
    const fullPrefix = this.key(prefix);
    const result: string[] = [];
    for (let index = 0; index < window.sessionStorage.length; index += 1) {
      const storageKey = window.sessionStorage.key(index);
      if (!storageKey) continue;
      if (!storageKey.startsWith(ns)) continue;
      if (prefix && !storageKey.startsWith(fullPrefix)) continue;
      result.push(storageKey.slice(ns.length));
    }
    return result.sort();
  }

  private key(key: string): string {
    return `${this.namespace}:${key}`;
  }
}
