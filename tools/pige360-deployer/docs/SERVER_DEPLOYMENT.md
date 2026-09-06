# Deploy em servidor

Use este documento quando o projeto derivado do template precisar rodar em servidor local, mini-server, VPS ou ambiente sem interface.

Recomendações:

1. Gere binário headless separado quando possível.
2. Configure API em `127.0.0.1` por padrão.
3. Exponha rede pública somente com token, firewall e decisão explícita.
4. Configure banco externo se necessário.
5. Registre logs em arquivo e banco.
6. Use systemd no Linux ou serviço Windows.
