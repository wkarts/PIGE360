import { isTauriRuntime } from "@pige360/app-manifest";

export type SyncOperation<T = unknown> = {
  idempotencyKey: string;
  aggregateType: string;
  aggregateId: string;
  baseRevision: number;
  localRevision: number;
  payload: T;
  createdAt: string;
};

export type NativeOfflineContext = { device_id: string; database_path: string };
export type NativePendingOperation<T = unknown> = {
  id: string;
  idempotency_key: string;
  aggregate_type: string;
  aggregate_id: string;
  base_revision: number;
  payload: T;
  attempts: number;
  created_at: string;
};

export type SyncConflict<T = unknown> = {
  operation: SyncOperation<T>;
  serverRevision: number;
  serverPayload: T;
  policy: "manual" | "server_wins" | "client_wins" | "field_merge";
};

function invoke<T>(command: string, args?: Record<string, unknown>): Promise<T> {
  const fn = window.__TAURI__?.core?.invoke;
  if (typeof fn !== "function") return Promise.reject(new Error("Bridge Tauri indisponível"));
  return fn<T>(command, args);
}

export class NativeOfflineStore {
  constructor(readonly tenantId: string, readonly userId: string) {}

  initialize(): Promise<NativeOfflineContext> {
    return invoke("offline_initialize", { tenantId: this.tenantId, userId: this.userId });
  }

  enqueue<T>(operation: SyncOperation<T>): Promise<void> {
    return invoke("offline_outbox_enqueue", {
      tenantId: this.tenantId, userId: this.userId,
      idempotencyKey: operation.idempotencyKey, aggregateType: operation.aggregateType,
      aggregateId: operation.aggregateId, baseRevision: operation.baseRevision, payload: operation.payload,
    });
  }

  pending<T>(limit = 100): Promise<NativePendingOperation<T>[]> {
    return invoke("offline_outbox_pending", { tenantId: this.tenantId, userId: this.userId, limit });
  }

  applyResult(idempotencyKey: string, result: unknown): Promise<string> {
    return invoke("offline_outbox_apply_result", { tenantId: this.tenantId, userId: this.userId, idempotencyKey, result });
  }

  cachePut(key: string, payload: unknown, serverRevision = 0, expiresAt?: string): Promise<void> {
    const args: Record<string, unknown> = { tenantId:this.tenantId,userId:this.userId,cacheKey:key,payload,serverRevision };
    if (expiresAt !== undefined) args.expiresAt = expiresAt;
    return invoke("offline_cache_put", args);
  }

  cacheGet<T>(key: string): Promise<T | null> {
    return invoke<T | null>("offline_cache_get", { tenantId:this.tenantId,userId:this.userId,cacheKey:key });
  }
}

type BrowserCacheRecord = {
  key: string;
  payload: unknown;
  serverRevision: number;
  expiresAt?: string;
};

type BrowserMetadataRecord = {
  key: string;
  value: string;
};

function requestResult<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("Falha no IndexedDB"));
  });
}

function transactionDone(transaction: IDBTransaction): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onabort = () => reject(transaction.error ?? new Error("Transação IndexedDB cancelada"));
    transaction.onerror = () => reject(transaction.error ?? new Error("Falha na transação IndexedDB"));
  });
}

function browserScope(tenantId: string, userId: string): string {
  return `${encodeURIComponent(tenantId)}:${encodeURIComponent(userId)}`;
}

function randomDeviceId(): string {
  const browserCrypto = globalThis.crypto;
  if (!browserCrypto) throw new Error("Web Crypto indisponível para identificar o dispositivo offline");
  if (typeof browserCrypto.randomUUID === "function") return browserCrypto.randomUUID();
  const bytes = new Uint8Array(16);
  browserCrypto.getRandomValues(bytes);
  bytes[6] = (bytes[6]! & 0x0f) | 0x40;
  bytes[8] = (bytes[8]! & 0x3f) | 0x80;
  const hex = [...bytes].map((value) => value.toString(16).padStart(2, "0"));
  return `${hex.slice(0, 4).join("")}-${hex.slice(4, 6).join("")}-${hex.slice(6, 8).join("")}-${hex.slice(8, 10).join("")}-${hex.slice(10).join("")}`;
}

/**
 * Persistência web equivalente ao contrato nativo. Cada par tenant/usuário usa
 * um banco próprio, impedindo que troca de sessão compartilhe outbox ou cache.
 */
export class BrowserOfflineStore extends NativeOfflineStore {
  readonly #databaseName: string;
  readonly #database: Promise<IDBDatabase>;

  constructor(tenantId: string, userId: string, factory: IDBFactory = indexedDB) {
    super(tenantId, userId);
    this.#databaseName = `pige360-offline:${browserScope(tenantId, userId)}`;
    this.#database = this.#open(factory);
  }

  #open(factory: IDBFactory): Promise<IDBDatabase> {
    return new Promise<IDBDatabase>((resolve, reject) => {
      // Versão 2 preserva bancos da primeira implementação web e acrescenta
      // metadados sem recriar ou apagar outbox/cache.
      const request = factory.open(this.#databaseName, 2);
      request.onupgradeneeded = () => {
        const database = request.result;
        if (!database.objectStoreNames.contains("outbox")) {
          database.createObjectStore("outbox", { keyPath: "idempotencyKey" });
        }
        if (!database.objectStoreNames.contains("cache")) {
          database.createObjectStore("cache", { keyPath: "key" });
        }
        if (!database.objectStoreNames.contains("metadata")) {
          database.createObjectStore("metadata", { keyPath: "key" });
        }
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error ?? new Error("Não foi possível abrir o armazenamento offline"));
      request.onblocked = () => reject(new Error("Atualização do armazenamento offline bloqueada por outra aba"));
    });
  }

