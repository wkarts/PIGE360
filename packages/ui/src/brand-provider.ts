export type BrandTheme = {
  legalName: string;
  tradeName: string;
  shortName: string;
  primaryColor: string;
  secondaryColor: string;
  accentColor: string;
  logoUrl?: string;
  typographyFamily: string;
  coBrandingPolicy: "disabled" | "optional" | "required";
};

const HEX = /^#[0-9a-fA-F]{6}$/;

export function validateBrandTheme(theme: BrandTheme): string[] {
  const errors: string[] = [];
  if (!theme.legalName.trim()) errors.push("legalName obrigatório");
  if (!theme.tradeName.trim()) errors.push("tradeName obrigatório");
  for (const [key, value] of Object.entries({
    primaryColor: theme.primaryColor,
    secondaryColor: theme.secondaryColor,
    accentColor: theme.accentColor,
  })) {
    if (!HEX.test(value)) errors.push(`${key} deve usar #RRGGBB`);
  }
  return errors;
}

export function applyBrandTheme(theme: BrandTheme, root: HTMLElement = document.documentElement): void {
  const errors = validateBrandTheme(theme);
  if (errors.length) throw new Error(errors.join("; "));
  root.style.setProperty("--brand-primary", theme.primaryColor);
  root.style.setProperty("--brand-secondary", theme.secondaryColor);
  root.style.setProperty("--brand-accent", theme.accentColor);
  root.style.setProperty("--brand-font", theme.typographyFamily);
  root.dataset.brand = theme.shortName;
}

export const platformBrand: BrandTheme = {
  legalName: "PIGE360 — Plataforma Integrada de Gestão Educacional",
  tradeName: "PIGE360",
  shortName: "PIGE360",
  primaryColor: "#006D77",
  secondaryColor: "#0D1B2A",
  accentColor: "#F59E0B",
  typographyFamily: "Inter, Arial, sans-serif",
  coBrandingPolicy: "disabled",
};
