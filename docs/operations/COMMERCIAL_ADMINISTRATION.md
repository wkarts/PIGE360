# Administração comercial do PIGE360

O módulo `commercial_administration` amplia o Control Plane sem substituir as
rotas de tenancy, provisioning, quotas ou operações já existentes.

## Escopo implementado

- cadastro, consulta, edição e ciclo de vida não destrutivo de parceiros;
- vínculo opcional e exclusivo de um parceiro por tenant;
- catálogo versionado de planos, features, limites e preços informativos;
- uma assinatura administrativa por tenant;
- snapshots de uso por tenant, período e origem;
- consulta consolidada de assinatura, plano, uso, saldo e entitlements;
- RBAC do Control Plane, chave de idempotência, lock transacional, auditoria e
  Outbox em todas as mutações.

O preço é persistido em unidade monetária mínima (`price_minor`). Não há
integração com gateway, cobrança automática, emissão fiscal, conciliação ou
webhook financeiro. Toda assinatura criada nesta versão declara
`billing_mode=manual` e `automatic_charging=false`.

Os entitlements desta etapa são uma visão **informativa** do catálogo e dos
snapshots (`entitlement_enforcement=informational`). Eles não substituem nem
alteram as quotas operacionais já existentes em `platform_tenants.quotas_json`.
Suspender um parceiro também não suspende automaticamente seus tenants.

## Rotas

Todas usam o prefixo `/api/v1/platform/commercial` e exigem token do Control
Plane com papel `platform_super_admin` ou `platform_admin`.

| Recurso | Operações |
|---|---|
| Parceiros | `GET/POST /partners`, `GET/PATCH/DELETE /partners/{id}` |
| Lifecycle | `POST /partners/{id}/suspend`, `POST /partners/{id}/reactivate` |
| Vínculo | `PUT/DELETE /partners/{id}/tenants/{tenant_id}` |
| Planos | `GET/POST /plans`, `GET/PATCH/DELETE /plans/{id}` |
| Assinatura | `GET/PUT /tenants/{tenant_id}/subscription` |
| Uso | `GET /tenants/{tenant_id}/usage`, `PUT /tenants/{tenant_id}/usage/{AAAA-MM}` |
| Entitlements | `GET /tenants/{tenant_id}/entitlements?period=AAAA-MM` |

Cada mutação exige `Idempotency-Key` (8–200 caracteres). Reutilizar a mesma
chave e o mesmo corpo reproduz a resposta; reutilizá-la com outro corpo retorna
`409 IDEMPOTENCY_KEY_REUSED`. Atualizações também exigem `expected_version`.

`DELETE` arquiva parceiros/planos em vez de apagar registros. Parceiros com
tenants vinculados e planos com assinaturas operacionais não podem ser
arquivados antes da regularização dos vínculos.

## Persistência e implantação

- SQLite local: tabelas `CREATE TABLE IF NOT EXISTS` em
  `backend/app/shared/database/control_schema.sql`;
- PostgreSQL: migration Control Plane `0007_commercial_administration`, encadeada
  depois de `0006_operational_control`;
- nenhuma tabela ou coluna anterior é removida ou renomeada;
- o downgrade remove somente as seis tabelas novas e, por isso, exige backup se
  já existirem dados comerciais.

## Componente do console

O componente isolado
`apps/platform-console/src/components/CommercialAdministrationPanel.vue` foi
criado sem alterar a composição concorrente de `App.vue`. Após consolidar as
demais mudanças do console, a integração é deliberadamente pequena:

```vue
<script setup lang="ts">
import CommercialAdministrationPanel from "./components/CommercialAdministrationPanel.vue";
</script>

<CommercialAdministrationPanel
  :api="api"
  :tenants="tenants"
  @feedback="({ type, message }) => type === 'error' ? error = message : notice = message"
/>
```

O shell pode adaptar o evento de feedback ao estado já usado por `App.vue`.

## Homologação ainda necessária

- migration e concorrência em PostgreSQL real;
- política comercial definitiva e aprovação dos nomes de features/limites;
- coleta automática de métricas a partir dos módulos operacionais;
- gateway de pagamento, cobrança, fiscal, conciliação e webhooks, caso o produto
  venha a exigir esses recursos;
- testes E2E do componente já integrado ao shell final.
