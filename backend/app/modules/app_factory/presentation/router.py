from __future__ import annotations

import hashlib
import hmac
import json
import re
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, Header, Request, Response, UploadFile
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, ValidationError, model_validator

from app.shared.application.idempotency import canonical_hash
from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser, current_user
from app.shared.tenant_quotas import tenant_quota_limit

router = APIRouter(tags=["app-factory"])

PRODUCTS = {
    "family-mobile", "teacher-mobile", "student-mobile", "admin-mobile", "pos-mobile",
    "kiosk", "timeclock", "desktop-admin", "pos-desktop", "pwa",
}
PLATFORMS = {
    "pwa", "android-apk", "android-aab", "ios-app", "ios-xcarchive", "ios-ipa-unsigned",
    "windows-x64", "windows-x86", "linux-x64", "linux-arm64", "macos-intel", "macos-apple",
}
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z.-]+))?$" )
BUILD_ADMIN_ROLES = {"platform_super_admin", "platform_admin"}
TENANT_APP_ROLES = {"tenant_owner", "institution_director"}
SECRET_REFERENCE_PATTERN = r"^secret://[A-Za-z0-9_.-]{1,120}$"
SENSITIVE_METADATA_KEY = re.compile(
    r"(?:^|[_.-])(?:password|passwd|passphrase|secret|credential|credentials|token|"
    r"private[_.-]?key|keystore|key[_.-]?password|provisioning[_.-]?profile|"
    r"pkcs12|p12)(?:$|[_.-])",
    flags=re.IGNORECASE,
)
PRIVATE_MATERIAL_VALUE = re.compile(
    r"-----BEGIN [A-Z0-9 ]*(?:PRIVATE KEY|PKCS12)[A-Z0-9 ]*-----|"
    r"^[a-z][a-z0-9+.-]*://[^/@\s:]+:[^/@\s]+@",
    flags=re.IGNORECASE,
)
PLATFORM_SIGNING_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "android-apk": (
        "android_keystore_reference",
        "android_key_alias_reference",
        "android_key_password_reference",
    ),
    "android-aab": (
        "android_keystore_reference",
        "android_key_alias_reference",
        "android_key_password_reference",
    ),
    "ios-app": ("ios_certificate_reference", "ios_provisioning_profile_reference"),
    "ios-xcarchive": ("ios_certificate_reference", "ios_provisioning_profile_reference"),
    "windows-x64": ("windows_certificate_reference",),
    "windows-x86": ("windows_certificate_reference",),
    "macos-intel": ("macos_certificate_reference",),
    "macos-apple": ("macos_certificate_reference",),
}


def _validate_public_metadata(value: Any) -> None:
    """Impede material sensível em metadata livre, inclusive aninhada.

    Referências de assinatura possuem contrato próprio em ``TenantApp.signing``;
    aceitá-las novamente em metadata reabriria um canal não tipado que também é
    copiado para audit/outbox.
    """

    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            for key, item in current.items():
                if SENSITIVE_METADATA_KEY.search(str(key)):
                    raise ValueError(
                        "Metadata do manifesto não aceita credenciais ou material de assinatura; use apps[*].signing"
                    )
                pending.append(item)
        elif isinstance(current, (list, tuple)):
            pending.extend(current)
        elif isinstance(current, str) and PRIVATE_MATERIAL_VALUE.search(current.strip()):
            raise ValueError(
                "Metadata do manifesto não aceita credenciais, userinfo em URL ou chaves privadas"
            )


def _redact_legacy_metadata(value: Any) -> tuple[Any, bool]:
    """Sanitiza manifestos anteriores sem devolver o material rejeitado hoje."""

    if isinstance(value, dict):
        result: dict[str, Any] = {}
        valid = True
        for key, item in value.items():
            if SENSITIVE_METADATA_KEY.search(str(key)):
                result[str(key)] = "[redacted]"
                valid = False
                continue
            sanitized, item_valid = _redact_legacy_metadata(item)
            result[str(key)] = sanitized
            valid = valid and item_valid
        return result, valid
    if isinstance(value, list):
        result_list: list[Any] = []
        valid = True
        for item in value:
            sanitized, item_valid = _redact_legacy_metadata(item)
            result_list.append(sanitized)
            valid = valid and item_valid
        return result_list, valid
    if isinstance(value, str) and PRIVATE_MATERIAL_VALUE.search(value.strip()):
        return "[redacted]", False
    return value, True


