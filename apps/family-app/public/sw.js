const CACHE_PREFIX = "pige360-shell-";
const scopePath = new URL(self.registration.scope).pathname.replace(/[^a-z0-9]+/gi, "-") || "root";
const CACHE_SCOPE_PREFIX = `${CACHE_PREFIX}${scopePath}-`;
const CACHE = `${CACHE_PREFIX}${scopePath}-1.1.2`;
const APP_SHELL = ["./", "./manifest.webmanifest", "./icon-192.png", "./icon-512.png"];
const API_PATH = new URL("./api/", self.registration.scope).pathname;

self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    const page = await fetch("./", { cache: "reload" });
    if (!page.ok) throw new Error(`Falha ao obter shell PWA: ${page.status}`);
    const html = await page.clone().text();
    await cache.put("./", page);
    const discovered = [...html.matchAll(/(?:src|href)=["']([^"'#]+)["']/g)]
      .map((match) => new URL(match[1], self.registration.scope))
      .filter((url) => url.origin === self.location.origin && url.href.startsWith(self.registration.scope))
      .map((url) => url.href);
    await cache.addAll([...new Set([...APP_SHELL.slice(1), ...discovered])]);
    await self.skipWaiting();
  })());
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key.startsWith(CACHE_SCOPE_PREFIX) && key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin || url.pathname.startsWith("/api/") || url.pathname.startsWith(API_PATH)) return;

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) void caches.open(CACHE).then((cache) => cache.put("./", response.clone()));
          return response;
        })
        .catch(() => caches.match("./").then((response) => response || Response.error())),
    );
    return;
  }

  if (!["script", "style", "image", "font", "manifest"].includes(request.destination)) return;
  event.respondWith(
    caches.match(request).then((cached) => cached || fetch(request).then((response) => {
      if (response.ok) void caches.open(CACHE).then((cache) => cache.put(request, response.clone()));
      return response;
    })),
  );
});
