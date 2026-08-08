from __future__ import annotations


def _template(local_env):
    created = local_env.client.post(
        "/api/v1/contract-templates",
        headers=local_env.alpha_headers(),
        json={"contract_type": "educational_services", "name": "Contrato Educacional Versionado"},
    )
    assert created.status_code == 201, created.text
    tid = created.json()["id"]
    version = local_env.client.post(
        f"/api/v1/contract-templates/{tid}/versions",
        headers=local_env.alpha_headers(),
        json={
            "body_text": "Contrato {{contract.number}} - {{student.name}} - R$ {{finance.total_amount}}",
            "variables": ["contract.number", "student.name", "finance.total_amount"],
            "rules": {},
        },
    )
    assert version.status_code == 201, version.text
    return tid, version.json()["id"]


def test_contract_full_lifecycle_versions_amendment_evidence_and_renewal(local_env):
    template_id, template_version_id = _template(local_env)

    validation = local_env.client.post(
        f"/api/v1/contract-templates/{template_id}/validate",
        headers=local_env.alpha_headers(),
        json={
            "version_id": template_version_id,
            "variables": {
                "contract": {"number": "MAT-2026-1000"},
                "student": {"name": "Aluno Contratual"},
                "finance": {"total_amount": "14400.00"},
            },
        },
    )
    assert validation.status_code == 200, validation.text
    assert validation.json()["valid_structure"] is True
    assert validation.json()["preview_complete"] is True

    preview = local_env.client.post(
        f"/api/v1/contract-templates/{template_id}/preview",
        headers=local_env.alpha_headers(),
        json={
            "version_id": template_version_id,
            "variables": {
                "contract": {"number": "MAT-2026-1000"},
                "student": {"name": "Aluno Contratual"},
                "finance": {"total_amount": "14400.00"},
            },
        },
    )
    assert preview.status_code == 200, preview.text
    assert "Aluno Contratual" in preview.json()["rendered_text"]
    assert len(preview.json()["rendered_sha256"]) == 64

    published = local_env.client.post(
        f"/api/v1/contract-templates/{template_id}/publish",
        headers=local_env.alpha_headers(),
    )
    assert published.status_code == 200, published.text

    created = local_env.client.post(
        "/api/v1/contracts",
        headers=local_env.alpha_headers(),
        json={
            "contract_type": "educational_services",
            "number": "MAT-2026-1000",
            "effective_from": "2026-01-01",
            "effective_until": "2026-12-31",
            "parties": [
                {
                    "party_type": "person",
                    "legal_name": "Responsável Contratual",
                    "document_number": "00000000000",
                    "role": "financial_responsible",
                    "signing_required": True,
                    "signing_order": 1,
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    contract = created.json()

    patched = local_env.client.patch(
        f"/api/v1/contracts/{contract['id']}",
        headers=local_env.alpha_headers(),
        json={
            "expected_version": contract["version"],
            "effective_from": "2026-01-05",
            "effective_until": "2026-12-20",
            "reason": "Ajuste de vigência antes da geração",
        },
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["version"] == 2

    generated = local_env.client.post(
        f"/api/v1/contracts/{contract['id']}/generate",
        headers=local_env.alpha_headers(),
        json={
            "expected_version": patched.json()["version"],
            "template_version_id": template_version_id,
            "variables": {
                "contract": {"number": "MAT-2026-1000"},
                "student": {"name": "Aluno Contratual"},
                "finance": {"total_amount": "14400.00"},
            },
            "source_references": {"enrollment": "fixture-contract-lifecycle"},
        },
    )
    assert generated.status_code == 200, generated.text
    generated_data = generated.json()

    immutable = local_env.client.patch(
        f"/api/v1/contracts/{contract['id']}",
        headers=local_env.alpha_headers(),
        json={
            "expected_version": generated_data["version"],
            "effective_until": "2026-12-31",
            "reason": "Tentativa posterior ao congelamento",
        },
    )
    assert immutable.status_code == 409, immutable.text
    assert immutable.json()["code"] == "CONTRACT_IMMUTABLE_AFTER_GENERATION"

    document = local_env.client.get(
        f"/api/v1/contracts/{contract['id']}/document",
        headers=local_env.alpha_headers(),
    )
    assert document.status_code == 200, document.text
    assert document.content.startswith(b"%PDF")
    assert document.headers["x-content-sha256"] == generated_data["document_sha256"]

    approved = local_env.client.post(
        f"/api/v1/contracts/{contract['id']}/approve",
        headers=local_env.alpha_headers(),
        json={"expected_version": generated_data["version"], "reason": "Aprovação jurídica"},
    )
    assert approved.status_code == 200, approved.text

    amendment = local_env.client.post(
        f"/api/v1/contracts/{contract['id']}/amendments",
        headers=local_env.alpha_headers(),
        json={
            "amendment_type": "scholarship",
            "title": "Aditivo de bolsa institucional",
            "payload": {"percentage": "25.00", "reason": "Bolsa institucional"},
            "effective_from": "2026-03-01",
        },
    )
    assert amendment.status_code == 201, amendment.text
    amendment_data = amendment.json()
    assert amendment_data["document_state"] == "draft"
    assert amendment_data["amendment_contract_id"]

    amendment_contract = local_env.client.get(
        f"/api/v1/contracts/{amendment_data['amendment_contract_id']}",
        headers=local_env.alpha_headers(),
    )
    assert amendment_contract.status_code == 200, amendment_contract.text
    assert amendment_contract.json()["contract_type"] == "amendment:scholarship"
    assert len(amendment_contract.json()["parties"]) == 1

    amendments = local_env.client.get(
        f"/api/v1/contracts/{contract['id']}/amendments",
        headers=local_env.alpha_headers(),
    )
    assert amendments.status_code == 200, amendments.text
    assert amendments.json()["items"][0]["amendment_contract_id"] == amendment_data["amendment_contract_id"]

    envelope = local_env.client.post(
        f"/api/v1/contracts/{contract['id']}/send-for-signature",
        headers=local_env.alpha_headers(),
        json={
            "expected_version": approved.json()["version"],
            "signing_order": "sequential",
            "signers": [
                {
                    "user_id": local_env.alpha_tenant["owner"]["id"],
                    "name": "Responsável Contratual",
                    "email": "owner@alpha.example.com",
                    "role": "financial_responsible",
                    "required": True,
                    "order": 1,
                }
            ],
        },
    )
    assert envelope.status_code == 200, envelope.text
    envelope_data = envelope.json()

    reminder = local_env.client.post(
        f"/api/v1/signature-envelopes/{envelope_data['id']}/remind",
        headers=local_env.alpha_headers(),
        json={"reason": "Lembrete antes do vencimento"},
    )
    assert reminder.status_code == 200, reminder.text
    assert reminder.json()["pending_signers"] == 1

    retry = local_env.client.post(
        f"/api/v1/signature-envelopes/{envelope_data['id']}/retry",
        headers=local_env.alpha_headers(),
        json={"reason": "Reprocessamento controlado"},
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["state"] == "queued"

    # Primeiro desafio: comprova bloqueio após o limite configurado de tentativas.
    locked_otp = local_env.client.post(
        f"/api/v1/signature-envelopes/{envelope_data['id']}/otp",
        headers=local_env.alpha_headers(),
        json={"channel": "email"},
    )
    assert locked_otp.status_code == 200, locked_otp.text
    locked_data = locked_otp.json()
    assert locked_data["state"] == "queued"
    assert "test_code" in locked_data
    wrong_code = "000000" if locked_data["test_code"] != "000000" else "999999"
    for attempt in range(5):
        wrong = local_env.client.post(
            f"/api/v1/signature-envelopes/{envelope_data['id']}/sign",
            headers=local_env.alpha_headers(),
            json={
                "consent": True,
                "document_sha256": generated_data["document_sha256"],
                "method": "simple_electronic",
                "otp_challenge_id": locked_data["challenge_id"],
                "otp_code": wrong_code,
            },
        )
        assert wrong.status_code == 422, (attempt, wrong.text)
        assert wrong.json()["code"] == "SIGNATURE_OTP_INVALID"

    locked = local_env.client.post(
        f"/api/v1/signature-envelopes/{envelope_data['id']}/sign",
        headers=local_env.alpha_headers(),
        json={
            "consent": True,
            "document_sha256": generated_data["document_sha256"],
            "method": "simple_electronic",
            "otp_challenge_id": locked_data["challenge_id"],
            "otp_code": locked_data["test_code"],
        },
    )
    assert locked.status_code == 423, locked.text
    assert locked.json()["code"] == "SIGNATURE_OTP_LOCKED"

    tenant_id = local_env.alpha_tenant["id"]
    locked_row = local_env.client.app.state.data_router.tenant_store(tenant_id).fetch_one(
        "SELECT attempts,consumed_at FROM signature_otp_challenges WHERE tenant_id=? AND id=?",
        (tenant_id, locked_data["challenge_id"]),
    )
    assert locked_row == {"attempts": 5, "consumed_at": None}

    # Segundo desafio: simula um replay/consumo concorrente antes da consolidação.
    replay_otp = local_env.client.post(
        f"/api/v1/signature-envelopes/{envelope_data['id']}/otp",
        headers=local_env.alpha_headers(),
        json={"channel": "email"},
    )
    assert replay_otp.status_code == 200, replay_otp.text
    replay_data = replay_otp.json()
    store = local_env.client.app.state.data_router.tenant_store(tenant_id)
    store.execute(
        "UPDATE signature_otp_challenges SET consumed_at=? WHERE tenant_id=? AND id=?",
        ("2026-08-08T15:00:00Z", tenant_id, replay_data["challenge_id"]),
    )
    replay = local_env.client.post(
        f"/api/v1/signature-envelopes/{envelope_data['id']}/sign",
        headers=local_env.alpha_headers(),
        json={
            "consent": True,
            "document_sha256": generated_data["document_sha256"],
            "method": "simple_electronic",
            "otp_challenge_id": replay_data["challenge_id"],
            "otp_code": replay_data["test_code"],
        },
    )
    assert replay.status_code == 409, replay.text
    assert replay.json()["code"] == "SIGNATURE_OTP_ALREADY_USED"

    # Terceiro desafio: fluxo feliz; o OTP é consumido uma única vez e não entra na evidência.
    otp = local_env.client.post(
        f"/api/v1/signature-envelopes/{envelope_data['id']}/otp",
        headers=local_env.alpha_headers(),
        json={"channel": "email"},
    )
    assert otp.status_code == 200, otp.text
    otp_data = otp.json()
    signed = local_env.client.post(
        f"/api/v1/signature-envelopes/{envelope_data['id']}/sign",
        headers=local_env.alpha_headers(),
        json={
            "consent": True,
            "document_sha256": generated_data["document_sha256"],
            "method": "simple_electronic",
            "otp_challenge_id": otp_data["challenge_id"],
            "otp_code": otp_data["test_code"],
        },
    )
    assert signed.status_code == 200, signed.text
    assert signed.json()["state"] == "signed"
    assert signed.json()["evidence"]["otp_challenge_id"] == otp_data["challenge_id"]
    assert signed.json()["evidence"]["otp_channel"] == "email"
    assert "otp_code" not in signed.json()["evidence"]
    consumed = local_env.client.app.state.data_router.tenant_store(tenant_id).fetch_one(
        "SELECT attempts,consumed_at FROM signature_otp_challenges WHERE tenant_id=? AND id=?",
        (tenant_id, otp_data["challenge_id"]),
    )
    assert consumed["attempts"] == 0
    assert consumed["consumed_at"]

    validation = local_env.client.post(
        f"/api/v1/signature-envelopes/{envelope_data['id']}/validate",
        headers=local_env.alpha_headers(),
    )
    assert validation.status_code == 200, validation.text
    assert validation.json()["valid"] is True
    assert len(validation.json()["evidence_package_sha256"]) == 64

    evidence = local_env.client.get(
        f"/api/v1/contracts/{contract['id']}/evidence",
        headers=local_env.alpha_headers(),
    )
    assert evidence.status_code == 200, evidence.text
    assert evidence.json()["envelopes"][0]["validations"]
    assert evidence.json()["envelopes"][0]["evidence_packages"]

    audit = local_env.client.get(
        f"/api/v1/contracts/{contract['id']}/audit",
        headers=local_env.alpha_headers(),
    )
    assert audit.status_code == 200, audit.text
    aggregate_types = {entry["aggregate_type"] for entry in audit.json()["audit"]}
    assert "contract" in aggregate_types
    assert "signature_envelope" in aggregate_types

    versions = local_env.client.get(
        f"/api/v1/contracts/{contract['id']}/versions",
        headers=local_env.alpha_headers(),
    )
    assert versions.status_code == 200, versions.text
    assert len(versions.json()["items"]) >= 5
    assert versions.json()["items"][0]["state"] == "signed"

    current = local_env.client.get(
        f"/api/v1/contracts/{contract['id']}",
        headers=local_env.alpha_headers(),
    ).json()
    renewed = local_env.client.post(
        f"/api/v1/contracts/{contract['id']}/renew",
        headers=local_env.alpha_headers(),
        json={
            "expected_version": current["version"],
            "effective_from": "2027-01-01",
            "effective_until": "2027-12-31",
            "number": "MAT-2027-1000",
            "reason": "Rematrícula 2027",
        },
    )
    assert renewed.status_code == 201, renewed.text
    assert renewed.json()["renews_contract_id"] == contract["id"]
    assert renewed.json()["state"] == "draft"


def test_template_with_undeclared_variable_cannot_be_published(local_env):
    template = local_env.client.post(
        "/api/v1/contract-templates",
        headers=local_env.alpha_headers(),
        json={"contract_type": "authorization", "name": "Modelo inválido controlado"},
    )
    assert template.status_code == 201, template.text
    template_id = template.json()["id"]
    version = local_env.client.post(
        f"/api/v1/contract-templates/{template_id}/versions",
        headers=local_env.alpha_headers(),
        json={
            "body_text": "Autorização de {{student.name}} para {{travel.destination}}.",
            "variables": ["student.name"],
            "rules": {},
        },
    )
    assert version.status_code == 201, version.text

    validation = local_env.client.post(
        f"/api/v1/contract-templates/{template_id}/validate",
        headers=local_env.alpha_headers(),
        json={"version_id": version.json()["id"], "variables": {"student": {"name": "Aluno"}}},
    )
    assert validation.status_code == 200, validation.text
    assert validation.json()["valid_structure"] is False
    assert validation.json()["undeclared_variables"] == ["travel.destination"]
    assert validation.json()["missing_preview_variables"] == ["travel.destination"]

    publish = local_env.client.post(
        f"/api/v1/contract-templates/{template_id}/publish",
        headers=local_env.alpha_headers(),
    )
    assert publish.status_code == 422, publish.text
    assert publish.json()["code"] == "CONTRACT_TEMPLATE_INVALID"
