#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path


DOMAIN_BANNED_EXTERNAL = {
    "sqlalchemy",
    "redis",
    "celery",
    "fastapi",
    "pydantic",
    "pydantic_settings",
}

APP_BANNED_EXTERNAL = {
    "sqlalchemy",
    "redis",
    "celery",
    "fastapi",
    "pydantic",
    "pydantic_settings",
}

API_BANNED_EXTERNAL = {
    "sqlalchemy",
    "redis",
    "celery",
}

WORKER_BANNED_EXTERNAL = {
    "sqlalchemy",
    "redis",
}


LAYER_NAMES = ("api", "worker", "application", "domain", "infrastructure")


@dataclass(frozen=True)
class ImportRef:
    module: str
    lineno: int


def _classify_layer(py_file: Path, *, pkg_root: Path) -> str | None:
    rel = py_file.relative_to(pkg_root)
    if not rel.parts:
        return None
    top = rel.parts[0]
    return top if top in LAYER_NAMES else None


def _normalize_module(module: str, package: str | None) -> str:
    if package and module.startswith(package + "."):
        return module[len(package) + 1 :]
    return module


def _extract_imports(py_path: Path) -> list[ImportRef]:
    tree = ast.parse(py_path.read_text(encoding="utf-8"), filename=str(py_path))
    found: list[ImportRef] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append(ImportRef(module=alias.name, lineno=node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                found.append(ImportRef(module=node.module, lineno=node.lineno))
    return found


def _is_internal_layer(top: str) -> bool:
    return top in LAYER_NAMES


def _detect_package(repo_root: Path) -> str:
    src_dir = repo_root / "src"
    if not src_dir.exists():
        raise SystemExit(f"src/ directory not found under repo root: {repo_root}")

    candidates: list[str] = []
    for child in sorted(src_dir.iterdir()):
        if not child.is_dir():
            continue
        if (child / "__init__.py").exists():
            candidates.append(child.name)

    if len(candidates) == 1:
        return candidates[0]

    if not candidates:
        raise SystemExit(f"Could not auto-detect package under {src_dir} (no packages with __init__.py).")

    raise SystemExit(
        "Multiple packages found under src/. Pass --package explicitly. "
        f"Candidates: {', '.join(candidates)}"
    )


def _resolve_pkg_root(repo_root: Path, package: str | None) -> tuple[Path, str | None]:
    src_dir = repo_root / "src"
    if not src_dir.exists():
        raise SystemExit(f"src/ directory not found under repo root: {repo_root}")

    if package:
        pkg_root = src_dir / package
        if not pkg_root.exists():
            raise SystemExit(f"Package root not found: {pkg_root}")
        return pkg_root, package

    flat_layers = {item.name for item in src_dir.iterdir() if item.is_dir()}
    if {"api", "application", "domain", "infrastructure", "worker"}.issubset(flat_layers):
        return src_dir, None

    detected = _detect_package(repo_root)
    pkg_root = src_dir / detected
    if not pkg_root.exists():
        raise SystemExit(f"Package root not found: {pkg_root}")
    return pkg_root, detected


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check layering/import boundaries for API/Worker->Application->Infrastructure->Domain."
    )
    parser.add_argument("--root", default=".", help="Repository root (default: current directory).")
    parser.add_argument("--package", default=None, help="Python package name under src/.")
    args = parser.parse_args()

    repo_root = Path(args.root).resolve()
    pkg_root, package = _resolve_pkg_root(repo_root, args.package)

    violations: list[str] = []
    py_files = sorted(p for p in pkg_root.rglob("*.py") if p.is_file())
    for py_file in py_files:
        layer = _classify_layer(py_file, pkg_root=pkg_root)
        if layer is None:
            continue

        for imp in _extract_imports(py_file):
            normalized = _normalize_module(imp.module, package)
            top = normalized.split(".", 1)[0]

            if layer == "domain" and top in DOMAIN_BANNED_EXTERNAL:
                violations.append(f"{py_file}:{imp.lineno} domain imports banned external module: {imp.module}")
            if layer == "application" and top in APP_BANNED_EXTERNAL:
                violations.append(f"{py_file}:{imp.lineno} application imports banned external module: {imp.module}")
            if layer == "api" and top in API_BANNED_EXTERNAL:
                violations.append(f"{py_file}:{imp.lineno} api imports banned external module: {imp.module}")
            if layer == "worker" and top in WORKER_BANNED_EXTERNAL:
                violations.append(f"{py_file}:{imp.lineno} worker imports banned external module: {imp.module}")

            if layer == "domain" and _is_internal_layer(top) and top != "domain":
                violations.append(f"{py_file}:{imp.lineno} domain must not depend on {top}: {imp.module}")
            if layer == "infrastructure" and _is_internal_layer(top) and top in {"api", "worker", "application"}:
                violations.append(f"{py_file}:{imp.lineno} infrastructure must not depend on {top}: {imp.module}")
            if layer == "application" and _is_internal_layer(top) and top in {"api", "worker"}:
                violations.append(f"{py_file}:{imp.lineno} application must not depend on {top}: {imp.module}")
            if layer == "api" and _is_internal_layer(top) and top == "infrastructure":
                violations.append(f"{py_file}:{imp.lineno} api must not depend on infrastructure: {imp.module}")
            if layer == "worker" and _is_internal_layer(top) and top == "infrastructure":
                violations.append(f"{py_file}:{imp.lineno} worker must not depend on infrastructure: {imp.module}")

    if violations:
        print("Boundary violations found:\n")
        for violation in violations:
            print("-", violation)
        return 1

    package_label = package if package is not None else "<flat-src>"
    print(f"No boundary violations under {pkg_root} (package={package_label})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
