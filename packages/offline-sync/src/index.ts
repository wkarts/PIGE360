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
  return isTauriRuntime() ? new NativeOfflineStore(tenantId, userId) : null;
}

export function detectConflict<T>(operation: SyncOperation<T>, serverRevision: number, serverPayload: T): SyncConflict<T> | null {
  if (operation.baseRevision === serverRevision) return null;
  return { operation, serverRevision, serverPayload, policy: "manual" };
}
