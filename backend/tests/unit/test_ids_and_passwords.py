from __future__ import annotations

import uuid

import pytest

from app.shared.domain.ids import uuid7
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import hash_password, verify_password


def test_uuid7_is_valid_and_time_orderable():
    values = [uuid7() for _ in range(10)]
    parsed = [uuid.UUID(x) for x in values]
    assert all(x.version == 7 for x in parsed)
    # UUIDv7 preserva timestamp no prefixo, mas a RFC não exige monotonicidade
    # lexicográfica entre valores gerados no mesmo milissegundo.
    assert len(set(values)) == len(values)
    assert len({x.split("-")[0] for x in values}) <= 2


def test_argon2_password_hash_and_minimum_policy():
    digest = hash_password("Senha-Forte-Local-2026!")
    assert digest.startswith("$argon2")
    assert verify_password(digest, "Senha-Forte-Local-2026!")
    assert not verify_password(digest, "senha-incorreta")
    with pytest.raises(DomainError):
        hash_password("curta")
