# Componente genérico de licenciamento para Rust + Tauri

Esta versão foi ajustada para aproximar o comportamento do Delphi e corrigir o fluxo estrutural do componente.

## O que mudou

- suporte a **endpoint orquestrador** de ativação: `POST /licensing/activation/resolve`;
- fallback automático para os endpoints legados da WWSoftware quando o endpoint novo não existir;
- enriquecimento automático dos metadados do dispositivo;
- suporte nativo a arquivo local de registro (`wwreg.json` / `wwreg.lic`);
- cache offline de **decisão final**, não apenas do payload bruto;
- retorno com `reason_code`, `step`, `diagnostics`, `company`, `application_license` e `device`;
- comando Tauri estruturado adicional: `license_check_structured`.

## Compatibilidade

A configuração padrão continua apontando para:

- `https://api.rest.wwsoftwares.com.br/api/v1`
- `81b3767f-7bc5-4275-9453-a6a921010a17/86d7b2bee439957e040b72be6fea5fc2/clientes`
- `81b3767f-7bc5-4275-9453-a6a921010a17/86d7b2bee439957e040b72be6fea5fc2/maquinas`
- `81b3767f-7bc5-4275-9453-a6a921010a17/86d7b2bee439957e040b72be6fea5fc2/cliente/{document}`

Se o backend já expuser `/licensing/activation/resolve`, o componente passa a preferir esse fluxo.

## Campos novos em `LicenseCheckInput`

Além dos campos antigos, agora o componente aceita:

- `company_email`
- `company_legal_name`
- `app_slug`
- `station_name`
- `hostname`
- `computer_name`
- `serial_number`
- `machine_guid`
- `bios_serial`
- `motherboard_serial`
- `logged_user`
- `os_name`
- `os_version`
- `os_arch`
- `domain_name`
- `mac_addresses`
- `install_mode`
- `registration_file_content_b64`
- `registration_file_path`
- `registration_file_verified`
- `allow_company_auto_create`
- `allow_device_auto_create`
- `allow_device_auto_update`

## Comandos Tauri

- `license_check`: compatível com o fluxo antigo, retornando erro como string
- `license_check_structured`: retorna erro serializável com `step`, `reason_code` e `message`
