#!/usr/bin/env python3
"""Generate a .codewiki/ directory for a cloned repository.

Analyzes repo structure, detects module boundaries, extracts exports/imports,
and produces structured markdown + JSON documentation.

Usage:
    python generate_wiki.py <repo_path> [--force] [--modules-only]
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SKIP_DIRS = {
    ".git", ".codewiki", "node_modules", "__pycache__", ".venv", "venv",
    "env", ".tox", ".mypy_cache", ".pytest_cache", "dist", "build",
    ".next", ".nuxt", "target", "vendor", ".gradle", ".idea", ".vscode",
    ".vs", "bin", "obj", "coverage", ".cache", ".eggs",
}

CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go", ".java", ".kt",
    ".rb", ".php", ".cs", ".cpp", ".c", ".h", ".swift", ".dart",
    ".ex", ".exs", ".vue", ".svelte", ".scala", ".zig",
}

ENTRY_FILE_NAMES = {
    "index.js", "index.ts", "index.tsx", "index.jsx",
    "main.py", "__init__.py", "mod.rs", "lib.rs", "main.rs",
    "main.go", "Main.java", "main.kt",
}

MONOREPO_DIRS = {"packages", "apps", "libs", "modules", "plugins"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _norm(p: str) -> str:
    """Normalise path to forward slashes."""
    return p.replace("\\", "/")


def _has_code_files(directory: Path) -> bool:
    """Return True if *directory* (recursively) contains at least one code file."""
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if Path(f).suffix in CODE_EXTENSIONS:
                return True
    return False


def get_commit_hash(repo_path: Path) -> str:
    """Return short commit hash via ``git rev-parse --short HEAD``."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(repo_path),
            capture_output=True, text=True,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def get_repo_name_from_remote(repo_path: Path) -> str:
    """Extract ``owner/repo`` from the git remote, fall back to dirname."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=str(repo_path),
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            url = result.stdout.strip()
            # Handle SSH (git@...:owner/repo.git) and HTTPS (.../owner/repo.git)
            m = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?$", url)
            if m:
                return m.group(1)
    except Exception:
        pass
    return repo_path.name


def get_repo_description(repo_path: Path) -> str:
    """Extract a one-line description from README.md or package.json."""
    # Try README first line after title
    readme = repo_path / "README.md"
    if readme.exists():
        try:
            lines = readme.read_text(encoding="utf-8", errors="replace").splitlines()
            for line in lines:
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    return stripped
        except Exception:
            pass

    # Try package.json description
    pkg = repo_path / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8", errors="replace"))
            if "description" in data:
                return data["description"]
        except Exception:
            pass

    return ""


def detect_architecture_patterns(repo_path: Path) -> list:
    """Detect high-level architecture patterns present in the repo."""
    patterns = []

    # Monorepo indicators
    pkg_json = repo_path / "package.json"
    if pkg_json.exists():
        try:
            data = json.loads(pkg_json.read_text(encoding="utf-8", errors="replace"))
            if "workspaces" in data:
                patterns.append("workspace")
        except Exception:
            pass

    for d in MONOREPO_DIRS:
        if (repo_path / d).is_dir():
            patterns.append("monorepo")
            break

    # Docker
    if (repo_path / "Dockerfile").exists() or (repo_path / "docker-compose.yml").exists() or (repo_path / "docker-compose.yaml").exists():
        patterns.append("docker")

    # GitHub Actions
    if (repo_path / ".github" / "workflows").is_dir():
        patterns.append("github-actions")

    return sorted(set(patterns))


# ---------------------------------------------------------------------------
# Part A  Module Boundary Detection
# ---------------------------------------------------------------------------


def detect_modules(repo_path: Path) -> list:
    """Detect module boundaries inside *repo_path*.

    Returns a list of ``{"name": str, "path": str}`` dicts where *path* uses
    forward slashes and is relative to *repo_path*.
    """
    repo_path = Path(repo_path)

    # Strategy 1: Monorepo
    for mono_dir_name in sorted(MONOREPO_DIRS):
        mono_dir = repo_path / mono_dir_name
        if mono_dir.is_dir():
            subs = [
                s for s in sorted(mono_dir.iterdir())
                if s.is_dir() and s.name not in SKIP_DIRS and _has_code_files(s)
            ]
            if len(subs) >= 2:
                return [
                    {"name": s.name, "path": _norm(str(s.relative_to(repo_path)))}
                    for s in subs
                ]

    # Strategy 2: Single-repo with src/
    src_dir = repo_path / "src"
    if src_dir.is_dir():
        subs = [
            s for s in sorted(src_dir.iterdir())
            if s.is_dir() and s.name not in SKIP_DIRS and _has_code_files(s)
        ]
        if subs:
            return [
                {"name": s.name, "path": _norm(str(s.relative_to(repo_path)))}
                for s in subs
            ]

    # Strategy 3: Fallback – top-level directories with code files
    subs = [
        s for s in sorted(repo_path.iterdir())
        if s.is_dir() and s.name not in SKIP_DIRS and _has_code_files(s)
    ]
    if subs:
        return [
            {"name": s.name, "path": _norm(str(s.relative_to(repo_path)))}
            for s in subs
        ]

    # Nothing found  treat entire repo as a single module
    return [{"name": repo_path.name, "path": "."}]


# ---------------------------------------------------------------------------
# Part B  Static Analysis
# ---------------------------------------------------------------------------


def _collect_code_files(module_abs: Path) -> list:
    """Return list of ``(relative_posix_path, abs_path)`` for all code files."""
    results = []
    for root, dirs, files in os.walk(module_abs):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if Path(f).suffix in CODE_EXTENSIONS:
                abs_p = Path(root) / f
                rel = _norm(str(abs_p.relative_to(module_abs)))
                results.append((rel, abs_p))
    return results


def _extract_exports_js(text: str) -> list:
    """Extract export names from JS/TS source text."""
    exports = []
    # export (default)? (function|class|const|let|var|type|interface) Name
    for m in re.finditer(
        r"export\s+(?:default\s+)?(?:function|class|const|let|var|type|interface)\s+(\w+)",
        text,
    ):
        exports.append(m.group(1))
    # export { Name1, Name2 }
    for m in re.finditer(r"export\s*\{([^}]+)\}", text):
        names = m.group(1)
        for part in names.split(","):
            part = part.strip().split(" as ")[0].strip()
            if part:
                exports.append(part)
    # module.exports = { a, b }
    for m in re.finditer(r"module\.exports\s*=\s*\{([^}]+)\}", text):
        names = m.group(1)
        for part in names.split(","):
            part = part.strip().split(":")[0].strip()
            if part:
                exports.append(part)
    # module.exports.name
    for m in re.finditer(r"module\.exports\.(\w+)", text):
        exports.append(m.group(1))
    return exports


def _extract_exports_python(text: str, filename: str) -> list:
    """Extract export names from a Python source file."""
    exports = []
    is_init = filename == "__init__.py"
    if is_init:
        # __all__ = [...]
        m = re.search(r"__all__\s*=\s*\[([^\]]+)\]", text)
        if m:
            for part in m.group(1).split(","):
                part = part.strip().strip("'\"")
                if part:
                    exports.append(part)
        # from .xxx import name
        for m in re.finditer(r"from\s+\.\w*\s+import\s+(.+)", text):
            names = m.group(1)
            for part in names.split(","):
                part = part.strip().split(" as ")[0].strip()
                if part:
                    exports.append(part)
    else:
        # Public def / class (no leading _)
        for m in re.finditer(r"^(?:def|class)\s+([A-Za-z]\w*)", text, re.MULTILINE):
            name = m.group(1)
            if not name.startswith("_"):
                exports.append(name)
    return exports


def _extract_imports(text: str, suffix: str) -> list:
    """Extract imported module names from source text."""
    imports = []
    if suffix in (".js", ".ts", ".tsx", ".jsx", ".vue", ".svelte"):
        # import ... from '...'
        for m in re.finditer(r"""(?:import|from)\s+['"]([^'"]+)['"]""", text):
            imports.append(m.group(1))
        for m in re.finditer(r"""import\s+.*?\s+from\s+['"]([^'"]+)['"]""", text):
            imports.append(m.group(1))
        # require('...')
        for m in re.finditer(r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)""", text):
            imports.append(m.group(1))
    elif suffix == ".py":
        # import X  /  from X import ...
        for m in re.finditer(r"^import\s+([\w.]+)", text, re.MULTILINE):
            imports.append(m.group(1))
        for m in re.finditer(r"^from\s+([\w.]+)\s+import", text, re.MULTILINE):
            imports.append(m.group(1))
    return list(dict.fromkeys(imports))  # dedupe while preserving order


