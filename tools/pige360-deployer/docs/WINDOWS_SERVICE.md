# Serviço Windows

O template possui estrutura para serviço Windows. Na Etapa 2.2, os comandos executam `sc.exe`. Em serviço:

- Não abrir splash.
- Não abrir janela.
- Inicializar banco, logs, API e workers.
- Registrar status.

Comandos previstos:

```text
app_service_install
app_service_uninstall
app_service_start
app_service_stop
app_service_restart
app_service_status
```
