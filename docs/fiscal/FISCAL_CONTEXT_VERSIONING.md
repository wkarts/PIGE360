# Contexto fiscal versionado

## Objetivo

O contexto fiscal seleciona, de forma determinística e auditável, a configuração tributária aplicável a uma operação do tenant. A seleção não depende de uma flag global e não altera documentos fiscais já solicitados.

Dimensões persistidas e versionadas:

```text
tenant
→ CNPJ
→ estabelecimento
→ instituição/unidade opcional
→ regime tributário
→ UF
→ município
→ vigência
→ tipo de operação
→ produto, serviço ou venda mista
→ destinatário
→ documento fiscal
→ ambiente
→ layout
→ schema
→ nota técnica
→ ruleset
```

## Persistência

Tabelas introduzidas pela migration `0032_fiscal_context_versioning`:

- `fiscal_contexts`: identidade estável do estabelecimento fiscal;
- `fiscal_context_versions`: configuração imutável por versão e vigência;
- `fiscal_context_operation_scopes`: escopos de operação associados à versão.

A tabela `fiscal_documents` recebeu:

- `fiscal_context_id`;
- `fiscal_context_version_id`;
- `fiscal_context_snapshot_json`.

As três tabelas novas possuem `tenant_id`, RLS habilitada e forçada e policy PostgreSQL baseada em `app.tenant_id`.

## Estados

Contexto:

```text
active
inactive
archived
```

Versão:

```text
draft
published
scheduled
superseded
```

Uma versão futura pode ser publicada como `scheduled`. A versão anterior continua resolvível para operações históricas e é encerrada na data imediatamente anterior à nova vigência.

## Resolução

Entrada mínima:

- data da operação;
- tipo de operação;
- natureza do item;
- tipo de destinatário;
- tipo de documento;
- seletor de contexto por ID, CNPJ, instituição ou unidade.

A resolução considera somente contexto ativo, versão publicada/agendada e intervalo vigente. Escopos exatos recebem precedência sobre escopos `any`. Empates com a mesma especificidade são rejeitados para evitar seleção arbitrária.

O resultado contém um snapshot canônico e seu SHA-256. Quando um documento fiscal é solicitado com uma versão explícita, o snapshot é congelado no próprio documento. Alterações futuras no cadastro não modificam o conteúdo fiscal que fundamentou a solicitação anterior.

## Idempotência e concorrência

- criação de contexto, versão e publicação aceitam `Idempotency-Key`;
- replay com o mesmo corpo retorna o mesmo resultado;
- alteração de contexto e publicação exigem versão esperada;
- vigências conflitantes são rejeitadas;
- escopos duplicados na mesma versão são rejeitados.

## Auditoria e eventos

Mutações gravam auditoria antes/depois e transactional outbox na mesma transação.

Eventos:

```text
FiscalContextCreated
FiscalContextUpdated
FiscalContextVersionCreated
FiscalContextVersionPublished
FiscalContextVersionScheduled
FiscalContextVersionSuperseded
```

## API

```text
GET    /api/v1/fiscal/contexts
POST   /api/v1/fiscal/contexts
GET    /api/v1/fiscal/contexts/{context_id}
PATCH  /api/v1/fiscal/contexts/{context_id}
GET    /api/v1/fiscal/contexts/{context_id}/versions
POST   /api/v1/fiscal/contexts/{context_id}/versions
POST   /api/v1/fiscal/contexts/{context_id}/versions/{version_id}/publish
POST   /api/v1/fiscal/contexts/resolve
```

O painel administrativo também consulta documentos, regras e conexões configuráveis. A ausência de provider real permanece `not_configured`; o sistema não apresenta fixture ou mock de teste como autorização fiscal real.

## Validações locais

```bash
PYTHONPATH=backend python -m pytest -q -p no:ddtrace backend/tests/fiscal
PYTHONPATH=backend python -m pytest -q -p no:ddtrace \
  backend/tests/migrations/test_fiscal_context_versioning_migration.py

DATABASE_TENANT_URL='postgresql+asyncpg://pige360_tenant:local-only@localhost:5432/tenant_template' \
python -m alembic -c backend/alembic_tenant/alembic.ini \
  upgrade 0031_inventory_reorder_suggestions:0032_fiscal_context_versioning --sql

DATABASE_TENANT_URL='postgresql+asyncpg://pige360_tenant:local-only@localhost:5432/tenant_template' \
python -m alembic -c backend/alembic_tenant/alembic.ini \
  downgrade 0032_fiscal_context_versioning:0031_inventory_reorder_suggestions --sql
```

A geração SQL offline e os testes de contrato não substituem a execução futura em PostgreSQL real. Essa validação permanece pendente enquanto o serviço não estiver disponível no workspace.
