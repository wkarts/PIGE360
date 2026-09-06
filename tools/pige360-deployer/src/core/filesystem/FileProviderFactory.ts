import { isTauriRuntime } from "../runtime/RuntimeProvider";
import type { FileProvider } from "./FileProvider";
import { TauriFileProvider } from "./TauriFileProvider";
import { WebFileProvider } from "./WebFileProvider";

let provider: FileProvider | null = null;

export function useFileProvider(): FileProvider {
  if (!provider) provider = isTauriRuntime() ? new TauriFileProvider() : new WebFileProvider();
  return provider;
}
