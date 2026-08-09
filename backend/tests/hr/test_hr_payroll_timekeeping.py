from __future__ import annotations
from datetime import UTC, datetime


def post(env,path,payload,headers=None,expected=201):
    r=env.client.post(path,headers=headers or env.alpha_headers(),json=payload);assert r.status_code==expected,r.text;return r.json()


def test_employment_payroll_and_timekeeping_sequence(local_env):
    person=post(local_env,"/api/v1/people",{"full_name":"Maria Colaboradora","cpf":"91919191919","email":"maria.hr@alpha.example.com"},local_env.alpha_headers(**{"Idempotency-Key":"hr-person-maria"}))
    employee=post(local_env,"/api/v1/employees",{"person_id":person["id"],"employee_number":"EMP-001","position":"Professora","department":"Pedagógico"})
    _,token=local_env.create_alpha_user("maria.hr@alpha.example.com",["employee"],person_id=person["id"])
    h=local_env.headers("admin.alpha.school.local",token)
    bad=local_env.client.post("/api/v1/timekeeping/me/entries",headers={**h,"Idempotency-Key":"clock-bad-001"},json={"event_type":"clock_out","origin":"app"})
    assert bad.status_code==409 and bad.json()["code"]=="TIMEKEEPING_INVALID_SEQUENCE"
    when=datetime(2026,8,8,11,0,tzinfo=UTC)
    events=[("clock_in",when.replace(hour=8)),("break_out",when.replace(hour=12)),("break_in",when.replace(hour=13)),("clock_out",when.replace(hour=17))]
    for idx,(event_type,dt) in enumerate(events):
        out=post(local_env,"/api/v1/timekeeping/me/entries",{"event_type":event_type,"occurred_at":dt.isoformat(),"origin":"app","device_id":"device-hr"},{**h,"Idempotency-Key":f"clock-{idx:03d}"})
        assert out["event_type"]==event_type
    duplicate=local_env.client.post("/api/v1/timekeeping/me/entries",headers={**h,"Idempotency-Key":"clock-003"},json={"event_type":"clock_out","occurred_at":events[-1][1].isoformat(),"origin":"app","device_id":"device-hr"})
    assert duplicate.status_code==201 and duplicate.json()["event_type"]=="clock_out"
    contract=post(local_env,"/api/v1/hr/employment-contracts",{"employee_id":employee["id"],"contract_type":"clt","starts_on":"2026-01-01","salary":"5000.00","weekly_hours":"40"})
    assert contract["state"]=="active"
    rule=post(local_env,"/api/v1/payroll/rules",{"code":"BONUS","name":"Gratificação","direction":"earning","calculation_type":"percentage","basis":"salary","value":"10","effective_from":"2026-01-01","priority":10})
    assert rule["version"]==1
    run=post(local_env,"/api/v1/payroll/runs",{"competence":"2026-08","run_type":"monthly"})
    assert run["employees"]==1 and run["gross_total"]=="5500.00" and run["net_total"]=="5500.00"
    entries=local_env.client.get(f"/api/v1/payroll/runs/{run['id']}/entries",headers=local_env.alpha_headers()).json()["items"]
    assert entries[0]["employee_id"]==employee["id"] and any(x["code"]=="BONUS" for x in entries[0]["items"])


