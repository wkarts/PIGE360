import fs from 'node:fs';
import path from 'node:path';

function readOptionalTag() {
  const tagArg = process.argv.find((arg) => arg.startsWith('--tag='));
  if (tagArg) return tagArg.split('=')[1]?.trim();
  const shortTagIndex = process.argv.findIndex((arg) => arg === '--tag' || arg === '-t');
  if (shortTagIndex >= 0) return process.argv[shortTagIndex + 1]?.trim();
  return undefined;
}

const root = process.cwd();
const versionFile = fs.readFileSync(path.join(root, 'VERSION'), 'utf8').trim();
const packageJson = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
const tauriConf = JSON.parse(fs.readFileSync(path.join(root, 'src-tauri', 'tauri.conf.json'), 'utf8'));
const projectConfig = fs.readFileSync(path.join(root, 'src', 'config', 'projectConfig.ts'), 'utf8');
const cargoToml = fs.readFileSync(path.join(root, 'src-tauri', 'Cargo.toml'), 'utf8');
const cargoMatch = cargoToml.match(/\[package\][\s\S]*?^version\s*=\s*"([^"]+)"/m);

if (!cargoMatch) {
  console.error('Não foi possível localizar a versão em src-tauri/Cargo.toml');
  process.exit(1);
}

const projectVersionMatch = projectConfig.match(/version:\s*"([^"]+)"/);
if (!projectVersionMatch) {
  console.error('Não foi possível localizar a versão em src/config/projectConfig.ts');
  process.exit(1);
}

const versions = {
  'VERSION': versionFile,
  'package.json': packageJson.version,
  'src-tauri/Cargo.toml': cargoMatch[1],
  'src-tauri/tauri.conf.json': tauriConf.version,
  'src/config/projectConfig.ts': projectVersionMatch[1],
};

const unique = new Set(Object.values(versions));
if (unique.size !== 1) {
  console.error('Versões fora de sincronia:');
  for (const [file, version] of Object.entries(versions)) {
    console.error(`- ${file}: ${version}`);
  }
  process.exit(1);
}

const expectedTag = readOptionalTag();
if (expectedTag) {
  const normalizedTag = expectedTag.replace(/^v/i, '');
  if (normalizedTag !== versionFile) {
    console.error(`Tag de release fora de sincronia: tag=${expectedTag} e versão=${versionFile}`);
    process.exit(1);
  }
}

const tagMsg = expectedTag ? ` e tag ${expectedTag}` : '';
console.log(`Versionamento sincronizado em ${versionFile}${tagMsg}`);
