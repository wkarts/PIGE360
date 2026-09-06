export interface PrintOptions {
  title?: string;
  css?: string;
}

export interface PrintProvider {
  providerName(): string;
  printHtml(html: string, options?: PrintOptions): Promise<void>;
  printElement(elementId: string, options?: PrintOptions): Promise<void>;
}
