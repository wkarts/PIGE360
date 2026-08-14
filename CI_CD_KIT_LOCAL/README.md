# CI_CD_KIT_LOCAL

Espelho verificável dos workflows canônicos. O workflow `50` cria uma GitHub Release somente quando `VERSION` é promovida na `main` e todos os gates passam; deploy remoto, registro de imagens, assinatura e publicação em lojas continuam desabilitados por padrão e exigem flags + segredos explícitos.
