# Diagnóstico de encerramento da suíte — ddtrace/Python 3.13

- Data UTC: 2026-08-10
- Ambiente: Python 3.13.5, pytest 9.0.2, ddtrace 4.4.0.
- Sintoma: todos os testes selecionados eram marcados como `PASSED`, porém o processo permanecia vivo após `pytest.main()` retornar `0`.
- Evidência: `regression-first-ten-faulthandler.log` mostra uma thread nativa sem frame Python durante a finalização; `ddtrace-thread-diagnostic.log` comprova retorno `0` do pytest.
- Contraprova: a mesma seleção com `-p no:ddtrace` encerrou normalmente com `10 passed` e código `0`.
- Correção: desabilitar o plugin de instrumentação externa somente no runner de testes por meio de `backend/pytest.ini`. A aplicação não depende desse plugin e a observabilidade funcional permanece sob os componentes próprios do projeto.
