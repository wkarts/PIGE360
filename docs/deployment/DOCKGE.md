# Dockge

Execute `sh deploy/self-hosted/install.sh --mode source --target dockge` no host ou
publique antes as sete imagens e use `--mode registry`. O target combina
`compose.yaml`, `compose.production.yaml`, `compose.edge.yaml` e
`compose.logging.yaml`; preserve o projeto `pige360`, os volumes nomeados e o
diretório persistente de secrets.

O grafo executa `pige360-app-init` depois de PostgreSQL/MinIO e antes da API. Não
crie no Dockge um serviço fictício `pige360-migrations`. Antes de atualizar, rode o
backup real e use `update.sh`; trocar somente a tag pela interface não registra
estado nem oferece rollback de dados.

Requisitos externos: portas 80/443, DNS dos hosts canônicos, token Cloudflare para
DNS-01 quando wildcard estiver ativo e validação de persistência após restart.
