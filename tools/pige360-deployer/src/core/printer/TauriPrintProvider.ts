import { WebPrintProvider } from "./WebPrintProvider";

export class TauriPrintProvider extends WebPrintProvider {
  providerName(): string {
    return "tauri-webview-print";
  }
}