def test_personnel_leave_timekeeping_adjustment_payroll_and_vacation_lifecycle(local_env):
    person=post(local_env,"/api/v1/people",{"full_name":"João Operacional","cpf":"81818181818","email":"joao.dp@alpha.example.com"},local_env.alpha_headers(**{"Idempotency-Key":"dp-person-joao"}))
    employee=post(local_env,"/api/v1/employees",{"person_id":person["id"],"employee_number":"EMP-002","position":"Assistente","department":"Administrativo"})
    _,token=local_env.create_alpha_user("joao.dp@alpha.example.com",["employee"],person_id=person["id"])
    own_headers=local_env.headers("admin.alpha.school.local",token)
    contract=post(local_env,"/api/v1/hr/employment-contracts",{"employee_id":employee["id"],"contract_type":"clt","starts_on":"2026-01-01","salary":"3000.00","weekly_hours":"40"})
    assert contract["state"]=="active"

    benefit=post(local_env,"/api/v1/personnel/benefits",{"employee_id":employee["id"],"benefit_type":"meal_voucher","provider":"Benefício Local","amount":"600.00","starts_on":"2026-01-01"})
    assert benefit["state"]=="active"

    leave=post(local_env,"/api/v1/personnel/leaves",{"leave_type":"unpaid_personal","starts_on":"2026-08-11","ends_on":"2026-08-12","reason":"Licença particular autorizável","deduct_payroll":True,"deduct_timekeeping":True},own_headers)
    assert leave["state"]=="submitted"
    approved=local_env.client.post(f"/api/v1/personnel/leaves/{leave['id']}/approve",headers=local_env.alpha_headers(),json={"expected_version":1,"reason":"Documentação conferida"})
    assert approved.status_code==200,approved.text
    assert approved.json()["state"]=="approved"

    in_entry=post(local_env,"/api/v1/timekeeping/me/entries",{"event_type":"clock_in","occurred_at":"2026-08-10T08:00:00+00:00","origin":"app","device_id":"device-dp"},{**own_headers,"Idempotency-Key":"dp-clock-in-001"})
    out_entry=post(local_env,"/api/v1/timekeeping/me/entries",{"event_type":"clock_out","occurred_at":"2026-08-10T17:00:00+00:00","origin":"app","device_id":"device-dp"},{**own_headers,"Idempotency-Key":"dp-clock-out-001"})
    assert in_entry["state"]==out_entry["state"]=="valid"

    adjustment=post(local_env,"/api/v1/timekeeping/adjustments",{"time_entry_id":out_entry["id"],"requested_event_type":"clock_out","requested_occurred_at":"2026-08-10T16:30:00+00:00","reason":"Saída correta conforme registro do terminal"},own_headers)
    reviewed=local_env.client.post(f"/api/v1/timekeeping/adjustments/{adjustment['id']}/approve",headers=local_env.alpha_headers(),json={"expected_version":1,"reason":"Conferido com registro do terminal"})
    assert reviewed.status_code==200,reviewed.text
    assert reviewed.json()["replacement_entry_id"]
    old=local_env.client.app.state.data_router.tenant_store(local_env.alpha_tenant["id"]).fetch_one("SELECT state FROM time_entries WHERE tenant_id=? AND id=?",(local_env.alpha_tenant["id"],out_entry["id"]))
    assert old["state"]=="superseded"

    summary=local_env.client.get(f"/api/v1/timekeeping/summary?employee_id={employee['id']}&date_from=2026-08-10&date_to=2026-08-10",headers=local_env.alpha_headers())
    assert summary.status_code==200,summary.text
    assert summary.json()["worked_minutes"]==510

    closed=local_env.client.post("/api/v1/timekeeping/closures/close",headers=local_env.alpha_headers(),json={"competence":"2026-08","reason":"Fechamento mensal do ponto"})
    assert closed.status_code==200,closed.text
    blocked=local_env.client.post("/api/v1/timekeeping/me/entries",headers={**own_headers,"Idempotency-Key":"dp-clock-closed-001"},json={"event_type":"clock_in","occurred_at":"2026-08-13T08:00:00+00:00","origin":"app"})
    assert blocked.status_code==409 and blocked.json()["code"]=="TIMEKEEPING_PERIOD_CLOSED"
    reopened=local_env.client.post("/api/v1/timekeeping/closures/2026-08/reopen",headers=local_env.alpha_headers(),json={"competence":"2026-08","reason":"Ajuste autorizado antes da folha"})
    assert reopened.status_code==200,reopened.text

    run=post(local_env,"/api/v1/payroll/runs",{"competence":"2026-08","run_type":"monthly"})
    assert run["employees"]==1
    assert run["gross_total"]=="3000.00"
    assert run["deductions_total"]=="200.00"
    assert run["net_total"]=="2800.00"
    payslip=local_env.client.get(f"/api/v1/payroll/runs/{run['id']}/payslips/{employee['id']}",headers=own_headers)
    assert payslip.status_code==200,payslip.text
    assert any(item["code"]=="UNPAID_LEAVE" and item["days"]==2 for item in payslip.json()["payslip"]["items"])
    payroll_closed=local_env.client.post(f"/api/v1/payroll/runs/{run['id']}/close",headers=local_env.alpha_headers(),json={"expected_version":1,"reason":"Folha conferida"})
    assert payroll_closed.status_code==200,payroll_closed.text
    payroll_reopened=local_env.client.post(f"/api/v1/payroll/runs/{run['id']}/reopen",headers=local_env.alpha_headers(),json={"expected_version":2,"reason":"Reabertura controlada para conferência"})
    assert payroll_reopened.status_code==200,payroll_reopened.text

    vacation=post(local_env,"/api/v1/personnel/vacations",{"employee_id":employee["id"],"accrual_start":"2025-01-01","accrual_end":"2025-12-31","scheduled_start":"2026-09-01","scheduled_end":"2026-09-30"})
    assert vacation["days"]==30
    vacation_approved=local_env.client.post(f"/api/v1/personnel/vacations/{vacation['id']}/approve",headers=local_env.alpha_headers(),json={"expected_version":1,"reason":"Programação anual aprovada"})
    assert vacation_approved.status_code==200,vacation_approved.text

    timeline=local_env.client.get(f"/api/v1/personnel/employees/{employee['id']}/timeline",headers=own_headers)
    assert timeline.status_code==200,timeline.text
    kinds={item["kind"] for item in timeline.json()["items"]}
    assert {"employment_contract","benefit","leave","vacation"}.issubset(kinds)
