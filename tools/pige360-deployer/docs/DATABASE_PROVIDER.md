# DatabaseProvider

A partir da Etapa 2.4, o template passa a ter uma base `DatabaseProvider` para iniciar a transição gradual do CRUD antigo, hoje baseado diretamente em `rusqlite`, para uma camada de banco reutilizável.

## Estado atual

- `SQLiteProvider`: funcional e usado como provider inicial.
- `MySqlProvider`: preparado por feature `mysql-db`, com health check e migrations já existentes.
- `PostgresProvider`: preparado por feature `postgres-db`, com health check e migrations já existentes.
- Firebird: fora do escopo funcional por compatibilidade.

## Arquivos principais

```text
src-tauri/src/core/database/provider/mod.rs
src-tauri/src/core/database/sqlite.rs
src-tauri/src/core/database/mysql.rs
src-tauri/src/core/database/postgres.rs
```

## CRUD provider-based

O CRUD antigo não foi removido. Foi criado o comando inicial:

```text
entity_provider_list
```

Ele permite iniciar a migração gradual das listagens para `DatabaseProvider`, preservando os comandos antigos e reduzindo risco de regressão.

## Próxima etapa recomendada

Criar repositórios por agregado, por exemplo:

```text
UserRepository
CompanyRepository
ProfileRepository
EntityRepository
```

Esses repositórios devem depender do provider em vez de usar `rusqlite` diretamente.
