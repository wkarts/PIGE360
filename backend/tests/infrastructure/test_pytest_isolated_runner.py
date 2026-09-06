from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[3]


def load_runner() -> ModuleType:
    path = ROOT / "scripts/ci/run_pytest_isolated.py"
    name = "pige360_run_pytest_isolated_regression"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_runner_executes_every_parameterized_pytest_item(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    test_file = tmp_path / "tests/test_parameterized.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text(
        """\
import os

import pytest


@pytest.mark.parametrize("case", ["one/two", "one two", "three", "four"])
def test_parameterized_case(case: str) -> None:
    with open(os.environ["PIGE360_PARAMETER_TRACE"], "a", encoding="utf-8") as trace:
        trace.write(case + "\\n")
""",
        encoding="utf-8",
    )
    trace = tmp_path / "parameter-trace.txt"
    runner = load_runner()
    monkeypatch.setattr(runner, "BACKEND", tmp_path)
    monkeypatch.setattr(runner, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(runner, "MAX_WORKERS", 1)
    monkeypatch.setenv("PIGE360_PARAMETER_TRACE", str(trace))
    monkeypatch.delenv("PIGE360_PYTEST_SHARD", raising=False)

    nodes = runner.collect_nodes(runner.pytest_environment())
    assert [node.node_id for node in nodes] == [
        f"tests/test_parameterized.py::test_parameterized_case[{case}]"
        for case in ("one/two", "one two", "three", "four")
    ]

    assert runner.main() == 0
    assert trace.read_text(encoding="utf-8").splitlines() == [
        "one/two",
        "one two",
        "three",
        "four",
    ]
    assert len(list((tmp_path / "logs").glob("*.log"))) == 4
    assert "4/4 nós passaram" in capsys.readouterr().out


def test_runner_exposes_backend_and_repository_helpers_with_absolute_paths(monkeypatch) -> None:
    runner = load_runner()
    monkeypatch.setenv("PYTHONPATH", "/existing/tooling")

    paths = runner.pytest_environment()["PYTHONPATH"].split(runner.os.pathsep)

    assert paths[:2] == [str(runner.BACKEND), str(runner.ROOT)]
    assert "/existing/tooling" in paths
    assert "." not in paths