def analyze_module(repo_path: Path, module: dict) -> dict:
    """Analyse a single module and return structured metadata.

    Parameters
    ----------
    repo_path : Path
        Root of the repository.
    module : dict
        ``{"name": str, "path": str}`` as returned by :func:`detect_modules`.

    Returns
    -------
    dict with keys ``entry_files``, ``exports``, ``internal_imports``, ``key_files``.
    """
    repo_path = Path(repo_path)
    mod_rel = module["path"]
    if mod_rel == ".":
        mod_abs = repo_path
    else:
        mod_abs = repo_path / mod_rel.replace("/", os.sep)

    code_files = _collect_code_files(mod_abs)

    entry_files = []
    all_exports = []
    all_imports = []

    for rel, abs_p in code_files:
        fname = abs_p.name
        suffix = abs_p.suffix

        # entry files
        if fname in ENTRY_FILE_NAMES:
            entry_files.append(rel)

        # read content
        try:
            text = abs_p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        # exports
        if suffix in (".js", ".ts", ".tsx", ".jsx", ".vue", ".svelte"):
            all_exports.extend(_extract_exports_js(text))
        elif suffix == ".py":
            all_exports.extend(_extract_exports_python(text, fname))

        # imports
        all_imports.extend(_extract_imports(text, suffix))

    # key files: sorted by size descending, top 10
    sized = []
    for rel, abs_p in code_files:
        try:
            sized.append((rel, abs_p.stat().st_size))
        except Exception:
            pass
    sized.sort(key=lambda x: x[1], reverse=True)
    key_files = sized[:10]

    return {
        "entry_files": sorted(set(entry_files)),
        "exports": list(dict.fromkeys(all_exports)),
        "internal_imports": list(dict.fromkeys(all_imports)),
        "key_files": key_files,
    }


