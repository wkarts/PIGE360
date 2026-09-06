#!/usr/bin/env node

import fs from 'node:fs';
import process from 'node:process';

function parseArgs(values) {
  const args = {};
  for (let index = 0; index < values.length; index += 1) {
    const value = values[index];
    if (!value.startsWith('--')) continue;
    const key = value.slice(2);
    const next = values[index + 1];
    if (!next || next.startsWith('--')) {
      args[key] = 'true';
    } else {
      args[key] = next;
      index += 1;
    }
  }
  return args;
}

function parseBoolean(value) {
  return ['1', 'true', 'yes', 'on'].includes(String(value ?? '').trim().toLowerCase());
}

function appendOutput(file, key, value) {
  fs.appendFileSync(file, `${key}=${value}\n`, 'utf8');
}

const args = parseArgs(process.argv.slice(2));
const statusPath = args.status;
const outputPath = args.output ?? process.env.GITHUB_OUTPUT;
if (!statusPath || !outputPath) throw new Error('--status e --output são obrigatórios.');

const status = JSON.parse(fs.readFileSync(statusPath, 'utf8'));
if (!['complete', 'partial'].includes(status.outcome)) {
  throw new Error(`Estado de matriz inválido: ${status.outcome ?? 'ausente'}`);
}

const allowPartial = parseBoolean(args['allow-partial']);
const coreReady = String(args['core-result'] ?? 'success') === 'success';
const publish = coreReady && (status.outcome === 'complete' || allowPartial);
let decision;
if (!coreReady) decision = 'core-failed-draft';
else if (status.outcome === 'complete') decision = 'complete';
else if (allowPartial) decision = 'partial-authorized';
else decision = 'partial-draft';

appendOutput(outputPath, 'publish', publish ? 'true' : 'false');
appendOutput(outputPath, 'decision', decision);
appendOutput(outputPath, 'outcome', status.outcome);

if (decision === 'core-failed-draft') {
  console.warn('O pacote Web/Server/self-hosted falhou; a release permanecerá em draft.');
} else if (decision === 'partial-draft') {
  console.warn(
    `Matriz parcial (${status.succeeded}/${status.total}). Os assets serão mantidos em draft; ` +
      'retome a tag após corrigir os alvos ou autorize allow_partial_release manualmente.',
  );
} else if (decision === 'partial-authorized') {
  console.warn(
    `Publicação parcial autorizada explicitamente (${status.succeeded}/${status.total}). ` +
      'Os alvos ausentes exigirão uma nova versão após a publicação.',
  );
} else {
  console.log(`Matriz completa: ${status.succeeded}/${status.total} alvos prontos.`);
}
