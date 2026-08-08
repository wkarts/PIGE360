import hashlib


def post(env,path,payload,*,expected=201,headers=None):
    response=env.client.post(path,headers=headers or env.alpha_headers(),json=payload)
    assert response.status_code==expected,f"{path}: {response.status_code} {response.text}"
    return response.json()


def test_government_layout_validation_import_export_and_transmission_queue(local_env):
    layout=post(local_env,"/api/v1/government-education/layouts",{
        "authority":"INEP","layout_code":"EDUCACENSO-MATRICULA","version":"2026.1","effective_from":"2026-01-01",
        "layout_schema":{"format":"csv","fields":[
            {"name":"student_code","required":True,"pattern":"^[A-Z0-9]{4,20}$","max_length":20},
            {"name":"enrollment_state","required":True,"enum":["ACTIVE","TRANSFERRED"]},
            {"name":"workload_hours","required":True,"type":"integer"}
        ]}
    })
    invalid=post(local_env,"/api/v1/government-education/validations",{
        "layout_id":layout["id"],"reference_period":"2026","direction":"export",
        "records":[{"student_code":"x","enrollment_state":"INVALID","workload_hours":"abc"}]
    })
    assert invalid["state"]=="invalid" and invalid["error_count"]==3
    issues=local_env.client.get(f"/api/v1/government-education/validations/{invalid['id']}/issues",headers=local_env.alpha_headers())
    assert issues.status_code==200 and {x["code"] for x in issues.json()["items"]}=={"PATTERN_MISMATCH","INVALID_ENUM","INVALID_INTEGER"}

    bad_content=b"student_code,enrollment_state,workload_hours\nABC1,INVALID,100\n"
    imported=local_env.client.post(
        "/api/v1/government-education/imports",
        params={"layout_id":layout["id"],"reference_period":"2026"},headers=local_env.alpha_headers(),
        files={"file":("educacenso-invalid.csv",bad_content,"text/csv")},
    )
    assert imported.status_code==201,imported.text
    imp=imported.json();assert imp["state"]=="rejected" and imp["rejected_count"]==1
    download=local_env.client.get(f"/api/v1/government-education/imports/{imp['id']}/download",headers=local_env.alpha_headers())
    assert download.status_code==200 and download.content==bad_content
    assert download.headers["X-Content-SHA256"]==hashlib.sha256(bad_content).hexdigest()

    export=post(local_env,"/api/v1/government-education/exports",{
        "layout_id":layout["id"],"reference_period":"2026",
        "records":[{"student_code":"ABC1","enrollment_state":"ACTIVE","workload_hours":800}]
    })
    assert export["state"]=="generated" and export["transmission"]=="not_configured"
    exports=local_env.client.get("/api/v1/government-education/exports",headers=local_env.alpha_headers())
    assert exports.status_code==200 and any(x["id"]==export["id"] for x in exports.json()["items"])
    exported=local_env.client.get(f"/api/v1/government-education/exports/{export['id']}/download",headers=local_env.alpha_headers())
    assert exported.status_code==200 and hashlib.sha256(exported.content).hexdigest()==export["sha256"]

    transmission=post(local_env,f"/api/v1/government-education/exports/{export['id']}/transmissions",{},headers={**local_env.alpha_headers(),"Idempotency-Key":"gov-export-2026-001"})
    assert transmission["state"]=="awaiting_configuration" and transmission["protocol"] is None
    replay=post(local_env,f"/api/v1/government-education/exports/{export['id']}/transmissions",{},headers={**local_env.alpha_headers(),"Idempotency-Key":"gov-export-2026-001"})
    assert replay["replayed"] is True and replay["id"]==transmission["id"]

    connection=post(local_env,"/api/v1/integration-connections",{
        "provider":"inep","name":"INEP Educacenso Homologação","environment":"homologation",
        "capabilities":["government_submission"],"secret_reference":"inep_homologation_credentials",
        "config":{"endpoint":"https://example.invalid/inep-homologation"}
    })
    assert connection["state"]=="configured"
    retry=post(local_env,f"/api/v1/government-education/transmissions/{transmission['id']}/retry",{"reason":"Credencial de homologação configurada"},expected=200)
    assert retry["state"]=="queued" and retry["connection_id"]==connection["id"] and retry["protocol"] is None
    transmissions=local_env.client.get("/api/v1/government-education/transmissions",headers=local_env.alpha_headers())
    assert transmissions.status_code==200
    row=next(x for x in transmissions.json()["items"] if x["id"]==transmission["id"])
    assert row["state"]=="queued" and row["protocol"] is None and row["attempts"]==1

    # Outro tenant não enxerga a fila nem os artifacts do Alpha.
    beta=local_env.client.get("/api/v1/government-education/transmissions",headers=local_env.beta_headers())
    assert beta.status_code==200 and not any(x["id"]==transmission["id"] for x in beta.json()["items"])


