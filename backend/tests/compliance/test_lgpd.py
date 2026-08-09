from __future__ import annotations

import hashlib
import json

from conftest import ALPHA_HOST, BETA_HOST


def post(env, path: str, payload: dict, *, headers=None, key: str | None = None, expected: int = 201):
    h = headers or env.alpha_headers()
    if key:
        h = {**h, "Idempotency-Key": key}
    response = env.client.post(path, headers=h, json=payload)
    assert response.status_code == expected, f"{path}: {response.status_code} {response.text}"
    return response.json()


def published_notice(env):
    notice = post(env, "/api/v1/compliance/privacy-notices", {
        "code": "PRIVACY-GENERAL", "title": "Aviso de Privacidade da Instituição",
        "content": "Este aviso descreve finalidades, bases legais, direitos do titular, retenção e canais de atendimento LGPD da instituição.",
        "effective_from": "2026-01-01",
    })
    published = post(env, f"/api/v1/compliance/privacy-notices/{notice['id']}/publish", {"reason": "Versão revisada e aprovada pelo responsável de compliance"}, expected=200)
    assert published["state"] == "published"
    return notice


def test_minor_consent_legal_guardian_revoke_and_tenant_isolation(local_env):
    notice = published_notice(local_env)
    child_person = post(local_env, "/api/v1/people", {"full_name": "Criança Titular LGPD", "cpf": "95555555555", "birth_date": "2015-05-10"}, key="lgpd-child-person")
    child = post(local_env, "/api/v1/students", {"person_id": child_person["id"], "registration_number": "LGPD-INF-001"})
    purpose=post(local_env,"/api/v1/compliance/processing-activities",{
        "code":"PHOTO_PEDAGOGICAL","name":"Uso pedagógico de imagem","purpose":"Registrar e compartilhar imagens pedagógicas autorizadas no contexto escolar.",
        "legal_basis":"consent","privacy_notice_code":"PRIVACY-GENERAL","data_categories":["imagem"],"data_subjects":["aluno"],"recipients":["responsaveis_autorizados"],"security_measures":["access_control","audit"]
    })
    assert purpose["privacy_notice_code"]=="PRIVACY-GENERAL"
    purposes=local_env.client.get("/api/v1/compliance/consent-purposes",headers=local_env.alpha_headers())
    assert purposes.status_code==200,purposes.text
    assert purposes.json()["items"][0]["privacy_notice_id"]==notice["id"]
    _,child_token=local_env.create_alpha_user("child.lgpd@alpha.example.com",["student"],person_id=child_person["id"])
    minor_self=local_env.client.post("/api/v1/compliance/consents",headers=local_env.headers(ALPHA_HOST,child_token),json={"subject_person_id":child_person["id"],"granted_by_person_id":child_person["id"],"purpose_code":"PHOTO_PEDAGOGICAL","privacy_notice_id":notice["id"],"channel":"mobile"})
    assert minor_self.status_code==403 and minor_self.json()["code"]=="MINOR_REQUIRES_LEGAL_GUARDIAN"
    guardian_person = post(local_env, "/api/v1/people", {"full_name": "Responsável Legal LGPD", "cpf": "96666666666", "email": "guardian.lgpd@example.com"}, key="lgpd-guardian-person")
    guardian = post(local_env, "/api/v1/guardians", {"person_id": guardian_person["id"]})
    post(local_env, "/api/v1/guardian-students", {"guardian_id": guardian["id"], "student_id": child["id"], "relationship": "mãe", "is_legal": True, "is_financial": True, "pickup_authorized": True})
    _, guardian_token = local_env.create_alpha_user("guardian.lgpd@alpha.example.com", ["guardian"], person_id=guardian_person["id"])
    guardian_headers = local_env.headers(ALPHA_HOST, guardian_token)

    consent = post(local_env, "/api/v1/compliance/consents", {
        "subject_person_id": child_person["id"], "granted_by_person_id": guardian_person["id"], "purpose_code": "PHOTO_PEDAGOGICAL",
        "privacy_notice_id": notice["id"], "channel": "mobile", "evidence": {"checkbox": True, "screen": "family-consent"},
    }, headers=guardian_headers)
    assert consent["state"] == "granted" and consent["subject_person_id"] == child_person["id"]

    listing = local_env.client.get(f"/api/v1/compliance/persons/{child_person['id']}/consents", headers=guardian_headers)
    assert listing.status_code == 200, listing.text
    assert listing.json()["items"][0]["purpose_code"] == "PHOTO_PEDAGOGICAL"

    revoked = post(local_env, f"/api/v1/compliance/consents/{consent['id']}/revoke", {"reason": "Responsável retirou a autorização de uso de imagem"}, headers=guardian_headers, expected=200)
    assert revoked["state"] == "revoked"

    unrelated_person = post(local_env, "/api/v1/people", {"full_name": "Responsável Não Vinculado", "cpf": "97777777777", "email": "unrelated.lgpd@example.com"}, key="lgpd-unrelated-person")
    unrelated_guardian = post(local_env, "/api/v1/guardians", {"person_id": unrelated_person["id"]})
    assert unrelated_guardian["state"] == "active"
    _, unrelated_token = local_env.create_alpha_user("unrelated.lgpd@alpha.example.com", ["guardian"], person_id=unrelated_person["id"])
    denied = local_env.client.post("/api/v1/compliance/consents", headers=local_env.headers(ALPHA_HOST, unrelated_token), json={
        "subject_person_id": child_person["id"], "granted_by_person_id": unrelated_person["id"], "purpose_code": "PHOTO_PEDAGOGICAL",
        "privacy_notice_id": notice["id"], "channel": "web",
    })
    assert denied.status_code == 403 and denied.json()["code"] == "LEGAL_GUARDIAN_REQUIRED"

    beta_denied = local_env.client.get(f"/api/v1/compliance/persons/{child_person['id']}/consents", headers=local_env.beta_headers())
    assert beta_denied.status_code == 404 and beta_denied.json()["code"] == "PERSON_NOT_FOUND"


