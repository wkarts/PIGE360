#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

const manifestArg = process.argv[2] || "app.manifest.json";
const manifestPath = path.resolve(process.cwd(), manifestArg);
if (!fs.existsSync(manifestPath)) {
  console.error(`Manifesto não encontrado: ${manifestPath}`);
  console.error("Use: npm run new:app -- app.manifest.json");
  process.exit(1);
}
const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
const root = process.cwd();
const readJson = (file) => JSON.parse(fs.readFileSync(path.join(root, file), "utf8"));
const writeJson = (file, data) => fs.writeFileSync(path.join(root, file), `${JSON.stringify(data, null, 2)}\n`);
const replaceInFile = (file, replacements) => {
  const full = path.join(root, file);
  if (!fs.existsSync(full)) return;
  let text = fs.readFileSync(full, "utf8");
  for (const [from, to] of replacements) {
    if (from instanceof RegExp) {
      text = text.replace(from, to);
    } else {
      text = text.replaceAll(from, to);
    }
  }
  fs.writeFileSync(full, text);
};
const copyIfExists = (src, dest) => {
  if (!src) return;
  const from = path.resolve(path.dirname(manifestPath), src);
  const to = path.join(root, dest);
  if (!fs.existsSync(from)) return;
  fs.mkdirSync(path.dirname(to), { recursive: true });
  fs.copyFileSync(from, to);
};
const appName = manifest.appName || manifest.name || "Minha Aplicação";
const productName = manifest.productName || appName;
const shortName = manifest.shortName || appName;
const identifier = manifest.identifier || "br.com.minhaempresa.app";
const packageName = manifest.packageName || identifier.split(".").slice(-1)[0].replace(/[^a-z0-9_-]/gi, "-").toLowerCase();
const localDataDir = manifest.localDataDir || packageName.replace(/-/g, "_");
const storagePrefix = manifest.storagePrefix || packageName;
const version = manifest.version || "1.0.0";

const pkg = readJson("package.json");
pkg.name = packageName;
pkg.version = version;
writeJson("package.json", pkg);

const tauri = readJson("src-tauri/tauri.conf.json");
tauri.productName = productName;
tauri.version = version;
tauri.identifier = identifier;
if (tauri.app?.windows?.[0]) tauri.app.windows[0].title = productName;
writeJson("src-tauri/tauri.conf.json", tauri);

replaceInFile("src/config/projectConfig.ts", [
  ['name: "PIGE360 Deployer"', `name: ${JSON.stringify(appName)}`],
  ['shortName: "Template"', `shortName: ${JSON.stringify(shortName)}`],
  ['productName: "PIGE360 Deployer"', `productName: ${JSON.stringify(productName)}`],
  ['windowTitle: "PIGE360 Deployer"', `windowTitle: ${JSON.stringify(productName)}`],
  ['identifier: "br.com.pige360.deployer"', `identifier: ${JSON.stringify(identifier)}`],
  ['developer: "PIGE360 Deployer"', `developer: ${JSON.stringify(manifest.developer || productName)}`],
  ['localDataDir: "pige360_deployer"', `localDataDir: ${JSON.stringify(localDataDir)}`],
  ['storagePrefix: "pige360-deployer"', `storagePrefix: ${JSON.stringify(storagePrefix)}`],
  [/version:\s*\"[^\"]+\"/, `version: ${JSON.stringify(version)}`],
]);
replaceInFile("src-tauri/Cargo.toml", [[/version\s*=\s*\"[^\"]+\"/, `version = "${version}"`]]);
fs.writeFileSync(path.join(root, "VERSION"), `${version}\n`);
copyIfExists(manifest.assets?.logoLight, "src/assets/branding/logo-light.png");
copyIfExists(manifest.assets?.logoDark, "src/assets/branding/logo-dark.png");
copyIfExists(manifest.assets?.logoMark, "src/assets/branding/logo-mark.png");
copyIfExists(manifest.assets?.iconPng, "src-tauri/icons/icon.png");
copyIfExists(manifest.assets?.iconIco, "src-tauri/icons/icon.ico");
copyIfExists(manifest.assets?.trayIcon, "src/assets/branding/tray-icon.png");
const envLines = [
  `APP_NAME=${appName}`,
  `APP_IDENTIFIER=${identifier}`,
  `APP_LOCAL_DATA_DIR=${localDataDir}`,
  `PIGE360_DEPLOYER_NAME=${appName}`,
  `PIGE360_DEPLOYER_IDENTIFIER=${identifier}`,
  `PIGE360_DEPLOYER_LOCAL_DATA_DIR=${localDataDir}`,
  `VITE_APP_NAME=${appName}`,
  `VITE_APP_IDENTIFIER=${identifier}`,
  `VITE_APP_LOCAL_DATA_DIR=${localDataDir}`,
  `VITE_APP_STORAGE_PREFIX=${storagePrefix}`,
];
fs.writeFileSync(path.join(root, ".env"), `${envLines.join("\n")}\n`);
console.log(`Aplicação derivada configurada: ${productName} (${identifier})`);
