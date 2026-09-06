export interface NotificationProvider {
  providerName(): string;
  notify(title: string, message: string): Promise<void>;
}
