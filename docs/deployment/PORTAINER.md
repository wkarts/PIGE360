# Portainer

O target `portainer` usa o mesmo edge Traefik/ACME do target `edge`. A forma
recomendada é preparar `.env` e `runtime-secrets` no host e executar o instalador;
se a stack for importada pela interface, replique exatamente os quatro arquivos
Compose selecionados por `lib.sh` e mantenha `PIGE360_PROJECT_NAME=pige360`.

Não coloque secrets como variáveis visíveis da UI. Restrinja endpoints e habilite
webhook somente após autenticação, allowlist e rollback ensaiado. Não há hoje
automação pela API do Portainer, rotação de credenciais ou prova de homologação da
interface; `backup.sh`, `update.sh`, `rollback.sh` e `healthcheck.sh` continuam sendo
os contratos operacionais no host.
