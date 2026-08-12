from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from typing import Any

from app.shared.events.dispatcher import event_envelope
from app.worker import handle_event

SIGNING_SECRET = "fiscal-lifecycle-secret-" + "z" * 64


class FiscalLifecycleTransport:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.issue_count = 0

    def request_json(self, method: str, url: str, *, headers: dict[str, str], body: Any | None = None, timeout: float = 20.0, retries: int = 2):
        self.calls.append({"method": method, "url": url, "body": body})
        if method == "POST" and url.endswith("/v1/fiscal/documents"):
            self.issue_count += 1
            xml = f'<nfeProc><protNFe>ISSUE-{self.issue_count}</protNFe></nfeProc>'.encode()
            pdf = b"%PDF-1.4\nfixture danfe\n%%EOF"
            return 201, {
                "state":"authorized","id":f"provider-doc-{self.issue_count:03d}","event_id":f"provider-issue-{self.issue_count:03d}",
                "access_key":f"2926081234567800012355001000000{self.issue_count:03d}1000001234","protocol":f"1292600000000{self.issue_count:02d}",
                "number":str(100+self.issue_count),"series":"1","xml_base64":base64.b64encode(xml).decode(),"pdf_base64":base64.b64encode(pdf).decode(),
            }
        if method == "GET" and "/v1/fiscal/documents/provider-doc-" in url:
            return 200, {"state":"authorized","id":url.rsplit("/",1)[-1],"protocol":"129260000000001","access_key":"29260812345678000123550010000001011000001234"}
        if method == "POST" and url.endswith("/events"):
            xml=b"<procEventoNFe><retEvento>135</retEvento></procEventoNFe>"
            return 200,{"state":"authorized","id":"provider-event-cc-001","protocol":"135260000000001","xml_base64":base64.b64encode(xml).decode()}
        if method == "POST" and url.endswith("/substitute"):
            xml=b"<nfeProc><protNFe>SUBSTITUTE-001</protNFe></nfeProc>"
            pdf=b"%PDF-1.4\nreplacement\n%%EOF"
            return 201,{"state":"authorized","id":"provider-doc-sub-001","event_id":"provider-sub-001","access_key":"29260812345678000123550010000002011000001234","protocol":"129260000000020","number":"102","series":"1","xml_base64":base64.b64encode(xml).decode(),"pdf_base64":base64.b64encode(pdf).decode()}
        if method == "POST" and url.endswith("/v1/fiscal/inutilizations"):
            return 200,{"state":"authorized","id":"provider-inut-001","protocol":"129260000000099"}
        if method == "POST" and url.endswith("/cancel"):
            return 200,{"state":"cancelled","id":url.split("/")[-2],"event_id":"provider-cancel-001"}
        if method == "GET" and url.endswith("/health"):
            return 200,{"status":"ok"}
        raise AssertionError(f"fixture não implementada: {method} {url}")

    def request_form(self, method: str, url: str, *, headers: dict[str, str], form: dict[str, str], timeout: float = 20.0, retries: int = 0):
        raise AssertionError("form não esperado")

    def request_bytes(self, method: str, url: str, *, headers: dict[str, str], timeout: float = 30.0, retries: int = 2):
        raise AssertionError("bytes não esperado")


def _secret(local_env, name: str, value: str = "secret-fixture") -> None:
    root=local_env.root/"integration-secrets";root.mkdir(parents=True,exist_ok=True);(root/name).write_text(value)


def _event(local_env, aggregate_id: str, event_type: str) -> dict[str, Any]:
    tid=local_env.alpha_tenant["id"];store=local_env.client.app.state.data_router.tenant_store(tid)
    row=store.fetch_one("SELECT * FROM outbox_events WHERE tenant_id=? AND aggregate_id=? AND event_type=? ORDER BY created_at DESC LIMIT 1",(tid,aggregate_id,event_type))
    assert row,(aggregate_id,event_type)
    return event_envelope(row,tenant_id=tid,secret=SIGNING_SECRET,plane="tenant")


