# Relatorio antes/depois da evolucao conservadora

A comparacao usa caminhos e SHA-256 dos arquivos-fonte. Diretorios de build, caches,
dependencias instaladas e artefatos de release sao excluidos para nao misturar produto com lixo gerado.
A revisao informada abaixo vem do comentario do ZIP; ela nao e apresentada como checkout Git verificado.

## Base rastreada

- ZIP: `PIGE360-develop(1).zip`
- SHA-256: `dfc2950813fcb3ea239e9715b66527e55b914ee1241101fc8b986f44bf21a607`
- Revisao declarada no comentario do ZIP: `9fa139bc20fc2f7173ffd2f07c78673e36e6090f`
- Checkout Git verificado: **nao**
- Papel: **unica base do produto nesta evolucao**

## Referencia arquitetural

- Arquivo: `Connect-API-Platform-v1.0.0-rc.34 (2).zip`
- SHA-256: `f10f59350a905daad9d884c514e055b3df17b36ce3bfd4e62b0fd3149397075b`
- Uso: referencia de padroes administrativos; **nao** foi usada como base, nem para copiar ou substituir o produto PIGE360.

## Resumo

| Medida | Quantidade |
|---|---:|
| Arquivos na base | 2894 |
| Arquivos na arvore atual | 3212 |
| Adicionados | 318 |
| Modificados | 305 |
| Removidos | 0 |
| Inalterados | 2589 |

Preservacao da base: **passed**.

## Compatibilidade Vue/JavaScript preservada

| Familia | Base | Atual | Caminhos preservados | Removidos |
|---|---:|---:|---:|---:|
| `*.vue.js` | 50 | 52 | 50 | 0 |
| `apps/*/src/main.js` | 13 | 13 | 13 | 0 |

## Alteracoes por area

### automation

| Estado | Quantidade |
|---|---:|
| Adicionados | 4 |
| Modificados | 3 |
| Removidos | 0 |

#### Adicionados

- `scripts/backup/backup_manifest.py`
- `scripts/deploy/generate_standalone_deployments.py`
- `scripts/execution/reconcile_requirements_summary.py`
- `scripts/frontend/test_offline_sync.mjs`

#### Modificados

- `scripts/deploy/deploy-saas-ssh.sh`
- `scripts/generate_workflows.py`
- `scripts/local/init-secrets.sh`

### backend

| Estado | Quantidade |
|---|---:|
| Adicionados | 52 |
| Modificados | 26 |
| Removidos | 0 |

#### Adicionados

- `backend/alembic_control/versions/0004_auth_session_hardening.py`
- `backend/alembic_control/versions/0005_tenant_api_rate_quota.py`
- `backend/alembic_control/versions/0006_operational_control.py`
- `backend/alembic_control/versions/0007_commercial_administration.py`
- `backend/alembic_tenant/versions/0045_auth_session_hardening.py`
- `backend/app/modules/commercial_administration/__init__.py`
- `backend/app/modules/commercial_administration/application/__init__.py`
- `backend/app/modules/commercial_administration/application/service.py`
- `backend/app/modules/commercial_administration/module.json`
- `backend/app/modules/commercial_administration/presentation/__init__.py`
- `backend/app/modules/commercial_administration/presentation/router.py`
- `backend/app/modules/commercial_administration/presentation/schemas.py`
- `backend/app/modules/foundation/application/metrics.py`
- `backend/app/modules/foundation/application/readiness.py`
- `backend/app/modules/foundation/presentation/schemas/readiness.py`
- `backend/app/modules/operational_control/__init__.py`
- `backend/app/modules/operational_control/module.json`
- `backend/app/modules/operational_control/presentation/__init__.py`
- `backend/app/modules/operational_control/presentation/router.py`
- `backend/app/modules/operational_control/presentation/schemas.py`
- `backend/app/modules/operational_control/providers.py`
- `backend/app/modules/operational_control/service.py`
- `backend/app/modules/platform_operations/presentation/router.py`
- `backend/app/shared/database/migrate_tenants.py`
- `backend/app/shared/tenant_quotas.py`
- `backend/tests/app_factory/test_build_farm_final_artifacts.py`
- `backend/tests/events/test_deferred_event_delivery.py`
- `backend/tests/foundation/test_metrics.py`
- `backend/tests/foundation/test_readiness.py`
- `backend/tests/frontend/test_auth_session_client.py`
- `backend/tests/frontend/test_commercial_administration_panel.py`
- `backend/tests/frontend/test_frontend_supply_chain.py`
- `backend/tests/frontend/test_offline_sync_persistence.py`
- `backend/tests/frontend/test_operational_administration_panel.py`
- `backend/tests/frontend/test_platform_console_administration.py`
- `backend/tests/frontend/test_pwa_installability.py`
- `backend/tests/infrastructure/test_backup_manifest.py`
- `backend/tests/infrastructure/test_deployment_contract.py`
- `backend/tests/infrastructure/test_oci_image_publication.py`
- `backend/tests/infrastructure/test_pytest_isolated_runner.py`
- `backend/tests/infrastructure/test_release_package_preservation.py`
- `backend/tests/infrastructure/test_runtime_entrypoints.py`
- `backend/tests/infrastructure/test_runtime_secret_permissions.py`
- `backend/tests/infrastructure/test_sbom_scope.py`
- `backend/tests/infrastructure/test_secret_scan_scope.py`
- `backend/tests/infrastructure/test_self_hosted_deploy.py`
- `backend/tests/infrastructure/test_tenant_migration_reconciliation.py`
- `backend/tests/migrations/test_auth_session_hardening_migrations.py`
- `backend/tests/platform/test_commercial_administration.py`
- `backend/tests/platform/test_operational_control.py`
- `backend/tests/platform/test_platform_administration.py`
- `backend/tests/platform/test_tenant_quota_gates.py`

