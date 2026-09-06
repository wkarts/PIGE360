export type AppDialogKind = "alert" | "confirm";

export interface AppDialogOptions {
  title?: string;
  message: string;
  detail?: string;
  kind?: AppDialogKind;
  danger?: boolean;
  confirmText?: string;
  cancelText?: string;
}

export interface AppDialogRequest extends Required<Pick<AppDialogOptions, "message" | "kind">> {
  id: number;
  title: string;
  detail: string;
  danger: boolean;
  confirmText: string;
  cancelText: string;
  resolve: (value: boolean) => void;
}

let dialogSequence = 0;

function buildRequest(options: AppDialogOptions, resolve: (value: boolean) => void): AppDialogRequest {
  const kind = options.kind || "alert";
  return {
    id: ++dialogSequence,
    kind,
    title: options.title || (kind === "confirm" ? "Confirmar ação" : "Mensagem do sistema"),
    message: options.message,
    detail: options.detail || "",
    danger: Boolean(options.danger),
    confirmText: options.confirmText || (kind === "confirm" ? "Confirmar" : "OK"),
    cancelText: options.cancelText || "Cancelar",
    resolve,
  };
}

function requestDialog(options: AppDialogOptions): Promise<boolean> {
  if (typeof window === "undefined") return Promise.resolve(false);

  return new Promise<boolean>((resolve) => {
    const request = buildRequest(options, resolve);
    window.dispatchEvent(new CustomEvent<AppDialogRequest>("pige360-deployer:dialog", { detail: request }));
  });
}

export function appConfirm(options: Omit<AppDialogOptions, "kind"> | string): Promise<boolean> {
  const payload = typeof options === "string" ? { message: options } : options;
  return requestDialog({ ...payload, kind: "confirm" });
}

export async function appAlert(options: Omit<AppDialogOptions, "kind" | "cancelText"> | string): Promise<void> {
  const payload = typeof options === "string" ? { message: options } : options;
  await requestDialog({ ...payload, kind: "alert" });
}
