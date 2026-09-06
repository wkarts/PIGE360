import { invoke } from "@tauri-apps/api/core";
import type { CommandArgs, CommandProvider } from "./CommandProvider";

export class TauriCommandProvider implements CommandProvider {
  providerName(): string {
    return "tauri";
  }

  async invoke<T>(command: string, args?: CommandArgs): Promise<T> {
    return invoke<T>(command, args);
  }
}
