#!/usr/bin/env node

import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

function parseArgs(argv) {
  const options = {};
  for (let index = 0; index < argv.length; index += 1) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith('--') || !value || value.startsWith('--')) {
      throw new Error(`Argumento inválido ou sem valor: ${key ?? '(ausente)'}`);
    }
    options[key.slice(2)] = value;
    index += 1;
  }
  return options;
}

function required(options, key) {
  const value = options[key]?.trim();
  if (!value) throw new Error(`--${key} é obrigatório.`);
  return value;
}

function normalizeStatus(value) {
  const status = value?.trim().toLowerCase() || 'unknown';
  return ['success', 'failure', 'cancelled', 'skipped'].includes(status)
    ? status
    : 'unknown';
}

function main() {
  const options = parseArgs(process.argv.slice(2));
  const output = path.resolve(required(options, 'output'));
  const label = required(options, 'label');
  const status = normalizeStatus(process.env.BUILD_STATUS);
  const runUrl = process.env.RELEASE_RUN_URL?.trim() || null;
  const payload = {
    schemaVersion: 1,
    id: required(options, 'id'),
    label,
    platform: required(options, 'platform'),
    arch: required(options, 'arch'),
    target: required(options, 'target'),
    artifact: required(options, 'artifact'),
    status,
    success: status === 'success',
    runUrl,
    error: status === 'success'
      ? null
      : `O job ${label} terminou com status ${status}. Consulte os logs da execução${runUrl ? `: ${runUrl}` : '.'}`,
  };

  fs.mkdirSync(path.dirname(output), { recursive: true });
  fs.writeFileSync(output, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
  console.log(`${label}: ${status} -> ${output}`);
}

try {
  main();
} catch (error) {
  console.error(`Falha ao registrar o resultado do build: ${error.message}`);
  process.exit(1);
}
