from __future__ import annotations


def _create_person(client, headers, name: str, key: str):
    return client.post(
        "/api/v1/people",
        headers=headers(**{"Idempotency-Key": key}),
        json={"full_name": name},
    )


def test_relational_students_and_physical_databases_are_isolated(local_env):
    person = _create_person(local_env.client, local_env.alpha_headers, "Aluno Exclusivo Alpha", "alpha-person-0001")
    assert person.status_code == 201, person.text
    created = local_env.client.post(
        "/api/v1/students",
        headers=local_env.alpha_headers(),
        json={"person_id": person.json()["id"], "registration_number": "ALPHA-0001"},
    )
    assert created.status_code == 201, created.text
    record_id = created.json()["id"]

    alpha_list = local_env.client.get("/api/v1/students", headers=local_env.alpha_headers())
    beta_list = local_env.client.get("/api/v1/students", headers=local_env.beta_headers())
    assert [x["id"] for x in alpha_list.json()["items"]] == [record_id]
    assert beta_list.json()["items"] == []

    cross_read = local_env.client.get(f"/api/v1/students/{record_id}", headers=local_env.beta_headers())
    assert cross_read.status_code == 404

    alpha_db = local_env.root / "tenants" / local_env.alpha_tenant["id"] / "database" / "tenant.db"
    beta_db = local_env.root / "tenants" / local_env.beta_tenant["id"] / "database" / "tenant.db"
    assert alpha_db.is_file() and beta_db.is_file()
    assert alpha_db.resolve() != beta_db.resolve()


def test_idempotency_replays_same_person_request_and_rejects_key_reuse(local_env):
    headers = local_env.alpha_headers(**{"Idempotency-Key": "idem-people-0001"})
    body = {"full_name": "Pessoa Idempotente"}
    first = local_env.client.post("/api/v1/people", headers=headers, json=body)
    replay = local_env.client.post("/api/v1/people", headers=headers, json=body)
    conflict = local_env.client.post(
        "/api/v1/people",
        headers=headers,
        json={"full_name": "Conteúdo Diferente"},
    )
    assert first.status_code == 201, first.text
    assert replay.status_code == 201, replay.text
    assert replay.json()["id"] == first.json()["id"]
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"
