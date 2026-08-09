#!/usr/bin/env python3
"""Regenera os manifests de infraestrutura a partir dos templates canônicos.

Este script deliberadamente não reescreve código Rust, Dockerfiles ou scripts de
runtime. Esses arquivos são fontes canônicas versionadas e uma regeneração de
Compose nunca deve substituí-los por scaffolding/descritores.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
TEMPLATES = ROOT / "infra" / "templates"


def render(template: str, target: str) -> None:
    source = TEMPLATES / template
    if not source.is_file():
        raise SystemExit(f"Template canônico ausente: {source.relative_to(ROOT)}")
    text = source.read_text(encoding="utf-8").replace("__PIGE360_VERSION__", VERSION)
    output = ROOT / target
    output.write_text(text, encoding="utf-8")
    yaml.safe_load(text)


def require(paths: list[str]) -> None:
    missing = [path for path in paths if not (ROOT / path).is_file()]
    if missing:
        raise SystemExit("Fontes de infraestrutura ausentes: " + ", ".join(missing))


def main() -> None:
    require([
        "infra/docker/Dockerfile.api",
        "infra/docker/Dockerfile.web",
        "infra/docker/Dockerfile.worker",
        "infra/docker/Dockerfile.migrations",
        "infra/docker/build-farm/Dockerfile.linux",
        "scripts/build-farm/agent.py",
        "infra/build-farm/builders.yaml",
        "infra/scripts/app-init.sh",
        "infra/scripts/init-minio.sh",
    ])
    render("compose.yaml.tmpl", "compose.yaml")
    render("compose.production.yaml.tmpl", "compose.production.yaml")
    compose: dict[str, Any] = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    forbidden = []
    for name, service in compose.get("services", {}).items():
        command = json.dumps(service.get("command", ""), ensure_ascii=False).lower()
        if "sleep infinity" in command:
            forbidden.append(name)
    if forbidden:
        raise SystemExit(f"Builders/serviços inertes detectados: {forbidden}")
    print(json.dumps({"status": "generated", "version": VERSION, "services": len(compose.get("services", {})), "forbidden_inert_services": forbidden}, ensure_ascii=False))


if __name__ == "__main__":
    main()
