from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
APPS = ROOT / "apps"


def test_every_web_application_has_an_installable_subpath_safe_pwa_shell() -> None:
    applications = sorted(path for path in APPS.iterdir() if path.is_dir())

    assert len(applications) == 13
    for application in applications:
        index = (application / "index.html").read_text(encoding="utf-8")
        main = (application / "src/main.ts").read_text(encoding="utf-8")
        service_worker = (application / "public/sw.js").read_text(encoding="utf-8")
        vite = (application / "vite.config.ts").read_text(encoding="utf-8")
        manifest = json.loads(
            (application / "public/manifest.webmanifest").read_text(encoding="utf-8")
        )

        assert 'rel="manifest" href="./manifest.webmanifest"' in index, application.name
        assert 'rel="apple-touch-icon"' in index, application.name
        assert "navigator.serviceWorker.register" in main, application.name
        assert "isViteDevelopmentEntry" in main, application.name
        assert '"./manifest.webmanifest"' in service_worker, application.name
        assert '"./assets/app.js"' not in service_worker, application.name
        assert '"./assets/app.css"' not in service_worker, application.name
        assert 'url.pathname.startsWith("/api/")' in service_worker, application.name
        assert "CACHE_SCOPE_PREFIX" in service_worker, application.name
        assert "key.startsWith(CACHE_SCOPE_PREFIX)" in service_worker, application.name
        assert "html.matchAll" in service_worker, application.name
        assert "self.registration.scope" in service_worker, application.name
        assert manifest["id"] == "./", application.name
        assert manifest["start_url"] == "./", application.name
        assert manifest["scope"] == "./", application.name
        theme = re.search(r'<meta name="theme-color" content="([^"]+)">', index)
        assert theme and theme.group(1).upper() == manifest["theme_color"].upper(), application.name
        assert 'base: "./"' in vite, application.name
        assert "sourcemap: false" in vite, application.name


def test_vue_generated_javascript_mirrors_remain_in_the_source_tree() -> None:
    vue_sources = sorted(APPS.glob("*/src/**/*.vue"))
    vue_js = sorted(APPS.glob("*/src/**/*.vue.js"))
    main_js = sorted(APPS.glob("*/src/main.js"))

    # Os 50 mirrors da base recebida são um piso de preservação, não um teto:
    # componentes Vue adicionados legitimamente também precisam do respectivo
    # mirror para manter a distribuição-fonte completa.
    assert len(vue_js) >= 50
    assert {Path(f"{source}.js") for source in vue_sources} == set(vue_js)
    assert len(main_js) == 13
