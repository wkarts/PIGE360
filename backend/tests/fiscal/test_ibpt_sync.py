from __future__ import annotations

from typing import Any

from app.shared.events.dispatcher import event_envelope
from app.worker import handle_event

SIGNING_SECRET = "ibpt-event-secret-" + "x" * 64


class IbptFakeTransport:
    def __init__(self, state_rate: str = "20,50") -> None:
        self.state_rate = state_rate
        self.calls: list[dict[str, Any]] = []

    def request_bytes(self, method: str, url: str, *, headers: dict[str, str], timeout: float = 30.0, retries: int = 2):
        self.calls.append({"method": method, "url": url, "headers": dict(headers)})
        csv_text = (
            "codigo;ex;tipo;descricao;nacionalfederal;importadosfederal;estadual;municipal;vigenciainicio;vigenciafim;versao;fonte\n"
            f"01012100;;0;Cavalos reprodutores;13,45;16,00;{self.state_rate};0,00;01/01/2026;31/12/2026;26.1.A;IBPT\n"
            "49019900;;0;Livros;4,20;7,10;0,00;0,00;01/01/2026;31/12/2026;26.1.A;IBPT\n"
        )
        return 200, csv_text.encode("utf-8")


def _event(local_env, run_id: str) -> dict:
    router = local_env.client.app.state.data_router
    tenant_id = local_env.alpha_tenant["id"]
    store = router.tenant_store(tenant_id)
    row = store.fetch_one(
        "SELECT * FROM outbox_events WHERE tenant_id=? AND aggregate_id=? AND event_type='IbptSyncRequested' ORDER BY created_at DESC LIMIT 1",
        (tenant_id, run_id),
    )
    assert row
    return event_envelope(row, tenant_id=tenant_id, secret=SIGNING_SECRET, plane="tenant")


def _queue(local_env, uf: str = "BA") -> dict:
    response = local_env.client.post(
        "/api/v1/fiscal/ibpt/sync",
        headers=local_env.alpha_headers(),
        json={"ufs": [uf]},
    )
    assert response.status_code == 202, response.text
    assert response.json()["state"] == "queued"
    return response.json()["runs"][0]


def test_ibpt_sync_publishes_hashed_snapshot_lookup_and_diff(local_env):
    router = local_env.client.app.state.data_router
    tenant_id = local_env.alpha_tenant["id"]
    store = router.tenant_store(tenant_id)
    fake = IbptFakeTransport()

    first_run = _queue(local_env)
    first = handle_event(_event(local_env, first_run["id"]), router=router, signing_secret=SIGNING_SECRET, transport=fake)
    assert first["status"] == "completed"
    first_result = first["result"]["domain"]
    assert first_result["state"] == "completed"
    assert first_result["rows"] == 2
    assert first_result["diff"] == {"added": 2, "removed": 0, "changed": 0}
    assert len(first_result["sha256"]) == 64
    assert fake.calls[-1]["url"] == "https://ibpt.wwsoftwares.com.br/tabela/ibpt/ba"

    snapshot = store.fetch_one("SELECT * FROM ibpt_snapshots WHERE tenant_id=? AND id=?", (tenant_id, first_result["snapshot_id"]))
    assert snapshot and snapshot["state"] == "active" and snapshot["source_version"] == "26.1.A"
    raw = router.object_storage(tenant_id).get_bytes(snapshot["storage_key"])
    assert b"01012100" in raw

    rate = local_env.client.get("/api/v1/fiscal/ibpt/rates/01012100?uf=BA", headers=local_env.alpha_headers())
    assert rate.status_code == 200, rate.text
    data = rate.json()
    assert str(data["national_federal"]) == "13.45"
    assert str(data["state_rate"]) == "20.5"
    assert data["purpose"] == "transparencia_vtottrib"
    assert data["tax_calculation_source"] is False

    second_run = _queue(local_env)
    second = handle_event(_event(local_env, second_run["id"]), router=router, signing_secret=SIGNING_SECRET, transport=fake)
    assert second["result"]["domain"]["state"] == "unchanged"
    assert second["result"]["domain"]["snapshot_id"] == first_result["snapshot_id"]
    assert store.scalar("SELECT COUNT(*) AS total FROM ibpt_snapshots WHERE tenant_id=? AND uf='BA'", (tenant_id,)) == 1

    fake.state_rate = "21,00"
    third_run = _queue(local_env)
    third = handle_event(_event(local_env, third_run["id"]), router=router, signing_secret=SIGNING_SECRET, transport=fake)
    third_result = third["result"]["domain"]
    assert third_result["state"] == "completed"
    assert third_result["diff"] == {"added": 0, "removed": 0, "changed": 1}
    snapshots = store.fetch_all("SELECT id,state FROM ibpt_snapshots WHERE tenant_id=? AND uf='BA' ORDER BY created_at", (tenant_id,))
    assert len(snapshots) == 2
    assert {row["state"] for row in snapshots} == {"active", "superseded"}


def test_ibpt_manual_all_ufs_queues_27_without_remote_access(local_env):
    response = local_env.client.post("/api/v1/fiscal/ibpt/sync", headers=local_env.alpha_headers(), json={})
    assert response.status_code == 202, response.text
    runs = response.json()["runs"]
    assert len(runs) == 27
    assert len({run["uf"] for run in runs}) == 27
    assert all(run["state"] == "queued" for run in runs)

    status = local_env.client.get("/api/v1/fiscal/ibpt/status", headers=local_env.alpha_headers())
    assert status.status_code == 200, status.text
    assert status.json()["all_ufs_ready"] is False
    assert len(status.json()["missing_ufs"]) == 27
