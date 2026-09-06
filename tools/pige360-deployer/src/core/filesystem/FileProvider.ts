export interface AppFile {
  name: string;
  path?: string;
  mimeType?: string;
  size?: number;
  content?: string | ArrayBuffer;
  nativeFile?: File;
}

export interface OpenFileOptions {
  accept?: string[];
  multiple?: boolean;
}

export interface FileProvider {
  providerName(): string;
  openTextFile(options?: OpenFileOptions): Promise<AppFile | null>;
  saveTextFile(fileName: string, content: string): Promise<void>;
  readTextFile(file: AppFile | File | string): Promise<string>;
}
