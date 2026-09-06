import type { DatabaseProvider, TableRecord } from "../database/DatabaseTypes";
import { useDatabaseProvider } from "../database/DatabaseProviderFactory";

export class GenericRepository<T extends TableRecord = TableRecord> {
  constructor(private readonly table: string, private readonly db: DatabaseProvider = useDatabaseProvider()) {}

  async list(search = "", fields: string[] = []): Promise<T[]> {
    await this.db.bootstrap();
    return this.db.list<T>(this.table, search, fields);
  }

  async get(id: number | string): Promise<T | null> {
    await this.db.bootstrap();
    return this.db.get<T>(this.table, id);
  }

  async save(payload: T): Promise<T> {
    await this.db.bootstrap();
    return this.db.save<T>(this.table, payload);
  }

  async delete(id: number | string): Promise<boolean> {
    await this.db.bootstrap();
    return this.db.delete(this.table, id);
  }
}