def test_government_transmission_worker_accepts_only_real_provider_protocol(local_env):
    from app.shared.events.dispatcher import event_envelope
    from app.worker import handle_event

    class FakeGovernmentTransport:
        def __init__(self): self.calls=[]
        def request_json(self,method,url,*,headers,body=None,timeout=20.0,retries=2):
            self.calls.append({"method":method,"url":url,"headers":headers,"body":body})
            if url.endswith("/submissions"):
                assert body["sha256"] and body["metadata"]["authority"]=="INEP"
                return 202,{"status":"accepted","protocol":"INEP-HML-2026-000001","submission_id":"sub-local-1","message":"Recebido em fixture local"}
            if url.endswith("/health"): return 200,{"status":"ok"}
            raise AssertionError(f"fixture ausente: {method} {url}")
        def request_bytes(self,*args,**kwargs): raise AssertionError("request_bytes não esperado")
        def request_form(self,*args,**kwargs): raise AssertionError("request_form não esperado")

    layout=post(local_env,"/api/v1/government-education/layouts",{
        "authority":"INEP","layout_code":"EDUCACENSO-ESCOLA","version":"2026.1","effective_from":"2026-01-01",
        "layout_schema":{"format":"csv","fields":[{"name":"school_code","required":True,"pattern":"^[0-9]{8}$"}]}
    })
    export=post(local_env,"/api/v1/government-education/exports",{
        "layout_id":layout["id"],"reference_period":"2026","records":[{"school_code":"12345678"}]
    })
    root=local_env.root/"integration-secrets";root.mkdir(parents=True,exist_ok=True);(root/"inep-worker-secret").write_text("fixture-provider-token",encoding="utf-8")
    connection=post(local_env,"/api/v1/integration-connections",{
        "provider":"inep","name":"INEP Worker Fixture","environment":"homologation","capabilities":["government_submission"],
        "secret_reference":"inep-worker-secret","config":{"base_url":"https://inep-fixture.example.edu.br","submission_path":"/submissions"}
    })
    transmission=post(local_env,f"/api/v1/government-education/exports/{export['id']}/transmissions",{"connection_id":connection["id"]},headers={**local_env.alpha_headers(),"Idempotency-Key":"gov-worker-fixture-001"})
    assert transmission["state"]=="queued" and transmission["protocol"] is None

    router=local_env.client.app.state.data_router;tid=local_env.alpha_tenant["id"];store=router.tenant_store(tid)
    row=store.fetch_one("SELECT * FROM outbox_events WHERE tenant_id=? AND event_type='GovernmentEducationTransmissionRequested' AND aggregate_id=? ORDER BY created_at DESC LIMIT 1",(tid,transmission["id"]))
    assert row
    secret="gov-worker-event-secret-"+"x"*64
    envelope=event_envelope(row,tenant_id=tid,secret=secret,plane="tenant")
    fake=FakeGovernmentTransport()
    consumed=handle_event(envelope,router=router,signing_secret=secret,transport=fake)
    assert consumed["status"]=="completed"
    result=store.fetch_one("SELECT state,protocol,attempts,provider_status FROM government_transmissions WHERE tenant_id=? AND id=?",(tid,transmission["id"]))
    assert result=={"state":"accepted","protocol":"INEP-HML-2026-000001","attempts":1,"provider_status":"accepted"}
    export_row=store.fetch_one("SELECT state,protocol FROM government_exports WHERE tenant_id=? AND id=?",(tid,export["id"]))
    assert export_row=={"state":"accepted","protocol":"INEP-HML-2026-000001"}
    assert fake.calls[0]["headers"]["Authorization"]=="Bearer fixture-provider-token"
    persisted=store.fetch_one("SELECT receipt_json,last_error FROM government_transmissions WHERE tenant_id=? AND id=?",(tid,transmission["id"]))
    events=store.fetch_all("SELECT details_json FROM government_transmission_events WHERE tenant_id=? AND transmission_id=?",(tid,transmission["id"]))
    outboxes=store.fetch_all("SELECT payload_json FROM outbox_events WHERE tenant_id=? AND aggregate_id=?",(tid,transmission["id"]))
    persisted_text=str(persisted)+str(events)+str(outboxes)
    assert "fixture-provider-token" not in persisted_text

    # Inbox impede uma segunda transmissão do mesmo evento ao provider.
    replay=handle_event(envelope,router=router,signing_secret=secret,transport=fake)
    assert replay["status"]=="duplicate" and len(fake.calls)==1
