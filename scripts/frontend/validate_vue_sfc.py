#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from html.parser import HTMLParser
from pathlib import Path

VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}


class TemplateStructureParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, int]] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in VOID_TAGS:
            self.stack.append((tag, self.getpos()[0]))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        return

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID_TAGS:
            return
        if not self.stack:
            self.errors.append(f"Fechamento </{tag}> sem abertura na linha {self.getpos()[0]}.")
            return
        current, line = self.stack.pop()
        if current != tag:
            self.errors.append(
                f"Fechamento </{tag}> na linha {self.getpos()[0]} não corresponde a <{current}> da linha {line}."
            )

    def finish(self) -> None:
        for tag, line in reversed(self.stack):
            self.errors.append(f"Tag <{tag}> aberta na linha {line} não foi fechada.")


def extract(source: str, tag: str, *, start_pattern: str | None = None) -> str:
    opening = start_pattern or rf"<{tag}(?:\s[^>]*)?>"
    start = re.search(opening, source, flags=re.IGNORECASE)
    if not start:
        raise ValueError(f"Bloco <{tag}> não localizado.")
    end_matches = list(re.finditer(rf"</{tag}\s*>", source, flags=re.IGNORECASE))
    if not end_matches:
        raise ValueError(f"Fechamento </{tag}> não localizado.")
    end = end_matches[-1]
    if end.start() < start.end():
        raise ValueError(f"Bloco <{tag}> inválido.")
    return source[start.end():end.start()]


def validate_typescript(script: str, source_path: Path) -> dict[str, object]:
    shim = '''
declare module "vue" {
  export function computed<T>(fn: () => T): { readonly value: T };
  export function onMounted(callback: () => void | Promise<void>): void;
  export function reactive<T extends object>(value: T): T;
  export function ref<T>(value: T): { value: T };
}
declare module "*.vue" { const component: unknown; export default component; }
declare function defineProps<T>(): Readonly<T>;
declare function defineEmits<T extends Record<PropertyKey, any[]>>(): <K extends keyof T>(event: K, ...args: T[K]) => void;
'''
    with tempfile.TemporaryDirectory(prefix="pige360-vue-sfc-") as directory:
        root = Path(directory)
        script_path = root / f"{source_path.stem}.script.ts"
        shim_path = root / "vue-sfc-shim.d.ts"
        script_path.write_text(script, encoding="utf-8")
        shim_path.write_text(shim, encoding="utf-8")
        command = [
            "tsc", "--noEmit", "--strict", "--noUncheckedIndexedAccess",
            "--exactOptionalPropertyTypes", "--skipLibCheck", "--target", "ES2022",
            "--module", "ES2022", "--moduleResolution", "Bundler", "--lib", "ES2022,DOM",
            str(shim_path), str(script_path),
        ]
        result = subprocess.run(command, text=True, capture_output=True, check=False, timeout=120)
        if result.returncode != 0:
            raise RuntimeError((result.stdout + result.stderr).strip())
        return {"command": " ".join(command[:-2] + ["<shim>", "<script>"]), "exit_code": result.returncode}


def validate_file(path: Path) -> dict[str, object]:
    source = path.read_text(encoding="utf-8")
    if "TODO" in source or "FIXME" in source:
        raise ValueError("TODO/FIXME encontrado no componente.")
    script = extract(source, "script", start_pattern=r'<script\s+setup(?:\s+lang=["\']ts["\'])?\s*>')
    template = extract(source, "template")
    parser = TemplateStructureParser()
    parser.feed(template)
    parser.close()
    parser.finish()
    if parser.errors:
        raise ValueError("\n".join(parser.errors))
    typescript = validate_typescript(script, path)
    return {
        "file": str(path),
        "bytes": path.stat().st_size,
        "template_structure": "ok",
        "typescript": typescript,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Valida estrutura HTML e TypeScript de componentes Vue SFC sem rede.")
    parser.add_argument("files", nargs="+", type=Path)
    arguments = parser.parse_args()
    results = [validate_file(path.resolve()) for path in arguments.files]
    print(json.dumps({"status": "ok", "files": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
