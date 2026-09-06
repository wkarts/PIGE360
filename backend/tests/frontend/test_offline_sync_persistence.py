from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_browser_outbox_contract_is_persistent_isolated_and_fail_closed() -> None:
    typescript = (ROOT / "packages/offline-sync/src/index.ts").read_text(encoding="utf-8")
    javascript = (ROOT / "packages/offline-sync/src/index.js").read_text(encoding="utf-8")

    for source in (typescript, javascript):
        assert "BrowserOfflineStore" in source
        assert "pige360-offline:" in source
        assert 'createObjectStore("outbox"' in source
        assert 'createObjectStore("cache"' in source
        assert 'createObjectStore("metadata"' in source
        assert "IDEMPOTENCY_CONFLICT" in source
        assert "não pode usar armazenamento volátil" in source
        assert "new BrowserOfflineStore(tenantId, userId)" in source

    assert "encodeURIComponent(tenantId)" in typescript
    assert "encodeURIComponent(userId)" in typescript
    assert 'if (typeof window === "undefined") return null;' in typescript

