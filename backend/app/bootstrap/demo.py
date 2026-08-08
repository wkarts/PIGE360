from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.bootstrap.config import Settings
from app.shared.database.router import DataRouter
from app.shared.domain.ids import iso_now, uuid7
from app.shared.security.auth import AuthService


def seed_demo(router:DataRouter,settings:Settings,project_root:Path|None=None)->dict:
    if not settings.demo_mode:raise RuntimeError("O seed demo exige APP_DEMO_MODE=true.")
    router.initialize()
    platform=AuthService(router.control,settings,tenant_id=None,plane="platform")
    if not router.control.fetch_one("SELECT id FROM users WHERE tenant_id IS NULL AND email='admin.demo@example.invalid'"):
        platform.create_user("admin.demo@example.invalid","DemoOnly!Change123",["platform_super_admin","platform_admin"])
    tenant=router.provision_tenant(code="demo-horizonte",legal_name="Colégio Horizonte Demonstrativo Ltda.",trade_name="Colégio Horizonte",hostname="demo.pige360.local")
    store=router.tenant_store(tenant["id"]);auth=AuthService(store,settings,tenant_id=tenant["id"],plane="tenant")
    if not store.fetch_one("SELECT id FROM users WHERE tenant_id=? AND email='gestor.demo@example.invalid'",(tenant["id"],)):
        auth.create_user("gestor.demo@example.invalid","DemoOnly!Change123",["tenant_owner","institution_director","academic_coordinator","teacher","secretary","finance_manager","finance_operator","fiscal_manager","hr_manager","personnel_operator","payroll_operator","timekeeping_operator","canteen_manager","pos_operator","inventory_manager","event_manager","request_agent","mail_admin"])
    brand_path=(project_root or Path.cwd())/"packages/tenant-branding/brands/demo-horizonte/tenant-brand-kit.json"
    logo_path=(project_root or Path.cwd())/"packages/tenant-branding/brands/demo-horizonte/logo-symbol.svg"
    if brand_path.is_file() and not store.fetch_one("SELECT id FROM brand_kits WHERE tenant_id=?",(tenant["id"],)):
        brand=json.loads(brand_path.read_text(encoding="utf-8"));kit_id=uuid7();now=iso_now();canonical=json.dumps(brand,ensure_ascii=False,sort_keys=True,separators=(",",":"));digest=hashlib.sha256(canonical.encode()).hexdigest()
        storage=router.tenant_storage_path(tenant["id"])/"branding"/kit_id/"originals";storage.mkdir(parents=True,exist_ok=True);logo=logo_path.read_bytes();logo_digest=hashlib.sha256(logo).hexdigest();asset_id=uuid7();target=storage/f"{asset_id}.svg";target.write_bytes(logo)
        with store.transaction() as conn:
            conn.execute("INSERT INTO brand_kits(id,tenant_id,state,active_version,payload_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",(kit_id,tenant["id"],"active",1,canonical,now,now));conn.execute("INSERT INTO brand_versions(id,tenant_id,brand_kit_id,version,state,payload_json,sha256,created_at) VALUES(?,?,?,?,?,?,?,?)",(uuid7(),tenant["id"],kit_id,1,"active",canonical,digest,now));conn.execute("INSERT INTO brand_assets(id,tenant_id,brand_kit_id,category,original_filename,storage_key,mime_type,bytes,sha256,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(asset_id,tenant["id"],kit_id,"logo_symbol","logo-symbol.svg",str(target.relative_to(router.tenant_storage_path(tenant["id"]))),"image/svg+xml",len(logo),logo_digest,now))
    return {"tenant_id":tenant["id"],"tenant_host":"demo.pige360.local","platform_host":"console.platform.local","demo_users":["admin.demo@example.invalid","gestor.demo@example.invalid"],"demo_password":"DemoOnly!Change123"}
