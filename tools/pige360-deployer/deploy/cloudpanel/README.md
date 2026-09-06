# PIGE360 Deployer - Release CloudPanel/Linux sem instalador

Pacote para **Debian/Ubuntu**, **CloudPanel**, **CLI** e **navegador**, sem instalador gráfico e sem abrir janela desktop/Tauri.

O release oficial gera dois artefatos:

- `linux-x64`: `x86_64-unknown-linux-gnu`
- `linux-x86`: `i686-unknown-linux-gnu`

## Uso no CloudPanel como Node.js Application

1. Envie/descompacte o `.tar.gz` gerado no GitHub Release.
2. Copie o ambiente padrão:
   ```bash
   cp .env.example .env
   ```
3. Confirme permissão do binário:
   ```bash
   chmod +x bin/pige360_deployer *.sh
   ```
4. No CloudPanel, use:
   ```bash
   npm start
   ```

O CloudPanel normalmente injeta a variável `PORT`. Por padrão, o launcher usa essa porta como porta do WebPort/browser.

## Uso direto por terminal Linux

```bash
cp .env.example .env
chmod +x bin/pige360_deployer *.sh
./start.sh
./status.sh
./logs.sh
```

Parar/reiniciar:

```bash
./stop.sh
./restart.sh
```

CLI:

```bash
./cli.sh
```

Worker:

```bash
./worker.sh
```

Ver portas configuradas:

```bash
./ports.sh
# ou
npm run ports
```

Health check:

```bash
npm run health
```

Cron opcional para checagem:

```cron
* * * * * cd /caminho/do/app && ./check.sh >/dev/null 2>&1
```

## Portas padrão

| Serviço | Variável | Padrão seguro | Porta |
|---|---|---:|---:|
| API Headless | `PIGE360_DEPLOYER_API_HOST` / `PIGE360_DEPLOYER_API_PORT` | `127.0.0.1` | `61001` |
| Web/browser/WebPort | `PIGE360_DEPLOYER_WEB_HOST` / `PIGE360_DEPLOYER_WEB_PORT` | `127.0.0.1` | `61002` |
| Webhook | `PIGE360_DEPLOYER_WEBHOOK_HOST` / `PIGE360_DEPLOYER_WEBHOOK_PORT` | `127.0.0.1` | `61003` |
| WebSocket | `PIGE360_DEPLOYER_WEBSOCKET_HOST` / `PIGE360_DEPLOYER_WEBSOCKET_PORT` | `127.0.0.1` | `61004` |

## Alterar portas

Edite o `.env`:

```env
PIGE360_DEPLOYER_API_PORT=62001
PIGE360_DEPLOYER_WEB_PORT=62002
PIGE360_DEPLOYER_WEBHOOK_PORT=62003
PIGE360_DEPLOYER_WEBSOCKET_PORT=62004
```

No CloudPanel, se ele injetar `PORT`, essa porta terá prioridade sobre `PIGE360_DEPLOYER_WEB_PORT`. Para forçar o uso da porta do `.env`:

```env
PIGE360_DEPLOYER_RESPECT_CLOUDPANEL_PORT=false
```

## Publicar todas as portas da aplicação

Por padrão, o release é seguro e mantém tudo em `127.0.0.1`. Para publicar API, Web, Webhook e WebSocket diretamente em todas as interfaces de rede, use:

```bash
cp .env.public.example .env
```

Ou ajuste manualmente:

```env
PIGE360_DEPLOYER_PUBLISH_ALL_PORTS=true
PIGE360_DEPLOYER_START_ALL_PORTS=true
PIGE360_DEPLOYER_RESPECT_CLOUDPANEL_PORT=false
PIGE360_DEPLOYER_PUBLIC_BIND_HOST=0.0.0.0

PIGE360_DEPLOYER_API_HOST=0.0.0.0
PIGE360_DEPLOYER_API_PORT=61001

PIGE360_DEPLOYER_WEB_HOST=0.0.0.0
PIGE360_DEPLOYER_WEB_PORT=61002

PIGE360_DEPLOYER_WEBHOOK_ENABLED=true
PIGE360_DEPLOYER_WEBHOOK_AUTO_START=true
PIGE360_DEPLOYER_WEBHOOK_HOST=0.0.0.0
PIGE360_DEPLOYER_WEBHOOK_PORT=61003

PIGE360_DEPLOYER_WEBSOCKET_ENABLED=true
PIGE360_DEPLOYER_WEBSOCKET_AUTO_START=true
PIGE360_DEPLOYER_WEBSOCKET_HOST=0.0.0.0
PIGE360_DEPLOYER_WEBSOCKET_PORT=61004
```

Depois libere as portas no firewall/Nginx/proxy conforme sua infraestrutura.

## Segurança

Se for publicar portas diretamente:

- troque `PIGE360_DEPLOYER_API_TOKEN`, `PIGE360_DEPLOYER_WEBHOOK_TOKEN` e `PIGE360_DEPLOYER_WEBSOCKET_TOKEN`;
- mantenha `PIGE360_DEPLOYER_API_REQUIRE_TOKEN=true`;
- use firewall para liberar apenas IPs confiáveis quando possível;
- prefira HTTPS/reverse proxy para tráfego público.

Para CloudPanel convencional, a recomendação é expor publicamente apenas o WebPort pelo painel e manter API/Webhook/WebSocket em `127.0.0.1`.
