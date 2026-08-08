#!/usr/bin/env python3
"""Agente efêmero da App Factory PIGE360.

O agente reivindica somente jobs compatíveis com seu SO/toolchain, materializa um
workspace temporário, aplica o manifesto fixado do tenant, compila e devolve
artefatos com SHA-256. Nenhum segredo de assinatura é persistido no workspace.
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import platform as host_platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from pathlib import Path
from typing import Any

API = os.getenv("PIGE360_API_URL", "http://pige360-api:8000/api/v1").rstrip("/")
PLATFORM_HOST = os.getenv("PIGE360_PLATFORM_HOST", "api.platform.local")
SOURCE = Path(os.getenv("PIGE360_SOURCE_ROOT", "/workspace/source")).resolve()
POLL_SECONDS = max(2, int(os.getenv("BUILD_FARM_POLL_SECONDS", "5")))
WORKER_ID = os.getenv("BUILD_FARM_WORKER_ID", f"{host_platform.node() or 'builder'}-{uuid.uuid4().hex[:8]}")
OPERATING_SYSTEM = os.getenv("BUILD_FARM_OS", {"Darwin":"macos","Windows":"windows"}.get(host_platform.system(), "linux"))
TOKEN_FILE = os.getenv("BUILD_FARM_TOKEN_FILE", "/run/secrets/build_farm_token")
TOKEN = Path(TOKEN_FILE).read_text(encoding="utf-8").strip() if Path(TOKEN_FILE).is_file() else os.getenv("BUILD_FARM_TOKEN", "")

APP_DIRS = {
    "family-mobile": "family-app", "teacher-mobile": "teacher-app", "student-mobile": "student-app",
    "admin-mobile": "admin-app", "pos-mobile": "pos-app", "kiosk": "kiosk-app", "timeclock": "timeclock-app",
    "desktop-admin": "desktop-admin", "pos-desktop": "pos-app", "pwa": "tenant-admin-web",
}


def _command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def capabilities() -> list[str]:
    result: list[str] = []
    node = _command_exists("node") and _command_exists("npm")
    cargo = _command_exists("cargo")
    tauri = cargo and subprocess.run(["cargo", "tauri", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    if node:
        result.append("pwa")
    if OPERATING_SYSTEM == "linux" and node and tauri:
        result += ["linux-x64", "linux-arm64"]
        if os.getenv("ANDROID_HOME") and (_command_exists("java") or _command_exists("javac")):
            result += ["android-apk", "android-aab"]
    elif OPERATING_SYSTEM == "windows" and node and tauri:
        result += ["windows-x64", "windows-x86"]
    elif OPERATING_SYSTEM == "macos" and node and tauri and _command_exists("xcodebuild"):
        result += ["macos-intel", "macos-apple", "ios-app", "ios-xcarchive", "ios-ipa-unsigned"]
    configured = {x.strip() for x in os.getenv("BUILD_FARM_PLATFORMS", "").split(",") if x.strip()}
    return sorted(set(result) & configured) if configured else sorted(set(result))


def api(method: str, path: str, body: dict[str, Any] | None = None, *, raw: bool = False) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{API}{path}", data=data, method=method,
        headers={"Host": PLATFORM_HOST, "X-Build-Farm-Token": TOKEN, **({"Content-Type":"application/json"} if data else {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            payload = response.read()
            if raw: return payload, dict(response.headers)
            return json.loads(payload) if payload else None
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        if exc.code == 204: return None
        raise RuntimeError(f"API {method} {path} -> {exc.code}: {payload}") from exc


def download_asset(job: dict[str, Any], asset: dict[str, Any], target: Path) -> None:
    query = urllib.parse.urlencode({"tenant_id": job["tenant_id"]})
    content, headers = api("GET", f"/platform/build-farm/jobs/{job['job_id']}/assets/{asset['id']}?{query}", raw=True)
    digest = hashlib.sha256(content).hexdigest()
    if digest != asset["sha256"] or headers.get("X-Asset-SHA256", headers.get("x-asset-sha256", "")) not in {"", digest}:
        raise RuntimeError(f"SHA-256 divergente no ativo {asset['id']}")
    target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(content)


def multipart_upload(job: dict[str, Any], artifact: Path, kind: str, signed_state: str = "unsigned") -> dict[str, Any]:
    boundary = f"----pige360-{uuid.uuid4().hex}"
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    fields = {"tenant_id": job["tenant_id"], "artifact_kind": kind, "sha256": digest, "signed_state": signed_state}
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
    ctype = mimetypes.guess_type(artifact.name)[0] or "application/octet-stream"
    chunks.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{artifact.name}\"\r\nContent-Type: {ctype}\r\n\r\n".encode())
    chunks.append(artifact.read_bytes()); chunks.append(f"\r\n--{boundary}--\r\n".encode())
    payload=b"".join(chunks)
    req=urllib.request.Request(
        f"{API}/platform/build-farm/jobs/{job['job_id']}/artifacts", data=payload, method="POST",
        headers={"Host":PLATFORM_HOST,"X-Build-Farm-Token":TOKEN,"Content-Type":f"multipart/form-data; boundary={boundary}","Content-Length":str(len(payload))},
    )
    with urllib.request.urlopen(req, timeout=600) as response:
        return json.loads(response.read())


def run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    subprocess.run(cmd, cwd=cwd, env={**os.environ, **(env or {})}, check=True)


def deterministic_zip(source: Path, target: Path) -> None:
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(p for p in source.rglob("*") if p.is_file()):
            info=zipfile.ZipInfo(str(path.relative_to(source)).replace(os.sep,"/"),(2026,1,1,0,0,0));info.external_attr=0o644<<16
            archive.writestr(info,path.read_bytes(),compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)


def package_tree(source: Path, target: Path) -> None:
    with tarfile.open(target, "w:gz", format=tarfile.PAX_FORMAT) as tar:
        for path in sorted(p for p in source.rglob("*") if p.is_file()):
            info=tar.gettarinfo(str(path), arcname=str(path.relative_to(source)));info.mtime=0;info.uid=0;info.gid=0;info.uname="";info.gname=""
            with path.open("rb") as fh: tar.addfile(info,fh)


def prepare_workspace(job: dict[str, Any], root: Path) -> tuple[Path, dict[str, Any]]:
    if not SOURCE.is_dir(): raise RuntimeError(f"Source root ausente: {SOURCE}")
    work=root/"source"; shutil.copytree(SOURCE,work,symlinks=False,ignore=shutil.ignore_patterns("node_modules","target","dist","runtime-data","release"))
    spec=job["spec"]; app_dir=work/"apps"/APP_DIRS[spec["app_product"]]
    if not app_dir.is_dir(): raise RuntimeError(f"Aplicativo não localizado para {spec['app_product']}")
    runtime_manifest={
        "schema_version":1,"tenant_id":spec["tenant_id"],"tenant_code":spec["tenant_code"],"brand_version":spec["brand_version"],
        "app_product":spec["app_product"],"display_name":spec["app"]["display_name"],"identifier":spec["app"]["identifier"],
        "api_url":spec["app"]["api_url"],"web_url":spec["app"]["web_url"],"update_url":spec["app"]["update_url"],
        "features":spec["app"].get("features",{}),"manifest_sha256":spec["manifest_sha256"],"build_job_id":job["job_id"],
    }
    public=app_dir/"public";public.mkdir(exist_ok=True);(public/"tenant-app-manifest.json").write_text(json.dumps(runtime_manifest,ensure_ascii=False,sort_keys=True,indent=2),encoding="utf-8")
    assets_dir=root/"brand-assets"; downloaded={}
    for asset in spec.get("assets",[]):
        suffix=Path(asset["storage_key"]).suffix or ".bin";target=assets_dir/f"{asset['id']}{suffix}";download_asset(job,asset,target);downloaded[asset["id"]]=target
    if spec["platform"] != "pwa" and spec["app"].get("icon_asset_id"):
        icon=downloaded.get(spec["app"]["icon_asset_id"])
        if icon and _command_exists("cargo"):
            run(["cargo","tauri","icon",str(icon)],app_dir)
    return app_dir,spec


def build(job: dict[str, Any], root: Path) -> list[tuple[Path,str,str]]:
    app_dir,spec=prepare_workspace(job,root);platform=spec["platform"];artifacts=root/"artifacts";artifacts.mkdir()
    run(["npm","ci","--ignore-scripts=false"],app_dir)
    if platform=="pwa":
        run(["npm","run","build"],app_dir);target=artifacts/f"{spec['app_product']}-pwa.zip";deterministic_zip(app_dir/"dist",target);return [(target,"pwa-zip","unsigned")]
    # Native build-time override: tenant and host are fixed in the generated binary.
    api_host=urllib.parse.urlparse(spec["app"]["api_url"]).hostname or ""
    override={"productName":spec["app"]["display_name"],"identifier":spec["app"]["identifier"],"app":{"security":{"csp":f"default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; connect-src 'self' https://{api_host}"}}}
    override_path=app_dir/"src-tauri"/"tenant.tauri.conf.json";override_path.write_text(json.dumps(override,ensure_ascii=False,indent=2),encoding="utf-8")
    if platform.startswith("android-"):
        cmd=["cargo","tauri","android","build","--config",str(override_path)]
        run(cmd,app_dir)
        patterns=["*.apk"] if platform=="android-apk" else ["*.aab"]
    elif platform.startswith("ios-"):
        run(["cargo","tauri","ios","build","--config",str(override_path),"--target","aarch64"],app_dir);patterns=["*.app","*.xcarchive","*.ipa"]
    else:
        target={"windows-x64":"x86_64-pc-windows-msvc","windows-x86":"i686-pc-windows-msvc","linux-x64":"x86_64-unknown-linux-gnu","linux-arm64":"aarch64-unknown-linux-gnu","macos-intel":"x86_64-apple-darwin","macos-apple":"aarch64-apple-darwin"}[platform]
        run(["cargo","tauri","build","--config",str(override_path),"--target",target],app_dir);patterns=["*"]
    bundle=app_dir/"src-tauri"/"target";target_archive=artifacts/f"{spec['app_product']}-{platform}-{spec['architecture']}.tar.gz";package_tree(bundle,target_archive)
    return [(target_archive,platform,"unsigned")]


def process(job: dict[str, Any]) -> None:
    with tempfile.TemporaryDirectory(prefix=f"pige360-build-{job['job_id']}-") as temp:
        root=Path(temp)
        try:
            outputs=build(job,root)
            for path,kind,signed in outputs: multipart_upload(job,path,kind,signed)
            api("POST",f"/platform/build-farm/jobs/{job['job_id']}/complete",{"tenant_id":job["tenant_id"]})
        except Exception as exc:
            try: api("POST",f"/platform/build-farm/jobs/{job['job_id']}/fail",{"tenant_id":job["tenant_id"],"error":str(exc)[:4000]})
            finally: raise


def main() -> int:
    if not TOKEN: print("BUILD_FARM_TOKEN ausente",file=sys.stderr);return 2
    caps=capabilities()
    if not caps: print(f"Nenhuma toolchain compatível detectada para {OPERATING_SYSTEM}; agente não reivindicará jobs.",file=sys.stderr);return 3
    print(json.dumps({"worker_id":WORKER_ID,"os":OPERATING_SYSTEM,"capabilities":caps},ensure_ascii=False),flush=True)
    once=os.getenv("BUILD_FARM_ONCE","").lower() in {"1","true","yes"}
    while True:
        try:
            job=api("POST","/platform/build-farm/jobs/claim",{"worker_id":WORKER_ID,"operating_system":OPERATING_SYSTEM,"supported_platforms":caps})
            if job: process(job)
            elif once: return 0
        except Exception as exc:
            print(f"build-agent error: {exc}",file=sys.stderr,flush=True)
            if once:return 1
        time.sleep(POLL_SECONDS)


if __name__=="__main__": raise SystemExit(main())
