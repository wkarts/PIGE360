# CI/CD preparado

Os 15 workflows em `.github/workflows` reproduzem validação, imagens, web, desktop, Android, iOS, white-label, segurança, release, self-hosted e restore. Publicação/deploy depende simultaneamente de input manual, variável `REMOTE_*_ENABLED` e environment protegido.

Nesta entrega, os workflows não foram enviados nem executados em provedor externo. O espelho está em `CI_CD_KIT_LOCAL`.