def _configured_provider(local_env):
    _secret(local_env,"fiscal-api-token");_secret(local_env,"fiscal-a1-pfx","fixture-pfx-not-real")
    now=datetime.now(UTC)
    cert=local_env.client.post(
        "/api/v1/fiscal/certificates",
        headers=local_env.alpha_headers(**{"Idempotency-Key":"certificate-a1-fixture-001"}),
        json={"certificate_type":"a1","subject_name":"Colégio Alpha","subject_document":"12345678000123","serial_number":"SERIAL-FIXTURE-001","issuer_name":"AC Fixture","valid_from":(now-timedelta(days=1)).isoformat(),"valid_until":(now+timedelta(days=365)).isoformat(),"fingerprint_sha256":"a"*64,"secret_ref":"fiscal-a1-pfx","metadata":{"fixture":True}},
    )
    assert cert.status_code==201,cert.text
    provider=local_env.client.post(
        "/api/v1/fiscal/providers",
        headers=local_env.alpha_headers(**{"Idempotency-Key":"provider-nfe-fixture-001"}),
        json={"provider_code":"SefazNfeProvider","display_name":"SEFAZ NF-e fixture","document_type":"NF-e","environment":"homologation","endpoint_url":"https://fiscal.fixture.invalid","secret_ref":"fiscal-api-token","certificate_metadata_id":cert.json()["id"],"capabilities":["issue","query","cancel","substitute","inutilize","event","health"],"enabled":True},
    )
    assert provider.status_code==201,provider.text
    assert provider.json()["status"]=="configured"
    health=local_env.client.post(f"/api/v1/fiscal/providers/{provider.json()['id']}/health",headers=local_env.alpha_headers())
    assert health.status_code==200 and health.json()["health"]=="configured_unchecked" and health.json()["remote_check_executed"] is False
    return provider.json()


def _profile(local_env, provider_id: str):
    response=local_env.client.post("/api/v1/fiscal/profiles",headers=local_env.alpha_headers(),json={"establishment_name":"Colégio Alpha","cnpj":"12345678000123","tax_regime":"simples_nacional","uf":"BA","environment":"homologation","provider_connection_id":provider_id})
    assert response.status_code==201,response.text
    return response.json()


