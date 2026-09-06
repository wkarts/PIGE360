# Serviço Linux/systemd

Exemplo de unidade systemd:

```ini
[Unit]
Description=PIGE360 Deployer Server
After=network.target

[Service]
ExecStart=/opt/pige360-deployer/app-server --mode=headless-api
Restart=always
User=pige360deployer
Environment=APP_ENV=production

[Install]
WantedBy=multi-user.target
```
