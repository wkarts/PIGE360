from __future__ import annotations

import base64
import hashlib

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
