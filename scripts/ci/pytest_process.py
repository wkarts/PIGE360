#!/usr/bin/env python3
"""Wrapper de processo para pytest.

`pytest.main()` só retorna depois de setup/call/teardown e do resultado final da suíte.
Algumas bibliotecas do host registram finalizadores de interpretador que podem prender
o processo depois desse retorno. Saímos com o código REAL do pytest e não executamos
apenas esses finalizadores externos à suíte.
"""
from __future__ import annotations

import os
import sys

import pytest


if __name__ == "__main__":
    code = int(pytest.main(sys.argv[1:]))
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)
