#!/bin/sh
set -eu
package="${1:?Informe o diretório local já extraído da nova versão.}"
current="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
[ -f "$package/VERSION" ] || { echo 'Pacote inválido.' >&2; exit 2; }
cd "$current"
python3 scripts/backup/test_backup_restore.py >/dev/null
printf 'Backup/restore de sanidade aprovado. A atualização deve usar blue/green e migrations antes da troca.\n'
printf 'Versão atual: %s; versão candidata: %s\n' "$(cat VERSION)" "$(cat "$package/VERSION")"
printf 'Nenhum arquivo foi sobrescrito automaticamente por segurança.\n'
