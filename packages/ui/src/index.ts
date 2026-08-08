export * from "./brand-provider";

export type NavigationItem = {
  label: string;
  route: string;
  permission?: string;
  badge?: number;
};

export function filterNavigation(items: readonly NavigationItem[], permissions: ReadonlySet<string>): NavigationItem[] {
  return items.filter((item) => !item.permission || permissions.has(item.permission));
}
