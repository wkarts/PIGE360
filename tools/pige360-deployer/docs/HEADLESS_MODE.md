# Modo headless

O template continua sendo uma aplicação Tauri desktop, mas o core Rust já pode ser executado sem interface gráfica em modo `headless-api`, `cli` ou `worker`.

Modos previstos:

- `desktop`
- `headless-api`
- `windows-service`
- `linux-service`
- `cli`
- `worker`

Em modo headless não deve abrir splash, janela Tauri ou frontend Vue. O fluxo deve inicializar banco, configurações, logs, API interna, integrações e workers.

Para projetos que exigem backend real desacoplado, recomenda-se criar binários separados:

```text
app-desktop
app-server
app-cli
```

## Execução funcional adicionada na etapa 2

```bash
cargo run --manifest-path src-tauri/Cargo.toml -- --mode=headless-api --host=127.0.0.1 --port=61001
cargo run --manifest-path src-tauri/Cargo.toml -- --mode=cli
cargo run --manifest-path src-tauri/Cargo.toml -- --mode=worker
```

Endpoints disponíveis no modo `headless-api`:

- `GET /health`
- `GET /version`
- `GET /status`
- `GET /app/meta`
- `GET /features`
- `GET /logs`
- `GET /openapi.json`
- `GET /docs`

A documentação `/docs` usa Scalar em layout claro fixo e não herda tema escuro da aplicação desktop.
