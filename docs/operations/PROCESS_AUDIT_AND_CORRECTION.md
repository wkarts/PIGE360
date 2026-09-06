# Auditoria do processo e correção da entrega

## Fonte de verdade

Esta evolução usa exclusivamente `PIGE360-develop(1).zip` como base do produto.
O SHA-256 do anexo é
`dfc2950813fcb3ea239e9715b66527e55b914ee1241101fc8b986f44bf21a607` e o
comentário do ZIP informa a revisão
`9fa139bc20fc2f7173ffd2f07c78673e36e6090f`. Como o anexo não contém `.git`, a
revisão não é apresentada como checkout Git verificado.

O arquivo reenviado é byte a byte idêntico ao `PIGE360-develop.zip` disponível
na tentativa anterior. O Connect|API anexado foi usado somente para comparar
padrões arquiteturais de administração e operação; não substituiu nem serviu de
base ao PIGE360.

## Respostas aos desvios da entrega anterior

1. **“Não fazer refatorações abruptas” não foi respeitado adequadamente.** A
   tentativa anterior acumulou 280 arquivos modificados em relação à origem e
   não os dividiu em incrementos pequenos, rastreáveis e revisáveis. Mesmo sem
   remover arquivos na árvore de trabalho, o volume transversal sem relatório
   caracterizou uma mudança abrupta do ponto de vista de entrega.
2. **Faltou relatório de processo.** Os gates finais foram registrados, mas não
   foi entregue o comparativo obrigatório entre origem, árvore alterada e
   conteúdo efetivo dos pacotes. Isso impediu verificar rapidamente o que havia
   sido preservado, alterado ou omitido.
3. **Os JavaScript associados ao Vue foram omitidos do ZIP.** Eles não foram
   apagados da árvore de trabalho. O empacotador anterior excluía deliberadamente
   50 arquivos `*.vue.js` e 13 arquivos `apps/*/src/main.js` por tratá-los como
   gerados. Essa política contrariava a preservação solicitada.
4. **A data 07/08/2026 era artificial.** O empacotador gravava a mesma data em
   todas as entradas para tentar obter reprodutibilidade. Ela não provava uso de
   workspace antigo, mas destruía a proveniência visual dos arquivos e gerava a
   interpretação legítima de que o pacote estava defasado.
5. **A base anexada foi usada, mas a rastreabilidade foi insuficiente.** Uma
   camada extensa de alterações e a omissão dos JavaScript no pacote fizeram a
   entrega deixar de representar fielmente sua base. A ausência do mapa de
   diferenças agravou o problema.
6. **A classificação “pronto para uso” foi incorreta.** O pacote anterior não
   continha binários nativos, carregava OCI apenas estrutural e ainda tinha
   falhas na instalação self-hosted, migrations de tenants, update, rollback e
   administração global. Validação local de fonte não equivale a homologação de
   produção.

## Política aplicada nesta correção

- nenhuma remoção de arquivo original é aceita pelo gate antes/depois;
- `*.vue`, `*.vue.js`, `main.ts` e `main.js` são preservados e conferidos no ZIP;
- o ZIP usa o `mtime` UTC real de cada fonte, sem data fixa;
- a escrita de ZIP é atômica e em fluxo, e cada pacote interno é validado por
  tamanho, SHA-256 e leitura integral antes/depois da montagem do bundle;
- um lock exclusivo do sistema operacional recusa empacotamentos concorrentes
  sobre o mesmo diretório, eliminando a corrida que truncou a tentativa anterior;
- migrations e schema existentes são evoluídos de forma aditiva e idempotente;
- telas e rotas existentes são preservadas; novos controles são incrementos;
- cada operação sensível exige motivo, autorização, auditoria e/ou confirmação;
- evidência com status falho, versão divergente ou origem não verificada bloqueia
  o empacotamento;
- build local, workflow preparado, artefato gerado e ambiente homologado são
  estados diferentes e nunca intercambiáveis no relatório.

## Evidências canônicas

- `docs/operations/SOURCE_BASELINE.json`: identidade e hashes dos anexos;
- `docs/operations/BEFORE_AFTER_REPORT.json`: diferenças finais por arquivo;
- `release/reports/local-ci-report.json`: comandos e resultados da CI local;
- `release/reports/build-report.json`: builds executados e não executados;
- `release/source-tree-manifest.json`: hash de cada fonte empacotada;
- `release/version-consistency.json`: versão canônica e metadados;
- `release/secret-scan-report.json`: varredura de segredos;
- `release/*provenance*.json`: proveniência dos pacotes e entradas externas.

## Limite de homologação

A árvore pode ser validada e empacotada localmente, mas Docker, PostgreSQL,
Redis, RabbitMQ, MinIO, DNS/TLS, CloudPanel, Dockge, Portainer, runners Windows,
Android e macOS/iOS exigem seus ambientes reais. Na ausência dessas toolchains,
o estado correto é `não executado`, nunca `aprovado`.
