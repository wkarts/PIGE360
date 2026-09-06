$ErrorActionPreference = "Stop"

Write-Host "[rustfmt] Formatando todo o código Rust do template..."
cargo fmt --manifest-path src-tauri/Cargo.toml --all

Write-Host "[rustfmt] Conferindo formatação..."
cargo fmt --manifest-path src-tauri/Cargo.toml --all --check
