from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCANNER = ROOT / "scripts/validation/secret_scan.py"


def test_secret_scan_covers_release_source_and_reports_but_skips_delivery_output(
    tmp_path: Path,
) -> None:
    (tmp_path / "scripts/release").mkdir(parents=True)
    (tmp_path / "release/reports").mkdir(parents=True)
    (tmp_path / "release/output").mkdir(parents=True)
    token = "ghp_" + "A" * 36
    (tmp_path / "scripts/release/tool.py").write_text(f'TOKEN = "{token}"\n', encoding="utf-8")
    (tmp_path / "release/reports/run.log").write_text("normal log\n", encoding="utf-8")
    (tmp_path / "release/output/ignored.log").write_text(f"{token}\n", encoding="utf-8")

    process = subprocess.run(
        [sys.executable, str(SCANNER), "--root", str(tmp_path), "--project-version", "1.2.3"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert process.returncode == 1
    report = json.loads(process.stdout)
    assert report["version"] == "1.2.3"
    assert report["strict"] is False
    assert {item["path"] for item in report["findings"]} == {"scripts/release/tool.py"}
    assert {item["kind"] for item in report["findings"]} == {"github_token", "generic_password"}


def test_strict_scan_does_not_exempt_fixture_like_paths(tmp_path: Path) -> None:
    path = tmp_path / "tests/evidence.log"
    path.parent.mkdir(parents=True)
    path.write_text("password=12345678901234567890\n", encoding="utf-8")

    process = subprocess.run(
        [sys.executable, str(SCANNER), "--root", str(tmp_path), "--strict"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert process.returncode == 1
    report = json.loads(process.stdout)
    assert report["strict"] is True
    assert report["findings"][0]["path"] == "tests/evidence.log"


def test_generic_secret_rule_ignores_runtime_expression_but_catches_literal(
    tmp_path: Path,
) -> None:
    source = tmp_path / "service.py"
    source.write_text(
        'token = generate_agent_token()\nsecret = "12345678901234567890"\n',
        encoding="utf-8",
    )

    process = subprocess.run(
        [sys.executable, str(SCANNER), "--root", str(tmp_path)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert process.returncode == 1
    report = json.loads(process.stdout)
    assert report["findings"] == [
        {"path": "service.py", "line": 2, "kind": "generic_password"}
    ]
