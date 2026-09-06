import type { AppFile, FileProvider, OpenFileOptions } from "./FileProvider";

export class WebFileProvider implements FileProvider {
  providerName(): string {
    return "web-file-api";
  }

  async openTextFile(options: OpenFileOptions = {}): Promise<AppFile | null> {
    return new Promise((resolve) => {
      const input = document.createElement("input");
      input.type = "file";
      input.multiple = options.multiple ?? false;
      if (options.accept?.length) input.accept = options.accept.join(",");
      input.onchange = () => {
        const file = input.files?.item(0);
        if (!file) {
          resolve(null);
          return;
        }
        resolve({ name: file.name, mimeType: file.type, size: file.size, nativeFile: file });
      };
      input.click();
    });
  }

  async saveTextFile(fileName: string, content: string): Promise<void> {
    const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = fileName;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async readTextFile(file: AppFile | File | string): Promise<string> {
    if (typeof file === "string") {
      throw new Error("No navegador não é permitido ler arquivo por caminho absoluto. Use File API.");
    }
    if (file instanceof File) return file.text();
    if (file.nativeFile) return file.nativeFile.text();
    if (typeof file.content === "string") return file.content;
    throw new Error("Arquivo Web sem conteúdo legível.");
  }
}
