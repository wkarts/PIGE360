from __future__ import annotations

import hashlib
import os
import stat
import subprocess
import tarfile
from pathlib import Path

import yaml

from scripts.backup.backup_manifest import create_manifest


ROOT = Path(__file__).resolve().parents[3]
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def _fake_docker(tmp_path: Path) -> tuple[Path, Path]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    log = tmp_path / "docker.log"
    docker = fake_bin / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        "printf '%s|tag=%s|api=%s|skip=%s|files=%s\\n' \"$*\" \"${PIGE360_IMAGE_TAG:-}\" \"${PIGE360_API_IMAGE:-}\" \"${PIGE360_SKIP_MIGRATIONS:-}\" \"${COMPOSE_FILE:-}\" >> \"$FAKE_DOCKER_LOG\"\n"
        "if [ -n \"${FAKE_DOCKER_FAIL_MATCH:-}\" ]; then case \"$*\" in *\"$FAKE_DOCKER_FAIL_MATCH\"*) exit 42 ;; esac; fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    return fake_bin, log


def _install_env(tmp_path: Path, fake_bin: Path, log: Path) -> dict[str, str]:
    env_file = tmp_path / ".env"
    # A tag declarada no env-file é autoritativa e independente de APP_VERSION.
    env_file.write_text(
        "PIGE360_IMAGE_REGISTRY=registry.example/pige\nPIGE360_IMAGE_TAG=0.1.0\nACME_EMAIL=infra@example.test\n",
        encoding="utf-8",
    )
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    (secrets / "cloudflare_api_token.txt").write_text("test-token-not-for-production\n", encoding="utf-8")
    return {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "FAKE_DOCKER_LOG": str(log),
        "PIGE360_ROOT": str(ROOT),
        "PIGE360_ENV_FILE": str(env_file),
        "PIGE360_SECRETS_DIR": str(secrets),
        "PIGE360_STATE_DIR": str(tmp_path / "state"),
    }


