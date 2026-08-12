from __future__ import annotations

import base64
from datetime import date, timedelta


def _headers(env, key: str | None = None):
    return env.alpha_headers(**({"Idempotency-Key": key} if key else {}))


def _create_catalog(env, kind: str, name: str, normalization: str = "upper_alnum") -> dict:
    response = env.client.post(
        "/api/v1/fiscal/catalogs",
        headers=_headers(env, f"catalog-{kind.lower()}-0001"),
        json={"kind": kind, "name": name, "normalization": normalization, "metadata": {}},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_source(env, catalog_id: str, *, key: str, fmt: str, mapping: dict | None = None, schema: dict | None = None) -> dict:
    response = env.client.post(
        f"/api/v1/fiscal/catalogs/{catalog_id}/sources",
        headers=_headers(env, f"source-{key}-0001"),
        json={
            "provider_type": "local_file",
            "provider_key": key,
            "provider_version": "1",
            "import_format": fmt,
            "encoding": "utf-8",
            "delimiter": ";",
            "max_age_days": 90,
            "mapping": mapping or {},
            "schema": schema or {},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _import(env, catalog_id: str, source_id: str, filename: str, raw: bytes, version_label: str, valid_from: date, *, key: str, auto_publish: bool = False):
    return env.client.post(
        f"/api/v1/fiscal/catalogs/{catalog_id}/imports",
        headers=_headers(env, key),
        json={
            "source_profile_id": source_id,
            "filename": filename,
            "content_base64": base64.b64encode(raw).decode(),
            "version_label": version_label,
            "valid_from": valid_from.isoformat(),
            "schema_version": "1",
            "auto_publish": auto_publish,
        },
    )


def test_csv_import_diff_atomic_publish_rollback_and_tenant_isolation(local_env):
    catalog = _create_catalog(local_env, "NCM", "NCM oficial", "digits")
    source = _create_source(
        local_env,
        catalog["id"],
        key="ncm-csv-v1",
        fmt="csv",
        mapping={"code": "codigo", "description": "descricao"},
        schema={"required_fields": ["codigo", "descricao"], "min_entries": 1},
    )
    first_date = date.today() - timedelta(days=30)
    first = _import(
        local_env, catalog["id"], source["id"], "ncm-1.csv",
        b"codigo;descricao\n01012100;Cavalos reprodutores\n01012900;Outros cavalos\n",
        "2026.1", first_date, key="import-ncm-0001",
    )
    assert first.status_code == 201, first.text
    first_run = first.json()
    assert first_run["status"] == "draft_created"
    assert first_run["entries_count"] == 2
    assert first_run["diff"]["added_count"] == 2
    storage = local_env.client.app.state.data_router.object_storage(local_env.alpha_tenant["id"])
    assert storage.exists(first_run["storage_key"])

    publish = local_env.client.post(
        f"/api/v1/fiscal/catalog-imports/{first_run['id']}/publish",
        headers=_headers(local_env, "publish-ncm-0001"),
        json={"expected_version": 1, "reason": "Publicação inicial revisada."},
    )
    assert publish.status_code == 200, publish.text
    assert publish.json()["status"] == "published"

    second = _import(
        local_env, catalog["id"], source["id"], "ncm-2.csv",
        b"codigo;descricao\n01012100;Cavalos reprodutores puros\n01013000;Asininos\n",
        "2026.2", date.today(), key="import-ncm-0002",
    )
    assert second.status_code == 201, second.text
    diff = second.json()["diff"]
    assert diff["added_count"] == 1
    assert diff["removed_count"] == 1
    assert diff["changed_count"] == 1
    publish2 = local_env.client.post(
        f"/api/v1/fiscal/catalog-imports/{second.json()['id']}/publish",
        headers=_headers(local_env, "publish-ncm-0002"),
        json={"expected_version": 1, "reason": "Nova vigência oficial revisada."},
    )
    assert publish2.status_code == 200, publish2.text
    detail = local_env.client.get(f"/api/v1/fiscal/catalogs/{catalog['id']}", headers=local_env.alpha_headers())
    assert detail.status_code == 200
    active_id = detail.json()["active_version_id"]
    assert active_id == second.json()["catalog_version_id"]

    rollback = local_env.client.post(
        f"/api/v1/fiscal/catalogs/{catalog['id']}/versions/{first_run['catalog_version_id']}/rollback",
        headers=_headers(local_env, "rollback-ncm-0001"),
        json={"effective_from": date.today().isoformat(), "reason": "Rollback técnico auditado."},
    )
    assert rollback.status_code == 201, rollback.text
    rollback_version = rollback.json()["rollback_version"]
    assert rollback_version["id"] not in {first_run["catalog_version_id"], second.json()["catalog_version_id"]}
    assert rollback_version["state"] == "published"

    foreign = local_env.client.get(
        f"/api/v1/fiscal/catalog-imports/{first_run['id']}", headers=local_env.beta_headers()
    )
    assert foreign.status_code == 404


def test_json_and_xsd_importers_support_new_governed_catalog_kinds(local_env):
    credit = _create_catalog(local_env, "CREDITO_PRESUMIDO", "Crédito presumido")
    source_json = _create_source(
        local_env, credit["id"], key="credit-json-v1", fmt="json",
        mapping={"code": "codigo", "description": "descricao", "metadata_fields": ["percentual"]},
        schema={"root_path": "items", "required_fields": ["codigo", "descricao"]},
    )
    response = _import(
        local_env, credit["id"], source_json["id"], "credito.json",
        b'{"items":[{"codigo":"CP01","descricao":"Credito presumido fixture","percentual":"10"}]}',
        "fixture-json", date.today(), key="import-credit-0001", auto_publish=True,
    )
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "published"

    rtc = _create_catalog(local_env, "RTC_TABLE", "Tabela RTC")
    source_xsd = _create_source(local_env, rtc["id"], key="rtc-xsd-v1", fmt="xsd", schema={"min_entries": 2})
    xsd = b'''<?xml version="1.0" encoding="UTF-8"?>
    <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
      <xs:simpleType name="RtcCode"><xs:restriction base="xs:string">
        <xs:enumeration value="RTC01"><xs:annotation><xs:documentation>Regra RTC 01</xs:documentation></xs:annotation></xs:enumeration>
        <xs:enumeration value="RTC02"/>
      </xs:restriction></xs:simpleType>
    </xs:schema>'''
    response = _import(
        local_env, rtc["id"], source_xsd["id"], "rtc.xsd", xsd,
        "fixture-xsd", date.today(), key="import-rtc-0001", auto_publish=True,
    )
    assert response.status_code == 201, response.text
    assert response.json()["entries_count"] == 2
    resolved = local_env.client.get(
        f"/api/v1/fiscal/catalogs/{rtc['id']}/resolve/RTC01", headers=local_env.alpha_headers()
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["entry"]["description"] == "Regra RTC 01"


def test_invalid_import_is_quarantined_without_replacing_active_version(local_env):
    catalog = _create_catalog(local_env, "CEST", "CEST oficial", "digits")
    source = _create_source(
        local_env, catalog["id"], key="cest-csv-v1", fmt="csv",
        mapping={"code": "codigo", "description": "descricao"},
        schema={"required_fields": ["codigo", "descricao"]},
    )
    valid = _import(
        local_env, catalog["id"], source["id"], "cest.csv",
        b"codigo;descricao\n0100100;CEST fixture\n", "v1", date.today(), key="import-cest-good", auto_publish=True,
    )
    assert valid.status_code == 201, valid.text
    active_before = local_env.client.get(f"/api/v1/fiscal/catalogs/{catalog['id']}", headers=local_env.alpha_headers()).json()["active_version_id"]

    bad = _import(
        local_env, catalog["id"], source["id"], "cest-bad.csv",
        b"codigo;outra_coluna\n0200200;sem descricao\n", "bad", date.today(), key="import-cest-bad",
    )
    assert bad.status_code == 422, bad.text
    payload = bad.json()
    assert payload["status"] == "quarantined"
    assert payload["quarantine_id"]
    active_after = local_env.client.get(f"/api/v1/fiscal/catalogs/{catalog['id']}", headers=local_env.alpha_headers()).json()["active_version_id"]
    assert active_after == active_before

    quarantine = local_env.client.get("/api/v1/fiscal/catalog-quarantine", headers=local_env.alpha_headers())
    assert quarantine.status_code == 200
    assert any(row["id"] == payload["quarantine_id"] for row in quarantine.json()["items"])
    health = local_env.client.get("/api/v1/fiscal/catalog-governance/health", headers=local_env.alpha_headers())
    assert health.status_code == 200
    cest = next(row for row in health.json()["catalogs"] if row["kind"] == "CEST")
    assert "quarantine_open" in cest["reasons"]

    resolved = local_env.client.post(
        f"/api/v1/fiscal/catalog-quarantine/{payload['quarantine_id']}/resolve",
        headers=local_env.alpha_headers(),
        json={"action": "discarded", "reason": "Arquivo inválido descartado após análise."},
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "discarded"


def test_external_provider_profile_is_explicitly_not_configured(local_env):
    catalog = _create_catalog(local_env, "NBS", "NBS oficial")
    response = local_env.client.post(
        f"/api/v1/fiscal/catalogs/{catalog['id']}/sources",
        headers=_headers(local_env, "source-nbs-http-0001"),
        json={
            "provider_type": "external_http",
            "provider_key": "nbs-official-http",
            "provider_version": "1",
            "import_format": "json",
            "source_reference": None,
            "mapping": {},
            "schema": {},
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "not_configured"
    health = local_env.client.get("/api/v1/fiscal/catalog-governance/health", headers=local_env.alpha_headers()).json()
    nbs = next(row for row in health["catalogs"] if row["kind"] == "NBS")
    assert "source_not_configured" in nbs["reasons"]
