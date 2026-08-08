SHELL := /bin/bash

.PHONY: test ci openapi sdk screenshots release clean

test:
	PYTHONPATH=backend pytest -q backend/tests

ci:
	bash scripts/ci/run-all.sh

openapi:
	PYTHONPATH=backend python backend/scripts/export_openapi.py

sdk: openapi
	python scripts/sdk/generate_typescript_sdk.py

screenshots:
	python scripts/visual/generate_catalog.py
	bash scripts/visual/capture-screenshots.sh

release:
	bash scripts/release/package-local.sh

clean:
	rm -rf .pytest_cache backend/.pytest_cache runtime-data release/staging
