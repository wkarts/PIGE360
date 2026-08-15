#!/usr/bin/env python3
"""Executa um único nó pytest e encerra após o teardown comprovado.

Alguns módulos nativos injetados no host de construção mantêm hooks/finalizadores
pós-sessão presos mesmo depois que o pytest conclui setup/call/teardown do teste.
Este entrypoint NÃO converte timeout em sucesso: ele só retorna 0 depois que o
pytest emite o relatório de teardown do nó e todos os relatórios setup/call/
teardown são aprovados. Falha, skip ou xfail não são considerados PASS na CI.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

import pytest

PASS_MARKER = "PIGE360_NODE_RESULT=PASS"
FAIL_MARKER = "PIGE360_NODE_RESULT=FAIL"


@dataclass(eq=False)
class NodeOutcomePlugin:
    failed: bool = False
    skipped: bool = False
    saw_call: bool = False
    failure_details: list[str] = field(default_factory=list)

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        if report.failed:
            self.failed = True
            detail = report.longreprtext
            if detail:
                self.failure_details.append(f"[{report.when}]\n{detail}")
        if report.skipped:
            self.skipped = True
        if report.when == "call":
            self.saw_call = True
        if report.when != "teardown":
            return

        passed = self.saw_call and not self.failed and not self.skipped and report.passed
        stream = sys.__stdout__
        if not passed and self.failure_details:
            stream.write("\n=== PIGE360 PYTEST NODE FAILURE ===\n")
            stream.write("\n\n".join(self.failure_details).rstrip() + "\n")
        stream.write((PASS_MARKER if passed else FAIL_MARKER) + "\n")
        stream.flush()
        sys.__stderr__.flush()
        os._exit(0 if passed else 1)


def main() -> None:
    if len(sys.argv) != 2:
        print("uso: pytest_node_entry.py <nodeid>", file=sys.stderr)
        os._exit(2)
    plugin = NodeOutcomePlugin()
    # O plugin encerra após o teardown do único nó. O retorno abaixo cobre apenas
    # erros de coleta/configuração que aconteçam antes de um teste ser executado.
    code = int(pytest.main(["-q", "--disable-warnings", sys.argv[1]], plugins=[plugin]))
    sys.stdout.flush(); sys.stderr.flush()
    os._exit(code)


if __name__ == "__main__":
    main()
