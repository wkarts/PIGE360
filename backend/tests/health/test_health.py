from __future__ import annotations
from datetime import UTC, datetime, timedelta


def post(env,path,payload,headers=None,expected=201,extra=None):
    h=headers or env.alpha_headers()
    if extra:h={**h,**extra}
    r=env.client.post(path,headers=h,json=payload);assert r.status_code==expected,r.text;return r.json()

def person(env,name,cpf,email):
    return post(env,"/api/v1/people",{"full_name":name,"cpf":cpf,"email":email},env.alpha_headers(**{"Idempotency-Key":f"health-{cpf}"}))

def test_health_incident_medication_and_family_privacy(local_env):
    student_person=person(local_env,"Aluno Saúde","10101010101","health.student@alpha.example.com")
    student=post(local_env,"/api/v1/students",{"person_id":student_person["id"],"registration_number":"HL-001"})
    guardian_person=person(local_env,"Responsável Saúde","20202020202","health.guardian@alpha.example.com")
    guardian=post(local_env,"/api/v1/guardians",{"person_id":guardian_person["id"]})
    post(local_env,"/api/v1/guardian-students",{"guardian_id":guardian["id"],"student_id":student["id"],"relationship":"father","is_legal":True,"is_financial":True,"pickup_authorized":True})
    _,gtoken=local_env.create_alpha_user("health.guardian@alpha.example.com",["guardian"],person_id=guardian_person["id"]);gheaders=local_env.headers("admin.alpha.school.local",gtoken)
    outsider=person(local_env,"Responsável Sem Vínculo","30303030303","health.out@alpha.example.com")
    _,otoken=local_env.create_alpha_user("health.out@alpha.example.com",["guardian"],person_id=outsider["id"]);oheaders=local_env.headers("admin.alpha.school.local",otoken)

    record=post(local_env,"/api/v1/health/records",{"person_id":student_person["id"],"record_type":"allergy","summary":"Alergia a amendoim","details":{"severity":"high"},"sensitivity":"restricted"})
    secret=post(local_env,"/api/v1/health/records",{"person_id":student_person["id"],"record_type":"clinical-note","summary":"Nota clínica restrita","details":{"private":"conteúdo clínico"},"sensitivity":"highly_restricted"})
    incident=post(local_env,"/api/v1/health/incidents",{"person_id":student_person["id"],"incident_type":"minor_injury","occurred_at":datetime.now(UTC).isoformat(),"location":"Pátio","summary":"Escoriação leve","first_aid":{"cleaned":True},"guardian_notified":False})
    today=datetime.now(UTC).date();auth=post(local_env,"/api/v1/health/medication-authorizations",{"person_id":student_person["id"],"medication_name":"Medicamento teste","dosage":"5 ml","instructions":"Administrar após almoço","starts_on":str(today-timedelta(days=1)),"ends_on":str(today+timedelta(days=5)),"guardian_person_id":guardian_person["id"]})
    admin=post(local_env,"/api/v1/health/medication-administrations",{"authorization_id":auth["id"],"administered_at":datetime.now(UTC).isoformat(),"notes":"Sem intercorrências"},extra={"Idempotency-Key":"med-admin-001"})
    replay=post(local_env,"/api/v1/health/medication-administrations",{"authorization_id":auth["id"],"administered_at":admin["administered_at"],"notes":"Sem intercorrências"},extra={"Idempotency-Key":"med-admin-001"})
    assert replay==admin

    family=local_env.client.get("/api/v1/health/me",headers=gheaders);assert family.status_code==200
    data=family.json();assert any(x["id"]==record["id"] for x in data["records"]);assert all(x["id"]!=secret["id"] for x in data["records"]);assert data["incidents"][0]["id"]==incident["id"];assert data["medications"][0]["id"]==auth["id"]
    out=local_env.client.get("/api/v1/health/me",headers=oheaders).json();assert all(x["person_id"]!=student_person["id"] for x in out["records"])
    access=post(local_env,f"/api/v1/health/records/{secret['id']}/access",{"reason":"Atendimento clínico autorizado"},expected=200);assert access["details"]["private"]=="conteúdo clínico"
    logs=local_env.client.get(f"/api/v1/health/access-log?record_id={secret['id']}",headers=local_env.alpha_headers());assert logs.status_code==200 and len(logs.json()["items"])==1
    closed=post(local_env,f"/api/v1/health/incidents/{incident['id']}/close",{"reason":"Aluno liberado sem novas queixas"},expected=200);assert closed["state"]=="closed"
