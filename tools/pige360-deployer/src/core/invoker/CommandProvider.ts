export type CommandArgs = Record<string, unknown> | undefined;

export interface CommandProvider {
  providerName(): string;
  invoke<T>(command: string, args?: CommandArgs): Promise<T>;
}
