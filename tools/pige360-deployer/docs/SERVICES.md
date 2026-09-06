# Serviços Windows e Linux

A Etapa 2.2 implementa comandos reais de serviço para Windows e Linux.

## Windows

Usa `sc.exe`.

- `app_service_install`: cria serviço apontando para o executável atual com `--mode=headless-api`.
- `app_service_uninstall`: remove o serviço.
- `app_service_start`: inicia.
- `app_service_stop`: para.
- `app_service_restart`: para e inicia.
- `app_service_status`: consulta status.

Variável opcional:

```bash
PIGE360_DEPLOYER_SERVICE_NAME=Pige360DeployerServer
```

## Linux

Usa `systemd` e requer permissão administrativa para instalar/remover unit.

- `app_service_install`: grava `/etc/systemd/system/pige360-deployer-server.service`, executa daemon-reload e enable.
- `app_service_uninstall`: disable, remove unit e daemon-reload.
- `app_service_start`: start.
- `app_service_stop`: stop.
- `app_service_restart`: stop/start.
- `app_service_status`: status.
