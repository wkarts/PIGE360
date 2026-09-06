# Correção Windows: caminhos com espaços

Esta correção evita falha no build Tauri quando o usuário do Windows possui espaço no caminho, por exemplo:

```text
C:\Users\ARGWS
```

O executor `scripts/ci/run-tauri.mjs` não chama mais `node_modules/.bin/tauri.cmd` via `cmd.exe`.

Agora ele executa diretamente:

```text
node node_modules/@tauri-apps/cli/tauri.js build
```

com `shell: false`, preservando corretamente caminhos com espaços.

## Validar

```bat
build-windows.bat
```

ou:

```bat
npm run build:windows
```
