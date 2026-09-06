# Base canônica e política de evolução

Esta evolução parte exclusivamente do anexo `PIGE360-develop(1).zip`, SHA-256
`dfc2950813fcb3ea239e9715b66527e55b914ee1241101fc8b986f44bf21a607`, cujo
comentário de origem é `9fa139bc20fc2f7173ffd2f07c78673e36e6090f`.

O anexo é byte a byte idêntico ao `PIGE360-develop.zip` usado na tentativa
anterior. Portanto, a data artificial de 07/08/2026 daquela entrega não veio de
uma base antiga: ela era gravada pelo empacotador em todas as entradas ZIP.

O Connect|API anexado foi consultado somente como referência arquitetural para
operações administrativas. Nenhum nome, identidade ou implementação dele é
tratado como fonte canônica do PIGE360.

O SHA-256 calculado diretamente do anexo Connect|API é
`f10f59350a905daad9d884c514e055b3df17b36ce3bfd4e62b0fd3149397075b`. Ele não foi
usado como base, nem para copiar ou substituir arquivos do produto.

A revisão `9fa139bc20fc2f7173ffd2f07c78673e36e6090f` foi lida do comentário do ZIP.
Como esta árvore não contém metadados `.git`, ela não é apresentada como commit
de um checkout Git verificado.

Regras desta evolução:

- nenhum arquivo original é removido silenciosamente;
- nenhuma reorganização destrutiva é permitida;
- os `*.vue`, `*.vue.js`, `main.ts` e `main.js` existentes são preservados;
- mudanças transversais precisam de teste e registro no relatório antes/depois;
- timestamps do ZIP refletem o `mtime` UTC dos arquivos, em vez de uma data fixa;
- validação local, build em runner e homologação de produção são estados distintos.

Os dados completos e verificáveis estão em `SOURCE_BASELINE.json`.

O `CHECKPOINT_MANIFEST.json` da raiz foi mantido byte a byte no repositório como
evidência do anexo original; por isso ele ainda descreve o checkpoint histórico
alpha. Ele é explicitamente excluído dos ZIPs atuais para não ser confundido com
o manifesto da entrega. O manifesto canônico é regenerado em
`release/source-tree-manifest.json`.
