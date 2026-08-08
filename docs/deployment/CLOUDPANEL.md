# CloudPanel

Use um site reverse proxy para a porta publicada somente em loopback. TLS de origem deve permanecer válido e o acesso direto deve ser bloqueado. Não exponha PostgreSQL, Redis, RabbitMQ, MinIO ou Grafana. O Cloudflare Tunnel, quando contratado, deve terminar em gateway interno separado para Control Plane e Tenant Plane.
