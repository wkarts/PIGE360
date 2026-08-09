from __future__ import annotations


def post(env,path,payload,headers=None,expected=201):
    r=env.client.post(path,headers=headers or env.alpha_headers(),json=payload);assert r.status_code==expected,r.text;return r.json()


def person_user(env,name,cpf,email):
    p=post(env,"/api/v1/people",{"full_name":name,"cpf":cpf,"email":email},env.alpha_headers(**{"Idempotency-Key":f"person-{cpf}"}))
    _,token=env.create_alpha_user(email,["guardian"],person_id=p["id"])
    return p,env.headers("admin.alpha.school.local",token)


def test_notice_audience_version_read_ack_and_receipts(local_env):
    p1,h1=person_user(local_env,"Responsável Um","11111111111","notice-one@alpha.example.com")
    _,h2=person_user(local_env,"Responsável Dois","22222222222","notice-two@alpha.example.com")
    notice=post(local_env,"/api/v1/notices",{"title":"Reunião individual","body":"Compareça à secretaria.","priority":"high","audience":{"type":"targeted","person_ids":[p1["id"]]},"channels":["internal"],"requires_acknowledgement":True})
    assert notice["state"]=="published" and notice["version"]==1
    visible=local_env.client.get("/api/v1/notices",headers=h1);hidden=local_env.client.get("/api/v1/notices",headers=h2)
    assert [x["id"] for x in visible.json()["items"]]==[notice["id"]]
    assert hidden.json()["items"]==[]
    read=post(local_env,f"/api/v1/notices/{notice['id']}/read",{},h1,200);assert read["first_seen_at"]
    ack=post(local_env,f"/api/v1/notices/{notice['id']}/acknowledge",{},h1,200);assert ack["acknowledged_at"]
    receipts=local_env.client.get(f"/api/v1/notices/{notice['id']}/receipts",headers=local_env.alpha_headers());assert receipts.status_code==200 and receipts.json()["items"][0]["person_id"]==p1["id"]
    version=post(local_env,f"/api/v1/notices/{notice['id']}/versions",{"title":"Reunião reagendada","body":"Nova data será informada.","priority":"normal","audience":{"type":"targeted","person_ids":[p1["id"]]},"channels":["internal"],"requires_acknowledgement":True,"reason":"Alteração de agenda"})
    assert version["version"]==2 and version["state"]=="draft"
    assert local_env.client.get("/api/v1/notices",headers=h1).json()["items"]==[]
    pub=post(local_env,f"/api/v1/notices/{notice['id']}/publish",{"reason":"Nova versão aprovada"},expected=200);assert pub["state"]=="published"
    detail=local_env.client.get(f"/api/v1/notices/{notice['id']}",headers=h1);assert detail.status_code==200 and detail.json()["version"]==2 and len(detail.json()["versions"])==2


def test_request_type_versioned_form_history_comments_and_scope(local_env):
    person,headers=person_user(local_env,"Solicitante","33333333333","requester@alpha.example.com")
    kind=post(local_env,"/api/v1/request-types",{"code":"document.second-copy","name":"Segunda via de documento","department":"Secretaria","default_sla_hours":24,"form_schema":{"fields":[{"name":"document","type":"string","required":True},{"name":"contact_email","type":"email","required":True}]},"workflow":{}})
    post(local_env,f"/api/v1/request-types/{kind['id']}/publish",{"expected_version":1,"reason":"Fluxo aprovado"},expected=200)
    bad=local_env.client.post("/api/v1/service-requests",headers=headers,json={"request_type":"document.second-copy","subject":"Preciso do documento","form_data":{"document":"Histórico"}});assert bad.status_code==422 and bad.json()["code"]=="REQUEST_FORM_INVALID"
    req=post(local_env,"/api/v1/service-requests",{"request_type":"document.second-copy","subject":"Segunda via do histórico","priority":"normal","form_data":{"document":"Histórico escolar","contact_email":"requester@alpha.example.com"}},headers)
    assert req["request_type_version"]==1
    detail=local_env.client.get(f"/api/v1/service-requests/{req['id']}",headers=headers);assert detail.status_code==200 and detail.json()["form_data"]["document"]=="Histórico escolar" and detail.json()["events"][0]["event_type"]=="created"
    internal=post(local_env,f"/api/v1/service-requests/{req['id']}/comments",{"body":"Validar arquivo antes da emissão.","visibility":"internal"},expected=201)
    public=post(local_env,f"/api/v1/service-requests/{req['id']}/comments",{"body":"Recebemos sua solicitação.","visibility":"requester"},expected=201)
    requester_detail=local_env.client.get(f"/api/v1/service-requests/{req['id']}",headers=headers).json();assert [x["id"] for x in requester_detail["comments"]]==[public["id"]]
    transitioned=post(local_env,f"/api/v1/service-requests/{req['id']}/transition",{"state":"in_progress","reason":"Atendimento iniciado"},expected=200);assert transitioned["state"]=="in_progress"
    admin_detail=local_env.client.get(f"/api/v1/service-requests/{req['id']}",headers=local_env.alpha_headers()).json();assert len(admin_detail["comments"])==2 and admin_detail["events"][-1]["to_state"]=="in_progress"
    beta=local_env.client.get(f"/api/v1/service-requests/{req['id']}",headers=local_env.beta_headers());assert beta.status_code==404
