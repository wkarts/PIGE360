from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[3]
BUILDER = ROOT / "scripts" / "execution" / "build_portable_checkpoint.py"


def test_builder_ignores_restored_checkpoint_manifest_and_emits_one_canonical_manifest(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "VERSION").write_text("1.0.0\n", encoding="utf-8")
    (workspace / "application.txt").write_text("conteúdo operacional\n", encoding="utf-8")
    generated_vue_mirror = workspace / "apps" / "admin-app" / "src" / "App.vue.js"
    generated_vue_mirror.parent.mkdir(parents=True)
    generated_vue_mirror.write_text("export default {};\n", encoding="utf-8")
    (workspace / "CHECKPOINT_MANIFEST.json").write_text(
        json.dumps({"format": "stale-restored-checkpoint"}),
        encoding="utf-8",
    )
    nested_cache = workspace / "backend" / ".pytest_cache" / "v" / "cache"
    nested_cache.mkdir(parents=True)
    (nested_cache / "nodeids").write_text("cache não distribuível\n", encoding="utf-8")
    output = workspace / "release" / "checkpoints" / "checkpoint.zip"

    result = subprocess.run(
        [
            sys.executable,
            str(BUILDER),
            "--root",
            str(workspace),
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert output.exists()
    with ZipFile(output) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names))
        assert names.count("CHECKPOINT_MANIFEST.json") == 1
        assert "application.txt" in names
        assert "apps/admin-app/src/App.vue.js" in names
        assert not any(".pytest_cache" in name for name in names)
        manifest = json.loads(archive.read("CHECKPOINT_MANIFEST.json"))
        assert manifest["format"] == "pige360-workspace-portable-checkpoint"
        assert all(item["path"] != "CHECKPOINT_MANIFEST.json" for item in manifest["files"])
        assert archive.testzip() is None
