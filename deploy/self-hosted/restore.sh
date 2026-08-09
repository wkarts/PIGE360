#!/bin/sh
set -eu
archive="${1:?Informe o diretório de backup.}"
[ -f "$archive/SHA256SUMS" ] || { echo 'Manifesto SHA256SUMS ausente.' >&2; exit 2; }
(cd "$archive" && sha256sum -c SHA256SUMS)
echo 'Integridade aprovada. Restaure primeiro em ambiente isolado e valide o UUID do tenant antes de reativar hostnames.'
echo 'A restauração destrutiva não é executada automaticamente por este script.'
