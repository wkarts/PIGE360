from __future__ import annotations


def _post(env, path: str, payload: dict, *, headers=None, expected=201):
    response=env.client.post(path,headers=headers or env.alpha_headers(),json=payload)
    assert response.status_code==expected,response.text
    return response.json()


def test_templates_preferences_notifications_idempotency_and_tenant_scope(local_env):
    person=_post(local_env,"/api/v1/people",{"full_name":"Responsável Comunicação","cpf":"39053344705","email":"resp@example.com","phone":"+5571999999999"},headers=local_env.alpha_headers(**{"Idempotency-Key":"comm-person"}))
    _,token=local_env.create_alpha_user("resp-user@alpha.example.com",["guardian"],person_id=person["id"])
    user_headers=local_env.headers("admin.alpha.school.local",token)

    template=_post(local_env,"/api/v1/communication/templates",{"template_key":"finance.due","name":"Parcela a vencer","channel":"internal","subject_template":"Parcela {{installment}}","body_template":"Olá {{person.name}}, sua parcela vence em {{due_date}}.","variables":["installment","person.name","due_date"]})
    published=_post(local_env,f"/api/v1/communication/templates/{template['id']}/publish",{"expected_version":1,"reason":"Template revisado"},expected=200)
    assert published["state"]=="published"

    headers=local_env.alpha_headers(**{"Idempotency-Key":"notification-001"})
    payload={"recipient_person_id":person["id"],"channel":"internal","template_key":"finance.due","variables":{"installment":"03/12","person":{"name":"Responsável"},"due_date":"10/08/2026"}}
    queued=_post(local_env,"/api/v1/notifications",payload,headers=headers)
    replay=_post(local_env,"/api/v1/notifications",payload,headers=headers)
    assert replay["id"]==queued["id"]
    assert "Responsável" in queued["body"] and "03/12" in queued["subject"]

    mine=local_env.client.get("/api/v1/notifications",headers=user_headers)
    assert mine.status_code==200 and [x["id"] for x in mine.json()["items"]]==[queued["id"]]
    detail=local_env.client.get(f"/api/v1/notifications/{queued['id']}",headers=user_headers)
    assert detail.status_code==200 and detail.json()["events"][0]["event_type"]=="queued"

    pref=local_env.client.put("/api/v1/communication/preferences/me",headers=user_headers,json={"channel":"internal","enabled":False,"quiet_hours":{}})
    assert pref.status_code==200 and pref.json()["enabled"] is False
    blocked=_post(local_env,"/api/v1/notifications",{"recipient_person_id":person["id"],"channel":"internal","body":"Bloqueada"},headers=local_env.alpha_headers(**{"Idempotency-Key":"notification-002"}),expected=409)
    assert blocked["code"]=="COMMUNICATION_CHANNEL_DISABLED"

    beta=local_env.client.get(f"/api/v1/notifications/{queued['id']}",headers=local_env.beta_headers())
    assert beta.status_code==404


def test_template_versioning_and_notification_cancel(local_env):
    person=_post(local_env,"/api/v1/people",{"full_name":"Pessoa Aviso","cpf":"52998224725"},headers=local_env.alpha_headers(**{"Idempotency-Key":"comm-person-2"}))
    template=_post(local_env,"/api/v1/communication/templates",{"template_key":"notice.general","name":"Aviso geral","channel":"internal","body_template":"Aviso: {{message}}","variables":["message"]})
    _post(local_env,f"/api/v1/communication/templates/{template['id']}/publish",{"expected_version":1,"reason":"Primeira publicação"},expected=200)
    version=_post(local_env,f"/api/v1/communication/templates/{template['id']}/versions",{"body_template":"Comunicado: {{message}}","variables":["message"],"reason":"Ajuste de redação"})
    assert version["current_version"]==2 and version["state"]=="draft"
    _post(local_env,f"/api/v1/communication/templates/{template['id']}/publish",{"expected_version":2,"reason":"Nova versão aprovada"},expected=200)

    queued=_post(local_env,"/api/v1/notifications",{"recipient_person_id":person["id"],"channel":"internal","template_key":"notice.general","variables":{"message":"Reunião amanhã"},"scheduled_at":"2099-01-01T10:00:00Z"},headers=local_env.alpha_headers(**{"Idempotency-Key":"notification-scheduled"}))
    assert queued["state"]=="scheduled" and queued["body"].startswith("Comunicado:")
    cancelled=_post(local_env,f"/api/v1/notifications/{queued['id']}/cancel",{"reason":"Evento cancelado"},expected=200)
    assert cancelled["state"]=="cancelled"


def test_scheduled_notifications_are_promoted_once_by_beat(local_env):
    from app.worker import queue_due_notifications

    person=_post(local_env,"/api/v1/people",{"full_name":"Pessoa Agenda","cpf":"15350946056"},headers=local_env.alpha_headers(**{"Idempotency-Key":"comm-person-schedule"}))
    scheduled=_post(local_env,"/api/v1/notifications",{"recipient_person_id":person["id"],"channel":"internal","body":"Mensagem agendada","scheduled_at":"2099-01-01T10:00:00+00:00"},headers=local_env.alpha_headers(**{"Idempotency-Key":"notification-future"}))
    assert scheduled["state"]=="scheduled"
    router=local_env.client.app.state.data_router
    store=router.tenant_store(local_env.alpha_tenant["id"])
    store.execute("UPDATE notifications SET scheduled_at='2000-01-01T00:00:00+00:00' WHERE tenant_id=? AND id=?",(local_env.alpha_tenant["id"],scheduled["id"]))
    first=queue_due_notifications(router=router)
    assert first["notifications"]==1, first
    row=store.fetch_one("SELECT state FROM notifications WHERE tenant_id=? AND id=?",(local_env.alpha_tenant["id"],scheduled["id"]))
    assert row["state"]=="queued"
    outbox=store.fetch_all("SELECT id FROM outbox_events WHERE tenant_id=? AND aggregate_type='notification' AND aggregate_id=? AND event_type='NotificationRequested'",(local_env.alpha_tenant["id"],scheduled["id"]))
    assert len(outbox)==1
    second=queue_due_notifications(router=router)
    assert second["notifications"]==0
