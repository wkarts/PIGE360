# Release e repositório GitHub

O template não deve apontar para um repositório fixo.

A configuração de release usa esta ordem:

1. `REPOSITORY_URL`, quando definida explicitamente;
2. `GITHUB_SERVER_URL` + `GITHUB_REPOSITORY`, no GitHub Actions;
3. autodetecção padrão do `semantic-release`, quando executado localmente.

Isso evita erro como:

```text
remote: Repository not found.
fatal: repository 'https://github.com/<org>/<repo>.git/' not found
```

## Exemplo opcional

```yaml
env:
  REPOSITORY_URL: https://github.com/sua-org/seu-repositorio.git
```

Na maioria dos repositórios GitHub, não é necessário configurar `REPOSITORY_URL`.
