from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_every_frontend_uses_the_audited_echarts_release() -> None:
    applications = sorted(path for path in (ROOT / "apps").iterdir() if path.is_dir())
    assert len(applications) == 13
    for application in applications:
        package = json.loads((application / "package.json").read_text(encoding="utf-8"))
        assert package["dependencies"]["echarts"] == "6.1.0", application.name

    lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))
    for application in applications:
        key = application.relative_to(ROOT).as_posix()
        assert lock["packages"][key]["dependencies"]["echarts"] == "6.1.0", key
    assert lock["packages"]["node_modules/echarts"]["version"] == "6.1.0"


def test_web_container_build_is_lockfile_first() -> None:
    dockerfile = (ROOT / "infra/docker/Dockerfile.web").read_text(encoding="utf-8")
    assert "ARG NPM_INSTALL_MODE=ci" in dockerfile
    assert "test -s package-lock.json && npm ci" in dockerfile


def test_vue_javascript_mirrors_are_not_ignored() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "*.vue.js" not in gitignore
    assert "apps/*/src/main.js" not in gitignore
