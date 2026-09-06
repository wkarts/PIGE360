#!/usr/bin/env node

import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

const ALLOWED_SUFFIXES = [
  '.AppImage', '.aab', '.apk', '.deb', '.dmg', '.exe', '.ipa', '.msi',
  '.rpm', '.sig', '.tar', '.tar.gz', '.zip',
];
const CORE_ARTIFACT = 'release-core-web-server';
const IGNORED_CORE_ASSETS = new Set(['.pige360-delivery-root.json']);
const CORE_STATIC_ASSETS = new Set([
  'DELIVERY-SUMMARY.json',
  'SHA256SUMS',
  'archive-validation-report.json',
  'build-report.json',
  'local-ci-report.json',
  'project-validation.json',
  'test-report.json',
  'visual-regression-report.json',
]);
const CORE_VERSIONED_SUFFIXES = [
  '-source.zip',
  '-self-hosted.zip',
  '-workflows-ci-cd.zip',
  '-release-bundle.zip',
  '-release-manifest.json',
  '-release-provenance.intoto.json',
  '-sbom.cdx.json',
  '-images-oci.tar',
  '-images-digests.json',
  '-relatorio-evidencias.pdf',
];

const EXPECTED_TARGETS = [
  { id: 'desktop-windows-x64', label: 'Windows x64', platform: 'windows', arch: 'x64', target: 'x86_64-pc-windows-msvc', artifact: 'release-desktop-windows-x64', allowedSuffixes: ['.tar.gz'], requiredAssets: [{ suffix: '.tar.gz', count: 2 }] },
  { id: 'desktop-windows-x86', label: 'Windows x86', platform: 'windows', arch: 'x86', target: 'i686-pc-windows-msvc', artifact: 'release-desktop-windows-x86', allowedSuffixes: ['.tar.gz'], requiredAssets: [{ suffix: '.tar.gz', count: 2 }] },
  { id: 'desktop-linux-x64', label: 'Linux x64', platform: 'linux', arch: 'x64', target: 'x86_64-unknown-linux-gnu', artifact: 'release-desktop-linux-x64', allowedSuffixes: ['.tar.gz'], requiredAssets: [{ suffix: '.tar.gz', count: 2 }] },
  { id: 'desktop-linux-arm64', label: 'Linux ARM64', platform: 'linux', arch: 'arm64', target: 'aarch64-unknown-linux-gnu', artifact: 'release-desktop-linux-arm64', allowedSuffixes: ['.tar.gz'], requiredAssets: [{ suffix: '.tar.gz', count: 2 }] },
  { id: 'desktop-macos-x64', label: 'macOS Intel', platform: 'macos', arch: 'x64', target: 'x86_64-apple-darwin', artifact: 'release-desktop-macos-x64', allowedSuffixes: ['.tar.gz'], requiredAssets: [{ suffix: '.tar.gz', count: 2 }] },
  { id: 'desktop-macos-arm64', label: 'macOS Apple Silicon', platform: 'macos', arch: 'arm64', target: 'aarch64-apple-darwin', artifact: 'release-desktop-macos-arm64', allowedSuffixes: ['.tar.gz'], requiredAssets: [{ suffix: '.tar.gz', count: 2 }] },
  { id: 'web-pwa', label: 'Web/PWA', platform: 'web', arch: 'universal', target: 'web', artifact: 'release-web-pwa', allowedSuffixes: ['.zip'], requiredAssets: [{ suffix: '.zip', count: 13 }] },
  { id: 'cloudpanel-linux-x64', label: 'CloudPanel Linux x64', platform: 'cloudpanel-linux', arch: 'x64', target: 'linux/amd64', artifact: 'release-cloudpanel-linux-x64', allowedSuffixes: ['.tar.gz'], requiredAssets: [{ suffix: '.tar.gz', count: 1 }] },
  { id: 'cloudpanel-linux-x86', label: 'CloudPanel Linux x86', platform: 'cloudpanel-linux', arch: 'x86', target: 'linux/386', artifact: 'release-cloudpanel-linux-x86', allowedSuffixes: ['.tar.gz'], requiredAssets: [{ suffix: '.tar.gz', count: 1 }] },
  { id: 'android-arm64-apk', label: 'Android APK ARM64', platform: 'android', arch: 'arm64', target: 'aarch64-linux-android', artifact: 'release-android-arm64-apk', allowedSuffixes: ['.apk'], requiredAssets: [{ suffix: '.apk', count: 7 }] },
  { id: 'android-aab', label: 'Android AAB ARM64', platform: 'android', arch: 'arm64', target: 'android-aab', artifact: 'release-android-aab', allowedSuffixes: ['.aab'], requiredAssets: [{ suffix: '.aab', count: 7 }] },
  { id: 'ios-arm64-unsigned-ipa', label: 'iOS ARM64 IPA não assinado', platform: 'ios', arch: 'arm64', target: 'aarch64-apple-ios', artifact: 'release-ios-arm64-unsigned-ipa', allowedSuffixes: ['.ipa', '.zip', '.tar.gz'], requiredAssets: [{ suffix: '.ipa', count: 5 }] },
];
const TARGET_BY_ARTIFACT = new Map(EXPECTED_TARGETS.map((target) => [target.artifact, target]));

