import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const rootDir = dirname(fileURLToPath(import.meta.url));
const envFile = resolve(rootDir, '.env');

function loadDotEnv(path) {
  if (!existsSync(path)) return;
  const content = readFileSync(path, 'utf8');
  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#') || !line.includes('=')) continue;
    const index = line.indexOf('=');
    const key = line.slice(0, index).trim();
    let value = line.slice(index + 1).trim();
    value = value.replace(/^['"]|['"]$/g, '');
    if (key && process.env[key] === undefined) {
      process.env[key] = value;
    }
  }
}

function envBool(name, fallback = false) {
  const value = process.env[name];
  if (value === undefined || value === null || value === '') return fallback;
  return ['1', 'true', 'yes', 'sim', 'on'].includes(String(value).trim().toLowerCase());
}

function setDefaultEnv(name, value) {
  if (process.env[name] === undefined || process.env[name] === '') {
    process.env[name] = String(value);
  }
}

function forceEnv(name, value) {
  process.env[name] = String(value);
}

loadDotEnv(envFile);

const publishAllPorts = envBool('PIGE360_DEPLOYER_PUBLISH_ALL_PORTS', false);
const startAllPorts = envBool('PIGE360_DEPLOYER_START_ALL_PORTS', false);
const respectCloudPanelPort = envBool('PIGE360_DEPLOYER_RESPECT_CLOUDPANEL_PORT', true);
const publicBindHost = process.env.PIGE360_DEPLOYER_PUBLIC_BIND_HOST || '0.0.0.0';

const binPath = resolve(rootDir, process.env.PIGE360_DEPLOYER_BINARY || './bin/pige360_deployer');
const dataDir = resolve(rootDir, process.env.PIGE360_DEPLOYER_DATA_DIR || './data');
const logsDir = resolve(rootDir, process.env.PIGE360_DEPLOYER_LOGS_DIR || './logs');
const distDir = resolve(rootDir, process.env.PIGE360_DEPLOYER_WEB_DIST_DIR || './dist');

mkdirSync(dataDir, { recursive: true });
mkdirSync(logsDir, { recursive: true });

if (!existsSync(binPath)) {
  console.error(`[cloudpanel] Binário não encontrado: ${binPath}`);
  console.error('[cloudpanel] Gere o release Linux com scripts/linux/build-cloudpanel-release.sh antes do deploy.');
  process.exit(1);
}

if (!existsSync(resolve(distDir, 'index.html'))) {
  console.error(`[cloudpanel] Frontend dist não encontrado em: ${distDir}`);
  console.error('[cloudpanel] Execute npm run build:web antes de empacotar ou copie a pasta dist para o release.');
  process.exit(1);
}

if (publishAllPorts) {
  forceEnv('PIGE360_DEPLOYER_API_HOST', process.env.PIGE360_DEPLOYER_API_HOST || publicBindHost);
  forceEnv('PIGE360_DEPLOYER_WEB_HOST', process.env.PIGE360_DEPLOYER_WEB_HOST || publicBindHost);
  forceEnv('PIGE360_DEPLOYER_WEBHOOK_HOST', process.env.PIGE360_DEPLOYER_WEBHOOK_HOST || publicBindHost);
  forceEnv('PIGE360_DEPLOYER_WEBSOCKET_HOST', process.env.PIGE360_DEPLOYER_WEBSOCKET_HOST || publicBindHost);

  setDefaultEnv('PIGE360_DEPLOYER_API_ALLOW_PUBLIC_NETWORK', 'true');
  setDefaultEnv('PIGE360_DEPLOYER_API_CORS', 'true');
  setDefaultEnv('PIGE360_DEPLOYER_WEB_BIND_LAN', 'true');
  setDefaultEnv('PIGE360_DEPLOYER_WEBHOOK_ALLOW_LAN', 'true');
  setDefaultEnv('PIGE360_DEPLOYER_WEBHOOK_ALLOW_EXTERNAL', 'true');
  setDefaultEnv('PIGE360_DEPLOYER_WEBSOCKET_ALLOW_LAN', 'true');
  setDefaultEnv('PIGE360_DEPLOYER_WEBSOCKET_ALLOW_EXTERNAL', 'true');
}

if (startAllPorts) {
  forceEnv('PIGE360_DEPLOYER_WEBHOOK_ENABLED', 'true');
  forceEnv('PIGE360_DEPLOYER_WEBHOOK_AUTO_START', 'true');
  forceEnv('PIGE360_DEPLOYER_WEBSOCKET_ENABLED', 'true');
  forceEnv('PIGE360_DEPLOYER_WEBSOCKET_AUTO_START', 'true');
  forceEnv('PIGE360_DEPLOYER_SERVICES_AUTO_START', 'true');
}

const apiHost = process.env.PIGE360_DEPLOYER_API_HOST || '127.0.0.1';
const apiPort = process.env.PIGE360_DEPLOYER_API_PORT || '61001';

// CloudPanel normalmente injeta PORT para a aplicação Node.js.
// Quando PIGE360_DEPLOYER_RESPECT_CLOUDPANEL_PORT=true, PORT vira a porta do WebPort.
// Para publicar todas as portas diretamente, use PIGE360_DEPLOYER_RESPECT_CLOUDPANEL_PORT=false.
const webPort = respectCloudPanelPort && process.env.PORT
  ? process.env.PORT
  : (process.env.PIGE360_DEPLOYER_WEB_PORT || '61002');
const webHost = process.env.PIGE360_DEPLOYER_WEB_HOST || '127.0.0.1';
const webhookHost = process.env.PIGE360_DEPLOYER_WEBHOOK_HOST || '127.0.0.1';
const webhookPort = process.env.PIGE360_DEPLOYER_WEBHOOK_PORT || '61003';
const websocketHost = process.env.PIGE360_DEPLOYER_WEBSOCKET_HOST || '127.0.0.1';
const websocketPort = process.env.PIGE360_DEPLOYER_WEBSOCKET_PORT || '61004';

process.env.PIGE360_DEPLOYER_ENV_FILE = process.env.PIGE360_DEPLOYER_ENV_FILE || envFile;
process.env.PIGE360_DEPLOYER_WEB_DIST_DIR = distDir;
process.env.PIGE360_DEPLOYER_API_HOST = apiHost;
process.env.PIGE360_DEPLOYER_API_PORT = apiPort;
process.env.PIGE360_DEPLOYER_API_BASE_URL = process.env.PIGE360_DEPLOYER_API_BASE_URL || `http://127.0.0.1:${apiPort}`;
process.env.PIGE360_DEPLOYER_WEB_HOST = webHost;
process.env.PIGE360_DEPLOYER_WEB_PORT = String(webPort);
process.env.PIGE360_DEPLOYER_WEB_ENABLED = process.env.PIGE360_DEPLOYER_WEB_ENABLED || 'true';
process.env.PIGE360_DEPLOYER_WEB_AUTO_START = process.env.PIGE360_DEPLOYER_WEB_AUTO_START || 'true';
process.env.PIGE360_DEPLOYER_SERVICES_AUTO_START = process.env.PIGE360_DEPLOYER_SERVICES_AUTO_START || 'true';
process.env.PIGE360_DEPLOYER_WEBHOOK_HOST = webhookHost;
process.env.PIGE360_DEPLOYER_WEBHOOK_PORT = webhookPort;
process.env.PIGE360_DEPLOYER_WEBSOCKET_HOST = websocketHost;
process.env.PIGE360_DEPLOYER_WEBSOCKET_PORT = websocketPort;

const args = [
  '--mode=headless-api',
  '--host', apiHost,
  '--port', String(apiPort),
  '--data-dir', dataDir,
  '--start-web-proxy',
  '--start-services'
];

if (process.env.PIGE360_DEPLOYER_WEBHOOK_ENABLED === 'true') {
  args.push('--start-webhook');
}

if (process.env.PIGE360_DEPLOYER_WEBSOCKET_ENABLED === 'true') {
  args.push('--start-websocket');
}

console.log(`[cloudpanel] Iniciando ${binPath}`);
console.log(`[cloudpanel] WebPort:   http://${webHost}:${webPort}`);
console.log(`[cloudpanel] API:       http://${apiHost}:${apiPort}`);
console.log(`[cloudpanel] Webhook:   http://${webhookHost}:${webhookPort}${process.env.PIGE360_DEPLOYER_WEBHOOK_BASE_PATH || '/webhooks'} (${process.env.PIGE360_DEPLOYER_WEBHOOK_ENABLED === 'true' ? 'enabled' : 'disabled'})`);
console.log(`[cloudpanel] WebSocket: ws://${websocketHost}:${websocketPort}${process.env.PIGE360_DEPLOYER_WEBSOCKET_PATH || '/ws'} (${process.env.PIGE360_DEPLOYER_WEBSOCKET_ENABLED === 'true' ? 'enabled' : 'disabled'})`);
console.log(`[cloudpanel] Data dir:  ${dataDir}`);
console.log(`[cloudpanel] Publish all ports: ${publishAllPorts ? 'true' : 'false'}`);

const child = spawn(binPath, args, {
  cwd: rootDir,
  env: process.env,
  stdio: 'inherit'
});

function shutdown(signal) {
  if (!child.killed) {
    child.kill(signal);
  }
}

process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));

child.on('exit', (code, signal) => {
  if (signal) {
    console.error(`[cloudpanel] Processo encerrado por sinal: ${signal}`);
    process.exit(128);
  }
  process.exit(code ?? 0);
});
