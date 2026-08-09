# Runbook operacional

## API indisponível

1. Verifique readiness e dependências.
2. Correlacione por request ID.
3. Não reinicie banco antes de capturar evidência.
4. Se outbox acumulou, preserve a ordem e reprocese com idempotência.

## Tenant degradado

1. Confirme hostname e status no Control Plane.
2. Valide banco/bucket exclusivos.
3. Suspenda somente o tenant afetado.
4. Registre sessão de suporte com motivo.

## Build de app falhou

1. Preserve build ID, brand/manifest version e toolchain.
2. Nunca reutilize workspace com segredo de outro tenant.
3. Limpe ambiente efêmero.
4. Reprocessar mantém a mesma idempotency key quando a entrada não mudou.
