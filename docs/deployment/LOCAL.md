# Execução local

## Núcleo sem containers

```bash
cd backend
PYTHONPATH=. uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Defina `APP_DEMO_MODE=true` somente em ambiente isolado. Hosts de exemplo precisam ser enviados no cabeçalho `Host`; o domínio desconhecido é rejeitado.

## Frontends

Os diretórios `apps/*/dist` são builds PWA estáticos determinísticos. O código Vue 3/TypeScript está em `apps/*/src`. Como as dependências npm não estavam em cache e a rede foi proibida, a compilação Vite real não foi executada nesta revisão.