def test_clean_host_source_install_builds_complete_chain_and_uses_container_readiness(tmp_path: Path) -> None:
    fake_bin, log = _fake_docker(tmp_path)
    env = _install_env(tmp_path, fake_bin, log)

    result = subprocess.run(
        ["sh", str(ROOT / "deploy/self-hosted/install.sh"), "--mode", "source", "--target", "cloudpanel"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    calls = log.read_text(encoding="utf-8")
    assert calls.count("-f infra/docker/base/Dockerfile") == 2
    assert "PYTHON_BASE_IMAGE=pige360-base-python:0.1.0" in calls
    assert "API_IMAGE=pige360-api:0.1.0" in calls
    for app in ("tenant-admin-web", "platform-console", "branding-studio", "tenant-download-center"):
        assert f"APP_DIR=apps/{app}" in calls
    assert calls.count("--pull") == 2
    assert " exec -T pige360-api python -c" in calls
    assert "compose.cloudpanel.yaml" in calls
    assert "api=pige360-api:0.1.0" in calls
    assert not (tmp_path / "state/locks/deployment.lock").exists()


def test_registry_install_pulls_all_runtime_variants_and_propagates_skip_migrations(tmp_path: Path) -> None:
    fake_bin, log = _fake_docker(tmp_path)
    env = _install_env(tmp_path, fake_bin, log)

    result = subprocess.run(
        [
            "sh",
            str(ROOT / "deploy/self-hosted/install.sh"),
            "--mode",
            "registry",
            "--target",
            "dockge",
            "--skip-migrations",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    calls = log.read_text(encoding="utf-8")
    expected_images = {
        "pige360-migrations",
        "pige360-api",
        "pige360-worker",
        "pige360-web",
        "pige360-platform-console",
        "pige360-branding-studio",
        "pige360-tenant-download-center",
    }
    pulled_images = {
        line.split("|", 1)[0].removeprefix("pull registry.example/pige/").split(":", 1)[0]
        for line in calls.splitlines()
        if line.startswith("pull registry.example/pige/")
    }
    assert pulled_images == expected_images
    assert "api=registry.example/pige/pige360-api:0.1.0" in calls
    assert "skip=true" in calls
    assert "compose.edge.yaml" in calls
    assert not any(line.startswith("build ") for line in calls.splitlines())


def test_registry_pull_failure_never_starts_services(tmp_path: Path) -> None:
    fake_bin, log = _fake_docker(tmp_path)
    env = _install_env(tmp_path, fake_bin, log)
    env["FAKE_DOCKER_FAIL_MATCH"] = "pull registry.example/pige/"

    result = subprocess.run(
        ["sh", str(ROOT / "deploy/self-hosted/install.sh"), "--mode", "registry"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    calls = log.read_text(encoding="utf-8")
    assert not any(" up " in line for line in calls.splitlines())
    assert not (tmp_path / "state/locks/deployment.lock").exists()


def test_production_overlay_maps_every_core_first_party_service_to_explicit_image() -> None:
    base = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    production = yaml.safe_load((ROOT / "compose.production.yaml").read_text(encoding="utf-8"))
    expected = {
        name
        for name, service in base["services"].items()
        if (service.get("build") and not service.get("profiles") and not name.startswith("pige360-builder-"))
    }
    configured = {
        name
        for name, service in production["services"].items()
        if service.get("image") and service.get("pull_policy")
    }

    assert expected <= configured
    assert production["services"]["pige360-app-init"]["image"].startswith("${PIGE360_MIGRATIONS_IMAGE")


def _minimal_backup(root: Path, fingerprint: str) -> None:
    (root / "tenant-databases").mkdir(parents=True)
    (root / "objects" / "pige360-platform").mkdir(parents=True)
    (root / "objects" / "pige360-tenant-abc").mkdir(parents=True)
    (root / "platform-control.dump").write_bytes(b"control")
    tenant_file = root / "tenant-volume-record.txt"
    tenant_file.write_text("local storage", encoding="utf-8")
    with tarfile.open(root / "tenant-storage.tar.gz", "w:gz") as archive:
        archive.add(tenant_file, arcname="tenant-volume-record.txt")
    tenant_file.unlink()
    (root / "postgres-versions.txt").write_text(
        "control=pg_dump (PostgreSQL) 17.5\ntenants=pg_dump (PostgreSQL) 17.5\n",
        encoding="utf-8",
    )
    (root / "tenant-databases/pige360_t_abc.dump").write_bytes(b"tenant")
    (root / "tenants.tsv").write_text(
        "018f0000-0000-7000-8000-000000000001\tschool\tactive\tpige360_t_abc\tpige360_u_abc\tpige360-tenant-abc\n",
        encoding="utf-8",
    )
    (root / "buckets.txt").write_text("pige360-platform\npige360-tenant-abc\n", encoding="utf-8")
    create_manifest(
        root,
        version="1.0.0",
        target="base",
        image_mode="source",
        database_key_fingerprint=fingerprint,
    )


def test_restore_rejects_wrong_database_key_before_any_docker_command(tmp_path: Path) -> None:
    fake_bin, log = _fake_docker(tmp_path)
    env = _install_env(tmp_path, fake_bin, log)
    secrets = Path(env["PIGE360_SECRETS_DIR"])
    secrets.mkdir(exist_ok=True)
    key = b"current-database-key"
    (secrets / "database_secret_key.txt").write_bytes(key)
    backup = tmp_path / "backup"
    _minimal_backup(backup, "0" * 64)

    result = subprocess.run(
        ["sh", str(ROOT / "deploy/self-hosted/restore.sh"), str(backup), "--confirm", "RESTORE-PIGE360"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "nenhuma operação destrutiva" in result.stderr
    assert hashlib.sha256(key).hexdigest() != "0" * 64
    assert not log.exists() or not log.read_text(encoding="utf-8")


def test_remote_deploy_has_no_phantom_service_or_host_port_probe() -> None:
    script = (ROOT / "scripts/deploy/deploy-saas-ssh.sh").read_text(encoding="utf-8")

    assert "pige360-migrations" not in script
    assert "127.0.0.1:8000" not in script
    assert "SAAS_IMAGE_MODE inválido" in script
    assert "SAAS_DEPLOY_TARGET inválido" in script
    assert "PIGE360_CURRENT_ROOT" in script


def test_secret_bootstrap_is_complete_idempotent_and_restrictive(tmp_path: Path) -> None:
    secrets = tmp_path / "secrets"
    command = ["sh", str(ROOT / "scripts/local/init-secrets.sh"), str(secrets)]
    first = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    assert first.returncode == 0, first.stderr
    expected = {
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
        "database_secret_key",
        "minio_access_key",
        "cloudflare_control_tunnel_token",
        "cloudflare_tenant_tunnel_token",
        "cloudflare_api_token",
        "connect_api_key",
    }
    before = {path.stem: path.read_bytes() for path in secrets.glob("*.txt")}
    assert set(before) == expected
    assert stat.S_IMODE(secrets.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o444 for path in secrets.glob("*.txt"))

    second = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    assert second.returncode == 0, second.stderr
    after = {path.stem: path.read_bytes() for path in secrets.glob("*.txt")}
    assert after == before


def _minimal_release(root: Path, version: str, install_body: str, backup_body: str = "#!/bin/sh\nmkdir -p \"$1\"\n") -> None:
    (root / "deploy/self-hosted").mkdir(parents=True)
    (root / "scripts/local").mkdir(parents=True)
    (root / "scripts/backup").mkdir(parents=True)
    (root / "infra/docker").mkdir(parents=True)
    (root / "backend/app/shared/database").mkdir(parents=True)
    (root / "VERSION").write_text(version + "\n", encoding="utf-8")
    (root / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    (root / "compose.production.yaml").write_text("services: {}\n", encoding="utf-8")
    (root / "deploy/self-hosted/lib.sh").write_text(
        (ROOT / "deploy/self-hosted/lib.sh").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (root / "deploy/self-hosted/install.sh").write_text(install_body, encoding="utf-8")
    (root / "deploy/self-hosted/build-images.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (root / "deploy/self-hosted/healthcheck.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (root / "deploy/self-hosted/backup.sh").write_text(backup_body, encoding="utf-8")
    (root / "deploy/self-hosted/restore.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (root / "deploy/self-hosted/rollback.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (root / "scripts/local/init-secrets.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (root / "scripts/backup/backup_manifest.py").write_text("# test fixture\n", encoding="utf-8")
    for name in ("Dockerfile.api", "Dockerfile.migrations", "Dockerfile.worker", "Dockerfile.web"):
        (root / "infra/docker" / name).write_text("FROM scratch\n", encoding="utf-8")
    (root / "backend/app/shared/database/migrate_tenants.py").write_text("# test fixture\n", encoding="utf-8")


def test_update_uses_candidate_tag_then_atomically_records_and_switches_pointer(tmp_path: Path) -> None:
    current = tmp_path / "releases/1.0.0"
    candidate = tmp_path / "releases/1.0.1"
    state = tmp_path / "state"
    env_file = tmp_path / ".env"
    secrets = tmp_path / "secrets"
    tag_log = tmp_path / "tag.log"
    env_file.write_text("PIGE360_IMAGE_TAG=0.1.0\n", encoding="utf-8")
    secrets.mkdir()
    install = f'#!/bin/sh\nprintf "%s|%s\\n" "$PIGE360_IMAGE_TAG" "$APP_VERSION" > "{tag_log}"\n'
    _minimal_release(current, "1.0.0", "#!/bin/sh\nexit 0\n")
    _minimal_release(candidate, "1.0.1", install)
    current_link = tmp_path / "current"
    current_link.symlink_to(current)
    env = {
        **os.environ,
        "PIGE360_CURRENT_ROOT": str(current),
        "PIGE360_CURRENT_LINK": str(current_link),
        "PIGE360_STATE_DIR": str(state),
        "PIGE360_ENV_FILE": str(env_file),
        "PIGE360_SECRETS_DIR": str(secrets),
    }

    result = subprocess.run(
        ["sh", str(ROOT / "deploy/self-hosted/update.sh"), str(candidate)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert tag_log.read_text(encoding="utf-8").strip() == "1.0.1|1.0.1"
    assert current_link.resolve() == candidate.resolve()
    records = list((state / "history").glob("update-*.json"))
    assert len(records) == 1
    assert '"status": "completed"' in records[0].read_text(encoding="utf-8")


def test_update_failure_keeps_pointer_and_pending_recovery_state(tmp_path: Path) -> None:
    current = tmp_path / "releases/1.0.0"
    candidate = tmp_path / "releases/1.0.1"
    state = tmp_path / "state"
    env_file = tmp_path / ".env"
    secrets = tmp_path / "secrets"
    env_file.write_text("PIGE360_IMAGE_TAG=0.1.0\n", encoding="utf-8")
    secrets.mkdir()
    _minimal_release(current, "1.0.0", "#!/bin/sh\nexit 0\n")
    _minimal_release(candidate, "1.0.1", "#!/bin/sh\nexit 42\n")
    current_link = tmp_path / "current"
    current_link.symlink_to(current)
    env = {
        **os.environ,
        "PIGE360_CURRENT_ROOT": str(current),
        "PIGE360_CURRENT_LINK": str(current_link),
        "PIGE360_STATE_DIR": str(state),
        "PIGE360_ENV_FILE": str(env_file),
        "PIGE360_SECRETS_DIR": str(secrets),
    }

    result = subprocess.run(
        ["sh", str(ROOT / "deploy/self-hosted/update.sh"), str(candidate)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert current_link.resolve() == current.resolve()
    assert not list((state / "history").glob("update-*.json"))
    pending = list(state.glob("pending-*.json"))
    assert len(pending) == 1
    assert '"status": "pending"' in pending[0].read_text(encoding="utf-8")
