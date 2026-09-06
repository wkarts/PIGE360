from __future__ import annotations

import base64
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

BUILD_TOKEN = "test-build-farm-token-" + "x" * 48


def _publish_brand(local_env) -> int:
    payload = {
        "legal_name": "Instituição Alpha Ltda.",
        "trade_name": "Colégio Alpha",
        "short_name": "Alpha",
        "app_display_name": "Colégio Alpha",
        "primary_domain": "alpha.school.local",
        "primary_color": "#006D77",
        "secondary_color": "#0D1B2A",
        "accent_color": "#F59E0B",
        "typography_family": "Inter",
        "co_branding_policy": "disabled",
        "demo_only": True,
    }
    response = local_env.client.post(
        "/api/v1/branding/publish",
        headers=local_env.alpha_headers(),
        json={"payload": payload, "reason": "Ativação do branding para build"},
    )
    assert response.status_code == 200, response.text
    return response.json()["version"]


def _manifest(local_env, brand_version: int) -> dict:
    return {
        "tenant_code": local_env.alpha_tenant["code"],
        "brand_version": brand_version,
        "release_channel": "stable",
        "apps": {
            "family-mobile": {
                "enabled": True,
                "display_name": "Colégio Alpha Família",
                "identifier": "br.com.colegioalpha.family",
                "api_url": "https://api.alpha.school.local",
                "web_url": "https://familia.alpha.school.local",
                "update_url": "https://apps.alpha.school.local/family",
                "features": {"finance": True, "canteen": True, "attendance": True},
            }
        },
        "metadata": {"tenant_pinned": True, "hostname_allowlist": ["api.alpha.school.local"]},
    }


def _activate_entitlement(local_env) -> None:
    response = local_env.client.post(
        f"/api/v1/platform/tenants/{local_env.alpha_tenant['id']}/apps/entitlements",
        headers=local_env.platform_headers(),
        json={"app_product": "family-mobile", "state": "active", "contract_reference": "contract-test-001"},
    )
    assert response.status_code == 201, response.text