def test_dsar_export_retention_legal_hold_and_controlled_anonymization(local_env):
    published_notice(local_env)
    person = post(local_env, "/api/v1/people", {
        "full_name": "Titular Exportação LGPD", "cpf": "98888888888", "email": "titular.export@example.com", "phone": "+557100000000",
        "civil_data": {"nationality": "BR"}, "address": {"city": "Salvador", "state": "BA"},
    }, key="lgpd-export-person")

    processing = post(local_env, "/api/v1/compliance/processing-activities", {
        "code": "ACADEMIC-MANAGEMENT", "name": "Gestão acadêmica", "purpose": "Executar matrícula, vida acadêmica e emissão de documentos escolares.",
        "legal_basis": "execucao_contrato_obrigacao_legal", "data_categories": ["identificacao", "academico"], "data_subjects": ["aluno"],
        "recipients": ["instituicao"], "retention_rule": "Enquanto exigido por legislação educacional", "security_measures": ["tenant_isolation", "encryption", "audit"], "owner_department": "Secretaria",
    })
    assert processing["state"] == "active"
    retention = post(local_env, "/api/v1/compliance/retention-policies", {
        "data_category": "cadastro_contato", "purpose_code": "RELATIONSHIP", "retention_days": 1825, "disposition": "anonymize",
        "legal_basis": "politica_interna_e_obrigacao_legal", "starts_on": "2026-01-01",
    })
    assert retention["version"] == 1

    export_request = post(local_env, "/api/v1/compliance/data-subject-requests", {
        "subject_person_id": person["id"], "request_type": "export", "description": "Solicitação de cópia estruturada dos dados pessoais", "priority": "normal",
    })
    post(local_env, f"/api/v1/compliance/data-subject-requests/{export_request['id']}/state", {"state": "under_review", "reason": "Identidade e escopo conferidos", "assigned_to": "privacy-office"}, expected=200)
    generated = post(local_env, f"/api/v1/compliance/data-subject-requests/{export_request['id']}/export", {}, expected=200)
    assert len(generated["sha256"]) == 64 and generated["bytes"] > 100
    download = local_env.client.get(f"/api/v1/compliance/data-subject-requests/{export_request['id']}/export", headers=local_env.alpha_headers())
    assert download.status_code == 200, download.text
    assert hashlib.sha256(download.content).hexdigest() == generated["sha256"] == download.headers["X-Content-SHA256"]
    payload = json.loads(download.content)
    assert payload["subject"]["person"]["email"] == "titular.export@example.com"
    assert payload["schema"] == "pige360-lgpd-export-v1"

    anon_request = post(local_env, "/api/v1/compliance/data-subject-requests", {
        "subject_person_id": person["id"], "request_type": "anonymization", "description": "Solicitação de anonimização do cadastro de contato", "priority": "normal",
    })
    state = post(local_env, f"/api/v1/compliance/data-subject-requests/{anon_request['id']}/state", {"state": "under_review", "reason": "Solicitação recebida pelo encarregado"}, expected=200)
    assert state["state"] == "under_review"
    state = post(local_env, f"/api/v1/compliance/data-subject-requests/{anon_request['id']}/state", {"state": "approved", "reason": "Não há impedimento legal identificado no momento"}, expected=200)
    assert state["state"] == "approved"

    hold = post(local_env, "/api/v1/compliance/legal-holds", {"person_id": person["id"], "reason": "Preservação temporária para auditoria jurídica"})
    blocked = local_env.client.post(f"/api/v1/compliance/data-subject-requests/{anon_request['id']}/anonymize", headers=local_env.alpha_headers())
    assert blocked.status_code == 409 and blocked.json()["code"] == "LEGAL_HOLD_ACTIVE"
    post(local_env, f"/api/v1/compliance/legal-holds/{hold['id']}/release", {"reason": "Auditoria jurídica encerrada"}, expected=200)

    anonymized = post(local_env, f"/api/v1/compliance/data-subject-requests/{anon_request['id']}/anonymize", {}, expected=200)
    assert anonymized["person_state"] == "anonymized" and anonymized["state"] == "fulfilled"
    people = local_env.client.get("/api/v1/people?q=Titular%20anonimizado", headers=local_env.alpha_headers())
    assert people.status_code == 200, people.text
    row = next(x for x in people.json()["items"] if x["id"] == person["id"])
    assert row["state"] == "anonymized" and row["cpf"] is None and row["email"] is None and row["phone"] is None

    dashboard = local_env.client.get("/api/v1/compliance/dashboard", headers=local_env.alpha_headers())
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["active_legal_holds"] == 0
    assert dashboard.json()["active_retention_policies"] == 1


