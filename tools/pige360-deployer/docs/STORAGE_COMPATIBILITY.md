# Storage compatibility

A versão `1.1.2` preserva a camada local de storage e adiciona providers formais para uso em Web/PWA/Tauri.

## Providers disponíveis

```text
src/core/storage/StorageProvider.ts
src/core/storage/WebLocalStorageProvider.ts
src/core/storage/WebSessionStorageProvider.ts
src/core/storage/StorageProviderFactory.ts
src/core/storage/WebLocalDatabase.ts
```

## Banco Web

O banco Web usa a seguinte ordem:

```text
IndexedDB disponível  -> IndexedDbDatabaseProvider
IndexedDB indisponível -> LocalStorageDatabaseProvider
```

## Regra de compatibilidade

Nenhuma tela deve acessar diretamente `localStorage`, `sessionStorage`, `indexedDB` ou `@tauri-apps`.

Use providers:

```ts
import { useStorageProvider } from '../core/storage/StorageProviderFactory'

const storage = useStorageProvider('local')
await storage.set('key', { value: true })
```
