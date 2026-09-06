# CI_CD_KIT_LOCAL

Espelho verificável de todos os workflows canônicos. O workflow `50` tenta os 16 alvos a partir da tag imutável, mantém falhas em draft e só permite publicação parcial por decisão manual explícita. O workflow `51` redispara essa mesma matriz sem reutilizar assets antigos. Deploy remoto, assinatura e publicação em lojas continuam condicionados a flags e segredos explícitos.