#### Modificados

- `backend/app/bootstrap/config.py`
- `backend/app/main.py`
- `backend/app/modules/app_factory/presentation/router.py`
- `backend/app/modules/fiscal/application/document_lifecycle_service.py`
- `backend/app/modules/foundation/presentation/router.py`
- `backend/app/modules/identity/presentation/router.py`
- `backend/app/modules/integrations/presentation/router.py`
- `backend/app/modules/operations/academic_core.py`
- `backend/app/modules/operations/community_operations.py`
- `backend/app/modules/tenancy/presentation/domain_router.py`
- `backend/app/modules/tenancy/presentation/router.py`
- `backend/app/shared/database/control_schema.sql`
- `backend/app/shared/database/postgres_store.py`
- `backend/app/shared/database/store.py`
- `backend/app/shared/database/tenant_schema.sql`
- `backend/app/shared/events/dispatcher.py`
- `backend/app/shared/events/handlers.py`
- `backend/app/shared/presentation/errors.py`
- `backend/app/shared/security/auth.py`
- `backend/app/shared/security/middleware.py`
- `backend/pyproject.toml`
- `backend/tests/app_factory/test_app_factory.py`
- `backend/tests/database/test_postgres_sql_contract.py`
- `backend/tests/infrastructure/test_compose_homologation_smoke.py`
- `backend/tests/security/test_host_and_auth.py`
- `backend/tests/tenancy/test_custom_domains_and_logs.py`

### ci_release_and_validation

| Estado | Quantidade |
|---|---:|
| Adicionados | 16 |
| Modificados | 43 |
| Removidos | 0 |

#### Adicionados

- `CI_CD_KIT_LOCAL/workflows/03-git-flow.yml`
- `CI_CD_KIT_LOCAL/workflows/04-version-sync.yml`
- `CI_CD_KIT_LOCAL/workflows/05-cleanup-stale-release.yml`
- `scripts/build-farm/test_agent.py`
- `scripts/oci/image-catalog.sh`
- `scripts/oci/publish-images.sh`
- `scripts/oci/publish-release-images.sh`
- `scripts/oci/smoke-published-images.sh`
- `scripts/release/collect-release-assets.mjs`
- `scripts/release/enforce-release-policy.mjs`
- `scripts/release/evidence_common.py`
- `scripts/release/generate_before_after_report.py`
- `scripts/release/tests/test_evidence_reports.py`
- `scripts/release/write-build-status.mjs`
- `scripts/validation/validate_deployments.py`
- `scripts/validation/validate_pwa_builds.py`

#### Modificados

