# Riscos residuais reais

| Risco | Evidência | Impacto | Tratamento antes de produção |
|---|---|---|---|
| Imagens Docker não executadas | Docker/Podman ausentes | incompatibilidade pode passar despercebida | build, scan e smoke test em engine real |
| Apps Tauri não compilados | Rust/Cargo ausentes | erro nativo possível | matriz Windows/Linux/macOS |
| APK/AAB não compilados | Android SDK/Gradle ausentes | erro mobile possível | runner Android fixado e teste em dispositivo |
| iOS não compilado | Xcode/macOS ausentes | `.app/.xcarchive/IPA` não comprovados | runner macOS e assinatura condicional |
| Matriz nativa ainda não executada remotamente | workflows preparados, mas anexo não contém `.git`/remoto | instaladores finais ainda não existem nesta entrega local | executar workflow 50 na tag imutável e manter draft se faltar alvo |
| Cargo locks ausentes no anexo | `0/14 Cargo.lock` e Cargo indisponível neste host | não há resolução Rust reprodutível nem release oficial local | workflow de release deve gerar, validar e persistir os 14 locks antes da tag; entrega local usa canal `source-candidate` não publicável |
| Provedores externos não homologados | sem credenciais/rede | emissão/assinatura/envio não comprovados | homologação por provider e protocolo |
| Domínios amplos usam kernel genérico | 47 recursos persistidos | regras específicas ainda requerem aprofundamento | testes e regras por agregado prioritário |
| Pins de produção não exercitados neste host | dependências estão declaradas em `requirements.production.lock`, mas não foram instaladas na regressão local | incompatibilidade de driver/worker pode surgir no container | build e smoke das imagens executáveis com PostgreSQL/Redis/RabbitMQ/MinIO |
| Backup consistente por recurso, não global | PostgreSQL Control/tenants e MinIO são fotografados em etapas | escrita concorrente entre recursos pode produzir corte temporal diferente | janela de manutenção ou protocolo coordenado para backup de corte global |
| Restore destrutivo não homologado | mocks e manifesto passaram; Docker/PostgreSQL/MinIO inexistem aqui | restauração real pode falhar por versão, volume ou permissão | ensaio de restore completo em clone do host antes do go-live |
| Baseline visual não é teste de pixels | catálogo/contrato visual validado sem navegador de regressão | desvio visual pode passar despercebido | screenshots reais e comparação pixel-a-pixel nos breakpoints suportados |
| Ledger V8 conserva requisitos não iniciados | `docs/execution/requirements.json` mantém a contagem real | a distribuição não representa implementação integral de todo o contrato V8 | priorizar e promover requisitos somente com código e evidência próprios |
| Quota de storage não aplicada | não existe ledger transacional unificado Local/S3 | consumo pode superar o valor configurado | implementar medição por objeto/volume, reconciliação e reserva atômica antes de bloquear uploads |
| Corridas legadas de bootstrap/manifest | bootstrap com mesmo token e numeração concorrente de manifest ainda dependem de unique conflict | resposta pode virar conflito de banco em concorrência extrema | converter para reserva/CAS e erro de domínio controlado |
| PR remota não criada | o ZIP-base não contém `.git` nem remoto | branch/revisão não existem no servidor | aplicar a árvore ao repositório, abrir PR para `develop` e executar CI protegida |
| ZIP de branding com quatro referências ausentes | checksum interno | rastreabilidade incompleta da fonte | obter arquivos originais ou atualizar manifesto oficial |
