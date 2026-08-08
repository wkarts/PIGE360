# Relatório de execução local

O relatório final gerado por `scripts/ci/run-all.sh` é a fonte de verdade para comandos e resultados. Esta construção não abriu conexão com hospedagem de código, registro, loja ou serviço de deploy.

Categorias:

- **passed:** comando executado e retorno zero;
- **skipped_not_configured:** toolchain/segredo ausente e nenhum artefato falso criado;
- **structural_only:** manifesto/OCI validado por estrutura, sem execução do runtime;
- **not_homologated:** integração implementada por contrato, sem protocolo real.