function parseArgs(argv) {
  const options = {};
  for (let index = 0; index < argv.length; index += 1) {
    const current = argv[index];
    if (!current.startsWith('--')) throw new Error(`Argumento inválido: ${current}`);
    const key = current.slice(2);
    const value = argv[index + 1];
    if (!value || value.startsWith('--')) throw new Error(`Valor ausente para --${key}`);
    options[key] = value;
    index += 1;
  }
  return options;
}

function sanitize(value) {
  return value.normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^A-Za-z0-9._+-]+/g, '-')
    .replace(/-{2,}/g, '-')
    .replace(/^-+|-+$/g, '');
}

function walk(directory) {
  if (!fs.existsSync(directory)) return [];
  const files = [];
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const absolute = path.join(directory, entry.name);
    if (entry.isDirectory()) files.push(...walk(absolute));
    else if (entry.isFile()) files.push(absolute);
  }
  return files;
}

function sha256(file) {
  return new Promise((resolve, reject) => {
    const hash = crypto.createHash('sha256');
    const stream = fs.createReadStream(file);
    stream.on('error', reject);
    stream.on('data', (chunk) => hash.update(chunk));
    stream.on('end', () => resolve(hash.digest('hex')));
  });
}

function isCoreAsset(file, product, version) {
  const name = path.basename(file);
  if (CORE_STATIC_ASSETS.has(name)) return true;
  const prefix = `${product}-${version}`;
  return CORE_VERSIONED_SUFFIXES.some((suffix) => name === `${prefix}${suffix}`);
}

function isReleaseAsset(file, input, product, version) {
  if (file.endsWith('.sha256')) return false;
  if (file.endsWith('.status.json')) return false;
  const relative = path.relative(input, file);
  const [artifactDirectory = ''] = relative.split(path.sep);
  if (artifactDirectory === CORE_ARTIFACT) {
    if (IGNORED_CORE_ASSETS.has(path.basename(file))) return false;
    if (isCoreAsset(file, product, version)) return true;
    throw new Error(`Asset core fora da allowlist: ${relative}`);
  }
  const targetContract = TARGET_BY_ARTIFACT.get(artifactDirectory);
  if (targetContract) {
    const name = path.basename(file);
    if (name === 'SHA256SUMS' || name.endsWith('-SHA256SUMS')) return false;
    if (targetContract.allowedSuffixes.some((suffix) => file.endsWith(suffix))) return true;
    throw new Error(`Tipo de artefato inesperado em ${artifactDirectory}: ${relative}`);
  }
  if (ALLOWED_SUFFIXES.some((suffix) => file.endsWith(suffix))) {
    throw new Error(`Contexto de artefato desconhecido: ${relative}`);
  }
  return false;
}

function escapeMarkdown(value) {
  return String(value ?? '').replaceAll('|', '\\|').replaceAll('\n', ' ');
}

function readBuildMatrix(input, assetsByContext) {
  const statusFiles = walk(input).filter((file) => file.endsWith('.status.json')).sort();
  const recorded = new Map();
  const expectedIds = new Set(EXPECTED_TARGETS.map((target) => target.id));
  for (const file of statusFiles) {
    let status;
    try {
      status = JSON.parse(fs.readFileSync(file, 'utf8'));
    } catch (error) {
      throw new Error(`Status de build inválido em ${file}: ${error.message}`);
    }
    if (!status.id || recorded.has(status.id)) {
      throw new Error(`Status de build ausente ou duplicado: ${status.id ?? file}`);
    }
    if (!expectedIds.has(status.id)) {
      throw new Error(`Status de build pertence a alvo desconhecido: ${status.id}`);
    }
    recorded.set(status.id, status);
  }

  const targets = EXPECTED_TARGETS.map((expected) => {
    const status = recorded.get(expected.id);
    const contextAssets = assetsByContext.get(expected.artifact) ?? [];
    const assetCounts = Object.fromEntries(expected.requiredAssets.map(({ suffix }) => [
      suffix,
      contextAssets.filter((asset) => asset.source.endsWith(suffix)).length,
    ]));
    const artifactPresent = expected.requiredAssets.every(({ suffix, count }) => assetCounts[suffix] === count);
    const assetContract = expected.requiredAssets.map(({ suffix, count }) => `${count} ${suffix}`).join(', ');
    if (!status) {
      return {
        ...expected, status: 'not-reported', success: false, artifactPresent, assetCounts,
        runUrl: null,
        error: `O job ${expected.label} não enviou o relatório de status.`,
      };
    }
    const metadataMatches = status.artifact === expected.artifact
      && status.label === expected.label
      && status.platform === expected.platform
      && status.arch === expected.arch
      && status.target === expected.target;
    const success = status.status === 'success' && artifactPresent && metadataMatches;
    return {
      ...expected,
      status: success ? 'success' : status.status,
      success,
      artifactPresent,
      assetCounts,
      runUrl: status.runUrl ?? null,
      error: success
        ? null
        : !metadataMatches
          ? `Metadados de status divergentes para ${expected.label}.`
          : status.status === 'success' && !artifactPresent
            ? `O job informou sucesso, mas ${expected.artifact} não contém exatamente ${assetContract}.`
            : status.error ?? `O job terminou com status ${status.status ?? 'unknown'}.`,
    };
  });
  const succeeded = targets.filter((target) => target.success).length;
  return {
    outcome: succeeded === targets.length ? 'complete' : 'partial',
    total: targets.length,
    succeeded,
    failed: targets.length - succeeded,
    targets,
  };
}

