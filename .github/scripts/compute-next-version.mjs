#!/usr/bin/env node

/**
 * PIGE360 semantic release planner, alinhado ao modelo Connect|API.
 *
 * Regras:
 * - Sem tag estável anterior: parte da base 1.0.0 e publica 1.0.1.
 * - label version:major => major.
 * - label version:minor => minor.
 * - label version:patch => patch.
 * - título Conventional Commit com ! ou BREAKING CHANGE => major.
 * - título feat(...) / feat: => minor.
 * - qualquer outra promoção => patch.
 */

const [latestTagRaw = '', labelsRaw = '', prTitleRaw = '', forceRaw = 'auto'] = process.argv.slice(2);
const base = { major: 1, minor: 0, patch: 0 };

function parseTag(tag) {
  const normalized = String(tag || '').trim().replace(/^v/, '');
  const match = normalized.match(/^(\d+)\.(\d+)\.(\d+)$/);
  if (!match) return null;
  return { major: Number(match[1]), minor: Number(match[2]), patch: Number(match[3]) };
}

function bump(v, type) {
  if (type === 'major') return `${v.major + 1}.0.0`;
  if (type === 'minor') return `${v.major}.${v.minor + 1}.0`;
  return `${v.major}.${v.minor}.${v.patch + 1}`;
}

const latest = parseTag(latestTagRaw) || base;
const labels = labelsRaw.split(',').map((x) => x.trim().toLowerCase()).filter(Boolean);
const title = prTitleRaw.trim();
const force = String(forceRaw || 'auto').trim().toLowerCase();

let type = 'patch';
if (['major', 'minor', 'patch'].includes(force)) type = force;
else if (labels.includes('version:major')) type = 'major';
else if (labels.includes('version:minor')) type = 'minor';
else if (labels.includes('version:patch')) type = 'patch';
else if (/^[a-z]+(?:\([^)]*\))?!:/.test(title) || /BREAKING[ -]CHANGE/i.test(title)) type = 'major';
else if (/^feat(?:\([^)]*\))?:/i.test(title)) type = 'minor';

const version = bump(latest, type);
process.stdout.write(JSON.stringify({
  version,
  bump: type,
  previous: `${latest.major}.${latest.minor}.${latest.patch}`,
}));
