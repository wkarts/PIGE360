# Correção da colisão do manifesto do checkpoint

Durante a geração do checkpoint r000007, foi detectado um arquivo `CHECKPOINT_MANIFEST.json` restaurado na raiz do workspace a partir do checkpoint-base. O builder também gera um manifesto canônico com o mesmo nome, o que provocava uma entrada duplicada no ZIP e fazia a validação falhar.

Correções aplicadas:

- o manifesto restaurado foi preservado em `.recovery/stale-overlay-r000005/CHECKPOINT_MANIFEST-r000004-restored.json`;
- `scripts/execution/build_portable_checkpoint.py` passou a excluir manifestos restaurados da coleta de arquivos;
- `scripts/execution/reconcile_physical_state.py` passou a ignorar esse arquivo técnico na comparação contra o baseline;
- foi criado `backend/tests/execution/test_portable_checkpoint_builder.py`;
- o teste comprova que o ZIP possui nomes únicos, exatamente um manifesto canônico, hashes verificáveis e `ZipFile.testzip()` sem erro.

Evidência executável:

`docs/execution/evidence/portable-checkpoint-builder-regression-r000007.log`
