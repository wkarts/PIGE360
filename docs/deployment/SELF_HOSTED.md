# Instalação self-hosted

1. Revise capacidade de CPU, RAM, storage e política de backup.
2. Gere secrets locais com `scripts/local/init-secrets.sh`.
3. Preencha `.env` sem copiar valores sensíveis para logs.
4. Execute `docker compose config` e scans das imagens.
5. Suba primeiro dados/init, depois aplicação e observabilidade.
6. Provisione tenant por domínio; não edite banco diretamente.
7. Teste restore antes da entrada em produção.

```bash
cp .env.example .env
bash scripts/local/init-secrets.sh runtime-secrets
docker compose -f compose.yaml -f compose.production.yaml config
docker compose -f compose.yaml -f compose.production.yaml up -d
```

O runtime de containers não estava disponível na construção; esses comandos são instruções futuras, não evidência de execução.
