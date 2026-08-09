# App Factory

O manifesto do tenant fixa tenant, brand version, app, identifier, hosts, features e secret references. Build request é idempotente e registra toolchain, canal, artifact, SBOM e provenance.

Estados: `awaiting_branding`, `ready`, `queued`, `building`, `testing`, `signing`, `available`, `failed`, `revoked`, `superseded`.

A ausência de keystore/certificado gera `skipped_not_configured`; nunca cria arquivo assinado falso. Apps dedicados não permitem troca arbitrária de tenant. O exemplo validado está em `deploy/local/tenant-app-manifest.demo.yaml`.
