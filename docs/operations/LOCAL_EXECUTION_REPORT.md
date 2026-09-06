# Relatorio de execucao local

## Fontes de verdade

- Comandos e retornos: `release/reports/local-ci-report.json`.
- Testes pytest: `release/reports/test-report.json`.
- Builds e limitacoes: `release/reports/build-report.json`.
- Arvore original versus atual: `docs/operations/BEFORE_AFTER_REPORT.json`.
- Origem do ZIP-base: `docs/operations/SOURCE_BASELINE.json`.

## Resultado

| Verificacao | Status | Duracao | Evidencia |
|---|---|---:|---|
| `toolchain-inventory` | **passed** | 0.574 s | `release/reports/logs/toolchain-inventory.log` |
| `python-compile` | **passed** | 0.07 s | `release/reports/logs/python-compile.log` |
| `pytest` | **passed** | 227.316 s | `release/reports/logs/pytest.log` |
| `release-tooling-tests` | **passed** | 0.768 s | `release/reports/logs/release-tooling-tests.log` |
| `openapi-export` | **passed** | 6.375 s | `release/reports/logs/openapi-export.log` |
| `frontend-install` | **passed** | 3.727 s | `release/reports/logs/frontend-install.log` |
| `npm-audit` | **passed** | 14.923 s | `release/reports/logs/npm-audit.log` |
| `sdk-generation` | **passed** | 0.055 s | `release/reports/logs/sdk-generation.log` |
| `frontend-build` | **passed** | 18.755 s | `release/reports/logs/frontend-build.log` |
| `pwa-build-validation` | **passed** | 0.043 s | `release/reports/logs/pwa-build-validation.log` |
| `typescript-strict` | **passed** | 1.309 s | `release/reports/logs/typescript-strict.log` |
| `migration-control-sql` | **passed** | 0.281 s | `release/reports/logs/migration-control-sql.log` |
| `migration-tenant-sql` | **passed** | 0.352 s | `release/reports/logs/migration-tenant-sql.log` |
| `visual-contract` | **passed** | 0.09 s | `release/reports/logs/visual-contract.log` |
| `tenant-app-manifest` | **passed** | 0.037 s | `release/reports/logs/tenant-app-manifest.log` |
| `version-consistency` | **passed** | 0.132 s | `release/reports/logs/version-consistency.log` |
| `release-build-readiness` | **passed** | 0.076 s | `release/reports/logs/release-build-readiness.log` |
| `dockerfile-policy` | **passed** | 0.023 s | `release/reports/logs/dockerfile-policy.log` |
| `secret-scan` | **passed** | 1.961 s | `release/reports/logs/secret-scan.log` |
| `backup-restore` | **passed** | 0.688 s | `release/reports/logs/backup-restore.log` |
| `sbom` | **passed** | 0.07 s | `release/reports/logs/sbom.log` |
| `oci-structural` | **passed** | 0.039 s | `release/reports/logs/oci-structural.log` |
| `project-validation` | **passed** | 7.977 s | `release/reports/logs/project-validation.log` |

## Uso de rede

Uso de rede registrado pelos relatorios desta execucao. Isso nao implica deploy, publicacao ou homologacao externa.

Relatorios consultados:

- `release/reports/local-ci-report.json`: `network_used=true`
- `release/reports/build-report.json`: `network_used=true`
- `release/toolchain-inventory.json`: `network_used=false`
- `docs/execution/evidence/branding-import-report.json`: `network_used=false`

## Limites de interpretacao

- `passed`: comando local executado com retorno zero.
- `structural_only`: arquivo, manifesto ou contrato validado sem executar o runtime alvo.
- baseline visual: catalogo e integridade dos screenshots; nao significa comparacao pixel-a-pixel.
- backup sintetico: SQLite/filesystem isolados; nao significa restore homologado de PostgreSQL/MinIO.
- homologacao externa: somente com ambiente, credenciais e protocolo reais.