- `.github/workflows/20-application-images.yml`
- `.github/workflows/31-build-desktop.yml`
- `.github/workflows/32-build-android.yml`
- `.github/workflows/33-build-ios.yml`
- `.github/workflows/34-build-tenant-apps.yml`
- `.github/workflows/50-release.yml`
- `.github/workflows/51-recover-release.yml`
- `CI_CD_KIT_LOCAL/README.md`
- `CI_CD_KIT_LOCAL/manifest.json`
- `CI_CD_KIT_LOCAL/scripts/deploy/deploy-saas-ssh.sh`
- `CI_CD_KIT_LOCAL/scripts/release/publish-github-release.sh`
- `CI_CD_KIT_LOCAL/workflows/00-ci.yml`
- `CI_CD_KIT_LOCAL/workflows/10-base-images.yml`
- `CI_CD_KIT_LOCAL/workflows/20-application-images.yml`
- `CI_CD_KIT_LOCAL/workflows/31-build-desktop.yml`
- `CI_CD_KIT_LOCAL/workflows/32-build-android.yml`
- `CI_CD_KIT_LOCAL/workflows/33-build-ios.yml`
- `CI_CD_KIT_LOCAL/workflows/34-build-tenant-apps.yml`
- `CI_CD_KIT_LOCAL/workflows/50-release.yml`
- `CI_CD_KIT_LOCAL/workflows/51-recover-release.yml`
- `scripts/build-farm/agent.py`
- `scripts/ci/run_all.py`
- `scripts/ci/run_pytest_isolated.py`
- `scripts/desktop/build-all.sh`
- `scripts/mobile/build-android.sh`
- `scripts/mobile/build-ios.sh`
- `scripts/mobile/build-tenant-app.sh`
- `scripts/mobile/sign-ios.sh`
- `scripts/oci/build-runtime-images.sh`
- `scripts/oci/build_structural_oci.py`
- `scripts/oci/publish-develop-images.sh`
- `scripts/release/generate-manifest.py`
- `scripts/release/generate_evidence_pdf.py`
- `scripts/release/generate_provenance.py`
- `scripts/release/package-web-pwa.sh`
- `scripts/release/package_local.py`
- `scripts/release/sync-version.py`
- `scripts/supply-chain/generate_sbom.py`
- `scripts/validation/secret_scan.py`
- `scripts/validation/validate_dockerfiles.py`
- `scripts/validation/validate_project.py`
- `scripts/validation/validate_release_build_readiness.py`
- `scripts/validation/validate_version_consistency.py`

### deployment_and_infrastructure

| Estado | Quantidade |
|---|---:|
| Adicionados | 11 |
| Modificados | 30 |
| Removidos | 0 |

#### Adicionados

- `compose.develop.yaml`
- `deploy/self-hosted/bootstrap-admin.sh`
- `deploy/self-hosted/build-images.sh`
- `deploy/self-hosted/compose.data.yaml`
- `deploy/self-hosted/compose.edge-data.yaml`
- `deploy/self-hosted/compose.edge-http.yaml`
- `deploy/self-hosted/compose.networks.yaml`
- `deploy/self-hosted/compose.runtime.yaml`
- `deploy/self-hosted/healthcheck.sh`
- `deploy/self-hosted/lib.sh`
- `deploy/self-hosted/rollback.sh`

#### Modificados

- `compose.production.yaml`
- `compose.yaml`
- `deploy/README.md`
- `deploy/cloudpanel/pige360-vhost.nginx.conf.example`
- `deploy/compose/compose.cloudpanel.yaml`
- `deploy/compose/compose.edge.yaml`
- `deploy/compose/compose.logging.yaml`
- `deploy/env/pige360.develop.env.example`
- `deploy/env/pige360.production.env.example`
- `deploy/images/catalog.yaml`
- `deploy/observability/alloy.config`
- `deploy/self-hosted/backup.sh`
- `deploy/self-hosted/install.sh`
- `deploy/self-hosted/restore.sh`
- `deploy/self-hosted/update.sh`
- `infra/docker/Dockerfile.api`
- `infra/docker/Dockerfile.migrations`
- `infra/docker/Dockerfile.reporting`
- `infra/docker/Dockerfile.web`
- `infra/docker/Dockerfile.worker`
- `infra/docker/base/Dockerfile.node`
- `infra/docker/base/Dockerfile.python`
- `infra/docker/base/Dockerfile.runtime`
- `infra/docker/base/Dockerfile.rust-tauri`
- `infra/docker/build-farm/Dockerfile.linux`
- `infra/docker/nginx.conf`
- `infra/monitoring/loki.yaml`
- `infra/scripts/app-init.sh`
- `infra/templates/compose.production.yaml.tmpl`
- `infra/templates/compose.yaml.tmpl`

### documentation_and_evidence

| Estado | Quantidade |
|---|---:|
| Adicionados | 8 |
| Modificados | 13 |
| Removidos | 0 |

#### Adicionados

- `docs/deployment/DEPLOY_NOW_1.1.1.md`
- `docs/operations/COMMERCIAL_ADMINISTRATION.md`
- `docs/operations/CONTROL_PLANE_OPERATIONS.md`
- `docs/operations/DELIVERY_1.1.0.md`
- `docs/operations/PROCESS_AUDIT_AND_CORRECTION.md`
- `docs/operations/PULL_REQUEST_1.1.0.md`
- `docs/operations/SOURCE_BASELINE.json`
- `docs/operations/SOURCE_BASELINE.md`

#### Modificados

- `docs/api/OPENAPI_REPORT.json`
- `docs/api/openapi.json`
- `docs/api/openapi.yaml`
- `docs/ci-cd/GIT_FLOW.md`
- `docs/ci-cd/RELEASE_SEMVER.md`
- `docs/deployment/CLOUDPANEL.md`
- `docs/deployment/DOCKGE.md`
- `docs/deployment/PORTAINER.md`
- `docs/deployment/SELF_HOSTED.md`
- `docs/execution/REQUIREMENTS_MATRIX.md`
- `docs/execution/requirements.json`
- `docs/operations/OBSERVABILITY.md`
- `docs/operations/RISK_REGISTER.md`