def test_operational_build_farm_release_and_download(local_env):
    brand_version = _publish_brand(local_env)
    _activate_entitlement(local_env)

    manifest = local_env.client.post(
        "/api/v1/apps/manifests",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "manifest-alpha-0001"}),
        json=_manifest(local_env, brand_version),
    )
    assert manifest.status_code == 201, manifest.text
    manifest_data = manifest.json()

    build = local_env.client.post(
        "/api/v1/apps/builds",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "tenant-build-alpha-0001"}),
        json={"manifest_id": manifest_data["id"], "platforms": ["pwa"], "products": ["family-mobile"]},
    )
    assert build.status_code == 202, build.text
    build_data = build.json()
    assert build_data["status"] == "queued"
    assert len(build_data["jobs"]) == 1

    claim = local_env.client.post(
        "/api/v1/platform/build-farm/jobs/claim",
        headers={"host": "api.platform.local", "X-Build-Farm-Token": BUILD_TOKEN},
        json={"worker_id": "linux-builder-test", "operating_system": "linux", "supported_platforms": ["pwa"]},
    )
    assert claim.status_code == 200, claim.text
    job = claim.json()
    assert job["tenant_id"] == local_env.alpha_tenant["id"]
    assert job["spec"]["app_product"] == "family-mobile"
    assert job["spec"]["platform"] == "pwa"

    artifact = b"PK\x03\x04PIGE360 deterministic PWA test artifact"
    digest = hashlib.sha256(artifact).hexdigest()
    upload = local_env.client.post(
        f"/api/v1/platform/build-farm/jobs/{job['job_id']}/artifacts",
        headers={"host": "api.platform.local", "X-Build-Farm-Token": BUILD_TOKEN},
        data={"tenant_id": local_env.alpha_tenant["id"], "artifact_kind": "pwa-zip", "sha256": digest, "signed_state": "unsigned"},
        files={"file": ("alpha-family-pwa.zip", artifact, "application/zip")},
    )
    assert upload.status_code == 201, upload.text
    artifact_id = upload.json()["id"]

    complete = local_env.client.post(
        f"/api/v1/platform/build-farm/jobs/{job['job_id']}/complete",
        headers={"host": "api.platform.local", "X-Build-Farm-Token": BUILD_TOKEN},
        json={"tenant_id": local_env.alpha_tenant["id"]},
    )
    assert complete.status_code == 200, complete.text
    assert complete.json()["build_request_status"] == "completed"

    release = local_env.client.post(
        f"/api/v1/platform/tenants/{local_env.alpha_tenant['id']}/apps/releases",
        headers=local_env.platform_headers(),
        json={"build_request_id": build_data["build_id"], "version": "1.0.0", "channel": "stable", "changelog": "Primeira release", "mandatory": False},
    )
    assert release.status_code == 201, release.text
    release_id = release.json()["id"]

    publish = local_env.client.post(
        f"/api/v1/platform/tenants/{local_env.alpha_tenant['id']}/apps/releases/{release_id}/publish",
        headers=local_env.platform_headers(),
        json={"reason": "Release homologada"},
    )
    assert publish.status_code == 200, publish.text
    assert publish.json()["state"] == "published"

    catalog = local_env.client.get("/api/v1/apps/catalog", headers=local_env.alpha_headers())
    assert catalog.status_code == 200
    assert catalog.json()["releases"][0]["id"] == release_id

    download = local_env.client.get(
        f"/api/v1/apps/releases/{release_id}/download",
        params={"artifact_id": artifact_id},
        headers=local_env.alpha_headers(),
    )
    assert download.status_code == 200, download.text
    assert download.content == artifact
    assert download.headers["x-artifact-sha256"] == digest

    replay = local_env.client.post(
        "/api/v1/apps/builds",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "tenant-build-alpha-0001"}),
        json={"manifest_id": manifest_data["id"], "platforms": ["pwa"], "products": ["family-mobile"]},
    )
    assert replay.status_code == 202
    assert replay.json()["build_id"] == build_data["build_id"]


def test_native_build_without_compatible_agent_stays_queued(local_env):
    brand_version = _publish_brand(local_env)
    _activate_entitlement(local_env)
    manifest = local_env.client.post(
        "/api/v1/apps/manifests",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "manifest-alpha-native"}),
        json=_manifest(local_env, brand_version),
    ).json()
    build = local_env.client.post(
        "/api/v1/apps/builds",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "tenant-build-alpha-native"}),
        json={"manifest_id": manifest["id"], "platforms": ["ios-app"], "products": ["family-mobile"]},
    )
    assert build.status_code == 202, build.text
    assert build.json()["status"] == "queued"
    claim = local_env.client.post(
        "/api/v1/platform/build-farm/jobs/claim",
        headers={"host": "api.platform.local", "X-Build-Farm-Token": BUILD_TOKEN},
        json={"worker_id": "linux-only", "operating_system": "linux", "supported_platforms": ["pwa", "android-apk"]},
    )
    assert claim.status_code == 204
    status = local_env.client.get(
        f"/api/v1/platform/tenants/{local_env.alpha_tenant['id']}/apps/builds/{build.json()['build_id']}",
        headers=local_env.platform_headers(),
    )
    assert status.json()["status"] == "queued"