class AppSigningReferences(BaseModel):
    """Referências lógicas de signing; valores secretos nunca entram no manifesto."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    mode: Literal["unsigned", "managed"] = "unsigned"
    android_keystore_reference: str | None = Field(default=None, pattern=SECRET_REFERENCE_PATTERN)
    android_key_alias_reference: str | None = Field(default=None, pattern=SECRET_REFERENCE_PATTERN)
    android_key_password_reference: str | None = Field(default=None, pattern=SECRET_REFERENCE_PATTERN)
    ios_certificate_reference: str | None = Field(default=None, pattern=SECRET_REFERENCE_PATTERN)
    ios_provisioning_profile_reference: str | None = Field(default=None, pattern=SECRET_REFERENCE_PATTERN)
    macos_certificate_reference: str | None = Field(default=None, pattern=SECRET_REFERENCE_PATTERN)
    windows_certificate_reference: str | None = Field(default=None, pattern=SECRET_REFERENCE_PATTERN)

    @model_validator(mode="after")
    def validate_mode(self):
        references = [
            value
            for key, value in self.model_dump().items()
            if key.endswith("_reference") and value is not None
        ]
        if self.mode == "managed" and not references:
            raise ValueError("Signing gerenciado exige ao menos uma referência secret://")
        if self.mode == "unsigned" and references:
            raise ValueError("Signing unsigned não aceita referências de credencial")
        return self


class TenantApp(BaseModel):
    enabled: bool = True
    display_name: str = Field(min_length=2, max_length=100)
    identifier: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9.-]{4,254}$")
    api_url: HttpUrl
    web_url: HttpUrl
    update_url: HttpUrl
    icon_asset_id: str | None = None
    splash_asset_id: str | None = None
    features: dict[str, bool] = Field(default_factory=dict)
    signing: AppSigningReferences = Field(default_factory=AppSigningReferences)

    @model_validator(mode="after")
    def validate_public_urls(self):
        for field_name in ("api_url", "web_url", "update_url"):
            url = getattr(self, field_name)
            if url.username is not None or url.password is not None:
                raise ValueError(f"{field_name} não aceita credenciais embutidas (userinfo)")
        return self


class AppManifestInput(BaseModel):
    tenant_code: str
    brand_version: int = Field(ge=1)
    release_channel: Literal["stable", "beta", "homologation"] = "stable"
    apps: dict[str, TenantApp]
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_apps(self):
        invalid = set(self.apps) - PRODUCTS
        if invalid:
            raise ValueError(f"Produtos desconhecidos: {sorted(invalid)}")
        enabled = [app for app in self.apps.values() if app.enabled]
        if not enabled:
            raise ValueError("Ao menos um aplicativo deve estar habilitado")
        identifiers = [app.identifier for app in enabled]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Identifiers duplicados")
        _validate_public_metadata(self.metadata)
        return self


class EntitlementInput(BaseModel):
    app_product: str
    state: Literal["active", "suspended", "revoked"] = "active"
    valid_until: str | None = None
    contract_reference: str | None = None

    @model_validator(mode="after")
    def validate_product(self):
        if self.app_product not in PRODUCTS:
            raise ValueError("Produto de aplicativo inválido")
        return self


class BuildInput(BaseModel):
    manifest_id: str
    platforms: list[str] = Field(min_length=1)
    products: list[str] | None = None

    @model_validator(mode="after")
    def validate_values(self):
        invalid_platforms = set(self.platforms) - PLATFORMS
        if invalid_platforms:
            raise ValueError(f"Plataformas desconhecidas: {sorted(invalid_platforms)}")
        if self.products:
            invalid_products = set(self.products) - PRODUCTS
            if invalid_products:
                raise ValueError(f"Produtos desconhecidos: {sorted(invalid_products)}")
        return self


class BuildRetryInput(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


class BuilderClaimInput(BaseModel):
    worker_id: str = Field(min_length=3, max_length=120)
    operating_system: Literal["linux", "windows", "macos"]
    supported_platforms: list[str] = Field(min_length=1)


class JobFailureInput(BaseModel):
    tenant_id: str
    error: str = Field(min_length=3, max_length=4000)


class JobCompleteInput(BaseModel):
    tenant_id: str


class ReleaseCreateInput(BaseModel):
    build_request_id: str
    version: str
    channel: Literal["stable", "beta", "homologation"] = "stable"
    changelog: str = ""
    mandatory: bool = False

    @model_validator(mode="after")
    def validate_version(self):
        if not SEMVER.fullmatch(self.version):
            raise ValueError("Versão deve seguir Semantic Versioning")
        return self


class ReleaseAction(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


def _platform_admin(user: CurrentUser) -> None:
    if user.plane != "platform" or not set(user.roles).intersection(BUILD_ADMIN_ROLES):
        raise DomainError("PERMISSION_DENIED", "Acesso global insuficiente.", 403)


def _target(request: Request, user: CurrentUser, tenant_id: str | None):
    if tenant_id:
        _platform_admin(user)
        row = request.app.state.data_router.control.fetch_one("SELECT id FROM platform_tenants WHERE id=?", (tenant_id,))
        if not row:
            raise DomainError("TENANT_NOT_FOUND", "Tenant não localizado.", 404)
        return tenant_id, request.app.state.data_router.tenant_store(tenant_id)
    if user.plane != "tenant" or not user.tenant_id:
        raise DomainError("TENANT_ROUTE_REQUIRED", "Domínio tenant necessário.", 404)
    return user.tenant_id, request.state.store


def _safe_manifest_payload(raw: str) -> tuple[dict[str, Any], bool]:
    payload = json.loads(raw)
    valid = True
    metadata, metadata_valid = _redact_legacy_metadata(payload.get("metadata", {}))
    payload["metadata"] = metadata
    valid = valid and metadata_valid
    for app in payload.get("apps", {}).values():
        if not isinstance(app, dict):
            continue
        try:
            app["signing"] = AppSigningReferences.model_validate(
                app.get("signing") or {}
            ).model_dump(exclude_none=True)
        except ValidationError:
            # Manifestos legados eventualmente persistidos com valores livres
            # nunca devolvem esses valores para API, auditoria ou build agent.
            app["signing"] = {
                "mode": "legacy_invalid",
                "requires_reconfiguration": True,
            }
            valid = False
        for field_name in ("api_url", "web_url", "update_url"):
            try:
                url = HttpUrl(str(app.get(field_name) or ""))
            except (TypeError, ValueError):
                continue
            if url.username is not None or url.password is not None:
                app[field_name] = "https://redacted.invalid/"
                valid = False
    return payload, valid


def _manifest(row: dict[str, Any]) -> dict[str, Any]:
    payload, signing_configuration_valid = _safe_manifest_payload(row["payload_json"])
    return {
        "id": row["id"], "tenant_id": row["tenant_id"], "version": row["version"], "state": row["state"],
        "payload": payload, "sha256": row["sha256"], "created_by": row["created_by"],
        "signing_configuration_valid": signing_configuration_valid,
        "created_at": row["created_at"],
    }


def _validate_stable_ids(store, tenant_id: str, payload: dict[str, Any]) -> None:
    previous = store.fetch_one(
        "SELECT payload_json FROM tenant_app_manifests WHERE tenant_id=? ORDER BY version DESC LIMIT 1", (tenant_id,)
    )
    if not previous:
        return
    old = json.loads(previous["payload_json"]).get("apps", {})
    for product, app in payload.get("apps", {}).items():
        if product in old and old[product].get("identifier") != app.get("identifier"):
            raise DomainError("APP_IDENTIFIER_IMMUTABLE", f"O identifier de {product} não pode mudar após a reserva inicial.", 409)


def _validate_brand_and_assets(store, tenant_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    brand = store.fetch_one(
        "SELECT id,version,state,payload_json,sha256 FROM brand_versions WHERE tenant_id=? AND version=?",
        (tenant_id, payload["brand_version"]),
    )
    if not brand or brand["state"] not in {"active", "superseded"}:
        raise DomainError("BRAND_VERSION_NOT_READY", "Versão de branding publicada não localizada.", 409)
    for product, app in payload["apps"].items():
        if not app.get("enabled"):
            continue
        for field in ("icon_asset_id", "splash_asset_id"):
            asset_id = app.get(field)
            if asset_id and not store.fetch_one("SELECT id FROM brand_assets WHERE tenant_id=? AND id=?", (tenant_id, asset_id)):
                raise DomainError("BRAND_ASSET_NOT_FOUND", f"Ativo {field} de {product} não pertence ao tenant.", 422)
    return brand


def _create_manifest(tenant_id: str, store, data: AppManifestInput, request: Request, user: CurrentUser):
    body = {"tenant_id": tenant_id, **data.model_dump(mode="json")}
    _validate_stable_ids(store, tenant_id, body)
    _validate_brand_and_assets(store, tenant_id, body)
    digest = canonical_hash(body)
    existing = store.fetch_one("SELECT * FROM tenant_app_manifests WHERE tenant_id=? AND sha256=?", (tenant_id, digest))
    if existing:
        return _manifest(existing)
    latest = store.scalar("SELECT MAX(version) AS n FROM tenant_app_manifests WHERE tenant_id=?", (tenant_id,)) or 0
    version = int(latest) + 1
    now = iso_now(); manifest_id = uuid7()
    with store.transaction() as conn:
        conn.execute(
            "INSERT INTO tenant_app_manifests(id,tenant_id,version,state,payload_json,sha256,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (manifest_id, tenant_id, version, "ready", json.dumps(body, ensure_ascii=False, sort_keys=True), digest, user.id, now),
        )
        result = {"id": manifest_id, "tenant_id": tenant_id, "version": version, "state": "ready", "payload": body, "sha256": digest, "created_by": user.id, "signing_configuration_valid": True, "created_at": now}
        add_audit(conn, tenant_id=tenant_id, actor_id=user.id, action="create_manifest", aggregate_type="tenant_app_manifest", aggregate_id=manifest_id, correlation_id=request.state.correlation_id, after=result)
        add_outbox(conn, tenant_id=tenant_id, event_type="TenantAppManifestCreated", aggregate_type="tenant_app_manifest", aggregate_id=manifest_id, payload=result, correlation_id=request.state.correlation_id)
    return result


@router.post("/platform/tenants/{tenant_id}/apps/entitlements", status_code=201, operation_id="set_platform_tenant_app_entitlement")
def set_entitlement(tenant_id: str, data: EntitlementInput, request: Request, user: CurrentUser = Depends(current_user)):
    tid, store = _target(request, user, tenant_id)
    now = iso_now()
    existing = store.fetch_one("SELECT * FROM tenant_app_entitlements WHERE tenant_id=? AND app_product=?", (tid, data.app_product))
    entitlement_id = existing["id"] if existing else uuid7()
    with store.transaction() as conn:
        if existing:
            conn.execute(
                "UPDATE tenant_app_entitlements SET state=?,valid_until=?,contract_reference=?,updated_at=? WHERE id=?",
                (data.state, data.valid_until, data.contract_reference, now, entitlement_id),
            )
        else:
            conn.execute(
                "INSERT INTO tenant_app_entitlements(id,tenant_id,app_product,state,valid_from,valid_until,contract_reference,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (entitlement_id, tid, data.app_product, data.state, now, data.valid_until, data.contract_reference, user.id, now, now),
            )
        result = {"id": entitlement_id, "tenant_id": tid, **data.model_dump(), "valid_from": existing["valid_from"] if existing else now, "updated_at": now}
        add_audit(conn, tenant_id=tid, actor_id=user.id, action="set_entitlement", aggregate_type="tenant_app_entitlement", aggregate_id=entitlement_id, correlation_id=request.state.correlation_id, after=result)
        add_outbox(conn, tenant_id=tid, event_type="TenantAppPackagePurchased" if data.state == "active" else "TenantAppEntitlementChanged", aggregate_type="tenant_app_entitlement", aggregate_id=entitlement_id, payload=result, correlation_id=request.state.correlation_id)
    return result


@router.get("/platform/tenants/{tenant_id}/apps", operation_id="list_platform_tenant_apps")
def list_apps(tenant_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    tid, store = _target(request, user, tenant_id)
    manifests = [_manifest(x) for x in store.fetch_all("SELECT * FROM tenant_app_manifests WHERE tenant_id=? ORDER BY version DESC", (tid,))]
    entitlements = store.fetch_all("SELECT * FROM tenant_app_entitlements WHERE tenant_id=? ORDER BY app_product", (tid,))
    builds = [_build_result(store, row["id"]) for row in store.fetch_all("SELECT id FROM app_build_requests WHERE tenant_id=? ORDER BY created_at DESC", (tid,))]
    releases = store.fetch_all("SELECT * FROM app_releases WHERE tenant_id=? ORDER BY created_at DESC", (tid,))
    return {"tenant_id": tid, "entitlements": entitlements, "manifests": manifests, "builds": builds, "releases": releases}


@router.post("/platform/tenants/{tenant_id}/apps/manifests", status_code=201, operation_id="create_platform_tenant_app_manifest")
def create_manifest_platform(tenant_id: str, data: AppManifestInput, request: Request, idempotency_key: str = Header(alias="Idempotency-Key", min_length=8), user: CurrentUser = Depends(current_user)):
    tid, store = _target(request, user, tenant_id)
    return _create_manifest(tid, store, data, request, user)


@router.post("/apps/manifests", status_code=201, operation_id="create_current_tenant_app_manifest")
def create_manifest_tenant(data: AppManifestInput, request: Request, idempotency_key: str = Header(alias="Idempotency-Key", min_length=8), user: CurrentUser = Depends(current_user)):
    if not set(user.roles).intersection(TENANT_APP_ROLES):
        raise DomainError("PERMISSION_DENIED", "Sem permissão para manifestos.", 403)
    tid, store = _target(request, user, None)
    return _create_manifest(tid, store, data, request, user)


def _platform_spec(platform: str) -> tuple[str, str]:
    if platform == "pwa": return "linux", "universal"
    if platform.startswith("android-"): return "linux", "universal"
    if platform in {"ios-app", "ios-xcarchive", "ios-ipa-unsigned"}: return "macos", "arm64"
    if platform == "windows-x64": return "windows", "x64"
    if platform == "windows-x86": return "windows", "x86"
    if platform == "linux-x64": return "linux", "x64"
    if platform == "linux-arm64": return "linux", "arm64"
    if platform == "macos-intel": return "macos", "x64"
    if platform == "macos-apple": return "macos", "arm64"
    raise DomainError("INVALID_BUILD_PLATFORM", "Plataforma de build inválida.", 422)


def _signing_expectation(app: dict[str, Any], platform: str) -> str:
    signing = app.get("signing") or {"mode": "unsigned"}
    mode = signing.get("mode", "unsigned")
    if platform == "ios-ipa-unsigned":
        if mode == "managed":
            raise DomainError(
                "APP_SIGNING_TARGET_CONFLICT",
                "ios-ipa-unsigned não aceita configuração de assinatura gerenciada.",
                422,
            )
        return "unsigned"
    required = PLATFORM_SIGNING_REQUIREMENTS.get(platform, ())
    if mode != "managed" or not required:
        return "unsigned"
    missing = [field for field in required if not signing.get(field)]
    if missing:
        raise DomainError(
            "APP_SIGNING_REFERENCES_INCOMPLETE",
            f"A assinatura gerenciada para {platform} exige todas as referências tipadas da plataforma.",
            422,
        )
    return "managed"


def _compatible(product: str, platform: str) -> bool:
    if platform == "pwa": return True
    if product in {"family-mobile", "teacher-mobile", "student-mobile", "admin-mobile", "pos-mobile"}:
        return platform.startswith("android-") or platform.startswith("ios-")
    if product in {"kiosk", "timeclock"}:
        return platform.startswith("android-") or platform.startswith("windows-") or platform.startswith("linux-")
    if product in {"desktop-admin", "pos-desktop"}:
        return platform.startswith("windows-") or platform.startswith("linux-") or platform.startswith("macos-")
    return product == "pwa" and platform == "pwa"


def _assets_for_app(store, tenant_id: str, app: dict[str, Any]) -> list[dict[str, Any]]:
    ids = [x for x in (app.get("icon_asset_id"), app.get("splash_asset_id")) if x]
    if not ids:
        return []
    items = []
    for asset_id in ids:
        row = store.fetch_one("SELECT id,category,storage_key,mime_type,bytes,sha256 FROM brand_assets WHERE tenant_id=? AND id=?", (tenant_id, asset_id))
        if not row:
            raise DomainError("BRAND_ASSET_NOT_FOUND", "Ativo do manifesto não localizado.", 409)
        items.append(row)
    return items


def _build_spec(request: Request, store, tenant_id: str, manifest: dict[str, Any], product: str, platform: str) -> dict[str, Any]:
    payload = manifest["payload"]; app = payload["apps"][product]; required_os, arch = _platform_spec(platform)
    signing_expectation = _signing_expectation(app, platform)
    spec = {
        "schema_version": 1,
        "tenant_id": tenant_id,
        "tenant_code": payload["tenant_code"],
        "manifest_id": manifest["id"],
        "manifest_version": manifest["version"],
        "manifest_sha256": manifest["sha256"],
        "brand_version": payload["brand_version"],
        "release_channel": payload["release_channel"],
        "app_product": product,
        "app": app,
        "platform": platform,
        "architecture": arch,
        "required_os": required_os,
        "signing_expectation": signing_expectation,
        "assets": _assets_for_app(store, tenant_id, app),
        "source_version": request.app.state.settings.version,
    }
    return spec


def _build_result(store, build_id: str) -> dict[str, Any]:
    row = store.fetch_one("SELECT * FROM app_build_requests WHERE id=?", (build_id,))
    if not row:
        raise DomainError("APP_BUILD_NOT_FOUND", "Build não localizado.", 404)
    jobs = store.fetch_all("SELECT * FROM app_build_jobs WHERE build_request_id=? ORDER BY app_product,platform,architecture", (build_id,))
    artifacts = store.fetch_all("SELECT * FROM app_build_artifacts WHERE build_request_id=? ORDER BY created_at", (build_id,))
    return {
        "build_id": row["id"], "tenant_id": row["tenant_id"], "manifest_id": row["manifest_id"], "status": row["status"],
        "requested_platforms": json.loads(row["requested_platforms_json"]), "created_at": row["created_at"],
        "started_at": row["started_at"], "finished_at": row["finished_at"], "jobs": jobs, "artifacts": artifacts,
    }


def _request_build(tenant_id: str, store, data: BuildInput, request: Request, user: CurrentUser, idempotency_key: str):
    existing = store.fetch_one("SELECT id FROM app_build_requests WHERE tenant_id=? AND idempotency_key=?", (tenant_id, idempotency_key))
    if existing:
        return _build_result(store, existing["id"])
    manifest_row = store.fetch_one("SELECT * FROM tenant_app_manifests WHERE id=? AND tenant_id=? AND state='ready'", (data.manifest_id, tenant_id))
    if not manifest_row:
        raise DomainError("APP_MANIFEST_NOT_FOUND", "Manifesto pronto não localizado.", 404)
    manifest = _manifest(manifest_row); _validate_brand_and_assets(store, tenant_id, manifest["payload"])
    if not manifest["signing_configuration_valid"]:
        raise DomainError(
            "APP_SIGNING_CONFIGURATION_INVALID",
            "O manifesto legado contém configuração de assinatura insegura e deve ser recriado com referências secret://.",
            409,
        )
    enabled = {name for name, app in manifest["payload"]["apps"].items() if app.get("enabled")}
    products = set(data.products or enabled)
    if not products or not products.issubset(enabled):
        raise DomainError("APP_PRODUCT_NOT_ENABLED", "Há produtos solicitados que não estão habilitados no manifesto.", 422)
    for product in sorted(products):
        entitlement = store.fetch_one("SELECT state,valid_until FROM tenant_app_entitlements WHERE tenant_id=? AND app_product=?", (tenant_id, product))
        if not entitlement or entitlement["state"] != "active":
            raise DomainError("APP_ENTITLEMENT_REQUIRED", f"O produto {product} não possui entitlement ativo.", 409)
    jobs_to_create = []
    for product in sorted(products):
        for platform in sorted(set(data.platforms)):
            if not _compatible(product, platform):
                continue
            spec = _build_spec(request, store, tenant_id, manifest, product, platform)
            jobs_to_create.append((spec, canonical_hash(spec)))
    if not jobs_to_create:
        raise DomainError("NO_COMPATIBLE_BUILD_TARGET", "Nenhum produto é compatível com as plataformas solicitadas.", 422)
    build_id = uuid7(); now = iso_now()
    limit = tenant_quota_limit(
        request.app.state.data_router.control,
        tenant_id,
        "max_concurrent_builds",
    )
    with store.transaction() as conn:
        store.transaction_lock(conn, f"tenant-build-quota:{tenant_id}")
        raced = conn.execute(
            "SELECT id FROM app_build_requests WHERE tenant_id=? AND idempotency_key=?",
            (tenant_id, idempotency_key),
        ).fetchone()
        if raced:
            return _build_result(store, raced["id"])
        concurrent = conn.execute(
            "SELECT COUNT(*) AS n FROM app_build_requests WHERE tenant_id=? AND status IN ('queued','building')",
            (tenant_id,),
        ).fetchone()
        if int(concurrent["n"] if concurrent else 0) >= limit:
            raise DomainError(
                "TENANT_QUOTA_EXCEEDED",
                f"A quota de builds simultâneos ({limit}) foi atingida.",
                409,
            )
        conn.execute(
            "INSERT INTO app_build_requests(id,tenant_id,manifest_id,status,requested_platforms_json,result_json,idempotency_key,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (build_id, tenant_id, manifest["id"], "queued", json.dumps(sorted(set(data.platforms))), None, idempotency_key, user.id, now),
        )
        for spec, digest in jobs_to_create:
            conn.execute(
                """INSERT INTO app_build_jobs(id,tenant_id,build_request_id,manifest_id,app_product,platform,architecture,status,required_os,spec_sha256,spec_json,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (uuid7(), tenant_id, build_id, manifest["id"], spec["app_product"], spec["platform"], spec["architecture"], "queued", spec["required_os"], digest, json.dumps(spec, ensure_ascii=False, sort_keys=True), now, now),
            )
        result = {"build_id": build_id, "tenant_id": tenant_id, "status": "queued", "jobs": len(jobs_to_create)}
        add_audit(conn, tenant_id=tenant_id, actor_id=user.id, action="request_build", aggregate_type="app_build", aggregate_id=build_id, correlation_id=request.state.correlation_id, after=result)
        add_outbox(conn, tenant_id=tenant_id, event_type="TenantAppBuildRequested", aggregate_type="app_build", aggregate_id=build_id, payload=result, correlation_id=request.state.correlation_id)
    return _build_result(store, build_id)


