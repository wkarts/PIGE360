import { IndexedDbDatabaseProvider } from "./IndexedDbDatabaseProvider";
import { LocalStorageDatabaseProvider } from "./LocalStorageDatabaseProvider";
import type { DatabaseProvider } from "./DatabaseTypes";

let instance: DatabaseProvider | null = null;

function indexedDbAvailable(): boolean {
  return typeof window !== "undefined" && "indexedDB" in window;
}

export function useDatabaseProvider(): DatabaseProvider {
  if (instance) return instance;
  instance = indexedDbAvailable() ? new IndexedDbDatabaseProvider() : new LocalStorageDatabaseProvider();
  return instance;
}

export function useLocalStorageDatabaseProvider(): DatabaseProvider {
  return new LocalStorageDatabaseProvider();
}

export function resetDatabaseProviderForTests(): void {
  instance = null;
}
