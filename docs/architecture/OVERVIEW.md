# Arquitetura

## Estilo

O PIGE360 usa **monólito modular orientado a domínios**. A API, os workers e o scheduler são processos diferentes do mesmo contrato de aplicação. Isso reduz transações distribuídas prematuras e mantém portas claras para extração futura.

```text
clientes web/PWA/Tauri
        ↓ HTTPS / REST / eventos autorizados
API FastAPI + resolução de Host
        ↓
Control Plane ── Tenant Plane dedicado
        ↓                ↓
PostgreSQL control    banco por tenant + RLS interno
        ↓                ↓
outbox → RabbitMQ → inbox/handlers idempotentes
        ↓
MinIO por tenant · Redis efêmero · observabilidade
```

## Fronteiras

- **Control Plane:** tenants, domínios, licenças, branding global, App Factory, suporte e auditoria global.
- **Tenant Plane:** dados acadêmicos, administrativos, financeiros, fiscais, trabalhistas e documentos da escola.
- **Clientes:** não acessam banco, fila, Redis ou storage diretamente.
- **Offline:** SQLite por tenant/usuário, outbox transacional, checkpoint e conflito explícito.

## Fonte de verdade

PostgreSQL é a fonte transacional; MinIO é a fonte de objetos; Mailcow permanece fonte das caixas; Redis não guarda informação definitiva; RabbitMQ transporta eventos, mas o estado é conciliado pela outbox/inbox.

## Estado desta revisão

O adapter local SQLite é usado para executar a suíte sem serviços externos. As migrations PostgreSQL e policies RLS estão em `backend/alembic_*` e `infra/migrations`. O adapter assíncrono SQLAlchemy está presente, porém a execução PostgreSQL não ocorreu por ausência de runtime de containers/servidor local.
