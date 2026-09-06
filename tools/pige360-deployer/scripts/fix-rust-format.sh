#!/usr/bin/env bash
set -euo pipefail

echo "[rustfmt] Formatando todo o código Rust do template..."
cargo fmt --manifest-path src-tauri/Cargo.toml --all

echo "[rustfmt] Conferindo formatação..."
cargo fmt --manifest-path src-tauri/Cargo.toml --all --check
