import { isTauriRuntime } from "../runtime/RuntimeProvider";
import type { NotificationProvider } from "./NotificationProvider";
import { TauriNotificationProvider } from "./TauriNotificationProvider";
import { WebNotificationProvider } from "./WebNotificationProvider";

let provider: NotificationProvider | null = null;

export function useNotificationProvider(): NotificationProvider {
  if (!provider) provider = isTauriRuntime() ? new TauriNotificationProvider() : new WebNotificationProvider();
  return provider;
}
