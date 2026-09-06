from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


RELEASE_SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RELEASE_SCRIPTS))

from evidence_common import collect_evidence, collect_inputs  # noqa: E402
from generate_before_after_report import compare_trees  # noqa: E402


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class EvidenceReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="pige360-evidence-test-")
        self.root = Path(self.temp.name)
        (self.root / "VERSION").write_text("9.8.7\n", encoding="utf-8")
        (self.root / "PROMPT_FINAL_COMPLETO_PIGE360_V8_LOCAL_SEM_REPOSITORIO.md").write_text(
            "contrato variavel\n", encoding="utf-8"
        )
        for name in ("alpha", "beta"):
            write_json(self.root / f"apps/{name}/package.json", {"name": name})
        (self.root / "apps/alpha/src").mkdir(parents=True)
        (self.root / "apps/alpha/src/main.js").write_text("main", encoding="utf-8")
        (self.root / "apps/alpha/src/View.vue.js").write_text("view", encoding="utf-8")
        (self.root / ".github/workflows").mkdir(parents=True)
        (self.root / ".github/workflows/a.yml").write_text("name: a\n", encoding="utf-8")
        (self.root / ".github/workflows/b.yaml").write_text("name: b\n", encoding="utf-8")
        (self.root / "compose.yaml").write_text(
            "services:\n  api:\n    image: api\n  web:\n    image: web\n  db:\n    image: db\n",
            encoding="utf-8",
        )
        write_json(
            self.root / "release/reports/test-report.json",
            {"status": "passed", "pytest_passed": 7, "checks": [{"name": "pytest"}]},
        )
        commands = [
            {
                "name": "pytest",
                "status": "passed",
                "duration_seconds": 1,
                "log": "pytest.log",
                "started_at": "2026-01-01T00:00:00+00:00",
                "finished_at": "2026-01-01T00:00:01+00:00",
            },
            {
                "name": "frontend-build",
                "status": "passed",
                "duration_seconds": 2,
                "log": "frontend.log",
                "started_at": "2026-01-01T00:00:01+00:00",
                "finished_at": "2026-01-01T00:00:03+00:00",
            },
            {
                "name": "visual-contract",
                "status": "passed",
                "duration_seconds": 0.1,
                "log": "visual.log",
                "started_at": "2026-01-01T00:00:03+00:00",
                "finished_at": "2026-01-01T00:00:04+00:00",
            },
        ]
        write_json(
            self.root / "release/reports/local-ci-report.json",
            {
                "status": "passed",
                "network_used": True,
                "network_usage_source": "test_fixture",
                "remote_operations_executed": False,
                "commands": commands,
            },
        )
        write_json(
            self.root / "release/reports/build-report.json",
            {
                "network_used": True,
                "builds": {
                    "backend": {"status": "passed"},
                    "visual": {"pixel_regression_executed": False},
                    "native_and_external_toolchains": [
                        {"name": "desktop", "status": "not_executed", "reason": "toolchain ausente"}
                    ],
                },
            },
        )
        write_json(
            self.root / "docs/api/OPENAPI_REPORT.json",
            {"paths": 11, "operations": 17, "schemas": 5, "duplicate_operation_ids": []},
        )
        write_json(
            self.root / "packages/visual-testing/baselines/visual-baseline-manifest.json",
            {
                "baseline_kind": "initial-local-baseline",
                "records": [{"screen": "one"}, {"screen": "one"}, {"screen": "two"}],
            },
        )
        write_json(
            self.root / "docs/design/visual-regression-report.json",
            {"status": "baseline_established", "pixel_differences": None},
        )
        write_json(
            self.root / "release/artifacts/backup-restore/report.json",
            {
                "status": "passed",
                "tenant_restored": "fixture-tenant",
                "backup_sha256": "abc",
                "cross_tenant_leakage": False,
            },
        )
        write_json(
            self.root / "release/artifacts/oci/PIGE360-9.8.7-images-digests.json",
            {
                "runtime_engine_available": False,
                "runtime_build_executed": False,
                "images": [{"name": "api", "runtime_executable": False}],
            },
        )
        write_json(
            self.root / "docs/execution/requirements.json",
            {
                "count": 999,
                "status_summary": {"VERIFIED": 999},
                "requirements": [
                    {"id": "A", "status": "VERIFIED"},
                    {"id": "B", "status": "NOT_STARTED"},
                ],
            },
        )
        write_json(
            self.root / "docs/operations/SOURCE_BASELINE.json",
            {
                "canonical_base": {
                    "name": "base.zip",
                    "sha256": "recorded-base",
                    "archive_comment_source_revision": "declared-revision",
                    "role": "unica base",
                },
                "previous_attachment_comparison": {"name": "previous.zip", "sha256": "recorded-previous"},
                "architectural_reference_only": {
                    "name": "reference.zip",
                    "sha256": "recorded-reference",
                    "role": "referencia somente",
                },
            },
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_counts_and_network_come_from_reports_and_tree(self) -> None:
        evidence = collect_evidence(self.root)
        self.assertEqual(evidence["tests"]["pytest_passed"], 7)
        self.assertEqual(evidence["tree"]["applications"]["count"], 2)
        self.assertEqual(evidence["tree"]["workflows"]["count"], 2)
        self.assertEqual(evidence["tree"]["compose"]["services_count"], 3)
        self.assertTrue(evidence["network"]["network_used"])
        self.assertEqual(evidence["requirements"]["requirements_count"], 2)
        self.assertEqual(evidence["requirements"]["status_summary"], {"NOT_STARTED": 1, "VERIFIED": 1})
        self.assertFalse(evidence["requirements"]["cache_matches_records"])

    def test_scope_does_not_promote_structural_or_synthetic_evidence(self) -> None:
        evidence = collect_evidence(self.root)
        self.assertEqual(evidence["oci"]["status"], "structural_only")
        self.assertFalse(evidence["oci"]["runtime_executable"])
        self.assertEqual(evidence["backup_restore"]["scope"], "local_synthetic_test")
        self.assertFalse(evidence["backup_restore"]["postgresql_restore_homologated"])
        self.assertFalse(evidence["backup_restore"]["minio_restore_homologated"])
        self.assertEqual(evidence["visual"]["scope"], "baseline_catalog_and_integrity")
        self.assertFalse(evidence["visual"]["pixel_regression_executed"])

    def test_hashes_are_recomputed_and_source_revision_is_not_git(self) -> None:
        base = self.root / "base.zip"
        previous = self.root / "previous.zip"
        reference = self.root / "reference.zip"
        base.write_bytes(b"base")
        previous.write_bytes(b"previous")
        reference.write_bytes(b"reference")
        baseline = json.loads((self.root / "docs/operations/SOURCE_BASELINE.json").read_text())
        baseline["canonical_base"]["sha256"] = digest(base)
        baseline["previous_attachment_comparison"]["sha256"] = digest(previous)
        baseline["architectural_reference_only"]["sha256"] = digest(reference)
        write_json(self.root / "docs/operations/SOURCE_BASELINE.json", baseline)
        inputs = collect_inputs(
            self.root,
            [f"canonical_base={base}", f"previous_attachment={previous}", f"architectural_reference={reference}"],
        )
        canonical = next(item for item in inputs["records"] if item["key"] == "canonical_base")
        prompt = next(item for item in inputs["records"] if item["key"] == "implementation_contract")
        self.assertEqual(canonical["verification"], "sha256_recomputed_from_file")
        self.assertEqual(prompt["sha256"], digest(self.root / prompt["name"]))
        self.assertEqual(inputs["source_revision"]["origin"], "zip_archive_comment")
        self.assertFalse(inputs["source_revision"]["vcs_checkout_verified"])
        base.write_bytes(b"changed")
        with self.assertRaises(ValueError):
            collect_inputs(self.root, [f"canonical_base={base}"])

    def test_before_after_lists_areas_and_preserves_javascript(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pige360-before-") as before_dir:
            before = Path(before_dir)
            for root in (before, self.root):
                (root / "apps/alpha/src").mkdir(parents=True, exist_ok=True)
            (before / "apps/alpha/src/main.js").write_text("main", encoding="utf-8")
            (before / "apps/alpha/src/View.vue.js").write_text("view", encoding="utf-8")
            (before / "backend/file.py").parent.mkdir(parents=True)
            (before / "backend/file.py").write_text("old", encoding="utf-8")
            (self.root / "backend/file.py").parent.mkdir(parents=True)
            (self.root / "backend/file.py").write_text("new", encoding="utf-8")
            (self.root / "docs/new.md").parent.mkdir(parents=True, exist_ok=True)
            (self.root / "docs/new.md").write_text("new", encoding="utf-8")
            report = compare_trees(before, self.root)
        self.assertEqual(report["summary"]["removed"], 0)
        self.assertEqual(report["summary"]["preservation_status"], "passed")
        self.assertEqual(report["source_compatibility"]["vue_js"]["current_count"], 1)
        self.assertEqual(report["source_compatibility"]["main_js"]["current_count"], 1)
        self.assertIn("backend/file.py", report["by_area"]["backend"]["modified"]["files"])
        self.assertFalse(report["comparison_basis"]["architectural_reference"]["used_as_product_base"])
        self.assertTrue(report["comparison_basis"]["current_tree_sha256"])

    def test_before_after_covers_release_source_but_ignores_generated_release_output(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pige360-before-release-") as before_dir:
            before = Path(before_dir)
            (before / "scripts/release").mkdir(parents=True)
            (before / "scripts/release/pack.py").write_text("original\n", encoding="utf-8")
            (before / "CI_CD_KIT_LOCAL/scripts/release").mkdir(parents=True)
            (before / "CI_CD_KIT_LOCAL/scripts/release/publish.sh").write_text("publish\n", encoding="utf-8")
            (before / "release/artifacts").mkdir(parents=True)
            (before / "release/artifacts/generated.json").write_text("{}\n", encoding="utf-8")
            current = self.root / "current-release-scope"
            current.mkdir()
            (current / "scripts/release").mkdir(parents=True)
            (current / "release/artifacts").mkdir(parents=True)
            (current / "release/artifacts/other.json").write_text("{}\n", encoding="utf-8")
            (current / "docs/operations").mkdir(parents=True)
            (current / "docs/operations/FINAL_LOCAL_VALIDATION.md").write_text(
                "generated\n", encoding="utf-8"
            )
            (current / "docs/operations/LOCAL_EXECUTION_REPORT.md").write_text(
                "generated\n", encoding="utf-8"
            )
            report = compare_trees(before, current)

        self.assertIn("scripts/release/pack.py", report["all_removed_files"])
        self.assertIn("CI_CD_KIT_LOCAL/scripts/release/publish.sh", report["all_removed_files"])
        self.assertNotIn("release/artifacts/generated.json", report["all_removed_files"])
        added = {
            path
            for area in report["by_area"].values()
            for path in area["added"]["files"]
        }
        self.assertNotIn("docs/operations/FINAL_LOCAL_VALIDATION.md", added)
        self.assertNotIn("docs/operations/LOCAL_EXECUTION_REPORT.md", added)
        self.assertEqual(report["summary"]["preservation_status"], "failed")

    def test_before_after_current_digest_rejects_stale_report(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pige360-before-digest-") as before_dir:
            before = Path(before_dir)
            (before / "backend").mkdir()
            (before / "backend/service.py").write_text("before\n", encoding="utf-8")
            current = self.root / "current-digest"
            (current / "backend").mkdir(parents=True)
            (current / "backend/service.py").write_text("after\n", encoding="utf-8")
            report_path = before / "report.json"
            write_json(report_path, compare_trees(before, current))

            command = [
                sys.executable,
                str(RELEASE_SCRIPTS / "generate_before_after_report.py"),
                "--current-dir",
                str(current),
                "--json-output",
                str(report_path),
                "--verify-current",
            ]
            verified = subprocess.run(command, check=False, capture_output=True, text=True)
            self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)

            (current / "backend/service.py").write_text("changed later\n", encoding="utf-8")
            stale = subprocess.run(command, check=False, capture_output=True, text=True)
            self.assertNotEqual(stale.returncode, 0)

    def test_manifest_uses_dynamic_counts_and_explicit_scopes(self) -> None:
        sbom = self.root / "release/PIGE360-9.8.7-sbom.cdx.json"
        write_json(sbom, {"bomFormat": "CycloneDX", "specVersion": "1.6"})
        output = self.root / "manifest.json"
        subprocess.run(
            [
                sys.executable,
                str(RELEASE_SCRIPTS / "generate-manifest.py"),
                "--root",
                str(self.root),
                "--output",
                str(output),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        manifest = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(manifest["evidence"]["pytest_passed"], 7)
        self.assertEqual(manifest["evidence"]["applications"], 2)
        self.assertEqual(manifest["evidence"]["workflows"], 2)
        self.assertEqual(manifest["evidence"]["compose_services"], 3)
        self.assertTrue(manifest["network_used"])
        self.assertFalse(manifest["oci"]["runtime_executable"])
        self.assertEqual(manifest["evidence"]["requirements"]["requirements_count"], 2)

    def test_provenance_uses_reported_network_and_computed_inputs(self) -> None:
        write_json(self.root / "release/source-tree-manifest.json", {"tree": "fixture"})
        output = self.root / "provenance.json"
        subprocess.run(
            [
                sys.executable,
                str(RELEASE_SCRIPTS / "generate_provenance.py"),
                "--root",
                str(self.root),
                "--output",
                str(output),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        statement = json.loads(output.read_text(encoding="utf-8"))
        definition = statement["predicate"]["buildDefinition"]
        self.assertTrue(definition["internalParameters"]["network_used"])
        self.assertIsNone(definition["internalParameters"]["vcs_commit"])
        self.assertFalse(definition["internalParameters"]["source_revision"]["vcs_checkout_verified"])
        prompt = next(
            item
            for item in definition["resolvedDependencies"]
            if item["uri"].endswith("PROMPT_FINAL_COMPLETO_PIGE360_V8_LOCAL_SEM_REPOSITORIO.md")
        )
        self.assertEqual(
            prompt["digest"]["sha256"],
            digest(self.root / "PROMPT_FINAL_COMPLETO_PIGE360_V8_LOCAL_SEM_REPOSITORIO.md"),
        )

    def test_pdf_generator_rewrites_final_docs_from_current_evidence(self) -> None:
        output_dir = self.root / "pdf"
        subprocess.run(
            [
                sys.executable,
                str(RELEASE_SCRIPTS / "generate_evidence_pdf.py"),
                "--root",
                str(self.root),
                "--output-dir",
                str(output_dir),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        final_doc = (self.root / "docs/operations/FINAL_LOCAL_VALIDATION.md").read_text(encoding="utf-8")
        self.assertIn("7 aprovados", final_doc)
        self.assertIn("regressao pixel-a-pixel executada: **false**", final_doc)
        self.assertIn("nao homologa restore de PostgreSQL nem de MinIO", final_doc)
        self.assertTrue((output_dir / "PIGE360-9.8.7-relatorio-evidencias.pdf").is_file())
        self.assertTrue((output_dir / "PDF-MANIFEST.json").is_file())


if __name__ == "__main__":
    unittest.main()
