#!/usr/bin/env python3
"""Operações service-native do deployment PIGE360.

O módulo é embarcado na imagem ``pige360-ops``. Ele não controla o Docker e
não monta o socket do daemon: cada comando atua somente sobre serviços de rede
e volumes explicitamente concedidos pelo Compose.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Iterator, Sequence


INTERNAL_SECRETS = (
    "app_jwt_secret",
    "bootstrap_token",
    "minio_secret_key",
    "postgres_control_password",
    "postgres_tenant_password",
    "grafana_admin_password",
    "redis_password",
    "rabbitmq_password",
    "worker_context_signing_key",
    "build_farm_token",
)
EXTERNAL_SECRETS = (
    "cloudflare_control_tunnel_token",
    "cloudflare_tenant_tunnel_token",
    "cloudflare_api_token",
    "connect_api_key",
)
SPECIAL_SECRETS = ("database_secret_key", "minio_access_key")
ALL_SECRETS = frozenset(INTERNAL_SECRETS + EXTERNAL_SECRETS + SPECIAL_SECRETS)
STABLE_SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
DEVELOP_TAG = re.compile(r"^develop(?:-[0-9a-f]{7,64})?$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _path_env(name: str, default: str) -> Path:
    return Path(os.getenv(name, default)).resolve()


SECRETS_ROOT = _path_env("PIGE360_SECRETS_VOLUME", "/var/lib/pige360/secrets")
CONFIG_ROOT = _path_env("PIGE360_CONFIG_VOLUME", "/var/lib/pige360/config")
DEFAULT_CONFIG_ROOT = _path_env("PIGE360_DEFAULT_CONFIG", "/opt/pige360/default-config")
STATE_ROOT = _path_env("PIGE360_STATE_VOLUME", "/var/lib/pige360/operations")
BACKUP_ROOT = _path_env("PIGE360_BACKUP_VOLUME", "/var/lib/pige360/backups")
TENANT_STORAGE_ROOT = _path_env("PIGE360_TENANT_STORAGE", "/var/lib/pige360/tenants")


class OperationError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _secret_path(name: str) -> Path:
    if name not in ALL_SECRETS:
        raise OperationError(f"segredo não permitido: {name}")
    return SECRETS_ROOT / f"{name}.txt"


def _assert_safe_directory(path: Path, *, create: bool = True, mode: int = 0o750) -> None:
    if path.is_symlink():
        raise OperationError(f"diretório não pode ser link simbólico: {path}")
    if create:
        path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise OperationError(f"diretório obrigatório ausente: {path}")
    os.chmod(path, mode)


def _atomic_write(path: Path, value: bytes, *, mode: int = 0o444) -> None:
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise OperationError(f"destino inseguro: {path}")
    _assert_safe_directory(path.parent, create=False, mode=path.parent.stat().st_mode & 0o777)
    fd, temporary_name = tempfile.mkstemp(prefix=".pige360-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _read_secret(name: str, *, required: bool = True) -> str:
    path = _secret_path(name)
    if not path.is_file() or path.is_symlink():
        if required:
            raise OperationError(f"segredo ausente ou inseguro: {path}")
        return ""
    value = path.read_text(encoding="utf-8").strip()
    if required and not value:
        raise OperationError(f"segredo vazio: {path}")
    return value


def _random_hex() -> str:
    return secrets.token_hex(48)


def _fernet_key() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")


def _minio_access_key() -> str:
    return "pige360" + secrets.token_hex(6)


def init_secrets(_: argparse.Namespace) -> int:
    _assert_safe_directory(SECRETS_ROOT, mode=0o711)
    generators = {name: _random_hex for name in INTERNAL_SECRETS}
    generators.update(
        {
            "database_secret_key": _fernet_key,
            "minio_access_key": _minio_access_key,
        }
    )
    created: list[str] = []
    preserved: list[str] = []
    for name, generator in generators.items():
        path = _secret_path(name)
        if path.is_file() and not path.is_symlink() and path.stat().st_size:
            os.chmod(path, 0o444)
            preserved.append(name)
            continue
        _atomic_write(path, (generator() + "\n").encode("utf-8"))
        created.append(name)
    for name in EXTERNAL_SECRETS:
        path = _secret_path(name)
        if path.exists():
            if path.is_symlink() or not path.is_file():
                raise OperationError(f"segredo externo inseguro: {path}")
            os.chmod(path, 0o444)
            preserved.append(name)
        else:
            _atomic_write(path, b"")
            created.append(name)
    print(json.dumps({"status": "ok", "created": created, "preserved": preserved}, ensure_ascii=False))
    return 0


def secret_set(args: argparse.Namespace) -> int:
    if args.name not in EXTERNAL_SECRETS:
        raise OperationError(
            "somente secrets externos podem ser definidos por este comando; "
            "a rotação de chaves internas exige procedimento dedicado"
        )
    raw = sys.stdin.buffer.read(65537)
    if len(raw) > 65536:
        raise OperationError("segredo excede 64 KiB")
    value = raw.rstrip(b"\r\n")
    if not value:
        raise OperationError("segredo externo não pode ser vazio")
    if b"\x00" in value:
        raise OperationError("segredo contém byte NUL")
    _atomic_write(_secret_path(args.name), value + b"\n")
    print(json.dumps({"status": "updated", "secret": args.name}, ensure_ascii=False))
    return 0


def init_config(_: argparse.Namespace) -> int:
    _assert_safe_directory(DEFAULT_CONFIG_ROOT, create=False)
    _assert_safe_directory(CONFIG_ROOT, mode=0o755)
    written: list[str] = []
    for source in sorted(DEFAULT_CONFIG_ROOT.rglob("*")):
        if source.is_symlink():
            raise OperationError(f"configuração padrão contém link simbólico: {source}")
        if not source.is_file():
            continue
        relative = source.relative_to(DEFAULT_CONFIG_ROOT)
        target = CONFIG_ROOT / relative
        _assert_safe_directory(target.parent, mode=0o755)
        value = source.read_bytes()
        if relative.as_posix() == "observability/grafana/provisioning/dashboards/dashboards.yml":
            value = value.replace(
                b"/var/lib/grafana/dashboards",
                b"/opt/pige360/config/observability/grafana/dashboards",
            )
        _atomic_write(target, value, mode=0o444)
        written.append(relative.as_posix())
    if not written:
        raise OperationError("imagem não contém configurações operacionais")
    manifest = {
        "schema_version": 1,
        "version": os.getenv("APP_VERSION", "unknown"),
        "generated_at": _utc_now(),
        "files": {
            relative: hashlib.sha256((CONFIG_ROOT / relative).read_bytes()).hexdigest()
            for relative in written
        },
    }
    _atomic_write(
        CONFIG_ROOT / "manifest.json",
        (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
    )
    print(json.dumps({"status": "ok", "files": len(written)}, ensure_ascii=False))
    return 0


def _chown_tree(path: Path, uid: int, gid: int, mode: int = 0o750) -> None:
    _assert_safe_directory(path, mode=mode)
    for item in [path, *sorted(path.rglob("*"))]:
        if item.is_symlink():
            raise OperationError(f"volume contém link simbólico: {item}")
        os.chown(item, uid, gid)
        if item.is_dir():
            os.chmod(item, mode)


def init_data(_: argparse.Namespace) -> int:
    targets = (
        (TENANT_STORAGE_ROOT, 10001, 10001),
        (STATE_ROOT, 10001, 10001),
        (BACKUP_ROOT, 10001, 10001),
        (_path_env("PIGE360_PROMETHEUS_VOLUME", "/var/lib/pige360/prometheus"), 65534, 65534),
        (_path_env("PIGE360_GRAFANA_VOLUME", "/var/lib/pige360/grafana"), 472, 472),
        (_path_env("PIGE360_LOKI_VOLUME", "/var/lib/pige360/loki"), 10001, 10001),
    )
    for path, uid, gid in targets:
        _chown_tree(path, uid, gid)
    print(json.dumps({"status": "ok", "volumes": len(targets)}, ensure_ascii=False))
    return 0


def validate_config(_: argparse.Namespace) -> int:
    environment = os.getenv("PIGE360_ENVIRONMENT", "").strip()
    tag = os.getenv("PIGE360_IMAGE_TAG", "").strip()
    version = os.getenv("APP_VERSION", "").strip()
    if environment not in {"develop", "production"}:
        raise OperationError("PIGE360_ENVIRONMENT deve ser develop ou production")
    if not STABLE_SEMVER.fullmatch(version):
        raise OperationError("APP_VERSION deve ser SemVer estável")
    if environment == "production":
        if not STABLE_SEMVER.fullmatch(tag) or tag != version:
            raise OperationError("produção exige PIGE360_IMAGE_TAG igual ao APP_VERSION SemVer")
    elif not (DEVELOP_TAG.fullmatch(tag) or STABLE_SEMVER.fullmatch(tag)):
        raise OperationError("homologação exige develop, develop-<sha> ou SemVer")
    for key in (
        "PIGE360_BASE_DOMAIN",
        "PLATFORM_API_HOST",
        "PLATFORM_CONSOLE_HOST",
        "PLATFORM_BRANDING_HOST",
        "PLATFORM_DOWNLOADS_HOST",
    ):
        value = os.getenv(key, "").strip()
        if not value or "/" in value or value.startswith(".") or " " in value:
            raise OperationError(f"{key} inválido")
    for name in INTERNAL_SECRETS + SPECIAL_SECRETS:
        _read_secret(name)
    if os.getenv("CLOUDFLARE_SAAS_ENABLED", "false").lower() == "true":
        _read_secret("cloudflare_api_token")
    if os.getenv("CONNECT_API_ENABLED", "false").lower() == "true":
        _read_secret("connect_api_key")
    required_config = (
        "gateway/default.conf.template",
        "observability/prometheus.yml",
        "observability/loki.yaml",
        "observability/alloy.config",
        "init-minio.sh",
    )
    for relative in required_config:
        path = CONFIG_ROOT / relative
        if not path.is_file() or path.is_symlink() or path.stat().st_size == 0:
            raise OperationError(f"configuração operacional ausente: {relative}")
    print(json.dumps({"status": "valid", "environment": environment, "tag": tag}, ensure_ascii=False))
    return 0


def migrate_control(_: argparse.Namespace) -> int:
    if os.getenv("PIGE360_SKIP_MIGRATIONS", "false").lower() == "true":
        print(json.dumps({"status": "skipped", "scope": "control"}))
        return 0
    _run(["python", "-m", "alembic", "-c", "backend/alembic_control/alembic.ini", "upgrade", "head"])
    print(json.dumps({"status": "completed", "scope": "control"}))
    return 0


def migrate_tenants(_: argparse.Namespace) -> int:
    if os.getenv("PIGE360_SKIP_MIGRATIONS", "false").lower() == "true" or os.getenv(
        "PIGE360_SKIP_TENANT_MIGRATIONS", "false"
    ).lower() == "true":
        print(json.dumps({"status": "skipped", "scope": "tenants"}))
        return 0
    _run(["python", "-m", "app.shared.database.migrate_tenants"])
    print(json.dumps({"status": "completed", "scope": "tenants"}))
    return 0


def _http_ok(url: str, *, host: str | None = None, timeout: float = 5.0) -> bool:
    headers = {"Host": host} if host else {}
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return 200 <= response.status < 300
    except (OSError, urllib.error.URLError, urllib.error.HTTPError):
        return False


def _tcp_ok(host: str, port: int, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _runtime_checks() -> dict[str, bool]:
    base_domain = os.getenv("PIGE360_BASE_DOMAIN", "pige360.com.br")
    return {
        "api": _http_ok(
            "http://pige360-api:8000/api/v1/health/ready",
            host=os.getenv("PLATFORM_CONSOLE_HOST", f"console.{base_domain}"),
        ),
        "web": _http_ok("http://pige360-web:8080/healthz"),
        "platform_console": _http_ok("http://pige360-platform-console:8080/healthz"),
        "branding_studio": _http_ok("http://pige360-branding-studio:8080/healthz"),
        "download_center": _http_ok("http://pige360-tenant-download-center:8080/healthz"),
        "gateway": _http_ok("http://pige360-gateway:8080/healthz"),
        "postgres_control": _tcp_ok("pige360-postgres-control", 5432),
        "postgres_tenants": _tcp_ok("pige360-postgres-tenants", 5432),
        "redis": _tcp_ok("pige360-redis", 6379),
        "rabbitmq": _tcp_ok("pige360-rabbitmq", 5672),
        "minio": _http_ok("http://pige360-minio:9000/minio/health/live"),
    }


def readiness(args: argparse.Namespace) -> int:
    attempts = args.attempts or int(os.getenv("PIGE360_READINESS_ATTEMPTS", "60"))
    delay = args.delay or int(os.getenv("PIGE360_READINESS_DELAY_SECONDS", "5"))
    if attempts < 1 or delay < 1:
        raise OperationError("attempts e delay devem ser positivos")
    report: dict[str, object] = {}
    for attempt in range(1, attempts + 1):
        checks = _runtime_checks()
        report = {
            "schema_version": 1,
            "status": "passed" if all(checks.values()) else "waiting",
            "attempt": attempt,
            "checked_at": _utc_now(),
            "checks": checks,
        }
        if all(checks.values()):
            _assert_safe_directory(STATE_ROOT)
            _atomic_write(
                STATE_ROOT / "readiness.json",
                (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
                mode=0o640,
            )
            print(json.dumps(report, ensure_ascii=False))
            return 0
        if attempt < attempts:
            time.sleep(delay)
    report["status"] = "failed"
    print(json.dumps(report, ensure_ascii=False), file=sys.stderr)
    return 1


def bootstrap_admin(args: argparse.Namespace) -> int:
    if not EMAIL.fullmatch(args.email):
        raise OperationError("e-mail administrativo inválido")
    raw = sys.stdin.buffer.read(4097)
    if len(raw) > 4096:
        raise OperationError("senha excede o limite permitido")
    password = raw.decode("utf-8").rstrip("\r\n")
    if len(password) < 10:
        raise OperationError("senha inicial deve possuir ao menos 10 caracteres")
    payload = json.dumps({"email": args.email, "password": password}).encode("utf-8")
    request = urllib.request.Request(
        "http://pige360-api:8000/api/v1/platform/bootstrap",
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Host": os.getenv("PLATFORM_CONSOLE_HOST", "console.pige360.com.br"),
            "X-Bootstrap-Token": _read_secret("bootstrap_token"),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise OperationError(f"bootstrap recusado (HTTP {exc.code}): {detail}") from exc
    if body.get("status") not in {"bootstrapped", "already_bootstrapped"}:
        raise OperationError(f"resposta inesperada do bootstrap: {body}")
    print(json.dumps({"status": body["status"], "admin": body.get("admin")}, ensure_ascii=False))
    return 0


def _run(command: Sequence[str], *, env: dict[str, str] | None = None, stdout=None, stdin=None) -> None:
    completed = subprocess.run(command, env=env, stdout=stdout, stdin=stdin, check=False)
    if completed.returncode:
        raise OperationError(f"comando falhou ({completed.returncode}): {' '.join(command)}")


def _pg_env(password_name: str) -> dict[str, str]:
    environment = os.environ.copy()
    environment["PGPASSWORD"] = _read_secret(password_name)
    return environment


def _psql_rows(host: str, user: str, database: str, query: str, password_name: str) -> list[str]:
    completed = subprocess.run(
        ["psql", "-X", "-h", host, "-U", user, "-d", database, "-v", "ON_ERROR_STOP=1", "-A", "-t", "-F", "\t", "-c", query],
        env=_pg_env(password_name),
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        raise OperationError(f"consulta PostgreSQL falhou: {completed.stderr.strip()}")
    return [line for line in completed.stdout.splitlines() if line.strip()]


@contextmanager
def _operation_lock(name: str) -> Iterator[None]:
    _assert_safe_directory(STATE_ROOT)
    lock = STATE_ROOT / "operation.lock"
    try:
        lock.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise OperationError("outra operação administrativa está em execução") from exc
    try:
        _atomic_write(lock / "owner.json", (json.dumps({"operation": name, "pid": os.getpid(), "started_at": _utc_now()}) + "\n").encode(), mode=0o600)
        yield
    finally:
        shutil.rmtree(lock, ignore_errors=True)


def _backup_module():
    sys.path.insert(0, "/opt/pige360/ops")
    import backup_manifest  # type: ignore

    return backup_manifest


def _tenant_catalog() -> list[str]:
    query = (
        "SELECT id,code,status,database_name,database_user,bucket_name "
        "FROM platform_tenants WHERE status IN ('active','degraded','suspended') ORDER BY id"
    )
    return _psql_rows("pige360-postgres-control", "pige360_control", "platform_control", query, "postgres_control_password")


def _safe_archive_name(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", value):
        raise OperationError("nome de backup inválido")
    return value


def _s3_client():
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=os.getenv("MINIO_ENDPOINT", "http://pige360-minio:9000"),
        aws_access_key_id=_read_secret("minio_access_key"),
        aws_secret_access_key=_read_secret("minio_secret_key"),
        region_name=os.getenv("MINIO_REGION", "us-east-1"),
        use_ssl=os.getenv("MINIO_SECURE", "false").lower() == "true",
    )


def _snapshot_bucket(client, bucket: str, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    token: str | None = None
    while True:
        kwargs = {"Bucket": bucket}
        if token:
            kwargs["ContinuationToken"] = token
        response = client.list_objects_v2(**kwargs)
        for item in response.get("Contents", []):
            key = str(item["Key"])
            relative = PurePosixPath(key)
            if relative.is_absolute() or ".." in relative.parts:
                raise OperationError(f"chave S3 insegura: {key!r}")
            target = destination.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            client.download_file(bucket, key, str(target))
        if not response.get("IsTruncated"):
            return
        token = str(response["NextContinuationToken"])


def backup(args: argparse.Namespace) -> int:
    backup_manifest = _backup_module()
    name = _safe_archive_name(args.name or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    destination = BACKUP_ROOT / name
    if destination.exists():
        raise OperationError(f"backup já existe: {name}")
    with _operation_lock("backup"):
        _assert_safe_directory(BACKUP_ROOT)
        stage = BACKUP_ROOT / f".{name}.partial-{os.getpid()}"
        stage.mkdir(mode=0o700)
        try:
            (stage / "tenant-databases").mkdir()
            (stage / "objects").mkdir()
            rows = _tenant_catalog()
            (stage / "tenants.tsv").write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")
            control_env = _pg_env("postgres_control_password")
            tenant_env = _pg_env("postgres_tenant_password")
            with (stage / "platform-control.dump").open("wb") as output:
                _run(["pg_dump", "-h", "pige360-postgres-control", "-U", "pige360_control", "--format=custom", "--no-owner", "--no-privileges", "platform_control"], env=control_env, stdout=output)
            for line in rows:
                _, _, _, database_name, _, _ = line.split("\t")
                with (stage / "tenant-databases" / f"{database_name}.dump").open("wb") as output:
                    _run(["pg_dump", "-h", "pige360-postgres-tenants", "-U", "pige360_tenant_admin", "--format=custom", "--no-owner", "--no-privileges", database_name], env=tenant_env, stdout=output)
            versions = subprocess.check_output(["pg_dump", "--version"], text=True)
            (stage / "postgres-versions.txt").write_text(f"control={versions}tenants={versions}", encoding="utf-8")
            with tarfile.open(stage / "tenant-storage.tar.gz", "w:gz") as archive:
                if TENANT_STORAGE_ROOT.exists():
                    for item in sorted(TENANT_STORAGE_ROOT.rglob("*")):
                        if item.is_symlink():
                            raise OperationError(f"link simbólico recusado no storage: {item}")
                    for item in sorted(TENANT_STORAGE_ROOT.iterdir()):
                        archive.add(item, arcname=item.name, recursive=True)
            buckets = sorted({"pige360-platform", *(line.split("\t")[5] for line in rows)})
            (stage / "buckets.txt").write_text("\n".join(buckets) + "\n", encoding="utf-8")
            client = _s3_client()
            for bucket_name in buckets:
                client.head_bucket(Bucket=bucket_name)
                _snapshot_bucket(client, bucket_name, stage / "objects" / bucket_name)
            fingerprint = hashlib.sha256(_read_secret("database_secret_key").encode()).hexdigest()
            backup_manifest.create_manifest(
                stage,
                version=os.getenv("APP_VERSION", ""),
                target=os.getenv("PIGE360_DEPLOY_TARGET", "base"),
                image_mode="registry",
                database_key_fingerprint=fingerprint,
            )
            backup_manifest.verify_manifest(stage)
            os.replace(stage, destination)
        except Exception:
            shutil.rmtree(stage, ignore_errors=True)
            raise
    print(json.dumps({"status": "completed", "backup": name}, ensure_ascii=False))
    return 0


def _safe_extract(archive: tarfile.TarFile, destination: Path) -> None:
    for member in archive.getmembers():
        path = PurePosixPath(member.name)
        if not member.name or path.is_absolute() or ".." in path.parts or member.issym() or member.islnk() or member.isdev():
            raise OperationError(f"entrada insegura no arquivo de storage: {member.name!r}")
    archive.extractall(destination, filter="data")


def _reset_database(host: str, admin: str, password_name: str, database: str, owner: str, dump: Path) -> None:
    environment = _pg_env(password_name)
    query = "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :'database' AND pid <> pg_backend_pid()"
    _run(["psql", "-X", "-h", host, "-U", admin, "-d", "postgres", "-v", "ON_ERROR_STOP=1", "-v", f"database={database}", "-c", query], env=environment)
    _run(["dropdb", "-h", host, "-U", admin, "--if-exists", database], env=environment)
    _run(["createdb", "-h", host, "-U", admin, "-O", owner, database], env=environment)
    _run(["pg_restore", "-h", host, "-U", admin, "--role", owner, "--exit-on-error", "--no-owner", "--no-privileges", "-d", database, str(dump)], env=environment)


def restore(args: argparse.Namespace) -> int:
    if args.confirm != "RESTORE-PIGE360":
        raise OperationError("restore exige --confirm RESTORE-PIGE360")
    if os.getenv("PIGE360_RESTORE_MAINTENANCE", "") != "RESTORE-PIGE360":
        raise OperationError("restore exige PIGE360_RESTORE_MAINTENANCE=RESTORE-PIGE360")
    if _http_ok("http://pige360-api:8000/api/v1/health/live", host="console.platform.local", timeout=2):
        raise OperationError("API ainda está ativa; interrompa API, workers, beat e gateway antes do restore")
    name = _safe_archive_name(args.name)
    source = BACKUP_ROOT / name
    backup_manifest = _backup_module()
    manifest = backup_manifest.verify_manifest(source)
    fingerprint = hashlib.sha256(_read_secret("database_secret_key").encode()).hexdigest()
    if fingerprint != manifest["database_secret_key_sha256"]:
        raise OperationError("DATABASE_SECRET_KEY não corresponde ao backup")
    with _operation_lock("restore"):
        _reset_database("pige360-postgres-control", "pige360_control", "postgres_control_password", "platform_control", "pige360_control", source / "platform-control.dump")
        _run(["python", "-m", "alembic", "-c", "backend/alembic_control/alembic.ini", "upgrade", "head"])
        _run(["python", "-m", "app.shared.database.migrate_tenants", "--ensure-resources", "--skip-migrations"])
        rows = _tenant_catalog()
        expected_rows = (source / "tenants.tsv").read_text(encoding="utf-8").splitlines()
        if rows != expected_rows:
            raise OperationError("catálogo restaurado diverge do backup")
        for line in rows:
            _, _, _, database_name, database_user, _ = line.split("\t")
            _reset_database("pige360-postgres-tenants", "pige360_tenant_admin", "postgres_tenant_password", database_name, database_user, source / "tenant-databases" / f"{database_name}.dump")
        client = _s3_client()
        for bucket_name in (source / "buckets.txt").read_text(encoding="utf-8").splitlines():
            if not bucket_name:
                continue
            paginator = client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=bucket_name):
                objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
                if objects:
                    client.delete_objects(Bucket=bucket_name, Delete={"Objects": objects, "Quiet": True})
            bucket_root = source / "objects" / bucket_name
            for file in sorted(bucket_root.rglob("*")):
                if file.is_file():
                    client.upload_file(str(file), bucket_name, file.relative_to(bucket_root).as_posix())
        _assert_safe_directory(TENANT_STORAGE_ROOT)
        for item in TENANT_STORAGE_ROOT.iterdir():
            shutil.rmtree(item) if item.is_dir() and not item.is_symlink() else item.unlink()
        with tarfile.open(source / "tenant-storage.tar.gz", "r:gz") as archive:
            _safe_extract(archive, TENANT_STORAGE_ROOT)
        _run(["python", "-m", "app.shared.database.migrate_tenants"])
    print(json.dumps({"status": "completed", "restored": name}, ensure_ascii=False))
    return 0


def diagnostics(_: argparse.Namespace) -> int:
    checks = _runtime_checks()
    report = {
        "schema_version": 1,
        "status": "passed" if all(checks.values()) else "failed",
        "checked_at": _utc_now(),
        "environment": os.getenv("PIGE360_ENVIRONMENT"),
        "version": os.getenv("APP_VERSION"),
        "image_tag": os.getenv("PIGE360_IMAGE_TAG"),
        "checks": checks,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("init-secrets").set_defaults(handler=init_secrets)
    commands.add_parser("init-config").set_defaults(handler=init_config)
    commands.add_parser("init-data").set_defaults(handler=init_data)
    commands.add_parser("validate").set_defaults(handler=validate_config)
    commands.add_parser("migrate-control").set_defaults(handler=migrate_control)
    commands.add_parser("migrate-tenants").set_defaults(handler=migrate_tenants)
    secret = commands.add_parser("secret-set")
    secret.add_argument("name", choices=EXTERNAL_SECRETS)
    secret.set_defaults(handler=secret_set)
    ready = commands.add_parser("readiness")
    ready.add_argument("--attempts", type=int)
    ready.add_argument("--delay", type=int)
    ready.set_defaults(handler=readiness)
    bootstrap = commands.add_parser("bootstrap-admin")
    bootstrap.add_argument("--email", required=True)
    bootstrap.set_defaults(handler=bootstrap_admin)
    backup_command = commands.add_parser("backup")
    backup_command.add_argument("--name")
    backup_command.set_defaults(handler=backup)
    restore_command = commands.add_parser("restore")
    restore_command.add_argument("--name", required=True)
    restore_command.add_argument("--confirm", required=True)
    restore_command.set_defaults(handler=restore)
    commands.add_parser("diagnostics").set_defaults(handler=diagnostics)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except (OperationError, OSError, ValueError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
