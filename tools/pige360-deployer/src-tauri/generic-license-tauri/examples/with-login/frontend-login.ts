import { invoke } from "@tauri-apps/api/core";

type LicenseCheckInput = {
  company_document: string;
  company_name?: string | null;
  app_id: string;
  app_name: string;
  app_version: string;
  device_key?: string | null;
  device_name?: string | null;
  login_context?: boolean;
};

export async function validateLicenseBeforeLogin(companyDocument: string, companyName?: string) {
  const decision = await invoke("license_check", {
    input: {
      company_document: companyDocument,
      company_name: companyName ?? null,
      app_id: "erp-desktop",
      app_name: "ERP Desktop",
      app_version: "1.0.0",
      login_context: true,
    } satisfies LicenseCheckInput,
  });

  return decision as {
    allowed: boolean;
    message: string;
    warning?: string | null;
    used_offline_cache: boolean;
  };
}

// Uso:
// const decision = await validateLicenseBeforeLogin(cnpj, razaoSocial);
// if (!decision.allowed) {
//   alert(decision.message);
//   return;
// }
// prosseguir com autenticação do usuário
