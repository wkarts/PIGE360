import { WebLocalDatabase, type WebRecord } from "../storage/WebLocalDatabase";
import type { DatabaseProvider, TableRecord } from "./DatabaseTypes";

export class LocalStorageDatabaseProvider implements DatabaseProvider {
  private readonly database = new WebLocalDatabase();

  providerName(): string {
    return "localstorage";
  }

  async bootstrap(): Promise<void> {
    this.database.table("companies");
    this.database.table("users");
    this.database.table("profiles");
    this.database.table("app_logs");
  }

  async list<T extends TableRecord>(table: string, search = "", fields: string[] = []): Promise<T[]> {
    const rows = this.database.list(table, search) as T[];
    if (!search.trim() || fields.length === 0) return rows;
    const term = normalizeForSearch(search);
    return rows.filter((row) => fields.some((field) => normalizeForSearch(row[field]).includes(term)));
  }

  async get<T extends TableRecord>(table: string, id: number | string): Promise<T | null> {
    return this.database.get(table, Number(id)) as T | null;
  }

  async save<T extends TableRecord>(table: string, payload: T): Promise<T> {
    return this.database.save(table, payload as WebRecord) as T;
  }

  async delete(table: string, id: number | string): Promise<boolean> {
    return this.database.delete(table, Number(id));
  }

  async clear(table: string): Promise<void> {
    this.database.clear(table);
  }
}

function normalizeForSearch(value: unknown): string {
  return String(value ?? "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
}
