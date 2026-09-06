# PIGE360 Deployer Tauri Desktop Web

Este template foi evoluído para operar como uma aplicação híbrida com uma única base visual e funcional para Web, PWA e Tauri.

## Princípio arquitetural

A aplicação não deve chamar Tauri diretamente em telas, stores, serviços de domínio ou CRUDs. Toda operação sensível ao runtime passa por providers.

```text
Tela / Store / Módulo
        ↓
Repository / Service
        ↓
Provider abstrato
        ↓
Web/PWA ou Tauri
```

## Providers disponíveis

- `RuntimeProvider`: detecta Web, PWA ou Tauri.
- `CommandProvider`: executa comandos no Tauri ou fallback Web.
- `DatabaseProvider`: usa IndexedDB no navegador/PWA.
- `FileProvider`: usa File API no Web e comandos Tauri no Desktop.
- `NotificationProvider`: usa Web Notification ou comando Tauri.
- `PrintProvider`: impressão HTML isolada do layout principal.
- `RuntimeDiagnostics`: exibe o estado operacional do runtime.

## Regra obrigatória

Tudo que for exposto no Tauri precisa ter implementação Web equivalente, mesmo que seja por fallback funcional, API remota, IndexedDB, File API, Service Worker ou aviso operacional seguro.

## Comandos principais

A camada de compatibilidade mantém `src/services/tauri.ts` para não quebrar códigos existentes, mas internamente ela usa `invokeAppCommand`.

```ts
import { invokeAppCommand } from '@/core/invoker/CommandProviderFactory'

const meta = await invokeAppCommand('app_meta')
```

## Execução

```bash
npm ci
npm run dev
npm run build:web
npm run tauri:dev
npm run tauri:build
```

## Autenticação Web/PWA

O provider Web/PWA não publica nem cria uma credencial administrativa fixa. Em produção, a
autenticação deve usar a API interna/headless, que compartilha o banco migrado e o bootstrap
aleatório da instalação.

## Diagnóstico

Acesse o menu `Diagnóstico Runtime` ou a rota:

```text
/#/runtime
```

A tela informa runtime atual, provider de comandos, provider de banco, IndexedDB, Service Worker, notificações, impressão e filesystem.
