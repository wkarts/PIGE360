from __future__ import annotations

import base64


def test_contract_snapshot_pdf_signature_evidence_and_public_validation(local_env):
    template = local_env.client.post(
        "/api/v1/contract-templates",
        headers=local_env.alpha_headers(),
        json={"contract_type": "educational_services", "name": "Matrícula 2026"},
    )
    assert template.status_code == 201, template.text
    template_id = template.json()["id"]
    version = local_env.client.post(
        f"/api/v1/contract-templates/{template_id}/versions",
        headers=local_env.alpha_headers(),
        json={
            "body_text": "CONTRATO {{contract.number}}\nInstituição: {{institution.name}}\nAluno: {{student.name}}\nResponsável: {{guardian.name}}\nValor: R$ {{finance.total_amount}}\nCláusulas: {{contract.clauses}}",
            "variables": ["contract.number", "institution.name", "student.name", "guardian.name", "finance.total_amount", "contract.clauses"],
            "rules": {},
        },
    )
    assert version.status_code == 201, version.text
    published = local_env.client.post(f"/api/v1/contract-templates/{template_id}/publish", headers=local_env.alpha_headers())
    assert published.status_code == 200, published.text

    created = local_env.client.post(
        "/api/v1/contracts",
        headers=local_env.alpha_headers(),
        json={"contract_type": "educational_services", "number": "MAT-2026-0001"},
    )
    assert created.status_code == 201, created.text
    contract = created.json()

    generated = local_env.client.post(
        f"/api/v1/contracts/{contract['id']}/generate",
        headers=local_env.alpha_headers(),
        json={
            "expected_version": contract["version"],
            "template_version_id": version.json()["id"],
            "variables": {
                "contract": {"number": "MAT-2026-0001", "clauses": ["Objeto e vigência", "Condições financeiras", "Proteção de dados"]},
                "institution": {"name": "Colégio Alpha"},
                "student": {"name": "Estudante Exemplo"},
                "guardian": {"name": "Responsável Exemplo"},
                "finance": {"total_amount": "12000.00"},
            },
            "source_references": {"reason": "Matrícula aprovada"},
        },
    )
    assert generated.status_code == 200, generated.text
    generated_data = generated.json()
    assert len(generated_data["document_sha256"]) == 64
    assert generated_data["validation_code"]

    tenant_root = local_env.client.app.state.data_router.tenant_storage_path(local_env.alpha_tenant["id"])
    pdf_path = tenant_root / generated_data["storage_key"]
    assert pdf_path.is_file()
    assert pdf_path.read_bytes().startswith(b"%PDF")

    approved = local_env.client.post(
        f"/api/v1/contracts/{contract['id']}/approve",
        headers=local_env.alpha_headers(),
        json={"expected_version": generated_data["version"], "reason": "Revisão interna concluída"},
    )
    assert approved.status_code == 200, approved.text

    envelope = local_env.client.post(
        f"/api/v1/contracts/{contract['id']}/send-for-signature",
        headers=local_env.alpha_headers(),
        json={
            "expected_version": approved.json()["version"],
            "signing_order": "sequential",
            "signers": [{
                "user_id": local_env.alpha_tenant["owner"]["id"],
                "name": "Responsável Exemplo",
                "email": "owner@alpha.example.com",
                "role": "financial_responsible",
                "required": True,
                "order": 1,
            }],
        },
    )
    assert envelope.status_code == 200, envelope.text
    envelope_data = envelope.json()

    otp = local_env.client.post(
        f"/api/v1/signature-envelopes/{envelope_data['id']}/otp",
        headers=local_env.alpha_headers(),
        json={"channel": "email"},
    )
    assert otp.status_code == 200, otp.text
    otp_data = otp.json()
    assert otp_data["state"] == "queued"
    assert "test_code" in otp_data

    signed = local_env.client.post(
        f"/api/v1/signature-envelopes/{envelope_data['id']}/sign",
        headers=local_env.alpha_headers(),
        json={"consent": True, "document_sha256": generated_data["document_sha256"], "method": "simple_electronic", "otp_challenge_id": otp_data["challenge_id"], "otp_code": otp_data["test_code"]},
    )
    assert signed.status_code == 200, signed.text
    assert signed.json()["state"] == "signed"
    evidence = signed.json()["evidence"]
    assert evidence["consent"] is True
    assert len(evidence["evidence_hmac_sha256"]) == 64

    public = local_env.client.get(
        f"/api/v1/public/contracts/validate/{generated_data['validation_code']}",
        headers={"host": "admin.alpha.school.local"},
    )
    assert public.status_code == 200
    public_data = public.json()
    assert public_data["authentic"] is True
    assert "student_name" not in public_data
    assert "cpf" not in str(public_data).lower()

    file_check = local_env.client.post(
        "/api/v1/public/contracts/validate-file",
        headers={"host": "admin.alpha.school.local"},
        json={"content_base64": base64.b64encode(pdf_path.read_bytes()).decode()},
    )
    assert file_check.status_code == 200
    assert file_check.json()["authentic"] is True

    providers = local_env.client.get("/api/v1/signatures/providers", headers=local_env.alpha_headers())
    statuses = {x["provider"]: x["status"] for x in providers.json()["items"]}
    assert statuses["internal_electronic"] == "available"
    assert statuses["icp_brasil_pades"] == "not_configured"
    assert statuses["govbr_advanced"] == "not_configured"