# ---------------------------------------------------------------------------
# Relationship detection
# ---------------------------------------------------------------------------


def detect_relationships(modules: list, analyses: dict) -> list:
    """Trace inter-module dependencies from import analysis."""
    module_names = {m["name"] for m in modules}
    relationships = []
    seen = set()
    for mod in modules:
        name = mod["name"]
        analysis = analyses.get(name, {})
        for imp in analysis.get("internal_imports", []):
            for other in module_names:
                if other != name and other in imp:
                    key = (name, other)
                    if key not in seen:
                        seen.add(key)
                        relationships.append({
                            "from": name, "to": other, "type": "depends"
                        })
    return relationships


# ---------------------------------------------------------------------------
# Part C  Output Generation
# ---------------------------------------------------------------------------


def _make_summary(analysis: dict) -> str:
    """Generate a short summary string from analysis data."""
    parts = []
    n_exports = len(analysis.get("exports", []))
    n_entries = len(analysis.get("entry_files", []))
    if n_entries:
        parts.append(f"{n_entries} entry file(s)")
    if n_exports:
        parts.append(f"{n_exports} export(s)")
    n_files = len(analysis.get("key_files", []))
    if n_files:
        parts.append(f"{n_files} code file(s)")
    return ", ".join(parts) if parts else "no code detected"


def _set_gitexclude(repo_path: Path):
    """Ensure ``.codewiki/`` is listed in ``.git/info/exclude``."""
    info_dir = repo_path / ".git" / "info"
    info_dir.mkdir(parents=True, exist_ok=True)
    exclude_file = info_dir / "exclude"
    marker = ".codewiki/"
    existing = ""
    if exclude_file.exists():
        existing = exclude_file.read_text(encoding="utf-8", errors="replace")
    if marker not in existing:
        with open(exclude_file, "a", encoding="utf-8") as fh:
            if existing and not existing.endswith("\n"):
                fh.write("\n")
            fh.write(marker + "\n")


def _preserve_l2l3(existing_md: str) -> str:
    """Extract the content under the L2/L3 section from an existing .md file.

    Returns the preserved text (including the heading) or empty string.
    """
    # Find everything from the L2/L3 heading onwards
    m = re.search(r"(## .*L2/L3.*)", existing_md, re.DOTALL)
    if m:
        return m.group(1)
    return ""