def test_build_job_claim_is_compare_and_set_under_concurrency(local_env):
    brand_version = _publish_brand(local_env)
    _activate_entitlement(local_env)
    manifest = local_env.client.post(
        "/api/v1/apps/manifests",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "manifest-concurrent-claim"}),
        json=_manifest(local_env, brand_version),
    )
    assert manifest.status_code == 201, manifest.text
    build = local_env.client.post(
        "/api/v1/apps/builds",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "build-concurrent-claim"}),
        json={"manifest_id": manifest.json()["id"], "platforms": ["pwa"], "products": ["family-mobile"]},
    )
    assert build.status_code == 202, build.text
    barrier = Barrier(2)

    def claim(worker_id: str):
        barrier.wait(timeout=5)
        return local_env.client.post(
            "/api/v1/platform/build-farm/jobs/claim",
            headers={"host": "api.platform.local", "X-Build-Farm-Token": BUILD_TOKEN},
            json={"worker_id": worker_id, "operating_system": "linux", "supported_platforms": ["pwa"]},
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = [
            executor.submit(claim, "linux-builder-a"),
            executor.submit(claim, "linux-builder-b"),
        ]
        resolved = [future.result() for future in responses]

    assert sorted(response.status_code for response in resolved) == [200, 204]
    claimed = next(response.json() for response in resolved if response.status_code == 200)
    store = local_env.client.app.state.data_router.tenant_store(local_env.alpha_tenant["id"])
    job = store.fetch_one(
        "SELECT status,claimed_by,attempts FROM app_build_jobs WHERE id=?",
        (claimed["job_id"],),
    )
    assert job["status"] == "building"
    assert job["claimed_by"] in {"linux-builder-a", "linux-builder-b"}
    assert int(job["attempts"]) == 1


def test_manifest_signing_accepts_only_typed_secret_references_and_redacts_legacy_values(local_env):
    brand_version = _publish_brand(local_env)
    unsafe = _manifest(local_env, brand_version)
    unsafe["apps"]["family-mobile"]["signing"] = {
        "mode": "managed",
        "android_keystore_reference": "raw-super-secret-value",
    }
    rejected = local_env.client.post(
        "/api/v1/apps/manifests",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "manifest-signing-unsafe"}),
        json=unsafe,
    )
    assert rejected.status_code == 422, rejected.text

    metadata_secret = _manifest(local_env, brand_version)
    metadata_secret["metadata"]["signing"] = {
        "password": "plain-secret",
        "keystore_base64": "AAAA",
    }
    metadata_rejected = local_env.client.post(
        "/api/v1/apps/manifests",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "manifest-metadata-secret"}),
        json=metadata_secret,
    )
    assert metadata_rejected.status_code == 422, metadata_rejected.text
    assert "plain-secret" not in metadata_rejected.text

    url_secret = _manifest(local_env, brand_version)
    url_secret["apps"]["family-mobile"]["api_url"] = "https://builder:plain-secret@api.alpha.school.local"
    url_rejected = local_env.client.post(
        "/api/v1/apps/manifests",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "manifest-url-secret"}),
        json=url_secret,
    )
    assert url_rejected.status_code == 422, url_rejected.text
    assert "plain-secret" not in url_rejected.text
    assert "raw-super-secret-value" not in rejected.text

    safe = _manifest(local_env, brand_version)
    safe["apps"]["family-mobile"]["signing"] = {
        "mode": "managed",
        "android_keystore_reference": "secret://alpha-android-keystore",
        "android_key_alias_reference": "secret://alpha-android-key-alias",
        "android_key_password_reference": "secret://alpha-android-key-password",
    }
    created = local_env.client.post(
        "/api/v1/apps/manifests",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "manifest-signing-safe"}),
        json=safe,
    )
    assert created.status_code == 201, created.text
    assert created.json()["payload"]["apps"]["family-mobile"]["signing"]["mode"] == "managed"

    _activate_entitlement(local_env)
    incomplete = _manifest(local_env, brand_version)
    incomplete["apps"]["family-mobile"]["signing"] = {
        "mode": "managed",
        "android_keystore_reference": "secret://alpha-android-keystore",
    }
    incomplete_manifest = local_env.client.post(
        "/api/v1/apps/manifests",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "manifest-signing-incomplete"}),
        json=incomplete,
    )
    assert incomplete_manifest.status_code == 201, incomplete_manifest.text
    incomplete_build = local_env.client.post(
        "/api/v1/apps/builds",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "build-signing-incomplete"}),
        json={
            "manifest_id": incomplete_manifest.json()["id"],
            "platforms": ["android-apk"],
            "products": ["family-mobile"],
        },
    )
    assert incomplete_build.status_code == 422, incomplete_build.text
    assert incomplete_build.json()["code"] == "APP_SIGNING_REFERENCES_INCOMPLETE"

    signed_build = local_env.client.post(
        "/api/v1/apps/builds",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "build-signing-managed"}),
        json={
            "manifest_id": created.json()["id"],
            "platforms": ["android-apk"],
            "products": ["family-mobile"],
        },
    )
    assert signed_build.status_code == 202, signed_build.text
    claim = local_env.client.post(
        "/api/v1/platform/build-farm/jobs/claim",
        headers={"host": "api.platform.local", "X-Build-Farm-Token": BUILD_TOKEN},
        json={
            "worker_id": "android-signing-builder",
            "operating_system": "linux",
            "supported_platforms": ["android-apk"],
        },
    )
    assert claim.status_code == 200, claim.text
    artifact = b"managed-signing-artifact"
    digest = hashlib.sha256(artifact).hexdigest()
    unsigned_upload = local_env.client.post(
        f"/api/v1/platform/build-farm/jobs/{claim.json()['job_id']}/artifacts",
        headers={"host": "api.platform.local", "X-Build-Farm-Token": BUILD_TOKEN},
        data={
            "tenant_id": local_env.alpha_tenant["id"],
            "artifact_kind": "apk",
            "sha256": digest,
            "signed_state": "unsigned",
        },
        files={"file": ("alpha.apk", artifact, "application/vnd.android.package-archive")},
    )
    assert unsigned_upload.status_code == 409, unsigned_upload.text
    assert unsigned_upload.json()["code"] == "APP_ARTIFACT_SIGNING_STATE_INVALID"
    signed_upload = local_env.client.post(
        f"/api/v1/platform/build-farm/jobs/{claim.json()['job_id']}/artifacts",
        headers={"host": "api.platform.local", "X-Build-Farm-Token": BUILD_TOKEN},
        data={
            "tenant_id": local_env.alpha_tenant["id"],
            "artifact_kind": "apk",
            "sha256": digest,
            "signed_state": "signed",
        },
        files={"file": ("alpha.apk", artifact, "application/vnd.android.package-archive")},
    )
    assert signed_upload.status_code == 201, signed_upload.text
    assert signed_upload.json()["signed_state"] == "signed"

    tenant_id = local_env.alpha_tenant["id"]
    store = local_env.client.app.state.data_router.tenant_store(tenant_id)
    owner = store.fetch_one("SELECT id FROM users WHERE tenant_id=? LIMIT 1", (tenant_id,))
    legacy_payload = _manifest(local_env, brand_version)
    legacy_payload["tenant_id"] = tenant_id
    legacy_payload["apps"]["family-mobile"]["signing"] = {
        "keystore_password": "persisted-legacy-secret-value"
    }
    legacy_payload["apps"]["family-mobile"]["api_url"] = (
        "https://legacy-user:persisted-url-secret@api.alpha.school.local"
    )
    legacy_payload["metadata"]["nested"] = {
        "signing_password": "persisted-metadata-secret",
    }
    store.execute(
        "INSERT INTO tenant_app_manifests(id,tenant_id,version,state,payload_json,sha256,created_by,created_at) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (
            "legacy-signing-manifest",
            tenant_id,
            999,
            "ready",
            json.dumps(legacy_payload),
            "0" * 64,
            owner["id"],
            "2026-09-04T00:00:00+00:00",
        ),
    )
    listed = local_env.client.get(
        f"/api/v1/platform/tenants/{tenant_id}/apps",
        headers=local_env.platform_headers(),
    )
    assert listed.status_code == 200, listed.text
    assert "persisted-legacy-secret-value" not in listed.text
    assert "persisted-url-secret" not in listed.text
    assert "persisted-metadata-secret" not in listed.text
    legacy = next(item for item in listed.json()["manifests"] if item["id"] == "legacy-signing-manifest")
    assert legacy["signing_configuration_valid"] is False
    assert legacy["payload"]["apps"]["family-mobile"]["signing"] == {
        "mode": "legacy_invalid",
        "requires_reconfiguration": True,
    }
    assert legacy["payload"]["apps"]["family-mobile"]["api_url"] == "https://redacted.invalid/"
    assert legacy["payload"]["metadata"]["nested"]["signing_password"] == "[redacted]"


