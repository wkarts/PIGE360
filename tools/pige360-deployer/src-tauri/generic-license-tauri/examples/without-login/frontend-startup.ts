import { invoke } from "@tauri-apps/api/core";

export async function validateLicenseOnStartup() {
  const decision = await invoke("license_check", {
    input: {
      company_document: "12345678000199",
      company_name: "Empresa Demo",
      app_id: "painel-kiosk",
      app_name: "Painel sem login",
      app_version: "1.0.0",
      login_context: false,
    },
  }) as {
    allowed: boolean;
    message: string;
    warning?: string | null;
  };

  if (!decision.allowed) {
    throw new Error(decision.message);
  }

  return decision;
}