def test_consent_requires_registered_purpose_matching_notice_and_verified_age(local_env):
    notice = published_notice(local_env)
    post(local_env, "/api/v1/compliance/processing-activities", {
        "code": "STUDENT-VOICE",
        "name": "Uso autorizado de voz do aluno",
        "purpose": "Utilizar gravações de voz exclusivamente em atividade pedagógica consentida.",
        "legal_basis": "consent",
        "privacy_notice_code": "PRIVACY-GENERAL",
        "data_categories": ["voz"],
        "data_subjects": ["aluno"],
        "recipients": ["equipe_pedagogica"],
        "security_measures": ["access_control", "audit"],
    })
    other = post(local_env, "/api/v1/compliance/privacy-notices", {
        "code": "PRIVACY-OTHER",
        "title": "Aviso de Privacidade de Outra Finalidade",
        "content": "Este aviso possui finalidade diferente e não pode ser reutilizado para consentimentos vinculados a outro tratamento.",
        "effective_from": "2026-01-01",
    })
    post(local_env, f"/api/v1/compliance/privacy-notices/{other['id']}/publish", {"reason": "Publicação para prova de segregação de finalidade"}, expected=200)

    person = post(local_env, "/api/v1/people", {
        "full_name": "Aluno Idade Não Informada", "cpf": "93333333333", "email": "student.age@example.com"
    }, key="lgpd-age-person")
    post(local_env, "/api/v1/students", {"person_id": person["id"], "registration_number": "LGPD-AGE-001"})
    _, token = local_env.create_alpha_user("student.age@example.com", ["student"], person_id=person["id"])
    headers = local_env.headers(ALPHA_HOST, token)

    detail = local_env.client.get(f"/api/v1/compliance/privacy-notices/{notice['id']}", headers=headers)
    assert detail.status_code == 200, detail.text
    assert "direitos do titular" in detail.json()["content"]

    unknown = local_env.client.post("/api/v1/compliance/consents", headers=headers, json={
        "subject_person_id": person["id"], "granted_by_person_id": person["id"],
        "purpose_code": "NOT-REGISTERED", "privacy_notice_id": notice["id"], "channel": "web",
    })
    assert unknown.status_code == 409 and unknown.json()["code"] == "CONSENT_PURPOSE_NOT_AVAILABLE"

    mismatch = local_env.client.post("/api/v1/compliance/consents", headers=headers, json={
        "subject_person_id": person["id"], "granted_by_person_id": person["id"],
        "purpose_code": "STUDENT-VOICE", "privacy_notice_id": other["id"], "channel": "web",
    })
    assert mismatch.status_code == 409 and mismatch.json()["code"] == "CONSENT_NOTICE_MISMATCH"

    age_unknown = local_env.client.post("/api/v1/compliance/consents", headers=headers, json={
        "subject_person_id": person["id"], "granted_by_person_id": person["id"],
        "purpose_code": "STUDENT-VOICE", "privacy_notice_id": notice["id"], "channel": "web",
    })
    assert age_unknown.status_code == 409 and age_unknown.json()["code"] == "CONSENT_AGE_UNVERIFIED"
