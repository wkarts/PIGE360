from __future__ import annotations

import stat
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "local" / "init-secrets.sh"


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_runtime_secrets_are_non_root_readable_but_host_directory_is_private(tmp_path: Path) -> None:
    secret_root = tmp_path / "runtime-secrets"

    subprocess.run(["sh", str(SCRIPT), str(secret_root)], check=True, capture_output=True, text=True)

    assert _mode(secret_root) == 0o700
    files = sorted(secret_root.glob("*.txt"))
    assert len(files) == 16
    assert all(path.is_file() and not path.is_symlink() for path in files)
    assert {_mode(path) for path in files} == {0o444}

    preserved = (secret_root / "app_jwt_secret.txt").read_bytes()
    subprocess.run(["sh", str(SCRIPT), str(secret_root)], check=True, capture_output=True, text=True)
    assert (secret_root / "app_jwt_secret.txt").read_bytes() == preserved


def test_runtime_secret_initializer_refuses_symlink_targets(tmp_path: Path) -> None:
    secret_root = tmp_path / "runtime-secrets"
    secret_root.mkdir(mode=0o700)
    outside = tmp_path / "outside.txt"
    outside.write_text("must-not-change\n", encoding="utf-8")
    (secret_root / "app_jwt_secret.txt").symlink_to(outside)

    result = subprocess.run(
        ["sh", str(SCRIPT), str(secret_root)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "link simbólico" in result.stderr
    assert outside.read_text(encoding="utf-8") == "must-not-change\n"


def test_runtime_secret_initializer_refuses_symlink_root(tmp_path: Path) -> None:
    actual = tmp_path / "actual"
    actual.mkdir()
    linked = tmp_path / "runtime-secrets"
    linked.symlink_to(actual, target_is_directory=True)

    result = subprocess.run(
        ["sh", str(SCRIPT), str(linked)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "não pode ser um link simbólico" in result.stderr
    assert list(actual.iterdir()) == []
