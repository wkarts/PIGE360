# Build Windows local

Este template inclui scripts oficiais para compilar e validar a aplicação no Windows.

## Pré-requisitos

Instale no Windows:

1. Node.js LTS.
2. Rust via `rustup`.
3. WebView2 Runtime atualizado.
4. Dependências nativas exigidas pelo Tauri para Windows.

Depois confirme no PowerShell:

```powershell
node --version
npm --version
rustc --version
cargo --version
```

## Build completo padrão

Na raiz do projeto:

```bat
build-windows.bat
```

Ou diretamente:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\build-windows.ps1
```

Esse fluxo executa:

1. verificação de pré-requisitos;
2. `npm ci` ou `npm install`;
3. validação de versão;
4. typecheck Vue/TypeScript;
5. build Web/Vite;
6. `cargo fmt`;
7. `cargo clippy`;
8. testes Rust;
9. build Tauri Windows.

## Build debug

```bat
build-windows.bat -Mode Debug
```

## Build web apenas

```bat
build-windows.bat -WebOnly
```

## Build Tauri sem executar clippy/testes Rust

Útil para validar rapidamente problemas de empacotamento:

```bat
build-windows.bat -SkipRustChecks
```

## Limpar artefatos antes do build

```bat
build-windows.bat -Clean
```

## Abrir pasta do resultado ao concluir

```bat
build-windows.bat -OpenOutput
```

## Usar portas diferentes durante validação

As portas de serviços devem ser configuradas por `.env`, `.env.local`, tela de parâmetros da aplicação ou variáveis de ambiente.

Exemplo temporário no build:

```bat
build-windows.bat -DevPort 62002 -InternalApiPort 62001
```

PowerShell:

```powershell
.\build-windows.bat -DevPort 62002 -InternalApiPort 62001
```

Variáveis compatíveis:

```env
VITE_DEV_HOST=127.0.0.1
VITE_DEV_PORT=61002
VITE_INTERNAL_API_HOST=127.0.0.1
VITE_INTERNAL_API_PORT=61001
```

A porta padrão do Tauri `devUrl` permanece independente em `1420` para desenvolvimento desktop.

## Resultado esperado

Release:

```text
src-tauri\target\release\bundle
```

Debug:

```text
src-tauri\target\debug\bundle
```

## Observação para apps derivados

Aplicações herdadas do template devem configurar identidade, diretório de dados, ícones, portas e serviços por:

- `app.manifest.json`;
- `.env.local`;
- tela de parâmetros;
- variáveis de ambiente.

Não altere manualmente arquivos espalhados quando for criar uma nova aplicação derivada. Use:

```bash
npm run new:app -- app.manifest.json
```

## Instalação de dependências sem travar no Windows

O pacote do template **não deve ser distribuído com `node_modules`, `dist` ou `src-tauri/target`**. Esses diretórios são gerados localmente.

O script aceita modos de instalação:

```bat
build-windows.bat -InstallMode Auto
build-windows.bat -InstallMode Ci
build-windows.bat -InstallMode Install
build-windows.bat -InstallMode Offline
build-windows.bat -NoInstall
build-windows.bat -PreferExistingNodeModules
```

Recomendação para primeira compilação limpa:

```bat
build-windows.bat -InstallMode Install
```

Recomendação quando as dependências já foram instaladas:

```bat
build-windows.bat -NoInstall
```

Ou:

```bat
build-windows.bat -PreferExistingNodeModules
```

O script também normaliza automaticamente o `package-lock.json` para o registry público:

```text
https://registry.npmjs.org/
```

Isso evita erro quando um lockfile foi gerado em ambiente interno/proxy e contém URLs de registry privado.

## Quando ocorrer timeout no npm

Se o `npm ci` falhar por rede/proxy, use uma destas opções:

```bat
npm config set registry https://registry.npmjs.org/
npm install
build-windows.bat -NoInstall
```

Ou, se o cache local já possuir os pacotes:

```bat
build-windows.bat -InstallMode Offline
```

## Limpeza manual recomendada

Caso o Windows bloqueie remoção de pasta com `EPERM`, feche editores, terminais e processos Node, depois execute:

```bat
rmdir /s /q node_modules
rmdir /s /q dist
rmdir /s /q src-tauri\target
npm install
build-windows.bat -NoInstall
```

## Correção aplicada para erro `LINK : fatal error LNK1104`

A partir deste pacote, o build Windows usa automaticamente um `CARGO_TARGET_DIR` curto fora da pasta do projeto, normalmente em:

```text
%TEMP%\tauri-target\<hash-do-projeto>
```

Isso evita falhas do `link.exe` quando o projeto está em caminho longo ou com espaços, por exemplo:

```text
C:\Users\ARGWS\Downloads\Template Tauri\...
```

O erro corrigido costuma aparecer assim:

```text
LINK : fatal error LNK1104: não é possível abrir o arquivo ...\target\debug\build\...\build_script_build-....exe
```

O comportamento padrão agora é o mais seguro:

```bat
build-windows.bat
```

Para forçar um diretório específico:

```bat
build-windows.bat -CargoTargetDir C:\tauri-target\pige360-deployer
```

Para voltar ao comportamento antigo, usando `src-tauri\target` dentro do projeto:

```bat
build-windows.bat -UseProjectCargoTarget
```

Quando o `CARGO_TARGET_DIR` curto estiver ativo, o bundle final deixa de ficar em `src-tauri\target\...` e passa a ficar em:

```text
%TEMP%\tauri-target\<hash-do-projeto>\release\bundle
```

O script mostra esse caminho no final do build.

## Recomendação adicional para Windows

Use preferencialmente:

- Node.js `22.14.0` ou superior da linha 22, ou Node.js `24.10.0` ou superior;
- Visual Studio Build Tools 2022 com workload C++;
- Rust instalado via `rustup`.

O Node `22.12.0` pode emitir `EBADENGINE` por causa do `semantic-release`
moderno. O CI/release usa Node 24.