  async initialize(): Promise<NativeOfflineContext> {
    const database = await this.#database;
    const transaction = database.transaction("metadata", "readwrite");
    const done = transactionDone(transaction);
    const store = transaction.objectStore("metadata");
    const current = await requestResult(store.get("device_id")) as BrowserMetadataRecord | undefined;
    const deviceId = current?.value ?? randomDeviceId();
    if (!current) store.put({ key: "device_id", value: deviceId } satisfies BrowserMetadataRecord);
    await done;
    return { device_id: deviceId, database_path: `indexeddb://${this.#databaseName}` };
  }

  async enqueue<T>(operation: SyncOperation<T>): Promise<void> {
    const database = await this.#database;
    const transaction = database.transaction("outbox", "readwrite");
    const done = transactionDone(transaction);
    const store = transaction.objectStore("outbox");
    const existing = await requestResult(store.get(operation.idempotencyKey)) as SyncOperation<T> | undefined;
    if (existing && JSON.stringify(existing) !== JSON.stringify(operation)) {
      transaction.abort();
      try { await done; } catch { /* cancelamento esperado para conflito */ }
      throw new Error("IDEMPOTENCY_CONFLICT");
    }
    store.put(structuredClone(operation));
    await done;
  }

  async pending<T>(limit = 100): Promise<NativePendingOperation<T>[]> {
    const database = await this.#database;
    const transaction = database.transaction("outbox", "readonly");
    const done = transactionDone(transaction);
    const rows = await requestResult(transaction.objectStore("outbox").getAll()) as SyncOperation<T>[];
    await done;
    return rows
      .sort((a, b) => a.createdAt.localeCompare(b.createdAt))
      .slice(0, Math.max(1, Math.min(limit, 500)))
      .map((operation) => ({
        id: operation.idempotencyKey,
        idempotency_key: operation.idempotencyKey,
        aggregate_type: operation.aggregateType,
        aggregate_id: operation.aggregateId,
        base_revision: operation.baseRevision,
        payload: structuredClone(operation.payload),
        attempts: 0,
        created_at: operation.createdAt,
      }));
  }

  async applyResult(idempotencyKey: string, _result: unknown): Promise<string> {
    const database = await this.#database;
    const transaction = database.transaction("outbox", "readwrite");
    const done = transactionDone(transaction);
    transaction.objectStore("outbox").delete(idempotencyKey);
    await done;
    return idempotencyKey;
  }

  async cachePut(key: string, payload: unknown, serverRevision = 0, expiresAt?: string): Promise<void> {
    const database = await this.#database;
    const transaction = database.transaction("cache", "readwrite");
    const done = transactionDone(transaction);
    const record: BrowserCacheRecord = { key, payload: structuredClone(payload), serverRevision };
    if (expiresAt !== undefined) record.expiresAt = expiresAt;
    transaction.objectStore("cache").put(record);
    await done;
  }

  async cacheGet<T>(key: string): Promise<T | null> {
    const database = await this.#database;
    const transaction = database.transaction("cache", "readwrite");
    const done = transactionDone(transaction);
    const store = transaction.objectStore("cache");
    const record = await requestResult(store.get(key)) as BrowserCacheRecord | undefined;
    if (record?.expiresAt && Date.parse(record.expiresAt) <= Date.now()) {
      store.delete(key);
      await done;
      return null;
    }
    await done;
    return record ? structuredClone(record.payload) as T : null;
  }
}

export class TransactionalOutbox<T = unknown> {
  readonly #items = new Map<string, SyncOperation<T>>();
  enqueue(operation: SyncOperation<T>): void {
    const existing = this.#items.get(operation.idempotencyKey);
    if (existing && JSON.stringify(existing) !== JSON.stringify(operation)) throw new Error("IDEMPOTENCY_CONFLICT");
    this.#items.set(operation.idempotencyKey, structuredClone(operation));
  }
  acknowledge(idempotencyKey: string): boolean { return this.#items.delete(idempotencyKey); }
  pending(limit = 100): SyncOperation<T>[] {
    return [...this.#items.values()].sort((a,b)=>a.createdAt.localeCompare(b.createdAt)).slice(0,Math.max(1,Math.min(limit,500))).map(item=>structuredClone(item));
  }
}

export function createOfflineStore(tenantId: string, userId: string): NativeOfflineStore | null {
  if (isTauriRuntime()) return new NativeOfflineStore(tenantId, userId);
  if (typeof window === "undefined") return null;
  if (typeof indexedDB === "undefined") {
    throw new Error("IndexedDB indisponível: a outbox web não pode usar armazenamento volátil");
  }
  return new BrowserOfflineStore(tenantId, userId);
}

export function detectConflict<T>(operation: SyncOperation<T>, serverRevision: number, serverPayload: T): SyncConflict<T> | null {
  if (operation.baseRevision === serverRevision) return null;
  return { operation, serverRevision, serverPayload, policy: "manual" };
}
