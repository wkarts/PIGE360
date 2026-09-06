export type TableRecord = Record<string, unknown> & { id?: number | string };

export interface DatabaseProvider {
  providerName(): string;
  bootstrap(): Promise<void>;
  list<T extends TableRecord>(table: string, search?: string, fields?: string[]): Promise<T[]>;
  get<T extends TableRecord>(table: string, id: number | string): Promise<T | null>;
  save<T extends TableRecord>(table: string, payload: T): Promise<T>;
  delete(table: string, id: number | string): Promise<boolean>;
  clear(table: string): Promise<void>;
}
