from __future__ import annotations

import hashlib
import importlib.util
import json
import tarfile
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("agent.py")
MODULE_SPEC = importlib.util.spec_from_file_location("pige360_build_farm_agent", MODULE_PATH)
assert MODULE_SPEC and MODULE_SPEC.loader
agent = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(agent)


class FinalArtifactTests(unittest.TestCase):
    def test_android_collects_requested_final_format_and_safe_metadata_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = root / "app"
            outputs = app / "src-tauri/gen/android/app/build/outputs"
            apk = outputs / "apk/release/app-release.apk"
            aab = outputs / "bundle/release/app-release.aab"
            mapping = outputs / "mapping/release/mapping.txt"
            metadata = outputs / "apk/release/output-metadata.json"
            for path, content in ((apk, b"apk"), (aab, b"aab"), (mapping, b"mapping"), (metadata, b"{}")):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            intermediate = app / "src-tauri/target/aarch64-linux-android/release/deps/large.rlib"
            intermediate.parent.mkdir(parents=True)
            intermediate.write_bytes(b"must-not-be-published")

            selected = agent.final_native_outputs(app, "android-apk")

            self.assertEqual(selected, sorted([apk, mapping, metadata]))
            self.assertNotIn(aab, selected)
            self.assertNotIn(intermediate, selected)

    def test_job_patterns_only_narrow_the_final_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory) / "app"
            outputs = app / "src-tauri/gen/android/app/build/outputs"
            apk = outputs / "apk/release/app-release.apk"
            mapping = outputs / "mapping/release/mapping.txt"
            apk.parent.mkdir(parents=True)
            mapping.parent.mkdir(parents=True)
            apk.write_bytes(b"apk")
            mapping.write_bytes(b"mapping")

            self.assertEqual(agent.final_native_outputs(app, "android-apk", patterns=["*.apk"]), [apk])
            with self.assertRaisesRegex(RuntimeError, "Pattern de artefato inseguro"):
                agent.final_native_outputs(app, "android-apk", patterns=["../**/*"])
            with self.assertRaisesRegex(RuntimeError, "formato final solicitado"):
                agent.final_native_outputs(app, "android-apk", patterns=["mapping.txt"])

    def test_materialization_adds_traceable_manifest_and_checksums(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = root / "app"
            apk = app / "src-tauri/gen/android/app/build/outputs/apk/release/app-release.apk"
            apk.parent.mkdir(parents=True)
            apk.write_bytes(b"final-apk")
            artifacts = root / "artifacts"
            artifacts.mkdir()

            result = agent.materialize_native_outputs(
                [apk], artifacts, product="family-mobile", platform="android-apk", architecture="arm64",
                provenance={"tenant_id": "tenant-1", "brand_version": 7},
            )

            self.assertEqual([kind for _, kind, _ in result], [
                "android-apk", "android-apk-manifest", "android-apk-checksums"
            ])
            copied, manifest_path, checksums_path = [path for path, _, _ in result]
            self.assertEqual(copied.read_bytes(), b"final-apk")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["platform"], "android-apk")
            self.assertEqual(manifest["provenance"], {"tenant_id": "tenant-1", "brand_version": 7})
            self.assertEqual(manifest["files"][0]["sha256"], hashlib.sha256(b"final-apk").hexdigest())
            self.assertIn(copied.name, checksums_path.read_text(encoding="utf-8"))
            self.assertIn(manifest_path.name, checksums_path.read_text(encoding="utf-8"))

    def test_desktop_collects_installers_and_symbols_but_not_cargo_intermediates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory) / "app"
            target = "x86_64-unknown-linux-gnu"
            release = app / "src-tauri/target" / target / "release"
            deb = release / "bundle/deb/pige360.deb"
            image = release / "bundle/appimage/pige360.AppImage"
            symbol = release / "pige360.debug"
            intermediate = release / "deps/pige360.rlib"
            for path in (deb, image, symbol, intermediate):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(path.name.encode())

            selected = agent.final_native_outputs(app, "linux-x64", target)

            self.assertEqual(selected, sorted([deb, image, symbol]))
            self.assertNotIn(intermediate, selected)

    def test_ios_app_does_not_duplicate_app_nested_in_xcarchive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory) / "app"
            build = app / "src-tauri/gen/apple/build/arm64"
            standalone = build / "PIGE360.app"
            archived = build / "PIGE360.xcarchive/Products/Applications/PIGE360.app"
            dsym = build / "PIGE360.app.dSYM"
            for bundle in (standalone, archived, dsym):
                binary = bundle / "Contents/MacOS/PIGE360"
                binary.parent.mkdir(parents=True, exist_ok=True)
                binary.write_bytes(b"binary")

            selected = agent.final_native_outputs(app, "ios-app")

            self.assertEqual(selected, sorted([standalone, dsym]))
            self.assertNotIn(archived, selected)

    def test_directory_bundle_archive_preserves_root_and_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = root / "PIGE360.app"
            executable = app / "Contents/MacOS/PIGE360"
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b"binary")
            framework = app / "Contents/Frameworks/Example.framework"
            versioned = framework / "Versions/A/Example"
            versioned.parent.mkdir(parents=True)
            versioned.write_bytes(b"framework")
            (framework / "Versions/Current").symlink_to("A", target_is_directory=True)
            (framework / "Example").symlink_to("Versions/Current/Example")
            target = root / "app.tar.gz"

            agent.package_tree(app, target, preserve_root=True)

            with tarfile.open(target, "r:gz") as archive:
                names = archive.getnames()
                current = archive.getmember("PIGE360.app/Contents/Frameworks/Example.framework/Versions/Current")
            self.assertIn("PIGE360.app/Contents/MacOS/PIGE360", names)
            self.assertTrue(current.issym())

    def test_missing_primary_artifact_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifacts = Path(directory) / "artifacts"
            artifacts.mkdir()
            with self.assertRaisesRegex(RuntimeError, "não produziu artefato final"):
                agent.materialize_native_outputs(
                    [], artifacts, product="student-mobile", platform="android-aab", architecture="arm64"
                )


if __name__ == "__main__":
    unittest.main()
