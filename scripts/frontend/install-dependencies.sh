#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
command -v npm >/dev/null 2>&1 || { echo 'npm não disponível.' >&2; exit 3; }
if [ -s package-lock.json ]; then
  echo 'Instalando dependências pelo package-lock raiz (npm ci).'
  npm ci --workspaces --include-workspace-root --no-audit --no-fund
else
  echo 'Package-lock raiz íntegro ainda não existe; resolvendo versões diretas exatas com npm install.' >&2
  npm install --workspaces --include-workspace-root --no-audit --no-fund
fi