### frontend_and_apps

| Estado | Quantidade |
|---|---:|
| Adicionados | 4 |
| Modificados | 181 |
| Removidos | 0 |

#### Adicionados

- `apps/platform-console/src/components/CommercialAdministrationPanel.vue`
- `apps/platform-console/src/components/CommercialAdministrationPanel.vue.js`
- `apps/platform-console/src/components/OperationalAdministrationPanel.vue`
- `apps/platform-console/src/components/OperationalAdministrationPanel.vue.js`

#### Modificados

- `apps/admin-app/index.html`
- `apps/admin-app/package.json`
- `apps/admin-app/public/manifest.webmanifest`
- `apps/admin-app/public/sw.js`
- `apps/admin-app/src-tauri/Cargo.toml`
- `apps/admin-app/src-tauri/gen/ios/PIGE360/Info.plist`
- `apps/admin-app/src-tauri/tauri.conf.json`
- `apps/admin-app/src/app-contract.js`
- `apps/admin-app/src/app-contract.ts`
- `apps/admin-app/src/main.js`
- `apps/admin-app/src/main.ts`
- `apps/admin-app/vite.config.ts`
- `apps/branding-studio/index.html`
- `apps/branding-studio/package.json`
- `apps/branding-studio/public/manifest.webmanifest`
- `apps/branding-studio/public/sw.js`
- `apps/branding-studio/src-tauri/Cargo.toml`
- `apps/branding-studio/src-tauri/gen/ios/PIGE360/Info.plist`
- `apps/branding-studio/src-tauri/tauri.conf.json`
- `apps/branding-studio/src/app-contract.js`
- `apps/branding-studio/src/app-contract.ts`
- `apps/branding-studio/src/main.js`
- `apps/branding-studio/src/main.ts`
- `apps/branding-studio/vite.config.ts`
- `apps/desktop-admin/index.html`
- `apps/desktop-admin/package.json`
- `apps/desktop-admin/public/manifest.webmanifest`
- `apps/desktop-admin/public/sw.js`
- `apps/desktop-admin/src-tauri/Cargo.toml`
- `apps/desktop-admin/src-tauri/gen/ios/PIGE360/Info.plist`
- `apps/desktop-admin/src-tauri/tauri.conf.json`
- `apps/desktop-admin/src/app-contract.js`
- `apps/desktop-admin/src/app-contract.ts`
- `apps/desktop-admin/src/main.js`
- `apps/desktop-admin/src/main.ts`
- `apps/desktop-admin/vite.config.ts`
- `apps/family-app/index.html`
- `apps/family-app/package.json`
- `apps/family-app/public/manifest.webmanifest`
- `apps/family-app/public/sw.js`
- `apps/family-app/src-tauri/Cargo.toml`
- `apps/family-app/src-tauri/gen/ios/PIGE360/Info.plist`
- `apps/family-app/src-tauri/tauri.conf.json`
- `apps/family-app/src/app-contract.js`
- `apps/family-app/src/app-contract.ts`
- `apps/family-app/src/main.js`
- `apps/family-app/src/main.ts`
- `apps/family-app/vite.config.ts`
- `apps/kiosk-app/index.html`
- `apps/kiosk-app/package.json`
- `apps/kiosk-app/public/manifest.webmanifest`
- `apps/kiosk-app/public/sw.js`
- `apps/kiosk-app/src-tauri/Cargo.toml`
- `apps/kiosk-app/src-tauri/gen/ios/PIGE360/Info.plist`
- `apps/kiosk-app/src-tauri/tauri.conf.json`
- `apps/kiosk-app/src/app-contract.js`
- `apps/kiosk-app/src/app-contract.ts`
- `apps/kiosk-app/src/main.js`
- `apps/kiosk-app/src/main.ts`
- `apps/kiosk-app/vite.config.ts`
- `apps/platform-console/index.html`
- `apps/platform-console/package.json`
- `apps/platform-console/public/manifest.webmanifest`
- `apps/platform-console/public/sw.js`
- `apps/platform-console/src-tauri/Cargo.toml`
- `apps/platform-console/src-tauri/gen/ios/PIGE360/Info.plist`
- `apps/platform-console/src-tauri/tauri.conf.json`
- `apps/platform-console/src/App.vue`
- `apps/platform-console/src/App.vue.js`
- `apps/platform-console/src/app-contract.js`
- `apps/platform-console/src/app-contract.ts`
- `apps/platform-console/src/main.js`
- `apps/platform-console/src/main.ts`
- `apps/platform-console/src/styles.css`
- `apps/platform-console/vite.config.ts`
- `apps/pos-app/index.html`
- `apps/pos-app/package.json`
- `apps/pos-app/public/manifest.webmanifest`
- `apps/pos-app/public/sw.js`
- `apps/pos-app/src-tauri/Cargo.toml`
- `apps/pos-app/src-tauri/gen/ios/PIGE360/Info.plist`
- `apps/pos-app/src-tauri/tauri.conf.json`
- `apps/pos-app/src/app-contract.js`
- `apps/pos-app/src/app-contract.ts`
- `apps/pos-app/src/main.js`
- `apps/pos-app/src/main.ts`
- `apps/pos-app/vite.config.ts`
- `apps/public-portal/index.html`
- `apps/public-portal/package.json`
- `apps/public-portal/public/manifest.webmanifest`
- `apps/public-portal/public/sw.js`
- `apps/public-portal/src-tauri/Cargo.toml`
- `apps/public-portal/src-tauri/gen/ios/PIGE360/Info.plist`
- `apps/public-portal/src-tauri/tauri.conf.json`
- `apps/public-portal/src/app-contract.js`
- `apps/public-portal/src/app-contract.ts`
- `apps/public-portal/src/main.js`
- `apps/public-portal/src/main.ts`
- `apps/public-portal/vite.config.ts`
- `apps/student-app/index.html`
- `apps/student-app/package.json`
- `apps/student-app/public/manifest.webmanifest`
- `apps/student-app/public/sw.js`
- `apps/student-app/src-tauri/Cargo.toml`
- `apps/student-app/src-tauri/gen/ios/PIGE360/Info.plist`
- `apps/student-app/src-tauri/tauri.conf.json`
- `apps/student-app/src/app-contract.js`
- `apps/student-app/src/app-contract.ts`
- `apps/student-app/src/main.js`
- `apps/student-app/src/main.ts`
- `apps/student-app/vite.config.ts`
- `apps/teacher-app/index.html`
- `apps/teacher-app/package.json`
- `apps/teacher-app/public/manifest.webmanifest`
- `apps/teacher-app/public/sw.js`
- `apps/teacher-app/src-tauri/Cargo.toml`
- `apps/teacher-app/src-tauri/gen/ios/PIGE360/Info.plist`
- `apps/teacher-app/src-tauri/tauri.conf.json`
- `apps/teacher-app/src/app-contract.js`
- `apps/teacher-app/src/app-contract.ts`
- `apps/teacher-app/src/main.js`
- `apps/teacher-app/src/main.ts`
- `apps/teacher-app/vite.config.ts`
- `apps/tenant-admin-web/index.html`
- `apps/tenant-admin-web/package.json`
- `apps/tenant-admin-web/public/manifest.webmanifest`
- `apps/tenant-admin-web/public/sw.js`
- `apps/tenant-admin-web/src-tauri/Cargo.toml`
- `apps/tenant-admin-web/src-tauri/gen/ios/PIGE360/Info.plist`
- `apps/tenant-admin-web/src-tauri/tauri.conf.json`
- `apps/tenant-admin-web/src/app-contract.js`
- `apps/tenant-admin-web/src/app-contract.ts`
- `apps/tenant-admin-web/src/components/ProcurementPanel.vue.js`
- `apps/tenant-admin-web/src/main.js`
- `apps/tenant-admin-web/src/main.ts`
- `apps/tenant-admin-web/vite.config.ts`
- `apps/tenant-download-center/index.html`
- `apps/tenant-download-center/package.json`
- `apps/tenant-download-center/public/manifest.webmanifest`
- `apps/tenant-download-center/public/sw.js`
- `apps/tenant-download-center/src-tauri/Cargo.toml`
- `apps/tenant-download-center/src-tauri/gen/ios/PIGE360/Info.plist`
- `apps/tenant-download-center/src-tauri/tauri.conf.json`
- `apps/tenant-download-center/src/app-contract.js`
- `apps/tenant-download-center/src/app-contract.ts`
- `apps/tenant-download-center/src/main.js`
- `apps/tenant-download-center/src/main.ts`
- `apps/tenant-download-center/vite.config.ts`
- `apps/timeclock-app/index.html`
- `apps/timeclock-app/package.json`
- `apps/timeclock-app/public/manifest.webmanifest`
- `apps/timeclock-app/public/sw.js`
- `apps/timeclock-app/src-tauri/Cargo.toml`
- `apps/timeclock-app/src-tauri/gen/ios/PIGE360/Info.plist`
- `apps/timeclock-app/src-tauri/tauri.conf.json`
- `apps/timeclock-app/src/app-contract.js`
- `apps/timeclock-app/src/app-contract.ts`
- `apps/timeclock-app/src/main.js`
- `apps/timeclock-app/src/main.ts`
- `apps/timeclock-app/vite.config.ts`
- `packages/api-sdk/package.json`
- `packages/api-sdk/src/generated/client.ts`
- `packages/api-sdk/src/generated/operations.json`
- `packages/api-sdk/src/generated/types.ts`
- `packages/app-manifest/package.json`
- `packages/auth/package.json`
- `packages/auth/src/index.js`
- `packages/auth/src/index.ts`
- `packages/design-tokens/package.json`
- `packages/domain-types/package.json`
- `packages/fiscal-types/package.json`
- `packages/mail-client/package.json`
- `packages/observability/package.json`
- `packages/offline-sync/package.json`
- `packages/offline-sync/src/index.js`
- `packages/offline-sync/src/index.ts`
- `packages/permissions/package.json`
- `packages/tenant-branding/package.json`
- `packages/testing/package.json`
- `packages/ui/package.json`
- `packages/validation/package.json`

