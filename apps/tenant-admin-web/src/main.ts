import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import "./styles.css";

const isViteDevelopmentEntry = document.querySelector('script[type="module"][src="/src/main.ts"]') !== null;
if (!isViteDevelopmentEntry && "serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    const workerUrl = new URL("sw.js", document.baseURI);
    const scope = new URL("./", document.baseURI).pathname;
    void navigator.serviceWorker.register(workerUrl, { scope }).catch((error: unknown) => {
      console.error("Falha ao registrar o Service Worker do PIGE360.", error);
    });
  });
}

createApp(App).use(createPinia()).mount("#app");
