import type { StorageProvider, StorageScope } from "./StorageProvider";
import { cloneStorageValue } from "./StorageProvider";
import { appBranding } from "../../config/appBranding";

export class WebLocalStorageProvider implements StorageProvider {
  private readonly namespace: string;

  constructor(namespace = appBranding.storagePrefix) {
    this.namespace = namespace;
  }

  providerName(): string {
    return "web-local-storage";
  }

  scope(): StorageScope {
    return "local";
  }

  isAvailable(): boolean {
    try {
      if (typeof window === "undefined" || !window.localStorage) return false;
      const key = `${this.namespace}:__storage_check__`;
      window.localStorage.setItem(key, "1");
      window.localStorage.removeItem(key);
      return true;
    } catch {
      return false;
    }
  }

  async get<T>(key: string, fallback?: T): Promise<T | null> {
    if (!this.isAvailable()) return fallback ?? null;
    const raw = window.localStorage.getItem(this.key(key));
    if (raw == null) return fallback ?? null;
    try {
      return JSON.parse(raw) as T;
    } catch {
      return raw as T;
    }
  }

  async set<T>(key: string, value: T): Promise<void> {
    if (!this.isAvailable()) return;
    window.localStorage.setItem(this.key(key), JSON.stringify(cloneStorageValue(value)));
  }

  async remove(key: string): Promise<void> {
    if (!this.isAvailable()) return;
    window.localStorage.removeItem(this.key(key));
  }

  async clear(prefix = ""): Promise<void> {
    if (!this.isAvailable()) return;
    const keys = await this.keys(prefix);
    keys.forEach((key) => window.localStorage.removeItem(this.key(key)));
  }

  async keys(prefix = ""): Promise<string[]> {
    if (!this.isAvailable()) return [];
    const ns = `${this.namespace}:`;
    const fullPrefix = this.key(prefix);
    const result: string[] = [];
    for (let index = 0; index < window.localStorage.length; index += 1) {
      const storageKey = window.localStorage.key(index);
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
