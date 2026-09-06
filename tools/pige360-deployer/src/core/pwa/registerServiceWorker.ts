export async function registerServiceWorker(): Promise<void> {
  if (!("serviceWorker" in navigator)) return;
  if (import.meta.env.DEV) return;
  try {
    await navigator.serviceWorker.register("/sw.js");
  } catch (error) {
    console.warn("Falha ao registrar Service Worker", error);
  }
}
