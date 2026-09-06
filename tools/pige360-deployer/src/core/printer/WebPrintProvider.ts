import type { PrintOptions, PrintProvider } from "./PrintProvider";

export class WebPrintProvider implements PrintProvider {
  providerName(): string {
    return "web-print";
  }

  async printHtml(html: string, options: PrintOptions = {}): Promise<void> {
    const win = window.open("", "_blank", "noopener,noreferrer,width=1100,height=800");
    if (!win) throw new Error("Não foi possível abrir a janela de impressão.");
    win.document.write(`<!doctype html><html><head><title>${options.title ?? "Impressão"}</title><style>${options.css ?? ""}</style></head><body>${html}</body></html>`);
    win.document.close();
    win.focus();
    window.setTimeout(() => win.print(), 150);
  }

  async printElement(elementId: string, options: PrintOptions = {}): Promise<void> {
    const element = document.getElementById(elementId);
    if (!element) throw new Error(`Elemento não encontrado para impressão: ${elementId}`);
    await this.printHtml(element.outerHTML, options);
  }
}
