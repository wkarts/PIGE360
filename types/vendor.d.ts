// Fallbacks mínimos para os componentes legados que são compilados também em
// bundles sem o type surface completo dos plugins de editor. O runtime usa as
// implementações oficiais instaladas pelo workspace.
declare module "vue" {
  export interface App { use(plugin: unknown): App; mount(selector: string): unknown }
  export function createApp(component: unknown): App;
  export function computed<T>(fn: () => T): { readonly value: T };
  export function ref<T>(value: T): { value: T };
  export function reactive<T extends object>(value: T): T;
  export function inject<T>(key: symbol): T | undefined;
  export function provide<T>(key: symbol, value: T): void;
  export function defineComponent<T>(component: T): T;
  export function onMounted(callback: () => void | Promise<void>): void;
  export function watch(...args: any[]): any;
}
declare module "vue-router" {
  export function createRouter(options: unknown): unknown;
  export function createWebHistory(base?: string): unknown;
  export type RouteRecordRaw = Record<string, unknown>;
}
declare module "pinia" { export function createPinia(): unknown; }
declare module "echarts" { export function init(element: HTMLElement): { setOption(value: unknown): void; resize(): void; dispose(): void }; }
declare module "*.vue" { const component: unknown; export default component; }