function buildStatusMarkdown(matrix) {
  const lines = [
    '## Estado da matriz de build', '',
    matrix.outcome === 'complete'
      ? 'Todos os 12 alvos obrigatórios foram gerados e possuem artefato.'
      : 'Matriz parcial: os alvos ausentes ou falhos mantêm a release em draft.',
    '', '| Alvo | Estado | Artefato | Diagnóstico |', '| --- | --- | --- | --- |',
  ];
  for (const target of matrix.targets) {
    lines.push(`| ${escapeMarkdown(target.label)} | ${target.success ? 'gerado' : escapeMarkdown(target.status)} | ${target.artifactPresent ? escapeMarkdown(target.artifact) : 'não gerado'} | ${target.success ? '-' : escapeMarkdown(target.error)} |`);
  }
  const runUrl = matrix.targets.find((target) => target.runUrl)?.runUrl;
  if (runUrl) lines.push('', `Logs da execução: ${runUrl}`);
  return `${lines.join('\n')}\n`;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const input = path.resolve(args.input ?? 'artifacts');
  const output = path.resolve(args.output ?? 'release-assets');
  const product = sanitize(args.product ?? 'PIGE360');
  const version = sanitize(args.version ?? fs.readFileSync('VERSION', 'utf8').trim());
  if (!fs.existsSync(input) || !fs.statSync(input).isDirectory()) {
    throw new Error(`Diretório de entrada ausente: ${input}`);
  }
  if (!product || !version) throw new Error('Produto e versão são obrigatórios.');
  fs.mkdirSync(output, { recursive: true });
  if (fs.readdirSync(output).length > 0) throw new Error(`Diretório de saída deve estar vazio: ${output}`);

  const selected = walk(input).filter((file) => isReleaseAsset(file, input, product, version)).sort();
  const names = new Set();
  const assets = [];
  for (const source of selected) {
    const relative = path.relative(input, source);
    if (relative.startsWith('..') || path.isAbsolute(relative)) {
      throw new Error(`Artefato fora do diretório de entrada: ${source}`);
    }
    if (relative.split(path.sep).includes('target')) {
      throw new Error(`Diretório Cargo target não pode ser publicado: ${relative}`);
    }
    const [artifactDirectory = 'artifact'] = relative.split(path.sep);
    const context = sanitize(artifactDirectory.replace(/^release-/, ''));
    const originalName = sanitize(path.basename(source));
    const outputName = `${product}-v${version}-${context}-${originalName}`;
    if (names.has(outputName)) throw new Error(`Colisão de nome de artefato: ${outputName}`);
    names.add(outputName);
    const destination = path.join(output, outputName);
    fs.copyFileSync(source, destination, fs.constants.COPYFILE_EXCL);
    assets.push({
      name: outputName,
      source: relative.split(path.sep).join('/'),
      size: fs.statSync(destination).size,
      sha256: await sha256(destination),
    });
  }

  const assetsByContext = new Map();
  for (const asset of assets) {
    const context = asset.source.split('/')[0];
    const contextAssets = assetsByContext.get(context) ?? [];
    contextAssets.push(asset);
    assetsByContext.set(context, contextAssets);
  }
  const buildMatrix = readBuildMatrix(input, assetsByContext);
  const generatedAt = new Date().toISOString();
  fs.writeFileSync(path.join(output, 'SHA256SUMS.txt'), `${assets.map((asset) => `${asset.sha256}  ${asset.name}`).join('\n')}${assets.length ? '\n' : ''}`, 'utf8');
  fs.writeFileSync(path.join(output, 'RELEASE-MANIFEST.json'), `${JSON.stringify({ product, version: args.version ?? version, generatedAt, buildMatrix, assets }, null, 2)}\n`, 'utf8');
  fs.writeFileSync(path.join(output, 'RELEASE-STATUS.json'), `${JSON.stringify({ generatedAt, ...buildMatrix }, null, 2)}\n`, 'utf8');
  fs.writeFileSync(path.join(output, 'RELEASE-STATUS.md'), buildStatusMarkdown(buildMatrix), 'utf8');
  console.log(`Artefatos coletados: ${assets.length}; matriz: ${buildMatrix.succeeded}/${buildMatrix.total}.`);
}

try {
  await main();
} catch (error) {
  console.error(`Falha ao coletar artefatos: ${error.message}`);
  process.exit(1);
}
