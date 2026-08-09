# Bancário

Providers suportam PIX, boleto, CNAB, OFX, extrato e conciliação. Todo webhook exige assinatura, replay protection, inbox e idempotência; uma parcela pode receber vários pagamentos e um pagamento pode alocar várias parcelas.

Não houve conexão bancária. Os recursos do domínio são persistidos e auditados, mas layouts de cada banco devem ser validados por contrato antes da produção.
