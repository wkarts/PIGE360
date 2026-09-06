from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _secret(env_name: str, file_env_name: str, default: str = "") -> str:
    direct = os.getenv(env_name, "")
    if direct:
        return direct
    file_name = os.getenv(file_env_name, "")
    if file_name and Path(file_name).is_file():
        return Path(file_name).read_text(encoding="utf-8").strip()
    return default


_DEFAULT_RESERVED_TENANT_SLUGS = (
    "www",
    "api",
    "console",
    "ops",
    "edge",
    "status",
    "assets",
    "cdn",
    "mail",
    "smtp",
    "imap",
    "admin",
    "control",
    "platform",
)


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str = "PIGE360"
    app_full_name: str = "PIGE360 — Plataforma Integrada de Gestão Educacional"
    version: str = "1.1.2"
    environment: str = "development"
    demo_mode: bool = False
    data_root: Path = Path("runtime-data")
    control_db_path: Path = Path("runtime-data/control/platform-control.db")
    storage_root: Path = Path("runtime-data/tenants")
    platform_hosts: tuple[str, ...] = ("console.platform.local", "api.platform.local")
    base_domain: str = "pige360.com.br"
    tenant_default_base_domain: str = "pige360.com.br"
    tenant_custom_domains_enabled: bool = True
    tenant_custom_domain_cname_target: str = "edge.pige360.com.br"
    tenant_reserved_slugs: tuple[str, ...] = _DEFAULT_RESERVED_TENANT_SLUGS
    jwt_secret: str = ""
    jwt_issuer: str = "pige360"
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    login_max_attempts: int = 5
    login_lockout_minutes: int = 15
    bootstrap_token: str = ""
    cors_origins: tuple[str, ...] = ()
    remote_ci_enabled: bool = False
    remote_registry_enabled: bool = False
    remote_release_enabled: bool = False
    remote_deploy_enabled: bool = False
    brand_asset_max_mb: int = 20
    database_control_url: str = ""
    database_control_password: str = ""
    database_tenant_admin_url: str = ""
    database_tenant_admin_password: str = ""
    database_secret_key: str = ""
    database_pool_size: int = 10
    database_max_overflow: int = 10
    object_storage_endpoint: str = ""
    object_storage_region: str = "us-east-1"
    object_storage_access_key: str = ""
    object_storage_secret_key: str = ""
    object_storage_secure: bool = False
    redis_url: str = ""
    redis_password: str = ""
    rabbitmq_url: str = ""
    rabbitmq_password: str = ""
    readiness_timeout_seconds: float = 3.0
    readiness_require_redis: bool = False
    readiness_require_rabbitmq: bool = False
    readiness_require_object_storage: bool = False
    build_farm_token: str = ""
    integration_remote_enabled: bool = False
    mail_mode: str = "disabled"
    mail_imap_host: str = ""
    mail_imap_port: int = 993
    mail_smtp_host: str = ""
    mail_smtp_port: int = 587
    mail_smtp_tls: str = "starttls"
    ibpt_provider: str = "wwsoftwares"
    ibpt_api_base_url: str = "https://ibpt.wwsoftwares.com.br"
    ibpt_api_uf_path: str = "/tabela/ibpt/{uf}"
    ibpt_sync_enabled: bool = False
    signature_internal_otp_required: bool = True
    signature_otp_ttl_seconds: int = 300
    signature_otp_max_attempts: int = 5

    @classmethod
    def from_env(cls) -> "Settings":
        environment = os.getenv("APP_ENV", "development")
        data_root = Path(os.getenv("APP_DATA_ROOT", "runtime-data"))
        jwt_secret = _secret("APP_JWT_SECRET", "APP_JWT_SECRET_FILE")
        bootstrap_token = _secret("APP_BOOTSTRAP_TOKEN", "APP_BOOTSTRAP_TOKEN_FILE")
        database_control_url = os.getenv("DATABASE_CONTROL_URL", "")
        database_control_password = _secret("DATABASE_CONTROL_PASSWORD", "DATABASE_CONTROL_PASSWORD_FILE")
        database_tenant_admin_url = os.getenv("DATABASE_TENANT_ADMIN_URL", "")
        database_tenant_admin_password = _secret("DATABASE_TENANT_ADMIN_PASSWORD", "DATABASE_TENANT_ADMIN_PASSWORD_FILE")
        database_secret_key = _secret("DATABASE_SECRET_KEY", "DATABASE_SECRET_KEY_FILE")
        object_storage_endpoint = os.getenv("MINIO_ENDPOINT", "")
        object_storage_access_key = _secret("MINIO_ACCESS_KEY", "MINIO_ACCESS_KEY_FILE")
        object_storage_secret_key = _secret("MINIO_SECRET_KEY", "MINIO_SECRET_KEY_FILE")
        redis_password = _secret("REDIS_PASSWORD", "REDIS_PASSWORD_FILE")
        rabbitmq_password = _secret("RABBITMQ_PASSWORD", "RABBITMQ_PASSWORD_FILE")
        build_farm_token = _secret("BUILD_FARM_TOKEN", "BUILD_FARM_TOKEN_FILE")
        readiness_timeout_seconds = float(os.getenv("READINESS_TIMEOUT_SECONDS", "3"))
        if not 0.1 <= readiness_timeout_seconds <= 30:
            raise RuntimeError("READINESS_TIMEOUT_SECONDS deve estar entre 0.1 e 30 segundos.")
        login_max_attempts = int(os.getenv("APP_LOGIN_MAX_ATTEMPTS", "5"))
        login_lockout_minutes = int(os.getenv("APP_LOGIN_LOCKOUT_MINUTES", "15"))
        if not 2 <= login_max_attempts <= 100:
            raise RuntimeError("APP_LOGIN_MAX_ATTEMPTS deve estar entre 2 e 100.")
        if not 1 <= login_lockout_minutes <= 1_440:
            raise RuntimeError("APP_LOGIN_LOCKOUT_MINUTES deve estar entre 1 e 1440.")

        base_domain = os.getenv("PIGE360_BASE_DOMAIN", "pige360.com.br").strip().lower().rstrip(".")
        tenant_default_base_domain = os.getenv("TENANT_DEFAULT_BASE_DOMAIN", base_domain).strip().lower().rstrip(".")
        tenant_custom_domain_cname_target = os.getenv(
            "TENANT_CUSTOM_DOMAIN_CNAME_TARGET", f"edge.{base_domain}"
        ).strip().lower().rstrip(".")
        reserved_raw = os.getenv("TENANT_RESERVED_SLUGS", ",".join(_DEFAULT_RESERVED_TENANT_SLUGS))
        tenant_reserved_slugs = tuple(
            dict.fromkeys(item.strip().lower() for item in reserved_raw.split(",") if item.strip())
        )
        if not base_domain or "." not in base_domain:
            raise RuntimeError("PIGE360_BASE_DOMAIN deve ser um domínio válido.")
        if not tenant_default_base_domain or "." not in tenant_default_base_domain:
            raise RuntimeError("TENANT_DEFAULT_BASE_DOMAIN deve ser um domínio válido.")
        if not tenant_custom_domain_cname_target or "." not in tenant_custom_domain_cname_target:
            raise RuntimeError("TENANT_CUSTOM_DOMAIN_CNAME_TARGET deve ser um hostname válido.")

        if not jwt_secret and environment not in {"production", "staging"}:
            jwt_secret = "local-development-only-change-me-" + "x" * 32
        if environment in {"production", "staging"} and len(jwt_secret) < 64:
            raise RuntimeError("APP_JWT_SECRET_FILE deve fornecer ao menos 64 caracteres em produção.")
        if environment in {"production", "staging"}:
            if not database_control_url.startswith("postgresql+asyncpg://"):
                raise RuntimeError("DATABASE_CONTROL_URL deve usar postgresql+asyncpg:// em produção.")
            if not database_tenant_admin_url.startswith("postgresql+asyncpg://"):
                raise RuntimeError("DATABASE_TENANT_ADMIN_URL deve usar postgresql+asyncpg:// em produção.")
            if not database_control_password or not database_tenant_admin_password:
                raise RuntimeError("Senhas PostgreSQL devem ser fornecidas por Docker Secret/secret manager.")
            if not database_secret_key:
                raise RuntimeError("DATABASE_SECRET_KEY_FILE é obrigatório para cifrar credenciais por tenant.")
            if not object_storage_endpoint or not object_storage_access_key or not object_storage_secret_key:
                raise RuntimeError("MinIO/S3 deve estar configurado por secrets em produção.")
            if len(build_farm_token) < 32:
                raise RuntimeError("BUILD_FARM_TOKEN_FILE deve fornecer um token forte em produção.")

        hosts = tuple(
            x.strip().lower()
            for x in os.getenv("ALLOWED_PLATFORM_HOSTS", "console.platform.local,api.platform.local").split(",")
            if x.strip()
        )
        origins = tuple(x.strip() for x in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if x.strip())
        return cls(
            version=os.getenv("APP_VERSION", "1.1.2"),
            environment=environment,
            demo_mode=_bool("APP_DEMO_MODE"),
            data_root=data_root,
            control_db_path=Path(os.getenv("APP_CONTROL_DB_PATH", str(data_root / "control/platform-control.db"))),
            storage_root=Path(os.getenv("APP_STORAGE_ROOT", str(data_root / "tenants"))),
            platform_hosts=hosts,
            base_domain=base_domain,
            tenant_default_base_domain=tenant_default_base_domain,
            tenant_custom_domains_enabled=_bool("TENANT_CUSTOM_DOMAINS_ENABLED", True),
            tenant_custom_domain_cname_target=tenant_custom_domain_cname_target,
            tenant_reserved_slugs=tenant_reserved_slugs,
            jwt_secret=jwt_secret,
            bootstrap_token=bootstrap_token,
            access_token_minutes=int(os.getenv("APP_ACCESS_TOKEN_MINUTES", "15")),
            refresh_token_days=int(os.getenv("APP_REFRESH_TOKEN_DAYS", "30")),
            login_max_attempts=login_max_attempts,
            login_lockout_minutes=login_lockout_minutes,
            cors_origins=origins,
            remote_ci_enabled=_bool("REMOTE_CI_ENABLED"),
            remote_registry_enabled=_bool("REMOTE_REGISTRY_ENABLED"),
            remote_release_enabled=_bool("REMOTE_RELEASE_ENABLED"),
            remote_deploy_enabled=_bool("REMOTE_DEPLOY_ENABLED"),
            brand_asset_max_mb=int(os.getenv("TENANT_BRAND_ASSET_MAX_MB", "20")),
            database_control_url=database_control_url,
            database_control_password=database_control_password,
            database_tenant_admin_url=database_tenant_admin_url,
            database_tenant_admin_password=database_tenant_admin_password,
            database_secret_key=database_secret_key,
            database_pool_size=int(os.getenv("DATABASE_POOL_SIZE", "10")),
            database_max_overflow=int(os.getenv("DATABASE_MAX_OVERFLOW", "10")),
            object_storage_endpoint=object_storage_endpoint,
            object_storage_region=os.getenv("MINIO_REGION", "us-east-1"),
            object_storage_access_key=object_storage_access_key,
            object_storage_secret_key=object_storage_secret_key,
            object_storage_secure=_bool("MINIO_SECURE"),
            redis_url=os.getenv("REDIS_URL", ""),
            redis_password=redis_password,
            rabbitmq_url=os.getenv("RABBITMQ_URL", ""),
            rabbitmq_password=rabbitmq_password,
            readiness_timeout_seconds=readiness_timeout_seconds,
            readiness_require_redis=_bool("READINESS_REQUIRE_REDIS", environment in {"production", "staging"}),
            readiness_require_rabbitmq=_bool("READINESS_REQUIRE_RABBITMQ", environment in {"production", "staging"}),
            readiness_require_object_storage=_bool(
                "READINESS_REQUIRE_OBJECT_STORAGE", environment in {"production", "staging"}
            ),
            build_farm_token=build_farm_token,
            integration_remote_enabled=_bool("INTEGRATION_REMOTE_ENABLED", environment in {"production", "staging"}),
            mail_mode=os.getenv("MAIL_MODE", "disabled"),
            mail_imap_host=os.getenv("IMAP_HOST", ""),
            mail_imap_port=int(os.getenv("IMAP_PORT", "993")),
            mail_smtp_host=os.getenv("SMTP_HOST", ""),
            mail_smtp_port=int(os.getenv("SMTP_PORT", "587")),
            mail_smtp_tls=os.getenv("SMTP_TLS", "starttls").lower(),
            ibpt_provider=os.getenv("IBPT_PROVIDER", "wwsoftwares"),
            ibpt_api_base_url=os.getenv("IBPT_API_BASE_URL", "https://ibpt.wwsoftwares.com.br"),
            ibpt_api_uf_path=os.getenv("IBPT_API_UF_PATH", "/tabela/ibpt/{uf}"),
            ibpt_sync_enabled=_bool("IBPT_SYNC_ENABLED", False),
            signature_internal_otp_required=_bool("SIGNATURE_INTERNAL_OTP_REQUIRED", True),
            signature_otp_ttl_seconds=int(os.getenv("SIGNATURE_OTP_TTL_SECONDS", "300")),
            signature_otp_max_attempts=int(os.getenv("SIGNATURE_OTP_MAX_ATTEMPTS", "5")),
        )

    def testing(self, root: Path) -> "Settings":
        return replace(
            self,
            environment="testing",
            demo_mode=False,
            data_root=root,
            control_db_path=root / "control/control.db",
            storage_root=root / "tenants",
            jwt_secret="test-only-secret-" + "x" * 64,
            bootstrap_token="test-bootstrap-token",
            build_farm_token="test-build-farm-token-" + "x" * 48,
            integration_remote_enabled=False,
        )
