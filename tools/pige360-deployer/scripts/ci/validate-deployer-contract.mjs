#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import process from "node:process";

const root = process.cwd();
const failures = [];

function read(relative) {
  const absolute = path.join(root, relative);
  if (!fs.existsSync(absolute)) {
    failures.push(`arquivo obrigatório ausente: ${relative}`);
    return "";
  }
  return fs.readFileSync(absolute, "utf8");
}

function requireText(relative, values) {
  const content = read(relative);
  for (const value of values) {
    if (!content.includes(value)) failures.push(`${relative} não contém: ${value}`);
  }
}

function rejectText(relative, values) {
  const content = read(relative);
  for (const value of values) {
    if (content.includes(value)) failures.push(`${relative} ainda contém identidade proibida: ${value}`);
  }
}

const packageJson = JSON.parse(read("package.json") || "{}");
const tauri = JSON.parse(read("src-tauri/tauri.conf.json") || "{}");
if (packageJson.name !== "pige360-deployer") failures.push("package.json:name deve ser pige360-deployer");
if (tauri.productName !== "PIGE360 Deployer") failures.push("tauri productName deve ser PIGE360 Deployer");
if (tauri.identifier !== "br.com.pige360.deployer") failures.push("identifier Tauri divergente");

requireText("src-tauri/src/deployer/catalog.rs", [
  "deployments/dockge",
  "deployments/cloudpanel",
  "deployments/portainer",
  "Produção não aceita o canal develop",
  "Produção não aceita prerelease",
]);
requireText("src-tauri/src/deployer/agent.rs", [
  "GENERATED-MANIFEST.json",
  "synchronize_distribution",
  "OperationLock::acquire",
  "pige360-config-validate",
  "pige360-secrets-init",
  "pige360-secret-set",
  "pige360-backup",
  "pige360-readiness",
  "service-native-image-only",
  "rollback_now",
]);
rejectText("src-tauri/src/deployer/agent.rs", [
  "install.sh",
  "validate.sh",
  "update.sh",
  "rollback.sh",
  "init-secrets.sh",
]);
requireText("src-tauri/src/deployer/desktop.rs", [
  "StrictHostKeyChecking=accept-new",
  "StrictHostKeyChecking=yes",
]);
requireText("src-tauri/build.rs", [
  "pige360-deploy-agent-linux-amd64",
]);
requireText("src/config/projectConfig.ts", ["licensing: false"]);
rejectText("src/pages/DeploymentPage.vue", ["vX.Y.Z-rc.N", "v1.0.0-rc.1"]);

for (const relative of [
  "src-tauri/build.rs",
  "src-tauri/src/deployer/desktop.rs",
  "src/pages/DeploymentPage.vue",
]) {
  rejectText(relative, ["AGENT_LINUX_ARM64", "pige360-deploy-agent-linux-arm64", "aarch64"]);
}

for (const relative of [
  "package.json",
  "src-tauri/tauri.conf.json",
  "src/pages/DeploymentPage.vue",
  "src-tauri/src/deployer/desktop.rs",
  "src-tauri/src/deployer/agent.rs",
]) {
  rejectText(relative, ["ARGWS Connect Deployer", "connect-deployer", "Connect Deployer"]);
}

if (failures.length) {
  console.error("Contrato do PIGE360 Deployer reprovado:\n");
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log("Contrato PIGE360 Deployer aprovado: identidade, canais, targets, agente e release.");