@router.post("/platform/tenants/{tenant_id}/apps/builds", status_code=202, operation_id="create_platform_tenant_app_build")
def build_platform(tenant_id: str, data: BuildInput, request: Request, idempotency_key: str = Header(alias="Idempotency-Key", min_length=8), user: CurrentUser = Depends(current_user)):
    tid, store = _target(request, user, tenant_id)
    return _request_build(tid, store, data, request, user, idempotency_key)


@router.post("/apps/builds", status_code=202, operation_id="create_current_tenant_app_build")
def build_tenant(data: BuildInput, request: Request, idempotency_key: str = Header(alias="Idempotency-Key", min_length=8), user: CurrentUser = Depends(current_user)):
    if not set(user.roles).intersection(TENANT_APP_ROLES):
        raise DomainError("PERMISSION_DENIED", "Sem permissão para builds.", 403)
    tid, store = _target(request, user, None)
    return _request_build(tid, store, data, request, user, idempotency_key)


@router.get("/platform/tenants/{tenant_id}/apps/builds/{build_id}", operation_id="get_platform_tenant_app_build")
def get_build_platform(tenant_id: str, build_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    tid, store = _target(request, user, tenant_id)
    row = store.fetch_one("SELECT id FROM app_build_requests WHERE id=? AND tenant_id=?", (build_id, tid))
    if not row: raise DomainError("APP_BUILD_NOT_FOUND", "Build não localizado.", 404)
    return _build_result(store, build_id)


@router.post("/platform/tenants/{tenant_id}/apps/builds/{build_id}/retry", operation_id="retry_platform_tenant_app_build")
def retry_build(tenant_id: str, build_id: str, data: BuildRetryInput, request: Request, user: CurrentUser = Depends(current_user)):
    tid, store = _target(request, user, tenant_id); now = iso_now()
    limit = tenant_quota_limit(
        request.app.state.data_router.control,
        tid,
        "max_concurrent_builds",
    )
    with store.transaction() as conn:
        store.transaction_lock(conn, f"tenant-build-quota:{tid}")
        row = conn.execute(
            "SELECT id,status FROM app_build_requests WHERE id=? AND tenant_id=?",
            (build_id, tid),
        ).fetchone()
        if not row: raise DomainError("APP_BUILD_NOT_FOUND", "Build não localizado.", 404)
        if row["status"] != "failed":
            raise DomainError(
                "APP_BUILD_NOT_FAILED",
                "Somente builds no estado failed podem ser reenfileirados.",
                409,
            )
        failed_jobs = conn.execute(
            "SELECT COUNT(*) AS n FROM app_build_jobs WHERE build_request_id=? AND status='failed'",
            (build_id,),
        ).fetchone()
        if int(failed_jobs["n"] if failed_jobs else 0) < 1:
            raise DomainError(
                "APP_BUILD_NOT_RETRYABLE",
                "O build não possui jobs com falha para reenfileirar.",
                409,
            )
        concurrent = conn.execute(
            "SELECT COUNT(*) AS n FROM app_build_requests WHERE tenant_id=? AND status IN ('queued','building')",
            (tid,),
        ).fetchone()
        if int(concurrent["n"] if concurrent else 0) >= limit:
            raise DomainError(
                "TENANT_QUOTA_EXCEEDED",
                f"A quota de builds simultâneos ({limit}) foi atingida.",
                409,
            )
        conn.execute("UPDATE app_build_jobs SET status='queued',claimed_by=NULL,claimed_at=NULL,started_at=NULL,finished_at=NULL,last_error=NULL,updated_at=? WHERE build_request_id=? AND status='failed'", (now, build_id))
        conn.execute("UPDATE app_build_requests SET status='queued',started_at=NULL,finished_at=NULL WHERE id=?", (build_id,))
        add_audit(conn, tenant_id=tid, actor_id=user.id, action="retry", aggregate_type="app_build", aggregate_id=build_id, correlation_id=request.state.correlation_id, reason=data.reason)
    return _build_result(store, build_id)


def _builder_auth(request: Request, token: str | None) -> None:
    expected = request.app.state.settings.build_farm_token
    if not expected or not token or not hmac.compare_digest(expected, token):
        raise DomainError("BUILD_FARM_UNAUTHORIZED", "Agente de build não autorizado.", 401)


def _active_tenants(request: Request) -> list[str]:
    return [row["id"] for row in request.app.state.data_router.control.fetch_all("SELECT id FROM platform_tenants WHERE status='active' ORDER BY created_at")]


@router.post("/platform/build-farm/jobs/claim", operation_id="claim_app_build_job")
def claim_job(data: BuilderClaimInput, request: Request, x_build_farm_token: str | None = Header(default=None, alias="X-Build-Farm-Token")):
    _builder_auth(request, x_build_farm_token)
    supported = set(data.supported_platforms) & PLATFORMS
    if not supported: raise DomainError("BUILD_FARM_NO_CAPABILITIES", "Agente não informou plataforma suportada.", 422)
    now = iso_now()
    for tenant_id in _active_tenants(request):
        store = request.app.state.data_router.tenant_store(tenant_id)
        candidates = store.fetch_all("SELECT * FROM app_build_jobs WHERE tenant_id=? AND status='queued' AND required_os=? ORDER BY created_at,id", (tenant_id, data.operating_system))
        job = next((row for row in candidates if row["platform"] in supported), None)
        if not job: continue
        with store.transaction() as conn:
            claimed = conn.execute(
                """UPDATE app_build_jobs
                   SET status='building',claimed_by=?,claimed_at=?,started_at=?,attempts=attempts+1,updated_at=?
                   WHERE id=? AND tenant_id=? AND status='queued'""",
                (data.worker_id, now, now, now, job["id"], tenant_id),
            ).rowcount
            # Compare-and-set é necessário no PostgreSQL: dois workers podem
            # observar o mesmo candidato antes de qualquer um adquirir o row lock.
            if claimed != 1:
                continue
            conn.execute("UPDATE app_build_requests SET status='building',started_at=COALESCE(started_at,?) WHERE id=?", (now, job["build_request_id"]))
        spec = json.loads(job["spec_json"])
        return {"job_id": job["id"], "tenant_id": tenant_id, "spec_sha256": job["spec_sha256"], "spec": spec}
    return Response(status_code=204)


def _job_store(request: Request, tenant_id: str, job_id: str):
    store = request.app.state.data_router.tenant_store(tenant_id)
    job = store.fetch_one("SELECT * FROM app_build_jobs WHERE tenant_id=? AND id=?", (tenant_id, job_id))
    if not job: raise DomainError("APP_BUILD_JOB_NOT_FOUND", "Job de build não localizado.", 404)
    return store, job


@router.get("/platform/build-farm/jobs/{job_id}/assets/{asset_id}", operation_id="download_app_build_asset")
def download_build_asset(job_id: str, asset_id: str, tenant_id: str, request: Request, x_build_farm_token: str | None = Header(default=None, alias="X-Build-Farm-Token")):
    _builder_auth(request, x_build_farm_token); store, job = _job_store(request, tenant_id, job_id)
    spec = json.loads(job["spec_json"]); allowed = {item["id"]: item for item in spec.get("assets", [])}
    asset = allowed.get(asset_id)
    if not asset: raise DomainError("BUILD_ASSET_NOT_ALLOWED", "Ativo não pertence ao build spec.", 403)
    storage=request.app.state.data_router.object_storage(tenant_id)
    if not storage.exists(asset["storage_key"]): raise DomainError("BUILD_ASSET_MISSING", "Ativo do branding não está disponível.", 503)
    content=storage.get_bytes(asset["storage_key"]);digest=hashlib.sha256(content).hexdigest()
    if not hmac.compare_digest(digest,asset["sha256"]): raise DomainError("BUILD_ASSET_INTEGRITY_ERROR", "Ativo do branding falhou na verificação SHA-256.", 409)
    return Response(content=content,media_type=asset["mime_type"],headers={"X-Asset-SHA256":digest})


@router.post("/platform/build-farm/jobs/{job_id}/artifacts", status_code=201, operation_id="upload_app_build_artifact")
async def upload_artifact(
    job_id: str,
    request: Request,
    tenant_id: str = Form(...),
    artifact_kind: str = Form(...),
    sha256: str = Form(pattern=r"^[0-9a-f]{64}$"),
    signed_state: Literal["signed", "unsigned", "skipped_not_configured"] = Form("unsigned"),
    file: UploadFile = File(...),
    x_build_farm_token: str | None = Header(default=None, alias="X-Build-Farm-Token"),
):
    _builder_auth(request, x_build_farm_token); store, job = _job_store(request, tenant_id, job_id)
    if job["status"] != "building": raise DomainError("APP_BUILD_JOB_NOT_BUILDING", "Job não está em execução.", 409)
    spec = json.loads(job["spec_json"])
    signing_expectation = spec.get("signing_expectation", "unsigned")
    if signing_expectation == "managed" and signed_state != "signed":
        raise DomainError(
            "APP_ARTIFACT_SIGNING_STATE_INVALID",
            "O target exige assinatura gerenciada e o agente não declarou o artefato como assinado.",
            409,
        )
    if signing_expectation != "managed" and signed_state == "signed":
        raise DomainError(
            "APP_ARTIFACT_SIGNING_STATE_INVALID",
            "O agente declarou assinatura para um target sem configuração gerenciada correspondente.",
            409,
        )
    content = await file.read()
    digest = hashlib.sha256(content).hexdigest()
    if not hmac.compare_digest(digest, sha256): raise DomainError("ARTIFACT_HASH_MISMATCH", "SHA-256 informado não corresponde ao artefato.", 409)
    filename = Path(file.filename or f"artifact-{job_id}.bin").name
    artifact_id = uuid7(); key = f"app-factory/builds/{job['build_request_id']}/{job_id}/{artifact_id}/{filename}"
    stored = request.app.state.data_router.object_storage(tenant_id).put_bytes(key, content, content_type=file.content_type or "application/octet-stream")
    now = iso_now()
    with store.transaction() as conn:
        conn.execute(
            """INSERT INTO app_build_artifacts(id,tenant_id,build_request_id,build_job_id,app_product,platform,architecture,artifact_kind,filename,storage_key,mime_type,bytes,sha256,signed_state,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (artifact_id, tenant_id, job["build_request_id"], job_id, job["app_product"], job["platform"], job["architecture"], artifact_kind, filename, key, file.content_type or "application/octet-stream", stored.bytes, stored.sha256, signed_state, now),
        )
    return {"id": artifact_id, "job_id": job_id, "sha256": stored.sha256, "bytes": stored.bytes, "storage_key": key, "signed_state": signed_state}


def _refresh_request_state(store, build_request_id: str) -> str:
    jobs = store.fetch_all("SELECT status FROM app_build_jobs WHERE build_request_id=?", (build_request_id,))
    statuses = {j["status"] for j in jobs}
    if jobs and statuses == {"completed"}: state = "completed"
    elif "failed" in statuses: state = "failed"
    elif "building" in statuses: state = "building"
    else: state = "queued"
    finished = iso_now() if state in {"completed", "failed"} else None
    store.execute("UPDATE app_build_requests SET status=?,finished_at=? WHERE id=?", (state, finished, build_request_id))
    return state


@router.post("/platform/build-farm/jobs/{job_id}/complete", operation_id="complete_app_build_job")
def complete_job(job_id: str, data: JobCompleteInput, request: Request, x_build_farm_token: str | None = Header(default=None, alias="X-Build-Farm-Token")):
    _builder_auth(request, x_build_farm_token); store, job = _job_store(request, data.tenant_id, job_id)
    if job["status"] != "building": raise DomainError("APP_BUILD_JOB_NOT_BUILDING", "Job não está em execução.", 409)
    count = store.scalar("SELECT COUNT(*) AS n FROM app_build_artifacts WHERE build_job_id=?", (job_id,)) or 0
    if int(count) < 1: raise DomainError("APP_BUILD_ARTIFACT_REQUIRED", "O job não pode ser concluído sem artefato verificado.", 409)
    now = iso_now(); store.execute("UPDATE app_build_jobs SET status='completed',finished_at=?,updated_at=? WHERE id=?", (now, now, job_id)); state = _refresh_request_state(store, job["build_request_id"])
    return {"job_id": job_id, "status": "completed", "build_request_status": state}


@router.post("/platform/build-farm/jobs/{job_id}/fail", operation_id="fail_app_build_job")
def fail_job(job_id: str, data: JobFailureInput, request: Request, x_build_farm_token: str | None = Header(default=None, alias="X-Build-Farm-Token")):
    _builder_auth(request, x_build_farm_token); store, job = _job_store(request, data.tenant_id, job_id); now = iso_now()
    store.execute("UPDATE app_build_jobs SET status='failed',last_error=?,finished_at=?,updated_at=? WHERE id=?", (data.error, now, now, job_id)); state = _refresh_request_state(store, job["build_request_id"])
    return {"job_id": job_id, "status": "failed", "build_request_status": state}


@router.get("/platform/tenants/{tenant_id}/apps/artifacts", operation_id="list_platform_tenant_app_artifacts")
def artifacts_platform(tenant_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    tid, store = _target(request, user, tenant_id)
    return {"tenant_id": tid, "items": store.fetch_all("SELECT * FROM app_build_artifacts WHERE tenant_id=? ORDER BY created_at DESC", (tid,))}


@router.post("/platform/tenants/{tenant_id}/apps/releases", status_code=201, operation_id="create_platform_tenant_app_release")
def create_release(tenant_id: str, data: ReleaseCreateInput, request: Request, user: CurrentUser = Depends(current_user)):
    tid, store = _target(request, user, tenant_id)
    build = store.fetch_one("SELECT * FROM app_build_requests WHERE tenant_id=? AND id=?", (tid, data.build_request_id))
    if not build: raise DomainError("APP_BUILD_NOT_FOUND", "Build não localizado.", 404)
    if build["status"] != "completed": raise DomainError("APP_BUILD_NOT_COMPLETED", "Release exige build integralmente concluído.", 409)
    artifacts = store.fetch_all("SELECT id FROM app_build_artifacts WHERE tenant_id=? AND build_request_id=?", (tid, data.build_request_id))
    if not artifacts: raise DomainError("APP_BUILD_ARTIFACT_REQUIRED", "Build não possui artefatos.", 409)
    existing = store.fetch_one("SELECT id FROM app_releases WHERE tenant_id=? AND version=? AND channel=?", (tid, data.version, data.channel))
    if existing: raise DomainError("APP_RELEASE_VERSION_EXISTS", "Já existe release nesta versão/canal.", 409)
    release_id = uuid7(); now = iso_now()
    with store.transaction() as conn:
        conn.execute("INSERT INTO app_releases(id,tenant_id,build_request_id,version,channel,state,changelog,mandatory,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (release_id,tid,data.build_request_id,data.version,data.channel,"draft",data.changelog,1 if data.mandatory else 0,user.id,now))
        for item in artifacts:
            conn.execute("INSERT INTO app_release_artifacts(id,tenant_id,release_id,artifact_id,created_at) VALUES(?,?,?,?,?)", (uuid7(),tid,release_id,item["id"],now))
        result={"id":release_id,"tenant_id":tid,"version":data.version,"channel":data.channel,"state":"draft","artifact_count":len(artifacts),"created_at":now}
        add_audit(conn,tenant_id=tid,actor_id=user.id,action="create_release",aggregate_type="app_release",aggregate_id=release_id,correlation_id=request.state.correlation_id,after=result)
    return result


def _release_transition(tenant_id: str, release_id: str, target: str, data: ReleaseAction, request: Request, user: CurrentUser):
    tid, store = _target(request, user, tenant_id); row = store.fetch_one("SELECT * FROM app_releases WHERE tenant_id=? AND id=?", (tid, release_id))
    if not row: raise DomainError("APP_RELEASE_NOT_FOUND", "Release não localizada.", 404)
    if target == "published" and row["state"] != "draft": raise DomainError("INVALID_RELEASE_STATE", "Somente release draft pode ser publicada.", 409)
    if target == "revoked" and row["state"] != "published": raise DomainError("INVALID_RELEASE_STATE", "Somente release publicada pode ser revogada.", 409)
    now=iso_now()
    with store.transaction() as conn:
        if target=="published": conn.execute("UPDATE app_releases SET state='published',published_at=? WHERE id=?",(now,release_id))
        else: conn.execute("UPDATE app_releases SET state='revoked',revoked_at=?,revoke_reason=? WHERE id=?",(now,data.reason,release_id))
        result={"id":release_id,"state":target,"reason":data.reason,"changed_at":now}
        add_audit(conn,tenant_id=tid,actor_id=user.id,action=target,aggregate_type="app_release",aggregate_id=release_id,correlation_id=request.state.correlation_id,before=row,after=result,reason=data.reason)
        add_outbox(conn,tenant_id=tid,event_type="TenantAppReleasePublished" if target=="published" else "TenantAppReleaseRevoked",aggregate_type="app_release",aggregate_id=release_id,payload=result,correlation_id=request.state.correlation_id)
    return result


@router.post("/platform/tenants/{tenant_id}/apps/releases/{release_id}/publish", operation_id="publish_platform_tenant_app_release")
def publish_release(tenant_id:str,release_id:str,data:ReleaseAction,request:Request,user:CurrentUser=Depends(current_user)):
    return _release_transition(tenant_id,release_id,"published",data,request,user)


@router.post("/platform/tenants/{tenant_id}/apps/releases/{release_id}/revoke", operation_id="revoke_platform_tenant_app_release")
def revoke_release(tenant_id:str,release_id:str,data:ReleaseAction,request:Request,user:CurrentUser=Depends(current_user)):
    return _release_transition(tenant_id,release_id,"revoked",data,request,user)


def _release_details(store, tenant_id: str, release_id: str, *, published_only: bool = False):
    sql="SELECT * FROM app_releases WHERE tenant_id=? AND id=?" + (" AND state='published'" if published_only else "")
    row=store.fetch_one(sql,(tenant_id,release_id))
    if not row: raise DomainError("APP_RELEASE_NOT_FOUND","Release não localizada.",404)
    artifacts=store.fetch_all("""SELECT a.* FROM app_release_artifacts ra JOIN app_build_artifacts a ON a.id=ra.artifact_id
                                 WHERE ra.tenant_id=? AND ra.release_id=? ORDER BY a.app_product,a.platform,a.architecture""",(tenant_id,release_id))
    return {**row,"mandatory":bool(row["mandatory"]),"artifacts":artifacts}


@router.get("/apps/catalog", operation_id="get_tenant_apps_catalog")
def catalog(request:Request,user:CurrentUser=Depends(current_user)):
    tid,store=_target(request,user,None);rows=store.fetch_all("SELECT id FROM app_releases WHERE tenant_id=? AND state='published' ORDER BY published_at DESC",(tid,))
    return {"tenant_id":tid,"releases":[_release_details(store,tid,row["id"],published_only=True) for row in rows]}


@router.get("/apps/releases/{release_id}", operation_id="get_tenant_app_release")
def release(release_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    tid,store=_target(request,user,None);return _release_details(store,tid,release_id,published_only=True)


@router.get("/apps/releases/{release_id}/download", operation_id="download_tenant_app_release")
def download(release_id:str,artifact_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    tid,store=_target(request,user,None);details=_release_details(store,tid,release_id,published_only=True);artifact=next((a for a in details["artifacts"] if a["id"]==artifact_id),None)
    if not artifact: raise DomainError("APP_ARTIFACT_NOT_FOUND","Artefato não pertence à release.",404)
    storage=request.app.state.data_router.object_storage(tid)
    if not storage.exists(artifact["storage_key"]): raise DomainError("APP_ARTIFACT_MISSING","Artefato não está disponível no storage.",503)
    content=storage.get_bytes(artifact["storage_key"]);digest=hashlib.sha256(content).hexdigest()
    if not hmac.compare_digest(digest,artifact["sha256"]): raise DomainError("ARTIFACT_INTEGRITY_ERROR","Integridade do artefato inválida.",409)
    with store.transaction() as conn:
        conn.execute("INSERT INTO app_download_events(id,tenant_id,release_id,artifact_id,user_id,ip,user_agent,created_at) VALUES(?,?,?,?,?,?,?,?)",(uuid7(),tid,release_id,artifact_id,user.id,request.client.host if request.client else None,request.headers.get("user-agent"),iso_now()))
    headers={"Content-Disposition":f'attachment; filename="{Path(artifact["filename"]).name}"',"X-Artifact-SHA256":digest}
    return Response(content=content,media_type=artifact["mime_type"],headers=headers)


def _semver_key(value:str):
    m=SEMVER.fullmatch(value);return (int(m.group(1)),int(m.group(2)),int(m.group(3)),0 if m.group(4) else 1,m.group(4) or "") if m else (0,0,0,0,value)


@router.get("/apps/update/{app}/{platform}/{arch}", operation_id="check_tenant_app_update")
def update_manifest(app:str,platform:str,arch:str,request:Request,user:CurrentUser=Depends(current_user)):
    tid,store=_target(request,user,None);rows=store.fetch_all("SELECT * FROM app_releases WHERE tenant_id=? AND state='published'",(tid,));rows.sort(key=lambda x:_semver_key(x["version"]),reverse=True)
    for row in rows:
        artifacts=store.fetch_all("""SELECT a.* FROM app_release_artifacts ra JOIN app_build_artifacts a ON a.id=ra.artifact_id
                                   WHERE ra.release_id=? AND a.app_product=? AND a.platform=? AND a.architecture=?""",(row["id"],app,platform,arch))
        if artifacts:
            return {"tenant_id":tid,"app":app,"platform":platform,"arch":arch,"latest":{"release_id":row["id"],"version":row["version"],"channel":row["channel"],"mandatory":bool(row["mandatory"]),"artifact":artifacts[0]}}
    return {"tenant_id":tid,"app":app,"platform":platform,"arch":arch,"latest":None}
