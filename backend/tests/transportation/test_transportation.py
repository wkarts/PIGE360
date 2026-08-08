from __future__ import annotations
from datetime import UTC, datetime


def post(env,path,payload,headers=None,expected=201,extra=None):
    h=headers or env.alpha_headers()
    if extra:h={**h,**extra}
    r=env.client.post(path,headers=h,json=payload);assert r.status_code==expected,r.text;return r.json()

def person(env,name,cpf,email):
    return post(env,"/api/v1/people",{"full_name":name,"cpf":cpf,"email":email},env.alpha_headers(**{"Idempotency-Key":f"transport-{cpf}"}))

def test_transport_schedule_events_occurrence_and_family_scope(local_env):
    student_person=person(local_env,"Aluno Transporte","77777777777","student.transport@alpha.example.com")
    student=post(local_env,"/api/v1/students",{"person_id":student_person["id"],"registration_number":"TR-001"})
    guardian_person=person(local_env,"Responsável Transporte","88888888888","guardian.transport@alpha.example.com")
    guardian=post(local_env,"/api/v1/guardians",{"person_id":guardian_person["id"]})
    post(local_env,"/api/v1/guardian-students",{"guardian_id":guardian["id"],"student_id":student["id"],"relationship":"mother","is_legal":True,"is_financial":False,"pickup_authorized":True})
    _,gtoken=local_env.create_alpha_user("guardian.transport@alpha.example.com",["guardian"],person_id=guardian_person["id"]);gheaders=local_env.headers("admin.alpha.school.local",gtoken)
    outsider_person=person(local_env,"Responsável Externo","99999999999","guardian.outsider@alpha.example.com")
    _,otoken=local_env.create_alpha_user("guardian.outsider@alpha.example.com",["guardian"],person_id=outsider_person["id"]);oheaders=local_env.headers("admin.alpha.school.local",otoken)

    route=post(local_env,"/api/v1/transport/routes",{"code":"R-01","name":"Rota Centro","vehicle":"Van 12","stops":[{"name":"Praça Central"},{"name":"Escola"}]})
    schedule=post(local_env,"/api/v1/transport/schedules",{"route_id":route["id"],"weekdays":[0,1,2,3,4],"outbound_time":"06:30:00","return_time":"17:30:00","valid_from":"2026-01-01"})
    assert schedule["state"]=="active"
    rider=post(local_env,"/api/v1/transport/riders",{"route_id":route["id"],"student_id":student["id"],"boarding_stop":"Praça Central","dropoff_stop":"Praça Central"})
    now=datetime.now(UTC).isoformat()
    event_payload={"route_id":route["id"],"rider_id":rider["id"],"event_type":"boarded","stop_name":"Praça Central","occurred_at":now,"device_id":"bus-device-01","location":{}}
    ev=post(local_env,"/api/v1/transport/events",event_payload,extra={"Idempotency-Key":"transport-board-001"})
    replay=post(local_env,"/api/v1/transport/events",event_payload,extra={"Idempotency-Key":"transport-board-001"})
    assert replay==ev
    visible=local_env.client.get(f"/api/v1/transport/students/{student['id']}/events",headers=gheaders)
    assert visible.status_code==200 and visible.json()["items"][0]["event_type"]=="boarded"
    hidden=local_env.client.get(f"/api/v1/transport/students/{student['id']}/events",headers=oheaders)
    assert hidden.status_code==404
    own_riders=local_env.client.get("/api/v1/transport/riders",headers=gheaders).json()["items"]
    assert len(own_riders)==1 and own_riders[0]["student_id"]==student["id"]
    own_schedules=local_env.client.get("/api/v1/transport/schedules",headers=gheaders)
    assert own_schedules.status_code==200 and {x["id"] for x in own_schedules.json()["items"]}=={schedule["id"]}
    outsider_schedules=local_env.client.get("/api/v1/transport/schedules",headers=oheaders)
    assert outsider_schedules.status_code==200 and outsider_schedules.json()["items"]==[]
    forbidden_route=local_env.client.get(f"/api/v1/transport/schedules?route_id={route['id']}",headers=oheaders)
    assert forbidden_route.status_code==404
    occurrence=post(local_env,"/api/v1/transport/occurrences",{"route_id":route["id"],"student_id":student["id"],"occurrence_type":"delay","description":"Atraso por trânsito intenso","severity":"normal"})
    resolved=post(local_env,f"/api/v1/transport/occurrences/{occurrence['id']}/resolve",{"resolution":"Responsáveis comunicados e rota normalizada"},expected=200)
    assert resolved["state"]=="resolved"
