import hashlib
from pathlib import Path

import pytest

from app.shared.storage.object_storage import LocalObjectStorage


def test_local_object_storage_is_tenant_scoped_and_hashes(tmp_path: Path):
    storage = LocalObjectStorage(tmp_path / "tenant-a")
    content = b"PIGE360-document"
    info = storage.put_bytes("documents/2026/test.pdf", content, content_type="application/pdf")
    assert info.sha256 == hashlib.sha256(content).hexdigest()
    assert info.bytes == len(content)
    assert storage.get_bytes(info.key) == content
    assert b"".join(storage.iter_bytes(info.key, 3)) == content
    assert storage.exists(info.key)


def test_local_object_storage_rejects_traversal(tmp_path: Path):
    storage = LocalObjectStorage(tmp_path / "tenant-a")
    with pytest.raises(ValueError):
        storage.put_bytes("../tenant-b/secret.txt", b"no")
