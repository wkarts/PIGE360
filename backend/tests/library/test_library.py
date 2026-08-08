from __future__ import annotations
from datetime import UTC, datetime, timedelta


def post(env,path,payload,headers=None,expected=201):
    r=env.client.post(path,headers=headers or env.alpha_headers(),json=payload);assert r.status_code==expected,r.text;return r.json()

def person_user(env,name,cpf,email):
    p=post(env,"/api/v1/people",{"full_name":name,"cpf":cpf,"email":email},env.alpha_headers(**{"Idempotency-Key":f"lib-person-{cpf}"}))
    _,token=env.create_alpha_user(email,["guardian"],person_id=p["id"])
    return p,env.headers("admin.alpha.school.local",token)

def test_library_policy_reservation_loan_fine_and_queue(local_env):
    p1,h1=person_user(local_env,"Leitor Um","55555555555","reader1@alpha.example.com")
    p2,h2=person_user(local_env,"Leitor Dois","66666666666","reader2@alpha.example.com")
    policy=post(local_env,"/api/v1/library/policies",{"code":"default","effective_from":"2020-01-01","max_loan_days":7,"max_renewals":1,"grace_days":0,"daily_fine":"2.00","reservation_hold_hours":24})
    assert policy["version"]==1
    item=post(local_env,"/api/v1/library/items",{"inventory_code":"LIV-001","title":"Arquitetura Educacional","authors":"Equipe PIGE360","category":"Tecnologia"})
    ready=post(local_env,"/api/v1/library/reservations",{"library_item_id":item["id"]},h1)
    assert ready["state"]=="ready" and ready["expires_at"]
    assert local_env.client.get("/api/v1/library/reservations",headers=h2).json()["items"]==[]
    due=(datetime.now(UTC)-timedelta(days=2)).isoformat()
    loan=post(local_env,"/api/v1/library/loans",{"library_item_id":item["id"],"person_id":p1["id"],"due_at":due})
    assert loan["policy_version"]==1
    queued=post(local_env,"/api/v1/library/reservations",{"library_item_id":item["id"]},h2)
    assert queued["state"]=="queued"
    blocked=local_env.client.post(f"/api/v1/library/loans/{loan['id']}/renew",headers=h1,json={"reason":"Preciso de mais tempo"})
    assert blocked.status_code==409 and blocked.json()["code"]=="LOAN_RENEWAL_BLOCKED_BY_RESERVATION"
    returned=post(local_env,f"/api/v1/library/loans/{loan['id']}/return",{},expected=200)
    assert returned["state"]=="returned" and returned["fine_amount"]=="4.00" and returned["fine_id"]
    p1_fines=local_env.client.get("/api/v1/library/fines",headers=h1).json()["items"]
    assert len(p1_fines)==1 and p1_fines[0]["amount"]=="4.00"
    p2_res=local_env.client.get("/api/v1/library/reservations",headers=h2).json()["items"]
    assert p2_res[0]["state"]=="ready"
    loan2=post(local_env,"/api/v1/library/loans",{"library_item_id":item["id"],"person_id":p2["id"]})
    assert loan2["state"]=="open"
    events=local_env.client.app.state.data_router.tenant_store(local_env.alpha_tenant["id"]).fetch_all("SELECT event_type FROM library_loan_events WHERE tenant_id=? ORDER BY occurred_at",(local_env.alpha_tenant["id"],))
    assert [x["event_type"] for x in events]==["loaned","returned","loaned"]
