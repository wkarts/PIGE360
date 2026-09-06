#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const lockPath = path.join(root, 'package-lock.json');

const internalPrefixes = [
  'https://packages.applied-caas-gateway1.internal.api.openai.org/artifactory/api/npm/npm-public/',
  'http://packages.applied-caas-gateway1.internal.api.openai.org/artifactory/api/npm/npm-public/',
];

if (!fs.existsSync(lockPath)) {
  console.log('[npm-lock] package-lock.json não encontrado; nada a normalizar.');
  process.exit(0);
}

let content = fs.readFileSync(lockPath, 'utf8');
let changed = false;

for (const prefix of internalPrefixes) {
  if (content.includes(prefix)) {
    content = content.split(prefix).join('https://registry.npmjs.org/');
    changed = true;
  }
}

if (changed) {
  fs.writeFileSync(lockPath, content, 'utf8');
  console.log('[npm-lock] package-lock.json normalizado para registry.npmjs.org.');
} else {
  console.log('[npm-lock] package-lock.json já está com registry público ou sem resolved interno.');
}
