# Backup e restore

## Escopo por tenant

Backup contém banco lógico/dedicado, prefixo/bucket, manifest, hashes, configuração e chaves necessárias sob custódia separada. Não combine dois tenants em um archive sem catálogo explícito.

## Teste local executado

`scripts/backup/test_backup_restore.py` cria Alpha e Beta, grava dados/objeto em ambos, gera backup somente de Alpha, restaura em diretório limpo, verifica SHA-256 e confirma ausência de Beta. O relatório fica em `release/artifacts/backup-restore/report.json`.

## Produção

Use `pg_dump --format=custom`, snapshot/versionamento de objetos, criptografia, retenção, legal hold e restore em infraestrutura isolada. A restauração deve validar tenant UUID antes de ativar hostnames.
