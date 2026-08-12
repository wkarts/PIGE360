import { isTauriRuntime } from "@pige360/app-manifest";
function invoke(command, args) {
    const fn = window.__TAURI__?.core?.invoke;
    if (typeof fn !== "function")
        return Promise.reject(new Error("Bridge Tauri indisponível"));
    return fn(command, args);
}
export class NativeOfflineStore {
    tenantId;
    userId;
    constructor(tenantId, userId) {
        this.tenantId = tenantId;
        this.userId = userId;
    }
    initialize() {
        return invoke("offline_initialize", { tenantId: this.tenantId, userId: this.userId });
    }
    enqueue(operation) {
        return invoke("offline_outbox_enqueue", {
            tenantId: this.tenantId, userId: this.userId,
            idempotencyKey: operation.idempotencyKey, aggregateType: operation.aggregateType,
            aggregateId: operation.aggregateId, baseRevision: operation.baseRevision, payload: operation.payload,
        });
    }
    pending(limit = 100) {
        return invoke("offline_outbox_pending", { tenantId: this.tenantId, userId: this.userId, limit });
    }
    applyResult(idempotencyKey, result) {
        return invoke("offline_outbox_apply_result", { tenantId: this.tenantId, userId: this.userId, idempotencyKey, result });
    }
    cachePut(key, payload, serverRevision = 0, expiresAt) {
        const args = { tenantId: this.tenantId, userId: this.userId, cacheKey: key, payload, serverRevision };
        if (expiresAt !== undefined)
            args.expiresAt = expiresAt;
        return invoke("offline_cache_put", args);
    }
    cacheGet(key) {
        return invoke("offline_cache_get", { tenantId: this.tenantId, userId: this.userId, cacheKey: key });
    }
}
export class TransactionalOutbox {
    #items = new Map();
    enqueue(operation) {
        const existing = this.#items.get(operation.idempotencyKey);
        if (existing && JSON.stringify(existing) !== JSON.stringify(operation))
            throw new Error("IDEMPOTENCY_CONFLICT");
        this.#items.set(operation.idempotencyKey, structuredClone(operation));
    }
    acknowledge(idempotencyKey) { return this.#items.delete(idempotencyKey); }
    pending(limit = 100) {
        return [...this.#items.values()].sort((a, b) => a.createdAt.localeCompare(b.createdAt)).slice(0, Math.max(1, Math.min(limit, 500))).map(item => structuredClone(item));
    }
}
export function createOfflineStore(tenantId, userId) {
    return isTauriRuntime() ? new NativeOfflineStore(tenantId, userId) : null;
}
export function detectConflict(operation, serverRevision, serverPayload) {
    if (operation.baseRevision === serverRevision)
        return null;
    return { operation, serverRevision, serverPayload, policy: "manual" };
}
