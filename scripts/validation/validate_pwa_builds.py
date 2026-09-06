#!/usr/bin/env python3
"""Valida os treze artefatos PWA depois do build Vite."""

from __future__ import annotations

import json
import struct
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "release/reports/pwa-build-validation.json"


class HeadParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.references: list[str] = []
        self.theme: str | None = None
        self.manifest: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "script" and values.get("src"):
            self.references.append(values["src"] or "")
        if tag == "link" and values.get("href"):
            href = values["href"] or ""
            self.references.append(href)
            if values.get("rel") == "manifest":
                self.manifest = href
        if tag == "meta" and values.get("name") == "theme-color":
            self.theme = values.get("content")


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:24]
    if len(data) != 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise ValueError("assinatura PNG inválida")
    return struct.unpack(">II", data[16:24])


def validate_application(application: Path) -> dict[str, object]:
    errors: list[str] = []
    dist = application / "dist"
    index = dist / "index.html"
    manifest_path = dist / "manifest.webmanifest"
    worker_path = dist / "sw.js"
    required = (index, manifest_path, worker_path, dist / "icon-192.png", dist / "icon-512.png")
    for path in required:
        if not path.is_file():
            errors.append(f"arquivo ausente: {path.relative_to(application)}")
    if errors:
        return {"application": application.name, "status": "failed", "errors": errors}

    parser = HeadParser()
    parser.feed(index.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    worker = worker_path.read_text(encoding="utf-8")
    if parser.manifest != "./manifest.webmanifest":
        errors.append("link do manifesto não é relativo/canônico")
    if str(parser.theme or "").upper() != str(manifest.get("theme_color") or "").upper():
        errors.append("theme-color do HTML diverge do manifesto")
    for field in ("id", "start_url", "scope"):
        if manifest.get(field) != "./":
            errors.append(f"{field} precisa ser ./")
    for reference in parser.references:
        parsed = urlsplit(reference)
        if parsed.scheme or parsed.netloc or reference.startswith("/"):
            errors.append(f"referência não portável: {reference}")
            continue
        local = (dist / parsed.path).resolve()
        if not local.is_relative_to(dist.resolve()) or not local.is_file():
            errors.append(f"asset referenciado ausente: {reference}")
    for size in (192, 512):
        try:
            actual = png_size(dist / f"icon-{size}.png")
            if actual != (size, size):
                errors.append(f"icon-{size}.png tem dimensões {actual}")
        except ValueError as exc:
            errors.append(f"icon-{size}.png: {exc}")
    for fragment in (
        "CACHE_SCOPE_PREFIX",
        "key.startsWith(CACHE_SCOPE_PREFIX)",
        "html.matchAll",
        "self.registration.scope",
        "API_PATH",
    ):
        if fragment not in worker:
            errors.append(f"service worker sem {fragment}")
    if "assets/app.js" in worker or "assets/app.css" in worker:
        errors.append("service worker referencia assets inexistentes antigos")
    return {
        "application": application.name,
        "status": "passed" if not errors else "failed",
        "references": sorted(set(parser.references)),
        "errors": errors,
    }


def main() -> int:
    applications = sorted(path for path in (ROOT / "apps").iterdir() if path.is_dir())
    records = [validate_application(application) for application in applications]
    failed = [record for record in records if record["status"] != "passed"]
    report = {
        "schema_version": 1,
        "version": (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
        "status": "failed" if failed else "passed",
        "applications": len(records),
        "records": records,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {"status": report["status"], "applications": len(records), "failed": len(failed)},
            ensure_ascii=False,
        )
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
