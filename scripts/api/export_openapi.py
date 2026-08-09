#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("APP_ENV", "testing")

from app.bootstrap.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


def main() -> None:
    settings = Settings().testing(ROOT / "release" / ".openapi-runtime")
    schema = create_app(settings).openapi()
    target = ROOT / "docs" / "api"
    target.mkdir(parents=True, exist_ok=True)
    (target / "openapi.json").write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (target / "openapi.yaml").write_text(yaml.safe_dump(schema, allow_unicode=True, sort_keys=False), encoding="utf-8")
    operations = []
    for path, path_item in schema["paths"].items():
        for method, operation in path_item.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            operations.append({
                "operationId": operation["operationId"],
                "method": method.upper(),
                "path": path,
                "tags": operation.get("tags", []),
                "summary": operation.get("summary", ""),
            })
    operation_ids = [x["operationId"] for x in operations]
    report = {
        "openapi": schema.get("openapi"),
        "title": schema["info"]["title"],
        "version": schema["info"]["version"],
        "paths": len(schema["paths"]),
        "operations": len(operations),
        "schemas": len(schema.get("components", {}).get("schemas", {})),
        "duplicate_operation_ids": sorted({x for x in operation_ids if operation_ids.count(x) > 1}),
        "operations_catalog": operations,
    }
    (target / "OPENAPI_REPORT.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if report["duplicate_operation_ids"]:
        raise SystemExit("operationId duplicado")
    print(json.dumps({k: report[k] for k in ["paths", "operations", "schemas", "duplicate_operation_ids"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
