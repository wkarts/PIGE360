from __future__ import annotations


def _create_context(local_env, *, key: str = "fiscal-context-alpha-001") -> dict:
    response = local_env.client.post(
        "/api/v1/fiscal/contexts",
        headers=local_env.alpha_headers(**{"Idempotency-Key": key}),
        json={
            "code": "MATRIZ-BA",
            "establishment_name": "Colégio Alpha — Matriz",
            "legal_name": "Instituição Alpha Ltda.",
            "cnpj": "12.345.678/0001-95",
            "state_registration": "ISENTO",
            "municipal_registration": "MUN-ALPHA-001",
            "metadata": {"source": "test"},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_version(
    local_env,
    context_id: str,
    expected_context_version: int,
    *,
    valid_from: str,
    tax_regime: str = "simples_nacional",
    key: str,
) -> dict:
    response = local_env.client.post(
        f"/api/v1/fiscal/contexts/{context_id}/versions",
        headers=local_env.alpha_headers(**{"Idempotency-Key": key}),
        json={
            "tax_regime": tax_regime,
            "uf": "BA",
            "municipality_code": "2927408",
            "valid_from": valid_from,
            "environment": "homologation",
            "rtc_mode": "simulation_only",
            "layout_version": "NF-e-4.00",
            "schema_version": "PL_010_V120",
            "technical_note_version": "RTC-2026.001",
            "ruleset_version": f"BA-{valid_from}",
            "configuration": {"simple_national_2026": True},
            "notes": "Contexto fiscal versionado para teste local.",
            "scopes": [
                {
                    "operation_type": "sale",
                    "item_kind": "product",
                    "recipient_scope": "company",
                    "document_type": "NF-e",
                },
                {
                    "operation_type": "service_billing",
                    "item_kind": "service",
                    "recipient_scope": "individual",
                    "document_type": "NFS-e",
                },
            ],
            "expected_context_version": expected_context_version,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _publish(local_env, context_id: str, version: dict, expected_context_version: int, *, key: str) -> dict:
    response = local_env.client.post(
        f"/api/v1/fiscal/contexts/{context_id}/versions/{version['id']}/publish",
        headers=local_env.alpha_headers(**{"Idempotency-Key": key}),
        json={
            "expected_context_version": expected_context_version,
            "expected_version": version["version"],
            "reason": "Publicação aprovada para vigência fiscal controlada.",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_fiscal_context_is_versioned_resolved_and_snapshotted_in_document(local_env):
    context = _create_context(local_env)
    replay = _create_context(local_env)
    assert replay["id"] == context["id"]
    assert context["version"] == 1

    version = _create_version(
        local_env,
        context["id"],
        1,
        valid_from="2026-01-01",
        key="fiscal-context-version-alpha-001",
    )
    replay_version = _create_version(
        local_env,
        context["id"],
        1,
        valid_from="2026-01-01",
        key="fiscal-context-version-alpha-001",
    )
    assert replay_version["id"] == version["id"]
    assert version["version_number"] == 1
    assert version["status"] == "draft"
    assert len(version["scopes"]) == 2

    published = _publish(
        local_env,
        context["id"],
        version,
        2,
        key="fiscal-context-publish-alpha-001",
    )
    assert published["status"] == "published"
    assert published["active_version_id"] == version["id"]
    assert published["context_version"] == 3

    resolved = local_env.client.post(
        "/api/v1/fiscal/contexts/resolve",
        headers=local_env.alpha_headers(),
        json={
            "occurred_on": "2026-08-10",
            "operation_type": "sale",
            "item_kind": "product",
            "recipient_scope": "company",
            "document_type": "NF-e",
            "context_id": context["id"],
        },
    )
    assert resolved.status_code == 200, resolved.text
    snapshot = resolved.json()
    assert snapshot["context"]["cnpj"] == "12345678000195"
    assert snapshot["version"]["tax_regime"] == "simples_nacional"
    assert snapshot["scope"]["operation_type"] == "sale"
    assert len(snapshot["sha256"]) == 64

    profile = local_env.client.post(
        "/api/v1/fiscal/profiles",
        headers=local_env.alpha_headers(),
        json={
            "establishment_name": "Colégio Alpha — Matriz",
            "cnpj": "12345678000195",
            "tax_regime": "simples_nacional",
            "uf": "BA",
            "municipality_code": "2927408",
            "environment": "homologation",
        },
    )
    assert profile.status_code == 201, profile.text
    requested = local_env.client.post(
        "/api/v1/fiscal/documents",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "fiscal-context-document-001"}),
        json={
            "fiscal_profile_id": profile.json()["id"],
            "fiscal_context_version_id": version["id"],
            "source_type": "manual",
            "source_id": "fiscal-context-sale-001",
            "document_type": "NF-e",
            "totals": {"total": "150.00"},
            "payload": {"operation_type": "sale"},
        },
    )
    assert requested.status_code == 201, requested.text
    assert requested.json()["fiscal_context_id"] == context["id"]
    assert requested.json()["fiscal_context_version_id"] == version["id"]
    assert requested.json()["fiscal_context_sha256"]

    store = local_env.client.app.state.data_router.tenant_store(local_env.alpha_tenant["id"])
    document = store.fetch_one(
        "SELECT fiscal_context_id,fiscal_context_version_id,fiscal_context_snapshot_json "
        "FROM fiscal_documents WHERE tenant_id=? AND id=?",
        (local_env.alpha_tenant["id"], requested.json()["id"]),
    )
    assert document and document["fiscal_context_id"] == context["id"]
    assert version["id"] in document["fiscal_context_snapshot_json"]
    assert store.scalar(
        "SELECT COUNT(*) AS total FROM audit_log WHERE tenant_id=? AND aggregate_type='fiscal_context' AND aggregate_id=?",
        (local_env.alpha_tenant["id"], context["id"]),
    ) >= 2
    assert store.scalar(
        "SELECT COUNT(*) AS total FROM outbox_events WHERE tenant_id=? AND aggregate_id=? AND event_type='FiscalContextVersionPublished'",
        (local_env.alpha_tenant["id"], context["id"]),
    ) == 1


def test_fiscal_context_future_version_preserves_historical_resolution_and_rejects_overlap(local_env):
    context = _create_context(local_env, key="fiscal-context-alpha-history")
    first = _create_version(
        local_env,
        context["id"],
        1,
        valid_from="2026-01-01",
        key="fiscal-context-history-v1",
    )
    first_published = _publish(local_env, context["id"], first, 2, key="fiscal-context-history-pub-v1")
    assert first_published["context_version"] == 3

    second = _create_version(
        local_env,
        context["id"],
        3,
        valid_from="2027-01-01",
        tax_regime="lucro_presumido",
        key="fiscal-context-history-v2",
    )
    second_published = _publish(local_env, context["id"], second, 4, key="fiscal-context-history-pub-v2")
    assert second_published["status"] == "scheduled"
    assert first["id"] in second_published["superseded_versions"]
    assert second_published["active_version_id"] == first["id"]

    for occurred_on, expected_version in (("2026-12-31", first["id"]), ("2027-01-01", second["id"])):
        response = local_env.client.post(
            "/api/v1/fiscal/contexts/resolve",
            headers=local_env.alpha_headers(),
            json={
                "occurred_on": occurred_on,
                "operation_type": "sale",
                "item_kind": "product",
                "recipient_scope": "company",
                "document_type": "NF-e",
                "cnpj": "12345678000195",
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["version"]["id"] == expected_version

    third = _create_version(
        local_env,
        context["id"],
        5,
        valid_from="2026-06-01",
        key="fiscal-context-history-v3",
    )
    conflict = local_env.client.post(
        f"/api/v1/fiscal/contexts/{context['id']}/versions/{third['id']}/publish",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "fiscal-context-history-pub-v3"}),
        json={
            "expected_context_version": 6,
            "expected_version": 1,
            "reason": "Tentativa controlada de vigência conflitante.",
        },
    )
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["code"] == "FISCAL_CONTEXT_PERIOD_OVERLAP"


def test_fiscal_context_enforces_validation_authorization_and_cross_tenant_isolation(local_env):
    invalid = local_env.client.post(
        "/api/v1/fiscal/contexts",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "fiscal-invalid-cnpj"}),
        json={
            "code": "INVALID",
            "establishment_name": "CNPJ inválido",
            "cnpj": "11.111.111/1111-11",
        },
    )
    assert invalid.status_code == 422, invalid.text

    context = _create_context(local_env, key="fiscal-context-isolation")
    beta_detail = local_env.client.get(
        f"/api/v1/fiscal/contexts/{context['id']}",
        headers=local_env.beta_headers(),
    )
    assert beta_detail.status_code == 404
    beta_list = local_env.client.get("/api/v1/fiscal/contexts", headers=local_env.beta_headers())
    assert beta_list.status_code == 200
    assert all(item["id"] != context["id"] for item in beta_list.json()["items"])

    _, teacher_token = local_env.create_alpha_user("teacher-fiscal@alpha.example.com", ["teacher"])
    forbidden = local_env.client.get(
        "/api/v1/fiscal/contexts",
        headers=local_env.headers("admin.alpha.school.local", teacher_token),
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "PERMISSION_DENIED"
