#!/usr/bin/env node
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const pathSeparator = process.platform === 'win32' ? ';' : ':';

function commandOutput(command, args, options = {}) {
  return spawnSync(command, args, {
    cwd: root,
    encoding: 'utf8',
    shell: false,
    ...options,
  });
}

function isUsableCargo(candidate) {
  if (!candidate || candidate.trim() === '') return false;

  const result = commandOutput(candidate, ['--version']);
  const output = `${result.stdout || ''}${result.stderr || ''}`.trim();

  return result.status === 0 && /^cargo\s+\d+\.\d+\.\d+/.test(output);
}

function pathCandidates() {
  const seen = new Set();
  const executable = process.platform === 'win32' ? 'cargo.exe' : 'cargo';
  const candidates = [];

  for (const entry of (process.env.PATH || '').split(pathSeparator)) {
    if (!entry) continue;
    const candidate = path.join(entry, executable);
    if (seen.has(candidate) || !fs.existsSync(candidate)) continue;
    seen.add(candidate);
    candidates.push(candidate);
  }

  return candidates;
}


function stableHash(value) {
  let hash = 0x811c9dc5;
  for (const char of value) {
    hash ^= char.charCodeAt(0);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash.toString(16).padStart(8, '0');
}

function resolveShortCargoTargetDir() {
  if (process.platform !== 'win32') return process.env.CARGO_TARGET_DIR;
  if (process.env.CARGO_TARGET_DIR && process.env.CARGO_TARGET_DIR.trim() !== '') {
    return process.env.CARGO_TARGET_DIR;
  }
  if (process.env.TAURI_USE_PROJECT_TARGET === 'true') return undefined;

  const base = process.env.CARGO_TARGET_BASE_DIR || path.join(process.env.TEMP || root, 'tauri-target');
  return path.join(base, stableHash(root));
}

function resolveCargo() {
  if (isUsableCargo(process.env.CARGO)) return process.env.CARGO;

  const rustup = commandOutput('rustup', ['which', 'cargo']);
  const rustupCargo = (rustup.stdout || '').trim();
  if (rustup.status === 0 && isUsableCargo(rustupCargo)) return rustupCargo;

  for (const candidate of pathCandidates()) {
    if (isUsableCargo(candidate)) return candidate;
  }

  throw new Error(
    'Cargo não está disponível ou aponta para um binário inválido. ' +
      'Instale o toolchain Rust antes de executar o build Tauri.',
  );
}

function resolveTauriCliScript() {
  const candidates = [
    path.join(root, 'node_modules', '@tauri-apps', 'cli', 'tauri.js'),
    path.join(root, 'node_modules', '@tauri-apps', 'cli', 'index.js'),
  ];

  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate;
  }

  throw new Error(
    'Tauri CLI local não encontrado em node_modules/@tauri-apps/cli. ' +
      'Execute npm ci antes do build.',
  );
}

function runTauriCli(tauriCliScript, args, env) {
  // Não executar tauri.cmd via cmd.exe. Em Windows com usuário contendo espaço
  // (ex.: C:\\Users\\ARGWS), o quoting do cmd pode quebrar.
  // Executamos diretamente o script JS do @tauri-apps/cli via node, com shell:false.
  return spawnSync(process.execPath, [tauriCliScript, ...args], {
    cwd: root,
    env,
    stdio: 'inherit',
    shell: false,
  });
}

const cargo = resolveCargo();
const cargoDir = path.dirname(cargo);
const cargoTargetDir = resolveShortCargoTargetDir();
const env = {
  ...process.env,
  CARGO: cargo,
  PATH: `${cargoDir}${pathSeparator}${process.env.PATH || ''}`,
  CARGO_INCREMENTAL: process.env.CARGO_INCREMENTAL || '0',
  CARGO_TERM_COLOR: process.env.CARGO_TERM_COLOR || 'always',
  CARGO_NET_RETRY: process.env.CARGO_NET_RETRY || '10',
};

if (cargoTargetDir) {
  fs.mkdirSync(cargoTargetDir, { recursive: true });
  env.CARGO_TARGET_DIR = cargoTargetDir;
}

const args = process.argv.slice(2);
const tauriCliScript = resolveTauriCliScript();

console.log(`[tauri-ci] usando cargo: ${cargo}`);
console.log(`[tauri-ci] usando tauri cli script: ${tauriCliScript}`);
console.log(`[tauri-ci] usando node: ${process.execPath}`);
if (env.CARGO_TARGET_DIR) console.log(`[tauri-ci] CARGO_TARGET_DIR: ${env.CARGO_TARGET_DIR}`);

const result = runTauriCli(tauriCliScript, args, env);

if (result.error) {
  console.error(`[tauri-ci] falha ao executar Tauri CLI: ${result.error.message}`);
  process.exit(1);
}

process.exit(result.status ?? 1);
