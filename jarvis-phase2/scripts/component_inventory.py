#!/usr/bin/env python3
"""Read explicitly selected package metadata, without running/importing packages.

No network, installers, subprocesses, service changes or credential/config reads.
This is an inventory, not a vulnerability scan or a proof of package origin.
"""
from __future__ import annotations

import argparse
from email.parser import Parser
import json
from pathlib import Path
import re

NPM_PACKAGES = ("ruflo", "claude-flow", "@claude-flow/cli", "omniroute")
PYTHON_PACKAGES = {"agent-reach", "mcp-scan", "snyk-agent-scan", "invariant-ai", "mcp"}
MAX_METADATA_BYTES = 1024 * 1024


def read_metadata(path: Path) -> str:
    if not path.is_file():
        raise ValueError("not_regular_file")
    with path.open("rb") as stream:
        content = stream.read(MAX_METADATA_BYTES + 1)
    if len(content) > MAX_METADATA_BYTES:
        raise ValueError("metadata_too_large")
    return content.decode("utf-8")


def version_text(value: object) -> str | None:
    # Only a version token is returned, never arbitrary metadata fields.
    if isinstance(value, str) and re.fullmatch(r"[0-9][0-9A-Za-z.+_-]{0,99}", value):
        return value
    return None


def inventory(npm_roots: list[Path], python_roots: list[Path]) -> dict:
    found, checks = [], []
    for root in npm_roots:
        for name in NPM_PACKAGES:
            path = root / name / "package.json"
            check = {"tur": "npm", "paket": name, "dosya": str(path)}
            try:
                content = json.loads(read_metadata(path))
                if not isinstance(content, dict) or content.get("name") != name:
                    raise ValueError("name_mismatch")
                version = version_text(content.get("version"))
                if not version:
                    raise ValueError("invalid_version")
            except (OSError, ValueError, UnicodeError):
                check["durum"] = "DOGRULANAMADI"
            else:
                check["durum"] = "METADATA_OKUNDU"
                found.append({**check, "surum": version})
            checks.append(check)
    for root in python_roots:
        check = {"tur": "python", "dizin": str(root)}
        try:
            paths = sorted(root.iterdir())
        except OSError:
            check["durum"] = "DOGRULANAMADI"
            checks.append(check)
            continue
        check["durum"] = "METADATA_TARAMASI_TAMAMLANDI"
        for directory in paths:
            if not directory.name.endswith(".dist-info"):
                continue
            path = directory / "METADATA"
            try:
                metadata = Parser().parsestr(read_metadata(path), headersonly=True)
                name = re.sub(r"[-_.]+", "-", metadata.get("Name", "")).lower()
                if name not in PYTHON_PACKAGES:
                    continue
                version = version_text(metadata.get("Version"))
                if not version:
                    raise ValueError("invalid_version")
                found.append({"tur": "python", "paket": name, "surum": version,
                              "dosya": str(path), "durum": "METADATA_OKUNDU"})
            except (OSError, ValueError, UnicodeError):
                check["durum"] = "KISMI_METADATA_OKUNAMADI"
        checks.append(check)
    return {
        "kapsam": "YALNIZ_BELIRTILEN_PAKET_DIZINLERI",
        "not": ("Bulunamayan paket sistem genelinde yok sayilmaz. Metadata adi/surumu "
                "paket kaynagini kanitlamaz; resmi kaynakla ayrica dogrulanmalidir. "
                "PyPI agent-reach adi resmi Agent Reach projesini kanitlamaz. "
                "Bu rapor guvenlik onayi veya canli servis surum dogrulamasi degildir."),
        "paketler": found, "kontroller": checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--npm-root", action="append", type=Path, default=[],
                        help="node_modules dizini; birden fazla verilebilir")
    parser.add_argument("--python-root", action="append", type=Path, default=[],
                        help="site-packages dizini; birden fazla verilebilir")
    args = parser.parse_args()
    if not args.npm_root and not args.python_root:
        parser.error("En az bir --npm-root veya --python-root belirtin.")
    print(json.dumps(inventory(args.npm_root, args.python_root), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
