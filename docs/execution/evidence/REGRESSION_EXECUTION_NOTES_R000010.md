# Notas da regressão r000010

Duas tentativas síncronas de executar a suíte integral foram interrompidas pelo limite do wrapper da ferramenta antes de o processo produzir um resultado final. Os logs incompletos foram preservados e não são usados como evidência de aprovação.

A execução canônica foi iniciada como processo local com saída e código de retorno persistidos e monitorada até o encerramento real:

```text
119 passed in 242.85s
pytest_exit=0
compileall_exit=0
```

Arquivos canônicos:

- `backend-final-regression-119.log`;
- `backend-final-regression-119.status`;
- `backend-final-regression-r000010.log`;
- `backend-final-regression-r000010.status`;
- `backend-test-report.txt`;
- `backend-compile-report.txt`.

O plugin externo `ddtrace` permaneceu desabilitado apenas no processo de testes por `-p no:ddtrace`, conforme a decisão já registrada no checkpoint anterior. Nenhum teste foi removido, ignorado ou flexibilizado.
