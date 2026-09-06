from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_session_client_revokes_server_session_before_local_cleanup() -> None:
    typescript = (ROOT / "packages/auth/src/index.ts").read_text(encoding="utf-8")
    javascript = (ROOT / "packages/auth/src/index.js").read_text(encoding="utf-8")

    for source in (typescript, javascript):
        assert 'this.url("/auth/logout")' in source
        assert '"Authorization": `Bearer ${tokens.access_token}`' in source
        assert "JSON.stringify({ refresh_token: tokens.refresh_token })" in source
        assert source.index('this.url("/auth/logout")') < source.index("await clearSession(this.manifest)")
        assert "finally" in source
        assert "await clearSession(this.manifest)" in source