### project_root_and_other

| Estado | Quantidade |
|---|---:|
| Adicionados | 223 |
| Modificados | 8 |
| Removidos | 0 |

#### Adicionados

- `.dockerignore`
- `deployments/cloudpanel/develop/.env.example`
- `deployments/cloudpanel/develop/GENERATED-MANIFEST.json`
- `deployments/cloudpanel/develop/PLATFORM.md`
- `deployments/cloudpanel/develop/README.md`
- `deployments/cloudpanel/develop/backup.sh`
- `deployments/cloudpanel/develop/bootstrap-admin.sh`
- `deployments/cloudpanel/develop/compose.yaml`
- `deployments/cloudpanel/develop/config/gateway/default.conf.template`
- `deployments/cloudpanel/develop/config/init-minio.sh`
- `deployments/cloudpanel/develop/config/observability/alloy.config`
- `deployments/cloudpanel/develop/config/observability/grafana/dashboards/operations.json`
- `deployments/cloudpanel/develop/config/observability/grafana/provisioning/dashboards/dashboards.yml`
- `deployments/cloudpanel/develop/config/observability/grafana/provisioning/datasources/datasources.yml`
- `deployments/cloudpanel/develop/config/observability/loki.yaml`
- `deployments/cloudpanel/develop/config/observability/otel-collector.yaml`
- `deployments/cloudpanel/develop/config/observability/prometheus.yml`
- `deployments/cloudpanel/develop/healthcheck.sh`
- `deployments/cloudpanel/develop/init-secrets.sh`
- `deployments/cloudpanel/develop/install.sh`
- `deployments/cloudpanel/develop/lib.sh`
- `deployments/cloudpanel/develop/logs.sh`
- `deployments/cloudpanel/develop/restore.sh`
- `deployments/cloudpanel/develop/rollback.sh`
- `deployments/cloudpanel/develop/stop.sh`
- `deployments/cloudpanel/develop/tools/backup_manifest.py`
- `deployments/cloudpanel/develop/update.sh`
- `deployments/cloudpanel/develop/validate.sh`
- `deployments/cloudpanel/production/.env.example`
- `deployments/cloudpanel/production/GENERATED-MANIFEST.json`
- `deployments/cloudpanel/production/PLATFORM.md`
- `deployments/cloudpanel/production/README.md`
- `deployments/cloudpanel/production/backup.sh`
- `deployments/cloudpanel/production/bootstrap-admin.sh`
- `deployments/cloudpanel/production/compose.yaml`
- `deployments/cloudpanel/production/config/gateway/default.conf.template`
- `deployments/cloudpanel/production/config/init-minio.sh`
- `deployments/cloudpanel/production/config/observability/alloy.config`
- `deployments/cloudpanel/production/config/observability/grafana/dashboards/operations.json`
- `deployments/cloudpanel/production/config/observability/grafana/provisioning/dashboards/dashboards.yml`
- `deployments/cloudpanel/production/config/observability/grafana/provisioning/datasources/datasources.yml`
- `deployments/cloudpanel/production/config/observability/loki.yaml`
- `deployments/cloudpanel/production/config/observability/otel-collector.yaml`
- `deployments/cloudpanel/production/config/observability/prometheus.yml`
- `deployments/cloudpanel/production/healthcheck.sh`
- `deployments/cloudpanel/production/init-secrets.sh`
- `deployments/cloudpanel/production/install.sh`
- `deployments/cloudpanel/production/lib.sh`
- `deployments/cloudpanel/production/logs.sh`
- `deployments/cloudpanel/production/restore.sh`
- `deployments/cloudpanel/production/rollback.sh`
- `deployments/cloudpanel/production/stop.sh`
- `deployments/cloudpanel/production/tools/backup_manifest.py`
- `deployments/cloudpanel/production/update.sh`
- `deployments/cloudpanel/production/validate.sh`
- `deployments/develop/.env.example`
- `deployments/develop/GENERATED-MANIFEST.json`
- `deployments/develop/README.md`
- `deployments/develop/backup.sh`
- `deployments/develop/bootstrap-admin.sh`
- `deployments/develop/compose.cloudpanel.yaml`
- `deployments/develop/compose.dockge.yaml`
- `deployments/develop/compose.yaml`
- `deployments/develop/config/gateway/default.conf.template`
- `deployments/develop/config/init-minio.sh`
- `deployments/develop/config/observability/alloy.config`
- `deployments/develop/config/observability/grafana/dashboards/operations.json`
- `deployments/develop/config/observability/grafana/provisioning/dashboards/dashboards.yml`
- `deployments/develop/config/observability/grafana/provisioning/datasources/datasources.yml`
- `deployments/develop/config/observability/loki.yaml`
- `deployments/develop/config/observability/otel-collector.yaml`
- `deployments/develop/config/observability/prometheus.yml`
- `deployments/develop/healthcheck.sh`
- `deployments/develop/init-secrets.sh`
- `deployments/develop/install.sh`
- `deployments/develop/lib.sh`
- `deployments/develop/logs.sh`
- `deployments/develop/restore.sh`
- `deployments/develop/rollback.sh`
- `deployments/develop/stack.portainer.yaml`
- `deployments/develop/stop.sh`
- `deployments/develop/tools/backup_manifest.py`
- `deployments/develop/update.sh`
- `deployments/develop/validate.sh`
- `deployments/dockge/develop/.env.example`
- `deployments/dockge/develop/GENERATED-MANIFEST.json`
- `deployments/dockge/develop/PLATFORM.md`
- `deployments/dockge/develop/README.md`
- `deployments/dockge/develop/backup.sh`
- `deployments/dockge/develop/bootstrap-admin.sh`
- `deployments/dockge/develop/compose.yaml`
- `deployments/dockge/develop/config/gateway/default.conf.template`
- `deployments/dockge/develop/config/init-minio.sh`
- `deployments/dockge/develop/config/observability/alloy.config`
- `deployments/dockge/develop/config/observability/grafana/dashboards/operations.json`
- `deployments/dockge/develop/config/observability/grafana/provisioning/dashboards/dashboards.yml`
- `deployments/dockge/develop/config/observability/grafana/provisioning/datasources/datasources.yml`
- `deployments/dockge/develop/config/observability/loki.yaml`
- `deployments/dockge/develop/config/observability/otel-collector.yaml`
- `deployments/dockge/develop/config/observability/prometheus.yml`
- `deployments/dockge/develop/healthcheck.sh`
- `deployments/dockge/develop/init-secrets.sh`
- `deployments/dockge/develop/install.sh`
- `deployments/dockge/develop/lib.sh`
- `deployments/dockge/develop/logs.sh`
- `deployments/dockge/develop/restore.sh`
- `deployments/dockge/develop/rollback.sh`
- `deployments/dockge/develop/stop.sh`
- `deployments/dockge/develop/tools/backup_manifest.py`
- `deployments/dockge/develop/update.sh`
- `deployments/dockge/develop/validate.sh`
- `deployments/dockge/production/.env.example`
- `deployments/dockge/production/GENERATED-MANIFEST.json`
- `deployments/dockge/production/PLATFORM.md`
- `deployments/dockge/production/README.md`
- `deployments/dockge/production/backup.sh`
- `deployments/dockge/production/bootstrap-admin.sh`
- `deployments/dockge/production/compose.yaml`
- `deployments/dockge/production/config/gateway/default.conf.template`
- `deployments/dockge/production/config/init-minio.sh`
- `deployments/dockge/production/config/observability/alloy.config`
- `deployments/dockge/production/config/observability/grafana/dashboards/operations.json`
- `deployments/dockge/production/config/observability/grafana/provisioning/dashboards/dashboards.yml`
- `deployments/dockge/production/config/observability/grafana/provisioning/datasources/datasources.yml`
- `deployments/dockge/production/config/observability/loki.yaml`
- `deployments/dockge/production/config/observability/otel-collector.yaml`
- `deployments/dockge/production/config/observability/prometheus.yml`
- `deployments/dockge/production/healthcheck.sh`
- `deployments/dockge/production/init-secrets.sh`
- `deployments/dockge/production/install.sh`
- `deployments/dockge/production/lib.sh`
- `deployments/dockge/production/logs.sh`
- `deployments/dockge/production/restore.sh`
- `deployments/dockge/production/rollback.sh`
- `deployments/dockge/production/stop.sh`
- `deployments/dockge/production/tools/backup_manifest.py`
- `deployments/dockge/production/update.sh`
- `deployments/dockge/production/validate.sh`
- `deployments/portainer/develop/.env.example`
- `deployments/portainer/develop/GENERATED-MANIFEST.json`
- `deployments/portainer/develop/PLATFORM.md`
- `deployments/portainer/develop/README.md`
- `deployments/portainer/develop/backup.sh`
- `deployments/portainer/develop/bootstrap-admin.sh`
- `deployments/portainer/develop/compose.yaml`
- `deployments/portainer/develop/config/gateway/default.conf.template`
- `deployments/portainer/develop/config/init-minio.sh`
- `deployments/portainer/develop/config/observability/alloy.config`
- `deployments/portainer/develop/config/observability/grafana/dashboards/operations.json`
- `deployments/portainer/develop/config/observability/grafana/provisioning/dashboards/dashboards.yml`
- `deployments/portainer/develop/config/observability/grafana/provisioning/datasources/datasources.yml`
- `deployments/portainer/develop/config/observability/loki.yaml`
- `deployments/portainer/develop/config/observability/otel-collector.yaml`
- `deployments/portainer/develop/config/observability/prometheus.yml`
- `deployments/portainer/develop/healthcheck.sh`
- `deployments/portainer/develop/init-secrets.sh`
- `deployments/portainer/develop/install.sh`
- `deployments/portainer/develop/lib.sh`
- `deployments/portainer/develop/logs.sh`
- `deployments/portainer/develop/restore.sh`
- `deployments/portainer/develop/rollback.sh`
- `deployments/portainer/develop/stack.yaml`
- `deployments/portainer/develop/stop.sh`
- `deployments/portainer/develop/tools/backup_manifest.py`
- `deployments/portainer/develop/update.sh`
- `deployments/portainer/develop/validate.sh`
- `deployments/portainer/production/.env.example`
- `deployments/portainer/production/GENERATED-MANIFEST.json`
- `deployments/portainer/production/PLATFORM.md`
- `deployments/portainer/production/README.md`
- `deployments/portainer/production/backup.sh`
- `deployments/portainer/production/bootstrap-admin.sh`
- `deployments/portainer/production/compose.yaml`
- `deployments/portainer/production/config/gateway/default.conf.template`
- `deployments/portainer/production/config/init-minio.sh`
- `deployments/portainer/production/config/observability/alloy.config`
- `deployments/portainer/production/config/observability/grafana/dashboards/operations.json`
- `deployments/portainer/production/config/observability/grafana/provisioning/dashboards/dashboards.yml`
- `deployments/portainer/production/config/observability/grafana/provisioning/datasources/datasources.yml`
- `deployments/portainer/production/config/observability/loki.yaml`
- `deployments/portainer/production/config/observability/otel-collector.yaml`
- `deployments/portainer/production/config/observability/prometheus.yml`
- `deployments/portainer/production/healthcheck.sh`
- `deployments/portainer/production/init-secrets.sh`
- `deployments/portainer/production/install.sh`
- `deployments/portainer/production/lib.sh`
- `deployments/portainer/production/logs.sh`
- `deployments/portainer/production/restore.sh`
- `deployments/portainer/production/rollback.sh`
- `deployments/portainer/production/stack.yaml`
- `deployments/portainer/production/stop.sh`
- `deployments/portainer/production/tools/backup_manifest.py`
- `deployments/portainer/production/update.sh`
- `deployments/portainer/production/validate.sh`
- `deployments/production/.env.example`
- `deployments/production/GENERATED-MANIFEST.json`
- `deployments/production/README.md`
- `deployments/production/backup.sh`
- `deployments/production/bootstrap-admin.sh`
- `deployments/production/compose.cloudpanel.yaml`
- `deployments/production/compose.dockge.yaml`
- `deployments/production/compose.yaml`
- `deployments/production/config/gateway/default.conf.template`
- `deployments/production/config/init-minio.sh`
- `deployments/production/config/observability/alloy.config`
- `deployments/production/config/observability/grafana/dashboards/operations.json`
- `deployments/production/config/observability/grafana/provisioning/dashboards/dashboards.yml`
- `deployments/production/config/observability/grafana/provisioning/datasources/datasources.yml`
- `deployments/production/config/observability/loki.yaml`
- `deployments/production/config/observability/otel-collector.yaml`
- `deployments/production/config/observability/prometheus.yml`
- `deployments/production/healthcheck.sh`
- `deployments/production/init-secrets.sh`
- `deployments/production/install.sh`
- `deployments/production/lib.sh`
- `deployments/production/logs.sh`
- `deployments/production/restore.sh`
- `deployments/production/rollback.sh`
- `deployments/production/stack.portainer.yaml`
- `deployments/production/stop.sh`
- `deployments/production/tools/backup_manifest.py`
- `deployments/production/update.sh`
- `deployments/production/validate.sh`

#### Modificados

- `.env.example`
- `.gitignore`
- `CHANGELOG.md`
- `README.md`
- `VERSION`
- `package-lock.json`
- `package.json`
- `release/version-consistency.json`

### rust_and_native_core

| Estado | Quantidade |
|---|---:|
| Adicionados | 0 |
| Modificados | 1 |
| Removidos | 0 |

#### Modificados

- `rust/Cargo.toml`

## Remocoes

Nenhum arquivo-fonte da base foi removido.
