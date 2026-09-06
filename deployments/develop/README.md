# PIGE360 1.1.2 — homologação/develop

Este pacote é **service-native**: para iniciar o PIGE360 são necessários somente
`compose.yaml` e `.env`. Configurações, secrets, migrations e volumes são
preparados por serviços idempotentes do próprio stack.

## Iniciar

```bash
cp .env.example .env
# revise domínio, portas, integrações e tag antes de continuar
docker compose --env-file .env config --quiet
docker compose --env-file .env pull
docker compose --env-file .env up -d --wait
docker compose --env-file .env --profile operations run --rm pige360-readiness readiness
```

O modo `develop` usa por padrão
`ghcr.io/wkarts/*:develop`. Em produção, `PIGE360_IMAGE_TAG` deve ser
exatamente igual ao `APP_VERSION` SemVer.

## Administração

```bash
# criar o primeiro administrador (senha pelo stdin, sem argumento/process list)
printf '%s' 'SENHA_FORTE' | docker compose --env-file .env --profile operations run --rm -T   pige360-bootstrap-admin bootstrap-admin --email admin@exemplo.com

# configurar integração externa
printf '%s' 'TOKEN' | docker compose --env-file .env --profile operations run --rm -T   pige360-secret-set secret-set cloudflare_api_token

# diagnóstico e backup
docker compose --env-file .env --profile operations run --rm pige360-diagnostics diagnostics
docker compose --env-file .env --profile operations run --rm pige360-backup backup --name pre-atualizacao
```

Para restore, pare API, gateway, workers e beat; defina temporariamente
`PIGE360_RESTORE_MAINTENANCE=RESTORE-PIGE360`; então execute:

```bash
docker compose --env-file .env --profile operations run --rm   pige360-restore restore --name NOME --confirm RESTORE-PIGE360
```

Atualizações de imagem continuam sob controle do Dockge, Portainer ou CI/CD.
Nenhum serviço administrativo recebe acesso ao socket Docker. O Alloy mantém
somente a montagem read-only necessária à descoberta de logs.

## Serviços automáticos

- `pige360-secrets-init`: cria e preserva secrets internos no volume nomeado.
- `pige360-config-init`: materializa gateway e observabilidade a partir da imagem.
- `pige360-data-init`: prepara ownership dos volumes persistentes.
- `pige360-config-validate`: bloqueia configuração/tag inválida antes das migrations.
- `pige360-migrations-control`: atualiza o Control Plane.
- `pige360-migrations-tenants`: atualiza todos os tenants elegíveis.
- `pige360-readiness`: acceptance test executável sob o profile `operations`.
- `pige360-backup`/`pige360-restore`: operação transacional em volume dedicado.
