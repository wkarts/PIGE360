# PIGE360 1.1.2 — deployment service-native

Os pacotes de homologação e produção exigem somente o manifesto YAML e as
variáveis de ambiente. Não é necessário executar scripts de instalação nem
criar diretórios de configuração, secrets ou dados no host.

## Homologação (`develop`)

```bash
cd deployments/develop
cp .env.example .env
# revisar domínio e integrações; a tag padrão é develop
docker compose --env-file .env config --quiet
docker compose --env-file .env pull
docker compose --env-file .env up -d --wait
docker compose --env-file .env --profile operations run --rm pige360-readiness readiness
```

## Produção (`1.1.2`)

```bash
cd deployments/production
cp .env.example .env
# manter APP_VERSION=1.1.2 e PIGE360_IMAGE_TAG=1.1.2
docker compose --env-file .env config --quiet
docker compose --env-file .env pull
docker compose --env-file .env up -d --wait
docker compose --env-file .env --profile operations run --rm pige360-readiness readiness
```

O Compose executa automaticamente, nesta ordem lógica:

1. criação idempotente de secrets;
2. materialização das configurações internas;
3. preparação dos volumes persistentes;
4. validação fail-closed do ambiente e da tag;
5. inicialização da infraestrutura;
6. migration do Control Plane;
7. migrations dos tenants;
8. API, workers, frontends, observabilidade e gateway.

## Serviços administrativos

Os comandos estão documentados no `README.md` de cada pacote. Os services de
administração usam o profile `operations` e não recebem acesso ao Docker socket.
Update e rollback de containers permanecem sob responsabilidade do Dockge,
Portainer ou pipeline CI/CD, que já controlam o ciclo do Compose.

## Limite da validação local

Os contratos YAML, dependências, políticas de imagem, isolamento, segurança e
código operacional são testados pela CI. A homologação em servidor ainda deve
confirmar pull do GHCR, persistência, DNS/TLS e backup/restore com PostgreSQL e
MinIO reais.
