# Builds móveis: validação e distribuição

## Validação de pull request

O workflow **32 · Android APK/AAB** não executa mais a matriz completa de sete
aplicações a cada PR. Ele constrói apenas o `family-app` em perfil `debug`,
gera APK e AAB com nomes únicos, verifica a assinatura do APK com `apksigner`
e a estrutura assinada do AAB com `jarsigner`, e publica o resultado como
artefato de validação.

O APK debug é adequado para instalação em dispositivos de QA. O AAB é um
pacote para distribuição pela Google Play; ele não é instalável diretamente em
um dispositivo Android.

Em execução manual, selecione `scope=all` para gerar a matriz debug completa.
Esse modo continua sendo uma atividade de QA, não uma release.

## Release publicável

O workflow **50 · Pré-lançamento Alpha** só inicia a matriz de distribuição
depois de conferir os materiais de assinatura. Se algum item estiver ausente ou
for rejeitado, a release falha antes dos builds pesados e nenhum binário
unsigned é publicado.

Android exige:

- `ANDROID_KEYSTORE_BASE64`
- `ANDROID_KEYSTORE_PASSWORD`
- `ANDROID_KEY_ALIAS`
- `ANDROID_KEY_PASSWORD`

iOS exige:

- `APPLE_DEVELOPMENT_TEAM` como variável ou segredo do repositório
- `APPLE_SIGNING_CERTIFICATE_BASE64`
- `APPLE_SIGNING_CERTIFICATE_PASSWORD`
- `APPLE_SIGNING_IDENTITY`
- `APPLE_PROVISIONING_PROFILE_BASE64`

A assinatura Android alinha, assina e verifica cada APK; também assina e
verifica cada AAB. Para iOS, o perfil é embutido, a assinatura é verificada e
somente as IPAs resultantes da etapa assinada permanecem no artefato da
release. A validade de instalação em um dispositivo iOS específico depende de
o perfil conter esse dispositivo.

Os workflows não fazem deploy SaaS ou publicação automática em lojas.


Quando `APPLE_DEVELOPMENT_TEAM` não está configurado, a PR registra explicitamente que nenhuma IPA foi gerada e executa apenas a validação estática. A execução manual exige o Team ID e falha sem ele; a release continua exigindo todo o conjunto de assinatura.