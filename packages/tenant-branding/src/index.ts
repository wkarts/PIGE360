export type TenantBrandKit = {
  legal_name: string;
  trade_name: string;
  short_name: string;
  slug: string;
  app_display_name: string;
  publisher_name: string;
  support_name: string;
  support_email: string;
  support_phone?: string;
  website?: string;
  primary_domain: string;
  primary_color: string;
  secondary_color: string;
  accent_color: string;
  typography_family: string;
  co_branding_policy: "disabled" | "optional" | "required";
  brand_version: number;
};

export function assertTenantBrandIsolation(html: string, platformName = "PIGE360"): void {
  if (html.toLocaleUpperCase("pt-BR").includes(platformName.toLocaleUpperCase("pt-BR"))) {
    throw new Error("PLATFORM_BRAND_LEAK_DETECTED");
  }
}

export function cssVariables(kit: TenantBrandKit): Record<string, string> {
  return {
    "--brand-primary": kit.primary_color,
    "--brand-secondary": kit.secondary_color,
    "--brand-accent": kit.accent_color,
    "--brand-font": kit.typography_family,
  };
}
