export type StorageScope = "local" | "session" | "indexeddb";

export interface StorageProvider {
  providerName(): string;
  scope(): StorageScope;
  isAvailable(): boolean;
  get<T>(key: string, fallback?: T): Promise<T | null>;
  set<T>(key: string, value: T): Promise<void>;
  remove(key: string): Promise<void>;
  clear(prefix?: string): Promise<void>;
  keys(prefix?: string): Promise<string[]>;
}

export function cloneStorageValue<T>(value: T): T {
  if (value == null) return value;
  return JSON.parse(JSON.stringify(value)) as T;
}
