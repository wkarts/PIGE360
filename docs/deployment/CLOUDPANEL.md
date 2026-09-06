# CloudPanel

Use `sh deploy/self-hosted/install.sh --mode source --target cloudpanel`. Esse target
publica API, Web, Console e Grafana somente em `127.0.0.1`; o readiness do instalador
é interno e funciona sem depender dessas portas. Configure o vhost a partir de
`deploy/cloudpanel/pige360-vhost.nginx.conf.example` e faça o CloudPanel terminar
TLS. Não exponha PostgreSQL, Redis, RabbitMQ ou MinIO.

Valide no host: `console`, `api`, um tenant wildcard, headers de proxy, upload,
WebSocket se habilitado, limite de corpo, renovação TLS e restore de ensaio.
Domínios personalizados registrados no Control Plane não criam automaticamente um
vhost no CloudPanel; até existir um reconciliador/agent homologado, essa etapa é
operacional e deve ser auditada.
