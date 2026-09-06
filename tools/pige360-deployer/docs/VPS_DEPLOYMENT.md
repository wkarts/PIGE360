# VPS Deployment

Modelo de uso em VPS:

```bash
./app-server --mode=headless-api --host=127.0.0.1 --port=61001
```

Checklist:

- Configurar banco.
- Configurar token da API.
- Habilitar `/health`.
- Criar serviço systemd.
- Configurar backup de banco e configurações.
- Validar logs.
