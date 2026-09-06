import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";


class FakeRequest {
  result;
  error = null;
  onsuccess = null;
  onerror = null;
  onupgradeneeded = null;
  onblocked = null;
}

class FakeTransaction {
  error = null;
  oncomplete = null;
  onabort = null;
  onerror = null;
  #database;
  #aborted = false;
  #pending = 0;
  #completion;

  constructor(database) {
    this.#database = database;
  }

  objectStore(name) {
    const definition = this.#database.stores.get(name);
    if (!definition) throw new Error(`Object store ausente: ${name}`);
    const request = (operation) => {
      const result = new FakeRequest();
      this.#pending += 1;
      clearTimeout(this.#completion);
      queueMicrotask(() => {
        if (this.#aborted) return;
        try {
          result.result = operation();
          result.onsuccess?.();
        } catch (error) {
          result.error = error;
          result.onerror?.();
        } finally {
          this.#pending -= 1;
          this.#scheduleCompletion();
        }
      });
      return result;
    };
    return {
      get: (key) => request(() => structuredClone(definition.data.get(key))),
      getAll: () => request(() => [...definition.data.values()].map((value) => structuredClone(value))),
      put: (value) => request(() => {
        const copy = structuredClone(value);
        definition.data.set(copy[definition.keyPath], copy);
        return copy[definition.keyPath];
      }),
      delete: (key) => request(() => definition.data.delete(key)),
    };
  }

  abort() {
    this.#aborted = true;
    clearTimeout(this.#completion);
    queueMicrotask(() => this.onabort?.());
  }

  #scheduleCompletion() {
    if (this.#aborted || this.#pending !== 0) return;
    clearTimeout(this.#completion);
    this.#completion = setTimeout(() => {
      if (!this.#aborted && this.#pending === 0) this.oncomplete?.();
    }, 0);
  }
}

class FakeDatabase {
  stores = new Map();
  objectStoreNames = { contains: (name) => this.stores.has(name) };

  createObjectStore(name, { keyPath }) {
    this.stores.set(name, { keyPath, data: new Map() });
  }

  transaction() {
    return new FakeTransaction(this);
  }
}

class FakeIndexedDB {
  databases = new Map();

  open(name, version) {
    const request = new FakeRequest();
    queueMicrotask(() => {
      let entry = this.databases.get(name);
      const upgrade = !entry || entry.version < version;
      if (!entry) entry = { version, database: new FakeDatabase() };
      if (upgrade) entry.version = version;
      this.databases.set(name, entry);
      request.result = entry.database;
      if (upgrade) request.onupgradeneeded?.();
      request.onsuccess?.();
    });
    return request;
  }
}

async function loadOfflineModule() {
  const sourcePath = new URL("../../packages/offline-sync/src/index.js", import.meta.url);
  const source = await readFile(sourcePath, "utf8");
  const manifestStub = Buffer.from(`
    export function isTauriRuntime() {
      return typeof window !== "undefined" && typeof window.__TAURI__?.core?.invoke === "function";
    }
  `).toString("base64");
  const replaced = source.replace(
    '"@pige360/app-manifest"',
    `"data:text/javascript;base64,${manifestStub}"`,
  );
  return import(`data:text/javascript;base64,${Buffer.from(replaced).toString("base64")}`);
}

const offline = await loadOfflineModule();


test("outbox IndexedDB persiste e isola tenant e usuário", async () => {
  const factory = new FakeIndexedDB();
  globalThis.window = {};
  globalThis.indexedDB = factory;
  const operation = {
    idempotencyKey: "operation-1",
    aggregateType: "attendance",
    aggregateId: "class-1",
    baseRevision: 2,
    localRevision: 3,
    payload: { present: 24 },
    createdAt: "2026-09-04T12:00:00Z",
  };

  const first = offline.createOfflineStore("tenant/a", "user:1");
  const firstContext = await first.initialize();
  await first.enqueue(operation);

  const reopened = offline.createOfflineStore("tenant/a", "user:1");
  const reopenedContext = await reopened.initialize();
  assert.equal(reopenedContext.device_id, firstContext.device_id);
  assert.equal((await reopened.pending())[0].idempotency_key, operation.idempotencyKey);

  const otherTenant = offline.createOfflineStore("tenant_a", "user:1");
  const otherUser = offline.createOfflineStore("tenant/a", "user:2");
  await otherTenant.initialize();
  await otherUser.initialize();
  assert.deepEqual(await otherTenant.pending(), []);
  assert.deepEqual(await otherUser.pending(), []);

  await assert.rejects(
    reopened.enqueue({ ...operation, payload: { present: 23 } }),
    /IDEMPOTENCY_CONFLICT/,
  );
  await reopened.applyResult(operation.idempotencyKey, {});
  assert.deepEqual(await reopened.pending(), []);
});


test("cache IndexedDB persiste e remove registro expirado", async () => {
  globalThis.window = {};
  globalThis.indexedDB = new FakeIndexedDB();
  const store = offline.createOfflineStore("tenant-cache", "user-cache");
  await store.initialize();
  await store.cachePut("active", { value: 1 }, 4, "2099-01-01T00:00:00Z");
  await store.cachePut("expired", { value: 2 }, 4, "2000-01-01T00:00:00Z");
  assert.deepEqual(await store.cacheGet("active"), { value: 1 });
  assert.equal(await store.cacheGet("expired"), null);
  assert.equal(await store.cacheGet("expired"), null);
});


test("browser sem IndexedDB falha explicitamente; somente SSR retorna null", () => {
  globalThis.window = {};
  delete globalThis.indexedDB;
  assert.throws(
    () => offline.createOfflineStore("tenant", "user"),
    /não pode usar armazenamento volátil/,
  );

  delete globalThis.window;
  assert.equal(offline.createOfflineStore("tenant", "user"), null);
});
