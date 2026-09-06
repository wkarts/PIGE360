import { isNativeMobileRuntime } from "../core/runtime/RuntimeProvider";
import { appFeatures } from "./projectConfig";

export type MenuSection = "dashboard" | "cadastro" | "sistema" | "ferramentas" | "documentacao";

export interface MenuItemConfig {
  title: string;
  route: string;
  permission?: string;
  feature?: keyof typeof appFeatures;
  section: MenuSection;
  eyebrow?: string;
  description?: string;
  desktopOnly?: boolean;
}

export const menuItems: MenuItemConfig[] = [
  { title: "Implantações", route: "/", permission: "dashboard:view", section: "dashboard", eyebrow: "PIGE360 Deployer", description: "Develop, prerelease e produção" },
  { title: "Logs", route: "/logs", permission: "config:view", feature: "logs", section: "sistema" },
  { title: "Sobre", route: "/sobre", feature: "about", section: "documentacao" },
  { title: "Guia do usuário", route: "/documentacao/guia", feature: "userGuide", section: "documentacao" },
];

export function isFeatureEnabled(feature?: keyof typeof appFeatures): boolean {
  return feature ? appFeatures[feature] !== false : true;
}

export function visibleMenuItems(): MenuItemConfig[] {
  const nativeMobile = isNativeMobileRuntime();
  return menuItems.filter((item) => isFeatureEnabled(item.feature) && !(nativeMobile && item.desktopOnly));
}


export function findMenuItemByRoute(route: string): MenuItemConfig | undefined {
  const normalize = (value: string) => {
    const clean = (value || "/").replace(/\/+$/, "");
    return clean || "/";
  };

  const target = normalize(route);
  return visibleMenuItems().find((item) => normalize(item.route) === target);
}
