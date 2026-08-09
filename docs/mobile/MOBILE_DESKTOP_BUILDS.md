# Builds mobile e desktop

Fontes Tauri 2 estão em `apps/*/src-tauri`. Os scripts verificam toolchain antes de compilar e retornam `SKIPPED_NOT_CONFIGURED` quando ausente.

Artefatos previstos:

- Windows x64/x86;
- Linux x64/ARM64;
- macOS Intel/Apple Silicon;
- Android APK/AAB;
- iOS `.app`, `.xcarchive` e IPA unsigned técnica;
- assinatura somente com secrets temporários.

Nesta máquina não havia Rust, Android SDK nem Xcode. Portanto, nenhum instalador nativo está listado como build aprovado.
