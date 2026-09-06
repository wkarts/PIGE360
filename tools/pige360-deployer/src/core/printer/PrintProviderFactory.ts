import { isTauriRuntime } from "../runtime/RuntimeProvider";
import type { PrintProvider } from "./PrintProvider";
import { TauriPrintProvider } from "./TauriPrintProvider";
import { WebPrintProvider } from "./WebPrintProvider";

let provider: PrintProvider | null = null;

export function usePrintProvider(): PrintProvider {
  if (!provider) provider = isTauriRuntime() ? new TauriPrintProvider() : new WebPrintProvider();
  return provider;
}
