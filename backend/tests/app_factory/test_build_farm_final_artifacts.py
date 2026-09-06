from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
AGENT_PATH = ROOT / "scripts/build-farm/agent.py"
MODULE_SPEC = importlib.util.spec_from_file_location("pige360_build_farm_agent_contract", AGENT_PATH)
assert MODULE_SPEC and MODULE_SPEC.loader
agent = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(agent)


def test_build_farm_selects_final_artifacts_without_cargo_intermediates() -> None:
    with tempfile.TemporaryDirectory() as directory:
        app = Path(directory) / "app"
        target = "x86_64-unknown-linux-gnu"
        release = app / "src-tauri/target" / target / "release"
        installer = release / "bundle/deb/pige360.deb"
        symbol = release / "pige360.debug"
        intermediate = release / "deps/huge-intermediate.rlib"
        for path in (installer, symbol, intermediate):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(path.name.encode())

        selected = agent.final_native_outputs(app, "linux-x64", target)

        assert selected == sorted([installer, symbol])
        assert intermediate not in selected


def test_build_farm_patterns_cannot_escape_the_final_artifact_allowlist() -> None:
    with tempfile.TemporaryDirectory() as directory:
        app = Path(directory) / "app"
        apk = app / "src-tauri/gen/android/app/build/outputs/apk/release/app.apk"
        apk.parent.mkdir(parents=True)
        apk.write_bytes(b"apk")

        assert agent.final_native_outputs(app, "android-apk", patterns=["*.apk"]) == [apk]
        try:
            agent.final_native_outputs(app, "android-apk", patterns=["../**/*"])
        except RuntimeError as error:
            assert "inseguro" in str(error)
        else:
            raise AssertionError("Pattern com travessia deveria ser rejeitado")

