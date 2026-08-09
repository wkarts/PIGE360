# Riscos residuais reais

| Risco | Evidência | Impacto | Tratamento antes de produção |
|---|---|---|---|
| Imagens Docker não executadas | Docker/Podman ausentes | incompatibilidade pode passar despercebida | build, scan e smoke test em engine real |
| Apps Tauri não compilados | Rust/Cargo ausentes | erro nativo possível | matriz Windows/Linux/macOS |
| APK/AAB não compilados | Android SDK/Gradle ausentes | erro mobile possível | runner Android fixado e teste em dispositivo |
| iOS não compilado | Xcode/macOS ausentes | `.app/.xcarchive/IPA` não comprovados | runner macOS e assinatura condicional |
| Vue/Vite sem bundle de dependências | cache npm insuficiente e rede proibida | divergência do bundle estático | `npm ci` e build Vite em CI autorizado |
| Provedores externos não homologados | sem credenciais/rede | emissão/assinatura/envio não comprovados | homologação por provider e protocolo |
| Domínios amplos usam kernel genérico | 47 recursos persistidos | regras específicas ainda requerem aprofundamento | testes e regras por agregado prioritário |
| Pins opcionais não baixados | requirements de produção não resolvido localmente | incompatibilidade de dependência | gerar lock com hashes em CI controlado |
| ZIP de branding com quatro referências ausentes | checksum interno | rastreabilidade incompleta da fonte | obter arquivos originais ou atualizar manifesto oficial |
