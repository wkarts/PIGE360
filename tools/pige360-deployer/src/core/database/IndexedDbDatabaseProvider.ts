import type { DatabaseProvider, TableRecord } from "./DatabaseTypes";

import { appDbName } from "../../config/appBranding";

const DB_NAME = appDbName();
const DB_VERSION = 1;
const STORE = "records";
const SEQUENCE_STORE = "sequences";
const DEFAULT_TABLES = [
  "companies",
  "users",
  "profiles",
  "departamentos",
  "funcoes",
  "centro_custos",
  "clientes",
  "fornecedores",
  "produtos",
  "app_logs",
  "settings",
  "integrations",
  "sync_queue",
];

interface StoredRecord extends TableRecord {
  table: string;
  storageKey: string;
  created_at?: string;
  updated_at?: string;
}

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onerror = () => reject(request.error ?? new Error("Falha ao abrir IndexedDB."));
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE)) {
        const store = db.createObjectStore(STORE, { keyPath: "storageKey" });
        store.createIndex("table", "table", { unique: false });
      }
      if (!db.objectStoreNames.contains(SEQUENCE_STORE)) {
        db.createObjectStore(SEQUENCE_STORE, { keyPath: "table" });
      }
    };
    request.onsuccess = () => resolve(request.result);
  });
}

function txStore(db: IDBDatabase, storeName: string, mode: IDBTransactionMode): IDBObjectStore {
  return db.transaction(storeName, mode).objectStore(storeName);
}

function requestToPromise<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onerror = () => reject(request.error ?? new Error("Falha em operação IndexedDB."));
    request.onsuccess = () => resolve(request.result);
  });
}

function nowIso(): string {
  return new Date().toISOString();
}

function normalizeForSearch(value: unknown): string {
  return String(value ?? "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
}

export class IndexedDbDatabaseProvider implements DatabaseProvider {
  providerName(): string {
    return "indexeddb";
  }

  async bootstrap(): Promise<void> {
    const db = await openDatabase();
    db.close();
    await this.seedDefaults();
  }

  async list<T extends TableRecord>(table: string, search = "", fields: string[] = []): Promise<T[]> {
    const db = await openDatabase();
    try {
      const index = txStore(db, STORE, "readonly").index("table");
      const rows = await requestToPromise<StoredRecord[]>(index.getAll(table));
      const term = normalizeForSearch(search.trim());
      const filtered = term
        ? rows.filter((row) => {
            const keys = fields.length ? fields : Object.keys(row);
            return keys.some((key) => normalizeForSearch(row[key]).includes(term));
          })
        : rows;
      return filtered
        .sort((a, b) => Number(a.id ?? 0) - Number(b.id ?? 0))
        .map(({ storageKey: _storageKey, table: _table, ...record }) => record as T);
    } finally {
      db.close();
    }
  }

  async get<T extends TableRecord>(table: string, id: number | string): Promise<T | null> {
    const db = await openDatabase();
    try {
      const row = await requestToPromise<StoredRecord | undefined>(txStore(db, STORE, "readonly").get(`${table}:${id}`));
      if (!row) return null;
      const { storageKey: _storageKey, table: _table, ...record } = row;
      return record as T;
    } finally {
      db.close();
    }
  }

  async save<T extends TableRecord>(table: string, payload: T): Promise<T> {
    const db = await openDatabase();
    try {
      const id = payload.id ?? (await this.nextId(db, table));
      const existing = await requestToPromise<StoredRecord | undefined>(txStore(db, STORE, "readonly").get(`${table}:${id}`));
      const timestamp = nowIso();
      const row: StoredRecord = {
        ...existing,
        ...payload,
        id,
        table,
        storageKey: `${table}:${id}`,
        created_at: existing?.created_at ?? String(payload.created_at ?? timestamp),
        updated_at: timestamp,
      };
      await requestToPromise(txStore(db, STORE, "readwrite").put(row));
      const { storageKey: _storageKey, table: _table, ...record } = row;
      return record as T;
    } finally {
      db.close();
    }
  }

  async delete(table: string, id: number | string): Promise<boolean> {
    const db = await openDatabase();
    try {
      await requestToPromise(txStore(db, STORE, "readwrite").delete(`${table}:${id}`));
      return true;
    } finally {
      db.close();
    }
  }

  async clear(table: string): Promise<void> {
    const rows = await this.list(table);
    await Promise.all(rows.map((row) => (row.id == null ? Promise.resolve(false) : this.delete(table, row.id))));
  }

  private async nextId(db: IDBDatabase, table: string): Promise<number> {
    const store = txStore(db, SEQUENCE_STORE, "readwrite");
    const current = await requestToPromise<{ table: string; value: number } | undefined>(store.get(table));
    const value = (current?.value ?? 0) + 1;
    await requestToPromise(store.put({ table, value }));
    return value;
  }

  private async seedDefaults(): Promise<void> {
    for (const table of DEFAULT_TABLES) {
      await this.list(table);
    }

    // O Web/PWA não cria dados demonstrativos nem credencial administrativa pública.
    // Para autenticação, use o provider da API interna/remota configurado no ambiente.
  }
}
