# Migração conservadora do Connect Deployer para o PIGE360

| Capacidade de origem | Destino PIGE360 | Estratégia | Validação |
|---|---|---|---|
| Tauri desktop | `src-tauri` | Preservar base Tauri 2 e integrar comandos específicos | build por runner |
| Vue de operação | `src/pages/DeploymentPage.vue` | Adaptar para canais e targets PIGE360 | typecheck + build |
| Protocolo desktop/agente | `src-tauri/src/deployer/protocol.rs` | Portar com tipos de canal, plataforma e recibo | testes Rust |
| Agente Linux temporário | binário `pige360-deploy-agent` | Portar sem runtime remoto adicional | self-test amd64/x86_64 |
| SSH com host key | `src-tauri/src/deployer/desktop.rs` | Usar OpenSSH do sistema com argv fixo e StrictHostKeyChecking | testes + runner |
| Resolução GitHub | `src-tauri/src/deployer/github.rs` | Adaptar para develop, prerelease e stable | testes de política |
| Catálogo Connect | catálogo PIGE360 | Substituir por genérico/Dockge/CloudPanel/Portainer | testes de mapping |
| Compose simples | árvore `deployments/**` | Baixar e validar todos os arquivos gerenciados | manifesto SHA-256 |
| Backup de configuração | journal PIGE360 | Preservar dados e gerar backup por operação | testes de storage |
| Pull/up/readiness | services operacionais versionados PIGE360 | Orquestrar `pige360-config-validate`, migrations, `pige360-readiness`, backup e restore pelo Compose | VPS de homologação |
| Credenciais em memória | protocolo com redaction | Preservar; tokens não entram em Debug/recibo | testes negativos |
| Branding Connect | branding PIGE360 | Substituir integralmente | auditoria de identidade |
| Release por tag | develop prerelease + SemVer stable | Separar canais e impedir promoção indevida | validação de workflows |
| Referência Python antiga | nenhuma | Não portar; agente Rust é canônico | auditoria de árvore |

## Origem preservada

O ZIP `ARGWS-Connect-Deployer-Tauri-Rust-v2.0.0.zip` é tratado somente como
referência funcional. Ele não é sobrescrito e seus binários/assets não são
reutilizados no produto PIGE360.

## Dados locais

Não existem aliases SQLite confirmados entre os dois produtos. Nenhuma migração
automática de banco do Connect é executada. O PIGE360 Deployer usa seu próprio
diretório canônico e mantém o bootstrap administrativo seguro da base Tauri.
