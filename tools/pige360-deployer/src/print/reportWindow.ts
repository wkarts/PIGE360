import { invokeCommand } from "../services/tauri";

export async function openReportPreview(html = "", title = "Preview de relatório") {
  await invokeCommand("open_print_preview", { html, title });
}