def test_build_quota_and_retry_state_are_enforced_transactionally(local_env):
    tenant_id = local_env.alpha_tenant["id"]
    control = local_env.client.app.state.data_router.control
    control.execute(
        "UPDATE platform_tenants SET quotas_json=? WHERE id=?",
        (json.dumps({"max_concurrent_builds": 1}), tenant_id),
    )
    brand_version = _publish_brand(local_env)
    _activate_entitlement(local_env)
    manifest = local_env.client.post(
        "/api/v1/apps/manifests",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "manifest-build-quota"}),
        json=_manifest(local_env, brand_version),
    )
    assert manifest.status_code == 201, manifest.text

    payload = {"manifest_id": manifest.json()["id"], "platforms": ["pwa"], "products": ["family-mobile"]}
    first = local_env.client.post(
        "/api/v1/apps/builds",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "build-quota-first"}),
        json=payload,
    )
    assert first.status_code == 202, first.text
    first_id = first.json()["build_id"]

    replay = local_env.client.post(
        "/api/v1/apps/builds",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "build-quota-first"}),
        json=payload,
    )
    assert replay.status_code == 202, replay.text
    assert replay.json()["build_id"] == first_id

    blocked = local_env.client.post(
        "/api/v1/apps/builds",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "build-quota-second-blocked"}),
        json=payload,
    )
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["code"] == "TENANT_QUOTA_EXCEEDED"

    invalid_retry = local_env.client.post(
        f"/api/v1/platform/tenants/{tenant_id}/apps/builds/{first_id}/retry",
        headers=local_env.platform_headers(),
        json={"reason": "Build ainda não falhou e não pode ser reenfileirado"},
    )
    assert invalid_retry.status_code == 409, invalid_retry.text
    assert invalid_retry.json()["code"] == "APP_BUILD_NOT_FAILED"

    store = local_env.client.app.state.data_router.tenant_store(tenant_id)
    store.execute("UPDATE app_build_requests SET status='failed' WHERE id=?", (first_id,))
    store.execute("UPDATE app_build_jobs SET status='failed' WHERE build_request_id=?", (first_id,))
    second = local_env.client.post(
        "/api/v1/apps/builds",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "build-quota-second"}),
        json=payload,
    )
    assert second.status_code == 202, second.text

    retry_at_capacity = local_env.client.post(
        f"/api/v1/platform/tenants/{tenant_id}/apps/builds/{first_id}/retry",
        headers=local_env.platform_headers(),
        json={"reason": "Retry bloqueado enquanto outro build ocupa a capacidade"},
    )
    assert retry_at_capacity.status_code == 409, retry_at_capacity.text
    assert retry_at_capacity.json()["code"] == "TENANT_QUOTA_EXCEEDED"

    second_id = second.json()["build_id"]
    store.execute("UPDATE app_build_requests SET status='completed' WHERE id=?", (second_id,))
    store.execute("UPDATE app_build_jobs SET status='completed' WHERE build_request_id=?", (second_id,))
    retried = local_env.client.post(
        f"/api/v1/platform/tenants/{tenant_id}/apps/builds/{first_id}/retry",
        headers=local_env.platform_headers(),
        json={"reason": "Capacidade liberada para reenfileirar o build com falha"},
    )
    assert retried.status_code == 200, retried.text
    assert retried.json()["status"] == "queued"
