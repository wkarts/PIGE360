#!/usr/bin/env python3
"""Executa cada *nó de teste* backend em processo independente.

O host desta construção retém alguns finalizadores nativos (OpenSSL/TestClient)
quando muitos testes compartilham o mesmo interpretador. A isolação ocorre por nó,
sem alterar setup/call/teardown do pytest e sem converter timeout/falha em sucesso.
Cada subprocesso recebe um process group próprio; timeout mata o grupo inteiro e
retorna falha 124.
"""
from __future__ import annotations

import hashlib
import os
import re
import signal
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
LOG_DIR = ROOT / "release/reports/logs/pytest-nodes"
TIMEOUT_SECONDS = int(os.getenv("PIGE360_PYTEST_NODE_TIMEOUT_SECONDS", "45"))
MAX_WORKERS = max(1, min(int(os.getenv("PIGE360_PYTEST_WORKERS", "1")), 12))


@dataclass(frozen=True)
class TestNode:
    node_id: str


class TestCollectionError(RuntimeError):
    """A coleta real do pytest falhou ou retornou um protocolo inválido."""


def pytest_environment() -> dict[str, str]:
    env = os.environ.copy()
    # Os testes são executados com cwd=backend para manter os node IDs estáveis,
    # mas alguns contratos de infraestrutura importam helpers versionados em
    # scripts/. Use caminhos absolutos e explícitos; depender de "." tornava a
    # coleta diferente conforme o diretório do chamador.
    python_paths = [str(BACKEND), str(ROOT)]
    python_paths.extend(
        item for item in env.get("PYTHONPATH", "").split(os.pathsep)
        if item and item not in python_paths
    )
    env.update({
        "PYTHONPATH": os.pathsep.join(python_paths),
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "DD_TRACE_ENABLED": "false",
        "DD_INSTRUMENTATION_TELEMETRY_ENABLED": "false",
    })
    return env


def collect_nodes(env: dict[str, str] | None = None) -> list[TestNode]:
    """Coleta item IDs finais do pytest, incluindo cada parametrização."""

    collected = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", "tests"],
        cwd=BACKEND,
        env=env or pytest_environment(),
        text=True,
        capture_output=True,
        check=False,
    )
    if collected.returncode != 0:
        detail = (collected.stdout + "\n" + collected.stderr).strip()
        raise TestCollectionError(
            f"Coleta pytest falhou com código {collected.returncode}:\n{detail[-4000:]}"
        )
    node_ids = [
        line.strip()
        for line in collected.stdout.splitlines()
        if line.startswith("tests/") and "::" in line
    ]
    if not node_ids:
        raise TestCollectionError("A coleta pytest não retornou nenhum item de teste.")
    if len(node_ids) != len(set(node_ids)):
        raise TestCollectionError("A coleta pytest retornou item IDs duplicados.")
    return [TestNode(node_id) for node_id in node_ids]


def run_node(node: TestNode, env: dict[str, str]) -> tuple[int, str, bool, float]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "__", node.node_id)[:180]
    digest = hashlib.sha256(node.node_id.encode("utf-8")).hexdigest()[:16]
    log_path = LOG_DIR / f"{safe_name}-{digest}.log"
    cmd = [sys.executable, str(ROOT / "scripts/ci/pytest_node_entry.py"), node.node_id]
    started = time.monotonic()
    with log_path.open("w", encoding="utf-8") as log:
        log.write("$ " + " ".join(cmd) + "\n\n"); log.flush()
        proc = subprocess.Popen(
            cmd,
            cwd=BACKEND,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        deadline = started + TIMEOUT_SECONDS
        while proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        timed_out = proc.poll() is None
        if timed_out:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait(timeout=5)
        code = proc.returncode if proc.returncode is not None else 124
    elapsed = time.monotonic() - started
    return int(code), log_path.read_text(encoding="utf-8", errors="replace"), timed_out, elapsed


def main() -> int:
    env = pytest_environment()
    try:
        nodes = collect_nodes(env)
    except TestCollectionError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    shard_spec = os.getenv("PIGE360_PYTEST_SHARD", "").strip()
    if shard_spec:
        try:
            shard_index_text, shard_count_text = shard_spec.split("/", 1)
            shard_index = int(shard_index_text); shard_count = int(shard_count_text)
            if shard_count < 1 or shard_index < 1 or shard_index > shard_count:
                raise ValueError
        except ValueError:
            print("PIGE360_PYTEST_SHARD deve usar formato N/T, ex.: 1/3", file=sys.stderr)
            return 2
        nodes = [node for index, node in enumerate(nodes) if index % shard_count == shard_index - 1]
    if not nodes:
        print("Nenhum teste backend coletado.", file=sys.stderr)
        return 2

    passed = 0
    failed: list[str] = []
    started = time.monotonic()
    results: dict[str, tuple[int, str, bool, float]] = {}

    def record(node: TestNode, result: tuple[int, str, bool, float]) -> None:
        nonlocal passed
        code, output, timed_out, node_elapsed = result
        results[node.node_id] = result
        did_pass = code == 0 and "PIGE360_NODE_RESULT=PASS" in output
        if did_pass:
            passed += 1
        status = "TIMEOUT" if timed_out else ("PASS" if did_pass else "FAIL")
        print(f"[{status}] {node.node_id} ({node_elapsed:.2f}s)", flush=True)
        if not did_pass:
            failed.append(node.node_id)
            print(output[-4000:], file=sys.stderr)

    if MAX_WORKERS == 1:
        # Caminho padrão: sem threads no host local. Cada teste já possui
        # isolamento de processo próprio; paralelização é feita por shards no CI.
        for node in nodes:
            record(node, run_node(node, env))
    else:
        # Opcional para hosts validados; não é o padrão do projeto.
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(run_node, node, env): node for node in nodes}
            for future in as_completed(futures):
                node = futures[future]
                record(node, future.result())

    elapsed = time.monotonic() - started
    shard_label = f" shard={shard_spec}" if shard_spec else ""
    print(f"\n{passed}/{len(nodes)} nós passaram em {elapsed:.2f}s; falhas={len(failed)}{shard_label}")
    if failed:
        print("Falhas: " + ", ".join(failed), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