def _write_module_md(
    wiki_dir: Path, mod_name: str, mod_path: str, analysis: dict,
    commit_hash: str, preserve_section: str = "",
):
    """Write ``modules/<name>.md``."""
    modules_dir = wiki_dir / "modules"
    modules_dir.mkdir(parents=True, exist_ok=True)
    md_path = modules_dir / f"{mod_name}.md"

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        f"# {mod_name}",
        "",
        f"> auto-generated {today} | commit: {commit_hash} | source: auto",
        "",
        "## Entry Points",
        "",
    ]
    for ef in analysis.get("entry_files", []):
        lines.append(f"- `{ef}`")
    if not analysis.get("entry_files"):
        lines.append("_none detected_")
    lines += ["", "## Key Files", ""]
    for kf_path, kf_size in analysis.get("key_files", []):
        lines.append(f"- `{kf_path}` ({kf_size} bytes)")
    if not analysis.get("key_files"):
        lines.append("_none_")
    lines += ["", "## Exports (API)", ""]
    for exp in analysis.get("exports", []):
        lines.append(f"- `{exp}`")
    if not analysis.get("exports"):
        lines.append("_none detected_")

    lines += ["", "## Internal Imports", ""]
    for imp in analysis.get("internal_imports", []):
        lines.append(f"- `{imp}`")
    if not analysis.get("internal_imports"):
        lines.append("_none detected_")

    # L2/L3 section
    if preserve_section:
        lines += ["", preserve_section]
    else:
        lines += [
            "",
            "## Conversation Notes (L2/L3)",
            "",
            "<!-- Add deeper understanding gained from conversation here -->",
        ]

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def generate_wiki(
    repo_path, *, force: bool = False, modules_only: bool = False
) -> bool:
    """Generate the ``.codewiki/`` directory for a repository.

    Returns ``True`` on success, ``False`` if wiki already exists and
    ``--force`` was not given.
    """
    repo_path = Path(repo_path)
    wiki_dir = repo_path / ".codewiki"

    if wiki_dir.exists() and not force and not modules_only:
        print(f".codewiki/ already exists at {wiki_dir}. Use --force to overwrite.")
        return False

    commit_hash = get_commit_hash(repo_path)
    repo_name = get_repo_name_from_remote(repo_path)
    description = get_repo_description(repo_path)
    now_iso = datetime.now(timezone.utc).isoformat()

    modules = detect_modules(repo_path)
    analyses = {}
    for mod in modules:
        analyses[mod["name"]] = analyze_module(repo_path, mod)

    # --- modules-only mode: rewrite module .md files preserving L2/L3 ------
    if modules_only and wiki_dir.exists():
        for mod in modules:
            existing_md_path = wiki_dir / "modules" / f"{mod['name']}.md"
            preserved = ""
            if existing_md_path.exists():
                preserved = _preserve_l2l3(
                    existing_md_path.read_text(encoding="utf-8", errors="replace")
                )
            _write_module_md(
                wiki_dir, mod["name"], mod["path"],
                analyses[mod["name"]], commit_hash,
                preserve_section=preserved,
            )
        return True

    # --- full generation (force or first time) -----------------------------
    if wiki_dir.exists() and force:
        import shutil
        shutil.rmtree(wiki_dir)

    wiki_dir.mkdir(parents=True, exist_ok=True)

    # Detect architecture
    arch_patterns = detect_architecture_patterns(repo_path)
    all_entry_points = []
    for mod in modules:
        a = analyses[mod["name"]]
        for ef in a.get("entry_files", []):
            all_entry_points.append(_norm(mod["path"] + "/" + ef) if mod["path"] != "." else ef)

    relationships = detect_relationships(modules, analyses)

    # index.json
    modules_index = {}
    for mod in modules:
        a = analyses[mod["name"]]
        modules_index[mod["name"]] = {
            "path": mod["path"],
            "file": f"modules/{mod['name']}.md",
            "summary": _make_summary(a),
            "stale": False,
            "last_updated": now_iso,
            "source": "auto",
        }

    index_data = {
        "version": 1,
        "repo": repo_name,
        "generated_at": now_iso,
        "code_commit": commit_hash,
        "modules": modules_index,
        "architecture": {
            "patterns": arch_patterns,
            "entry_points": all_entry_points,
            "key_relationships": relationships,
        },
    }
    (wiki_dir / "index.json").write_text(
        json.dumps(index_data, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # overview.md
    overview_lines = [
        f"# {repo_name}",
        "",
        description if description else "_No description found._",
        "",
        "## Modules",
        "",
        "| Module | Path | Entry Files | Exports |",
        "|--------|------|-------------|---------|",
    ]
    for mod in modules:
        a = analyses[mod["name"]]
        entries = ", ".join(f"`{e}`" for e in a.get("entry_files", [])) or "-"
        n_exp = len(a.get("exports", []))
        overview_lines.append(
            f"| {mod['name']} | `{mod['path']}` | {entries} | {n_exp} |"
        )
    (wiki_dir / "overview.md").write_text(
        "\n".join(overview_lines) + "\n", encoding="utf-8"
    )

    # module .md files
    for mod in modules:
        _write_module_md(
            wiki_dir, mod["name"], mod["path"],
            analyses[mod["name"]], commit_hash,
        )

    # .git/info/exclude
    _set_gitexclude(repo_path)

    print(f"Generated .codewiki/ with {len(modules)} module(s) at {wiki_dir}")
    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Generate a .codewiki/ knowledge base for a repository."
    )
    parser.add_argument("repo_path", type=str, help="Path to the cloned repo")
    parser.add_argument("--force", action="store_true", help="Overwrite existing .codewiki/")
    parser.add_argument("--modules-only", action="store_true",
                        help="Regenerate module .md files only (preserves L2/L3 notes)")
    args = parser.parse_args()

    repo = Path(args.repo_path).resolve()
    if not repo.is_dir():
        print(f"Error: {repo} is not a directory.", file=sys.stderr)
        sys.exit(1)

    success = generate_wiki(repo, force=args.force, modules_only=args.modules_only)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
