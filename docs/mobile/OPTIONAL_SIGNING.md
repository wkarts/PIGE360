# Assinatura móvel opcional

Os workflows Android e iOS tratam assinatura como capacidade opcional do ambiente. A ausência de variáveis, certificado, perfil de provisionamento, ferramenta nativa ou credencial válida não invalida a execução: o workflow registra um `WARNING`, preserva os artefatos não assinados e encerra essa etapa com sucesso.

## Android

Quando a entrada `sign` estiver ativada, o workflow aceita `ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS` e `ANDROID_KEY_PASSWORD`. Se o keystore, a senha ou o alias forem rejeitados, o APK/AAB original é preservado e nenhuma publicação na Google Play é realizada.

## iOS

Quando a entrada `sign` estiver ativada, o workflow aceita `APPLE_SIGNING_CERTIFICATE_BASE64`, `APPLE_SIGNING_CERTIFICATE_PASSWORD`, `APPLE_SIGNING_IDENTITY` e `APPLE_PROVISIONING_PROFILE_BASE64` (opcional). Se o certificado, a identidade ou o perfil forem inválidos, o aplicativo original é preservado e nenhuma publicação na App Store é realizada.

## Limites desta configuração

Esses workflows não publicam em lojas. Eles processam artefatos locais e fazem
upload para consulta; o workflow `50` pode anexar os binários **unsigned** a
uma GitHub Release após a promoção de versão. Deploy remoto, registro de
imagens, assinatura e publicação em lojas permanecem desabilitados até etapa
explícita e autorizada.
