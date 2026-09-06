import { appAlert } from "../../services/dialog";
import { invokeAppCommand } from "../invoker/CommandProviderFactory";
import type { NotificationProvider } from "./NotificationProvider";

export class TauriNotificationProvider implements NotificationProvider {
  providerName(): string {
    return "tauri-command-notification";
  }

  async notify(title: string, message: string): Promise<void> {
    try {
      await invokeAppCommand<boolean>("notification_send", { title, message });
    } catch {
      await appAlert({ title, message });
    }
  }
}
