import { invokeAppCommand } from "../invoker/CommandProviderFactory";
import type { AppFile, FileProvider, OpenFileOptions } from "./FileProvider";

export class TauriFileProvider implements FileProvider {
  providerName(): string {
    return "tauri-command-fs";
  }

  async openTextFile(options: OpenFileOptions = {}): Promise<AppFile | null> {
    return invokeAppCommand<AppFile | null>("file_open_text", { options });
  }

  async saveTextFile(fileName: string, content: string): Promise<void> {
    await invokeAppCommand<boolean>("file_save_text", { file_name: fileName, content });
  }

  async readTextFile(file: AppFile | File | string): Promise<string> {
    if (file instanceof File) return file.text();
    const path = typeof file === "string" ? file : file.path;
    if (!path) {
      if (typeof file !== "string" && typeof file.content === "string") return file.content;
      throw new Error("Caminho do arquivo não informado.");
    }
    return invokeAppCommand<string>("file_read_text", { path });
  }
}
