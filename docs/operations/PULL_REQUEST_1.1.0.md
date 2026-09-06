# Pull Request — PIGE360 1.1.0

## Status remoto

Não aberta: o ZIP-base não contém `.git` nem remoto configurado. A árvore e a
descrição abaixo estão preparadas para aplicação no repositório canônico.

## Branch

`feat/pige360-1-1-0-admin-deploy-distribution`

## Destino

`develop`

## Título

`feat(platform): conclui administração, deploy e distribuição PIGE360 1.1.0`

## Descrição

### Contexto e objetivo

Evolui conservadoramente o `develop` anexado, preserva todos os arquivos
recebidos e fecha falhas de autenticação, administração, PWA, deploy,
empacotamento e release sem apresentar build estrutural como homologação.

### Escopo

- Control Plane: tenants, usuários, quotas, suporte, parceiros, planos,
  assinaturas, uso, entitlements, agents, providers e jobs operacionais.
- Segurança: lockout, refresh/replay/logout, CAS/locks, signing por referência e
  sanitização de status/inventário.
- Deploy: self-hosted, migrations multitenant, backup/restore/update/rollback,
  CloudPanel, Dockge, Portainer, edge e SSH.
- Distribuição: PWA, App Factory e matriz nativa coordenada/fail-closed.
- Supply chain: locks npm, audit, SBOM, secret scan, manifesto, proveniência,
  preservação de fontes e ZIPs verificáveis.

### Banco de dados e migrations

- `0004_auth_session_hardening`;
- `0005_tenant_api_rate_quota`;
- `0006_operational_control`;
- `0007_commercial_administration`;
- tenant `0045` para autenticação/RLS compatível;
- cadeia Control Plane linear, aditiva e com um único head.

### Fora do escopo comprovado

- homologação em host produtivo e providers externos;
- compilação local de binários nativos e containers;
- billing automático/gateway;
- enforcement de `storage_bytes` sem ledger comum;
- implementação integral dos requisitos futuros mantidos no ledger.

### Testes e evidências

Usar como fonte os relatórios gerados no pacote final. Nenhuma contagem histórica
substitui a CI executada após o último arquivo alterado.

### Deploy e rollback

O instalador aceita fonte/registry e targets explícitos. Update exige backup;
rollback não faz downgrade silencioso de schema. O go-live depende do checklist
de homologação descrito em `docs/operations/DELIVERY_1.1.0.md`.

### Compatibilidade e versão

- `1.0.0 → 1.1.0`;
- incremento `minor` por novas capacidades administrativas e de distribuição;
- migrations e contratos são aditivos;
- nenhuma remoção da base anexada é aceita pelo gate.

### Riscos

Consultar `docs/operations/RISK_REGISTER.md` e o relatório final de evidências.

### Checklist

- [x] Base anexada identificada por hash.
- [x] Nenhum arquivo original removido.
- [x] JavaScript espelho do Vue preservado.
- [x] Administração global ampliada e auditável.
- [x] Deploy/update/rollback corrigidos.
- [x] Matriz nativa reativada com falha fechada.
- [ ] CI remota protegida no repositório canônico.
- [ ] Build dos 12 alvos da matriz.
- [ ] Homologação de infraestrutura e providers reais.
- [ ] PR remota, revisão e merge em `develop`.

## Commit sugerido

`feat(platform): entrega administração e distribuição PIGE360 1.1.0`

## Merge sugerido

`merge: integra feat/pige360-1-1-0-admin-deploy-distribution`

