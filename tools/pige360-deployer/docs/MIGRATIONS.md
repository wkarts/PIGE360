# Migrations

As migrations devem ser idempotentes sempre que possível.

Tabelas centrais previstas:

- users/usuarios
- profiles/perfis_acesso
- permissions/permissoes
- companies/empresas
- sessions/sessoes
- app_logs
- app_settings
- feature_flags
- license_data
- integration_configs
- integration_logs
- api_tokens

Para múltiplos bancos, isole diferenças por driver.
