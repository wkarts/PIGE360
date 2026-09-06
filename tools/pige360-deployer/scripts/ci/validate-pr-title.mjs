import fs from 'node:fs';

const pattern = /^(build|chore|ci|docs|feat|fix|perf|refactor|revert|style|test)(\([^)]+\))?!?:\s.+$/;
const legacyPattern = /^([A-Za-z][\w -]{1,40}):\s.+$/;
const freeformLegacyPattern = /^[A-ZÀ-Ý][\s\S]{11,}$/u;

function resolveTitle() {
  const explicitTitle = process.env.PR_TITLE?.trim();
  if (explicitTitle) return explicitTitle;

  const eventPath = process.env.GITHUB_EVENT_PATH;
  if (!eventPath || !fs.existsSync(eventPath)) return '';

  const payload = JSON.parse(fs.readFileSync(eventPath, 'utf8'));
  return payload.pull_request?.title?.trim() ?? '';
}

const title = resolveTitle();

if (!title) {
  console.log('Sem payload de Pull Request e sem PR_TITLE. Validação ignorada.');
  process.exit(0);
}

if (pattern.test(title)) {
  console.log(`Título do PR válido: ${title}`);
  process.exit(0);
}

if (legacyPattern.test(title)) {
  const [, scopeRaw, descriptionRaw] = title.match(/^([A-Za-z][\w -]{1,40}):\s(.+)$/) ?? [];
  const scope = scopeRaw
    .trim()
    .toLowerCase()
    .replace(/\s+/g, '-')
    .replace(/[^a-z0-9-]/g, '');
  const description = descriptionRaw?.trim() ?? 'descreva a mudança';

  console.warn(`Título legado aceito para compatibilidade: ${title}`);
  console.warn(`Recomendação: use "feat(${scope}): ${description}" nas próximas PRs.`);
  process.exit(0);
}

if (freeformLegacyPattern.test(title)) {
  console.warn(`Título legado aceito para compatibilidade: ${title}`);
  console.warn('Recomendação: use Conventional Commits (ex.: feat(core): adiciona recurso genérico).');
  process.exit(0);
}

console.error(`Título do PR inválido: "${title}"`);
console.error('Use Conventional Commits. Exemplos válidos:');
console.error('- feat(core): adiciona novo módulo da aplicação');
console.error('- fix(auth): corrige restauração de sessão local');
console.error('- docs(ci): documenta fluxo de release desktop');
console.error('Formato legado aceito temporariamente: Core: descrição');
process.exit(1);
