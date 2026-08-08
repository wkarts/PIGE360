from __future__ import annotations

import base64


def _brand_payload(name: str, primary: str) -> dict:
    return {
        "legal_name": f"{name} Educação Ltda.",
        "trade_name": name,
        "short_name": name,
        "slug": name.lower().replace(" ", "-"),
        "app_display_name": name,
        "publisher_name": name,
        "support_name": f"Suporte {name}",
        "support_email": f"suporte@{name.lower().replace(' ', '')}.example.com",
        "primary_domain": f"{name.lower().replace(' ', '-')}.school.local",
        "primary_color": primary,
        "secondary_color": "#006D77",
        "accent_color": "#F59E0B",
        "typography_family": "Inter",
        "light_theme": {"surface": "#FFFFFF", "text": "#0D1B2A"},
        "dark_theme": {"surface": "#0D1B2A", "text": "#F2F4F7"},
        "co_branding_policy": "disabled",
    }


def test_branding_is_versioned_and_never_leaks_between_tenants(local_env):
    alpha_preview = local_env.client.post("/api/v1/branding/preview", headers=local_env.alpha_headers(), json={"changes": _brand_payload("Alpha", "#005577")})
    assert alpha_preview.status_code == 200, alpha_preview.text
    assert alpha_preview.json()["contrast"]["primary_color"]["on_white"]["passes_aa"] is True
    tiny_svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><rect width="32" height="32" fill="#005577"/></svg>'
    asset_alpha = local_env.client.post("/api/v1/branding/assets", headers=local_env.alpha_headers(), json={"category":"logo_symbol","filename":"alpha-symbol.svg","content_base64":base64.b64encode(tiny_svg).decode(),"mime_type":"image/svg+xml"})
    assert asset_alpha.status_code == 201, asset_alpha.text
    alpha_publish = local_env.client.post(
        "/api/v1/branding/publish",
        headers=local_env.alpha_headers(),
        json={"payload": _brand_payload("Alpha", "#005577"), "reason": "Branding inicial aprovado"},
    )
    assert alpha_publish.status_code == 200, alpha_publish.text
    assert alpha_publish.json()["version"] == 1

    beta_svg = tiny_svg.replace(b"#005577", b"#7A1F5D")
    asset_beta = local_env.client.post("/api/v1/branding/assets", headers=local_env.beta_headers(), json={"category":"logo_symbol","filename":"beta-symbol.svg","content_base64":base64.b64encode(beta_svg).decode(),"mime_type":"image/svg+xml"})
    assert asset_beta.status_code == 201, asset_beta.text
    beta_publish = local_env.client.post(
        "/api/v1/branding/publish",
        headers=local_env.beta_headers(),
        json={"payload": _brand_payload("Beta", "#7A1F5D"), "reason": "Branding próprio do tenant Beta"},
    )
    assert beta_publish.status_code == 200

    alpha = local_env.client.get("/api/v1/branding/current", headers=local_env.alpha_headers()).json()
    beta = local_env.client.get("/api/v1/branding/current", headers=local_env.beta_headers()).json()
    assert alpha["payload"]["trade_name"] == "Alpha"
    assert beta["payload"]["trade_name"] == "Beta"
    assert alpha["active_version"] == 1 and beta["active_version"] == 1
    assert "PIGE360" not in str(alpha["payload"])
    assert "PIGE360" not in str(beta["payload"])

    second = local_env.client.post(
        "/api/v1/branding/publish",
        headers=local_env.alpha_headers(),
        json={"payload": _brand_payload("Alpha Renovado", "#004466"), "reason": "Nova versão institucional"},
    )
    assert second.status_code == 200
    rolled = local_env.client.post(
        "/api/v1/branding/rollback",
        headers=local_env.alpha_headers(),
        json={"version": 1, "reason": "Rollback visual aprovado"},
    )
    assert rolled.status_code == 200
    current = local_env.client.get("/api/v1/branding/current", headers=local_env.alpha_headers()).json()
    assert current["payload"]["trade_name"] == "Alpha"


def test_brand_asset_is_hashed_and_stored_in_tenant_boundary(local_env):
    tiny_svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><rect width="32" height="32" fill="#005577"/></svg>'
    response = local_env.client.post(
        "/api/v1/branding/assets",
        headers=local_env.alpha_headers(),
        json={"category": "logo_symbol", "filename": "symbol.svg", "content_base64": base64.b64encode(tiny_svg).decode(), "mime_type": "image/svg+xml"},
    )
    assert response.status_code == 201, response.text
    asset = response.json()
    assert len(asset["sha256"]) == 64
    tenant_root = local_env.client.app.state.data_router.tenant_storage_path(local_env.alpha_tenant["id"]).resolve()
    stored = (tenant_root / asset["storage_key"]).resolve()
    stored.relative_to(tenant_root)
    assert stored.is_file()