def test_document_lifecycle_issue_query_event_substitute_and_inutilize(local_env):
    provider=_configured_provider(local_env);profile=_profile(local_env,provider["id"]);transport=FiscalLifecycleTransport();router=local_env.client.app.state.data_router
    requested=local_env.client.post("/api/v1/fiscal/documents",headers=local_env.alpha_headers(**{"Idempotency-Key":"lifecycle-document-001"}),json={"fiscal_profile_id":profile["id"],"source_type":"manual","source_id":"order-lifecycle-001","document_type":"NF-e","totals":{"total":"150.00"},"payload":{"operation":"sale"},"contingency_mode":"offline"})
    assert requested.status_code==201,requested.text;document_id=requested.json()["id"]
    issued=handle_event(_event(local_env,document_id,"FiscalDocumentRequested"),router=router,signing_secret=SIGNING_SECRET,transport=transport)
    assert issued["status"]=="completed" and issued["result"]["domain"]["state"]=="authorized" and issued["result"]["domain"]["xml_sha256"]
    detail=local_env.client.get(f"/api/v1/fiscal/documents/{document_id}",headers=local_env.alpha_headers())
    assert detail.status_code==200,detail.text
    body=detail.json();assert body["state"]=="authorized" and body["contingency_mode"]=="offline";assert any(a["operation"]=="issue" and a["state"]=="completed" for a in body["attempts"]);assert {a["artifact_type"] for a in body["artifacts"]}>={"authorized_xml","danfe"}
    for artifact in body["artifacts"]:
        content=router.object_storage(local_env.alpha_tenant["id"]).get_bytes(artifact["storage_key"]);import hashlib;assert hashlib.sha256(content).hexdigest()==artifact["sha256"]

    queued=local_env.client.post(f"/api/v1/fiscal/documents/{document_id}/query",headers=local_env.alpha_headers(),json={"reason":"Conferência após autorização."})
    assert queued.status_code==200 and queued.json()["provider_status"]=="queued"
    queried=handle_event(_event(local_env,document_id,"FiscalDocumentQueryRequested"),router=router,signing_secret=SIGNING_SECRET,transport=transport)
    assert queried["status"]=="completed" and queried["result"]["domain"]["state"]=="authorized"

    event_req=local_env.client.post(f"/api/v1/fiscal/documents/{document_id}/events",headers=local_env.alpha_headers(**{"Idempotency-Key":"cc-event-001"}),json={"event_type":"correction_letter","payload":{"text":"Correção fixture sem alteração de valores."},"reason":"Correção de informação textual."})
    assert event_req.status_code==201,event_req.text
    event_done=handle_event(_event(local_env,document_id,"FiscalDocumentProviderEventRequested"),router=router,signing_secret=SIGNING_SECRET,transport=transport)
    assert event_done["status"]=="completed" and event_done["result"]["domain"]["state"]=="authorized" and event_done["result"]["domain"]["protocol"]=="135260000000001"

    substitute=local_env.client.post(f"/api/v1/fiscal/documents/{document_id}/substitute",headers=local_env.alpha_headers(**{"Idempotency-Key":"substitution-001"}),json={"source_type":"manual","source_id":"order-lifecycle-001-sub","totals":{"total":"150.00"},"payload":{"operation":"sale","replacement":True},"reason":"Substituição controlada da fixture."})
    assert substitute.status_code==201,substitute.text;replacement_id=substitute.json()["id"]
    substituted=handle_event(_event(local_env,replacement_id,"FiscalDocumentSubstitutionRequested"),router=router,signing_secret=SIGNING_SECRET,transport=transport)
    assert substituted["status"]=="completed" and substituted["result"]["domain"]["state"]=="authorized"
    store=router.tenant_store(local_env.alpha_tenant["id"]);original=store.fetch_one("SELECT state,substituted_by_document_id FROM fiscal_documents WHERE tenant_id=? AND id=?",(local_env.alpha_tenant["id"],document_id));assert original=={"state":"substituted","substituted_by_document_id":replacement_id}

    inutilization=local_env.client.post("/api/v1/fiscal/inutilizations",headers=local_env.alpha_headers(**{"Idempotency-Key":"inutilization-001"}),json={"fiscal_profile_id":profile["id"],"provider_configuration_id":provider["id"],"document_type":"NF-e","year":2026,"series":"1","start_number":200,"end_number":205,"reason":"Faixa não utilizada durante teste de homologação local."})
    assert inutilization.status_code==201,inutilization.text;inut_id=inutilization.json()["id"]
    inut_done=handle_event(_event(local_env,inut_id,"FiscalInutilizationRequested"),router=router,signing_secret=SIGNING_SECRET,transport=transport)
    assert inut_done["status"]=="completed" and inut_done["result"]["domain"]["state"]=="authorized" and inut_done["result"]["domain"]["protocol"]=="129260000000099"
    beta=local_env.client.get(f"/api/v1/fiscal/documents/{replacement_id}",headers=local_env.beta_headers());assert beta.status_code==404


def test_provider_without_secrets_is_not_configured_and_never_executes_remote(local_env):
    provider=local_env.client.post("/api/v1/fiscal/providers",headers=local_env.alpha_headers(**{"Idempotency-Key":"provider-nfse-unconfigured-001"}),json={"provider_code":"NationalNfseProvider","display_name":"NFS-e nacional sem segredo","document_type":"NFS-e","environment":"homologation","endpoint_url":"https://nfse.fixture.invalid","secret_ref":"missing-secret","capabilities":["issue","query","cancel"],"enabled":True})
    assert provider.status_code==201,provider.text
    assert provider.json()["status"]=="not_configured"
    health=local_env.client.post(f"/api/v1/fiscal/providers/{provider.json()['id']}/health",headers=local_env.alpha_headers())
    assert health.status_code==200 and health.json()["health"]=="not_configured" and health.json()["remote_check_executed"] is False
