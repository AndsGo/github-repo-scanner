# CodeWiki Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add knowledge persistence (codewiki) to github-repo-scanner so that code understanding survives across conversations.

**Architecture:** Two new Python scripts (`generate_wiki.py`, `update_wiki.py`) plus a modification to `clone_repo.py`. All scripts use Python stdlib only (no external deps). A test fixture with a mock repo structure validates the logic. The `.codewiki/` directory is created inside each cloned repo's cache path.

**Tech Stack:** Python 3.9+ (stdlib only: os, sys, json, re, pathlib, argparse, subprocess, datetime, unittest)

**Design doc:** `docs/plans/2026-02-12-codewiki-design.md`

---

## Task 1: Test Fixture — Mock Repo Structure

Create a reusable test fixture that simulates different repo layouts (monorepo, single-repo, fallback) for validating all subsequent scripts.

**Files:**
- Create: `tests/fixtures/create_fixtures.py`
- Create: `tests/__init__.py`

**Step 1: Create the test fixture generator**

```python
# tests/fixtures/create_fixtures.py
"""Create mock repo structures for testing codewiki generation."""
import os
import json
import shutil
import subprocess
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent

def create_monorepo(base=None):
    """Create a mock monorepo (like React) with packages/."""
    root = base or FIXTURES_DIR / "mock_monorepo"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    # Initialize git repo so we can get commit hash
    subprocess.run(["git", "init"], cwd=root, capture_output=True)

    # package.json at root
    (root / "package.json").write_text(json.dumps({
        "name": "mock-monorepo",
        "private": True,
        "workspaces": ["packages/*"]
    }), encoding="utf-8")

    # README.md
    (root / "README.md").write_text(
        "# Mock Monorepo\n\nA test monorepo for codewiki.\n",
        encoding="utf-8"
    )

    # Package A — has exports and imports
    pkg_a = root / "packages" / "core"
    (pkg_a / "src").mkdir(parents=True)
    (pkg_a / "package.json").write_text(json.dumps({
        "name": "@mock/core",
        "main": "src/index.js"
    }), encoding="utf-8")
    (pkg_a / "src" / "index.js").write_text(
        "export { createApp } from './app.js';\n"
        "export { Config } from './config.js';\n",
        encoding="utf-8"
    )
    (pkg_a / "src" / "app.js").write_text(
        "import { Config } from './config.js';\n"
        "export function createApp(options) {\n"
        "  return new Config(options);\n"
        "}\n",
        encoding="utf-8"
    )
    (pkg_a / "src" / "config.js").write_text(
        "export class Config {\n"
        "  constructor(options) { this.options = options; }\n"
        "}\n",
        encoding="utf-8"
    )

    # Package B — depends on A
    pkg_b = root / "packages" / "renderer"
    (pkg_b / "src").mkdir(parents=True)
    (pkg_b / "package.json").write_text(json.dumps({
        "name": "@mock/renderer",
        "main": "src/index.js",
        "dependencies": {"@mock/core": "workspace:*"}
    }), encoding="utf-8")
    (pkg_b / "src" / "index.js").write_text(
        "import { createApp } from '@mock/core';\n"
        "export function render(el) {\n"
        "  const app = createApp({});\n"
        "  return app;\n"
        "}\n",
        encoding="utf-8"
    )

    # Package C — standalone utils
    pkg_c = root / "packages" / "utils"
    (pkg_c / "src").mkdir(parents=True)
    (pkg_c / "package.json").write_text(json.dumps({
        "name": "@mock/utils",
        "main": "src/index.js"
    }), encoding="utf-8")
    (pkg_c / "src" / "index.js").write_text(
        "export function debounce(fn, ms) { /* ... */ }\n"
        "export function throttle(fn, ms) { /* ... */ }\n",
        encoding="utf-8"
    )

    # git commit so we have a hash
    subprocess.run(["git", "add", "."], cwd=root, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=root, capture_output=True,
        env={**os.environ, "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@test.com",
             "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@test.com"}
    )

    return root


def create_single_repo(base=None):
    """Create a mock single-repo with src/ layout."""
    root = base or FIXTURES_DIR / "mock_single"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    subprocess.run(["git", "init"], cwd=root, capture_output=True)

    # pyproject.toml
    (root / "pyproject.toml").write_text(
        '[project]\nname = "mock-single"\nversion = "1.0.0"\n',
        encoding="utf-8"
    )
    (root / "README.md").write_text(
        "# Mock Single\n\nA single-repo Python project.\n",
        encoding="utf-8"
    )

    # src/auth/
    auth = root / "src" / "auth"
    auth.mkdir(parents=True)
    (auth / "__init__.py").write_text(
        "from .login import authenticate\nfrom .token import create_token\n",
        encoding="utf-8"
    )
    (auth / "login.py").write_text(
        "from .token import create_token\n\n"
        "def authenticate(user, password):\n"
        "    return create_token(user)\n",
        encoding="utf-8"
    )
    (auth / "token.py").write_text(
        "def create_token(user):\n"
        "    return f'token_{user}'\n",
        encoding="utf-8"
    )

    # src/api/
    api = root / "src" / "api"
    api.mkdir(parents=True)
    (api / "__init__.py").write_text(
        "from .routes import setup_routes\n",
        encoding="utf-8"
    )
    (api / "routes.py").write_text(
        "from src.auth import authenticate\n\n"
        "def setup_routes(app):\n"
        "    pass\n",
        encoding="utf-8"
    )

    # src/models/
    models = root / "src" / "models"
    models.mkdir(parents=True)
    (models / "__init__.py").write_text("", encoding="utf-8")
    (models / "user.py").write_text(
        "class User:\n"
        "    def __init__(self, name): self.name = name\n",
        encoding="utf-8"
    )

    subprocess.run(["git", "add", "."], cwd=root, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=root, capture_output=True,
        env={**os.environ, "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@test.com",
             "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@test.com"}
    )

    return root


def create_flat_repo(base=None):
    """Create a mock repo with no standard layout (fallback strategy)."""
    root = base or FIXTURES_DIR / "mock_flat"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    subprocess.run(["git", "init"], cwd=root, capture_output=True)

    (root / "README.md").write_text("# Flat Project\n", encoding="utf-8")
    (root / "main.py").write_text(
        "from helpers import utils\n\ndef main():\n    utils.run()\n",
        encoding="utf-8"
    )

    helpers = root / "helpers"
    helpers.mkdir()
    (helpers / "utils.py").write_text(
        "def run():\n    print('running')\n",
        encoding="utf-8"
    )
    (helpers / "__init__.py").write_text("", encoding="utf-8")

    scripts = root / "scripts"
    scripts.mkdir()
    (scripts / "deploy.sh").write_text("#!/bin/bash\necho deploy\n", encoding="utf-8")

    subprocess.run(["git", "add", "."], cwd=root, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=root, capture_output=True,
        env={**os.environ, "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@test.com",
             "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@test.com"}
    )

    return root


def cleanup_fixtures():
    """Remove all fixture directories."""
    for name in ["mock_monorepo", "mock_single", "mock_flat"]:
        p = FIXTURES_DIR / name
        if p.exists():
            shutil.rmtree(p)


if __name__ == "__main__":
    print("Creating monorepo fixture...")
    print(f"  -> {create_monorepo()}")
    print("Creating single-repo fixture...")
    print(f"  -> {create_single_repo()}")
    print("Creating flat-repo fixture...")
    print(f"  -> {create_flat_repo()}")
    print("Done.")
```

**Step 2: Create empty `__init__.py`**

```python
# tests/__init__.py
# (empty)
```

**Step 3: Run fixture generator to verify it works**

Run: `cd C:\Users\Administrator\.claude\skills\github-repo-scanner && PYTHONIOENCODING=utf-8 python tests/fixtures/create_fixtures.py`

Expected: Three mock directories created with git history, output shows paths.

**Step 4: Commit**

```bash
git add tests/
git commit -m "test: add mock repo fixtures for codewiki testing"
```

---

## Task 2: `generate_wiki.py` — Module Boundary Detection

The first building block: detecting modules in a repo. Three strategies: monorepo, single-repo, fallback.

**Files:**
- Create: `scripts/generate_wiki.py` (partial — module detection only)
- Create: `tests/test_generate_wiki.py` (partial — module detection tests)

**Step 1: Write the failing test for module detection**

```python
# tests/test_generate_wiki.py
"""Tests for generate_wiki.py"""
import sys
import unittest
from pathlib import Path

# Add scripts/ to path so we can import generate_wiki
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))

from fixtures.create_fixtures import create_monorepo, create_single_repo, create_flat_repo
import tempfile
import shutil


class TestDetectModules(unittest.TestCase):

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_monorepo_detects_packages(self):
        from generate_wiki import detect_modules
        root = create_monorepo(self.tmpdir / "mono")
        modules = detect_modules(str(root))
        names = {m["name"] for m in modules}
        self.assertEqual(names, {"core", "renderer", "utils"})
        # Each module should have a path relative to root
        for m in modules:
            self.assertTrue(m["path"].startswith("packages/"))

    def test_single_repo_detects_src_dirs(self):
        from generate_wiki import detect_modules
        root = create_single_repo(self.tmpdir / "single")
        modules = detect_modules(str(root))
        names = {m["name"] for m in modules}
        self.assertEqual(names, {"auth", "api", "models"})
        for m in modules:
            self.assertTrue(m["path"].startswith("src/"))

    def test_flat_repo_fallback(self):
        from generate_wiki import detect_modules
        root = create_flat_repo(self.tmpdir / "flat")
        modules = detect_modules(str(root))
        names = {m["name"] for m in modules}
        # helpers/ contains code files, scripts/ contains only .sh
        self.assertIn("helpers", names)


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run test to verify it fails**

Run: `cd C:\Users\Administrator\.claude\skills\github-repo-scanner && PYTHONIOENCODING=utf-8 python -m pytest tests/test_generate_wiki.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'generate_wiki'`

**Step 3: Implement module detection**

```python
# scripts/generate_wiki.py (initial version — module detection)
#!/usr/bin/env python3
"""Generate a CodeWiki for a cloned repository.

Analyzes module boundaries, entry points, exports, and imports
to produce a structured .codewiki/ directory with index.json,
overview.md, and per-module Markdown files.

Usage:
    python generate_wiki.py <repo_path>
    python generate_wiki.py <repo_path> --force
    python generate_wiki.py <repo_path> --modules-only
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Directories to skip (same as repo_overview.py)
SKIP_DIRS = {
    ".git", ".codewiki", "node_modules", "__pycache__", ".venv", "venv",
    "env", ".tox", ".mypy_cache", ".pytest_cache", "dist", "build",
    ".next", ".nuxt", "target", "vendor", ".gradle", ".idea",
    ".vscode", ".vs", "bin", "obj", "coverage", ".cache", ".eggs",
}

# Code file extensions
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go", ".java",
    ".kt", ".rb", ".php", ".cs", ".cpp", ".c", ".h", ".swift",
    ".dart", ".ex", ".exs", ".vue", ".svelte", ".scala", ".zig",
}

# Monorepo marker directories
MONOREPO_DIRS = {"packages", "apps", "libs", "modules", "plugins"}

# Entry file names
ENTRY_FILES = {
    "index.js", "index.ts", "index.tsx", "index.jsx",
    "main.py", "__init__.py", "mod.rs", "lib.rs", "main.rs",
    "main.go", "Main.java", "main.kt",
}


def dir_has_code_files(dirpath):
    """Check if a directory (non-recursively) contains code files."""
    try:
        for item in os.listdir(dirpath):
            fp = os.path.join(dirpath, item)
            if os.path.isfile(fp):
                ext = os.path.splitext(item)[1].lower()
                if ext in CODE_EXTENSIONS:
                    return True
    except OSError:
        pass
    return False


def dir_has_code_files_recursive(dirpath, max_depth=3):
    """Check if a directory tree contains code files up to max_depth."""
    for root, dirs, files in os.walk(dirpath):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        rel = os.path.relpath(root, dirpath)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        if depth > max_depth:
            dirs.clear()
            continue
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in CODE_EXTENSIONS:
                return True
    return False


def detect_modules(repo_path):
    """Detect module boundaries in a repository.

    Strategy:
    1. Monorepo: if packages/, apps/, libs/ etc. exist with subdirectories
    2. Single-repo: if src/ exists with subdirectories containing code
    3. Fallback: top-level directories containing code files

    Returns list of dicts: [{"name": str, "path": str (relative)}]
    """
    repo = Path(repo_path)
    modules = []

    # Strategy 1: Monorepo detection
    for marker in MONOREPO_DIRS:
        marker_path = repo / marker
        if marker_path.is_dir():
            subdirs = [
                d for d in sorted(marker_path.iterdir())
                if d.is_dir() and d.name not in SKIP_DIRS and not d.name.startswith(".")
            ]
            if len(subdirs) >= 2:  # At least 2 packages to count as monorepo
                for d in subdirs:
                    if dir_has_code_files_recursive(str(d)):
                        rel = os.path.relpath(str(d), repo_path).replace("\\", "/")
                        modules.append({"name": d.name, "path": rel})
                if modules:
                    return modules

    # Strategy 2: src/ directory with subdirectories
    src_path = repo / "src"
    if src_path.is_dir():
        subdirs = [
            d for d in sorted(src_path.iterdir())
            if d.is_dir() and d.name not in SKIP_DIRS and not d.name.startswith(".")
        ]
        for d in subdirs:
            if dir_has_code_files_recursive(str(d)):
                rel = os.path.relpath(str(d), repo_path).replace("\\", "/")
                modules.append({"name": d.name, "path": rel})
        if modules:
            return modules

    # Strategy 3: Fallback — top-level dirs with code files
    for item in sorted(repo.iterdir()):
        if item.is_dir() and item.name not in SKIP_DIRS and not item.name.startswith("."):
            if dir_has_code_files_recursive(str(item)):
                rel = os.path.relpath(str(item), repo_path).replace("\\", "/")
                modules.append({"name": item.name, "path": rel})

    return modules
```

**Step 4: Run tests to verify they pass**

Run: `cd C:\Users\Administrator\.claude\skills\github-repo-scanner && PYTHONIOENCODING=utf-8 python -m pytest tests/test_generate_wiki.py -v`

Expected: 3 tests PASS

**Step 5: Commit**

```bash
git add scripts/generate_wiki.py tests/test_generate_wiki.py
git commit -m "feat(codewiki): add module boundary detection with 3 strategies"
```

---

## Task 3: `generate_wiki.py` — Static Analysis (Entries, Exports, Imports)

Per-module analysis: find entry files, extract exports, trace inter-module imports.

**Files:**
- Modify: `scripts/generate_wiki.py` — add `analyze_module()` function
- Modify: `tests/test_generate_wiki.py` — add analysis tests

**Step 1: Write the failing tests**

Append to `tests/test_generate_wiki.py`:

```python
class TestAnalyzeModule(unittest.TestCase):

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_js_monorepo_entry_and_exports(self):
        from generate_wiki import analyze_module
        root = create_monorepo(self.tmpdir / "mono")
        result = analyze_module(str(root), "packages/core")
        self.assertIn("src/index.js", [e.replace("\\", "/") for e in result["entry_files"]])
        self.assertTrue(len(result["exports"]) > 0)  # Should find createApp, Config

    def test_python_imports_detected(self):
        from generate_wiki import analyze_module
        root = create_single_repo(self.tmpdir / "single")
        result = analyze_module(str(root), "src/auth")
        self.assertIn("__init__.py", [os.path.basename(e) for e in result["entry_files"]])
        # auth imports from .token
        self.assertTrue(len(result["internal_imports"]) > 0)

    def test_key_files_sorted_by_size(self):
        from generate_wiki import analyze_module
        root = create_monorepo(self.tmpdir / "mono")
        result = analyze_module(str(root), "packages/core")
        # key_files should be list of (relative_path, size_bytes)
        self.assertTrue(len(result["key_files"]) > 0)
        sizes = [s for _, s in result["key_files"]]
        self.assertEqual(sizes, sorted(sizes, reverse=True))
```

**Step 2: Run tests to verify they fail**

Run: `cd C:\Users\Administrator\.claude\skills\github-repo-scanner && PYTHONIOENCODING=utf-8 python -m pytest tests/test_generate_wiki.py::TestAnalyzeModule -v`

Expected: FAIL — `ImportError: cannot import name 'analyze_module'`

**Step 3: Implement `analyze_module()`**

Add to `scripts/generate_wiki.py`:

```python
# ── Export extraction patterns ─────────────────────────────

# JavaScript/TypeScript
JS_EXPORT_PATTERNS = [
    re.compile(r"export\s+(?:default\s+)?(?:function|class|const|let|var|type|interface)\s+(\w+)"),
    re.compile(r"export\s*\{\s*([^}]+)\}"),
    re.compile(r"module\.exports\s*=\s*\{\s*([^}]+)\}"),
    re.compile(r"module\.exports\.(\w+)"),
]

# Python
PY_EXPORT_PATTERNS = [
    re.compile(r"^__all__\s*=\s*\[([^\]]+)\]", re.MULTILINE),
    re.compile(r"^from\s+\.\w*\s+import\s+(.+)$", re.MULTILINE),  # in __init__.py
]

# Import patterns for inter-module detection
JS_IMPORT_PATTERN = re.compile(
    r"""(?:import|require)\s*\(?['"]([^'"]+)['"]"""
)
PY_IMPORT_PATTERN = re.compile(
    r"^(?:from|import)\s+([\w.]+)", re.MULTILINE
)


def extract_exports(filepath):
    """Extract exported names from a file."""
    exports = []
    try:
        content = Path(filepath).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return exports

    ext = os.path.splitext(filepath)[1].lower()

    if ext in (".js", ".ts", ".tsx", ".jsx", ".mjs"):
        for pattern in JS_EXPORT_PATTERNS:
            for match in pattern.finditer(content):
                raw = match.group(1)
                # Handle "{ a, b, c }" style
                names = [n.strip().split(" as ")[0].strip()
                         for n in raw.split(",") if n.strip()]
                exports.extend(names)

    elif ext == ".py":
        basename = os.path.basename(filepath)
        if basename == "__init__.py":
            for pattern in PY_EXPORT_PATTERNS:
                for match in pattern.finditer(content):
                    raw = match.group(1)
                    names = [n.strip().strip("'\"")
                             for n in raw.split(",") if n.strip()]
                    exports.extend(names)
        else:
            # Public functions and classes (no leading underscore)
            exports.extend(re.findall(r"^(?:def|class)\s+([a-zA-Z]\w*)", content, re.MULTILINE))

    return list(dict.fromkeys(exports))  # deduplicate preserving order


def extract_imports(filepath, module_path):
    """Extract import targets from a file. Returns list of raw import strings."""
    imports = []
    try:
        content = Path(filepath).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return imports

    ext = os.path.splitext(filepath)[1].lower()

    if ext in (".js", ".ts", ".tsx", ".jsx", ".mjs"):
        imports = JS_IMPORT_PATTERN.findall(content)
    elif ext == ".py":
        imports = PY_IMPORT_PATTERN.findall(content)

    return imports


def analyze_module(repo_path, module_rel_path):
    """Analyze a single module: entries, exports, imports, key files.

    Args:
        repo_path: absolute path to repo root
        module_rel_path: relative path to module (e.g. "packages/core")

    Returns dict with: entry_files, exports, internal_imports, key_files
    """
    mod_abs = os.path.join(repo_path, module_rel_path)
    entry_files = []
    all_exports = []
    all_imports = []
    file_sizes = []

    for root, dirs, files in os.walk(mod_abs):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext not in CODE_EXTENSIONS:
                continue

            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, mod_abs).replace("\\", "/")

            # Track entry files
            if fname in ENTRY_FILES:
                entry_files.append(rel)

            # Track file sizes
            try:
                size = os.path.getsize(fpath)
                file_sizes.append((rel, size))
            except OSError:
                pass

            # Extract exports (primarily from entry files, but scan all)
            exports = extract_exports(fpath)
            all_exports.extend(exports)

            # Extract imports
            imports = extract_imports(fpath, module_rel_path)
            all_imports.extend(imports)

    # Sort key files by size descending
    file_sizes.sort(key=lambda x: x[1], reverse=True)

    return {
        "entry_files": entry_files,
        "exports": list(dict.fromkeys(all_exports)),
        "internal_imports": all_imports,
        "key_files": file_sizes[:10],  # Top 10 by size
    }
```

**Step 4: Run tests to verify they pass**

Run: `cd C:\Users\Administrator\.claude\skills\github-repo-scanner && PYTHONIOENCODING=utf-8 python -m pytest tests/test_generate_wiki.py::TestAnalyzeModule -v`

Expected: 3 tests PASS

**Step 5: Commit**

```bash
git add scripts/generate_wiki.py tests/test_generate_wiki.py
git commit -m "feat(codewiki): add per-module static analysis (entries, exports, imports)"
```

---

## Task 4: `generate_wiki.py` — Output Generation (index.json, overview.md, modules/*.md)

Generate the actual `.codewiki/` directory with all files.

**Files:**
- Modify: `scripts/generate_wiki.py` — add `generate_wiki()`, `get_commit_hash()`, CLI
- Modify: `tests/test_generate_wiki.py` — add output tests

**Step 1: Write the failing tests**

Append to `tests/test_generate_wiki.py`:

```python
class TestGenerateWiki(unittest.TestCase):

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_generates_codewiki_dir(self):
        from generate_wiki import generate_wiki
        root = create_monorepo(self.tmpdir / "mono")
        generate_wiki(str(root))
        wiki_dir = root / ".codewiki"
        self.assertTrue(wiki_dir.exists())
        self.assertTrue((wiki_dir / "index.json").exists())
        self.assertTrue((wiki_dir / "overview.md").exists())
        self.assertTrue((wiki_dir / "modules").is_dir())

    def test_index_json_has_correct_structure(self):
        from generate_wiki import generate_wiki
        root = create_monorepo(self.tmpdir / "mono")
        generate_wiki(str(root))
        with open(root / ".codewiki" / "index.json", encoding="utf-8") as f:
            index = json.load(f)
        self.assertEqual(index["version"], 1)
        self.assertIn("modules", index)
        self.assertIn("architecture", index)
        self.assertIn("core", index["modules"])
        self.assertFalse(index["modules"]["core"]["stale"])
        self.assertEqual(index["modules"]["core"]["source"], "auto")

    def test_module_md_has_template_sections(self):
        from generate_wiki import generate_wiki
        root = create_monorepo(self.tmpdir / "mono")
        generate_wiki(str(root))
        md = (root / ".codewiki" / "modules" / "core.md").read_text(encoding="utf-8")
        self.assertIn("# core", md)
        self.assertIn("## 职责", md)
        self.assertIn("## 关键文件", md)
        self.assertIn("## 对外 API", md)
        self.assertIn("## 对话补充", md)

    def test_force_overwrites_existing(self):
        from generate_wiki import generate_wiki
        root = create_monorepo(self.tmpdir / "mono")
        generate_wiki(str(root))
        # Modify a file
        idx_path = root / ".codewiki" / "index.json"
        original = idx_path.read_text(encoding="utf-8")
        idx_path.write_text('{"tampered": true}', encoding="utf-8")
        # Regenerate with force
        generate_wiki(str(root), force=True)
        restored = idx_path.read_text(encoding="utf-8")
        self.assertNotEqual(restored, '{"tampered": true}')

    def test_skips_if_exists_without_force(self):
        from generate_wiki import generate_wiki
        root = create_monorepo(self.tmpdir / "mono")
        generate_wiki(str(root))
        # Should return False (skipped)
        result = generate_wiki(str(root), force=False)
        self.assertFalse(result)

    def test_single_repo_generates_wiki(self):
        from generate_wiki import generate_wiki
        root = create_single_repo(self.tmpdir / "single")
        generate_wiki(str(root))
        wiki_dir = root / ".codewiki"
        self.assertTrue((wiki_dir / "modules" / "auth.md").exists())
        self.assertTrue((wiki_dir / "modules" / "api.md").exists())

    def test_gitexclude_is_set(self):
        from generate_wiki import generate_wiki
        root = create_monorepo(self.tmpdir / "mono")
        generate_wiki(str(root))
        exclude_path = root / ".git" / "info" / "exclude"
        if exclude_path.exists():
            content = exclude_path.read_text(encoding="utf-8")
            self.assertIn(".codewiki", content)
```

**Step 2: Run tests to verify they fail**

Run: `cd C:\Users\Administrator\.claude\skills\github-repo-scanner && PYTHONIOENCODING=utf-8 python -m pytest tests/test_generate_wiki.py::TestGenerateWiki -v`

Expected: FAIL — `ImportError: cannot import name 'generate_wiki'`

**Step 3: Implement output generation**

Add to `scripts/generate_wiki.py`:

```python
def get_commit_hash(repo_path):
    """Get current HEAD commit hash (short)."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_path, capture_output=True, text=True,
            encoding="utf-8", timeout=10
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return "unknown"


def get_repo_name_from_remote(repo_path):
    """Try to extract owner/repo from git remote URL."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=repo_path, capture_output=True, text=True,
            encoding="utf-8", timeout=10
        )
        if result.returncode == 0:
            url = result.stdout.strip()
            # Match github.com/owner/repo
            match = re.search(r"github\.com[/:]([^/]+)/([^/.]+)", url)
            if match:
                return f"{match.group(1)}/{match.group(2)}"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return Path(repo_path).name


def get_repo_description(repo_path):
    """Extract repo description from README or manifest files."""
    for name in ("README.md", "README.rst", "README.txt", "README"):
        readme_path = os.path.join(repo_path, name)
        if os.path.exists(readme_path):
            try:
                content = Path(readme_path).read_text(encoding="utf-8", errors="replace")
                lines = content.strip().split("\n")
                # Skip title line, find first non-empty paragraph
                for line in lines[1:]:
                    stripped = line.strip()
                    if stripped and not stripped.startswith("#") and not stripped.startswith("!"):
                        return stripped[:200]
            except OSError:
                pass

    # Try package.json description
    pkg_json = os.path.join(repo_path, "package.json")
    if os.path.exists(pkg_json):
        try:
            with open(pkg_json, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("description", "")
        except (OSError, json.JSONDecodeError):
            pass

    return ""


def detect_architecture_patterns(repo_path, modules):
    """Detect high-level architecture patterns."""
    patterns = []
    repo = Path(repo_path)

    # Monorepo?
    for d in MONOREPO_DIRS:
        if (repo / d).is_dir():
            patterns.append("monorepo")
            break

    # Package manager workspace?
    pkg_json = repo / "package.json"
    if pkg_json.exists():
        try:
            data = json.loads(pkg_json.read_text(encoding="utf-8"))
            if "workspaces" in data:
                patterns.append("workspace")
        except (OSError, json.JSONDecodeError):
            pass

    # Docker?
    if (repo / "Dockerfile").exists() or (repo / "docker-compose.yml").exists():
        patterns.append("docker")

    # CI/CD?
    if (repo / ".github" / "workflows").is_dir():
        patterns.append("github-actions")

    return patterns


def detect_relationships(repo_path, modules, analyses):
    """Detect inter-module dependencies from import analysis."""
    relationships = []
    module_names = {m["name"] for m in modules}

    for mod, analysis in zip(modules, analyses):
        for imp in analysis["internal_imports"]:
            # Check if import references another known module
            for other in module_names:
                if other == mod["name"]:
                    continue
                # Check various import patterns
                if other in imp:
                    relationships.append({
                        "from": mod["name"],
                        "to": other,
                        "type": "depends"
                    })
                    break

    # Deduplicate
    seen = set()
    unique = []
    for r in relationships:
        key = (r["from"], r["to"], r["type"])
        if key not in seen:
            seen.add(key)
            unique.append(r)

    return unique


def set_gitexclude(repo_path):
    """Add .codewiki to .git/info/exclude so it doesn't pollute git status."""
    exclude_path = os.path.join(repo_path, ".git", "info", "exclude")
    exclude_dir = os.path.dirname(exclude_path)

    os.makedirs(exclude_dir, exist_ok=True)

    marker = ".codewiki"
    if os.path.exists(exclude_path):
        content = Path(exclude_path).read_text(encoding="utf-8", errors="replace")
        if marker in content:
            return  # Already excluded
        with open(exclude_path, "a", encoding="utf-8") as f:
            f.write(f"\n# CodeWiki generated knowledge\n{marker}/\n")
    else:
        with open(exclude_path, "w", encoding="utf-8") as f:
            f.write(f"# CodeWiki generated knowledge\n{marker}/\n")


def generate_module_md(module_name, module_path, analysis, commit_hash):
    """Generate Markdown content for a module."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        f"# {module_name}",
        "",
        f"> 自动生成于 {now} | commit: {commit_hash} | source: auto",
        "",
        "## 职责",
        "",
        f"`{module_path}` 模块。",
        "",
        "## 关键文件",
        "",
    ]

    if analysis["key_files"]:
        for fpath, size in analysis["key_files"][:8]:
            lines.append(f"- `{fpath}` ({size} bytes)")
    else:
        lines.append("- (无代码文件)")

    lines.extend(["", "## 对外 API", ""])

    if analysis["exports"]:
        for exp in analysis["exports"][:20]:
            lines.append(f"- `{exp}`")
    else:
        lines.append("- (未检测到导出)")

    lines.extend([
        "",
        "## 对话补充（L2/L3）",
        "",
        "<!-- 后续对话中沉淀的深层知识将追加在此 -->",
        "",
    ])

    return "\n".join(lines)


def generate_overview_md(repo_name, description, modules, analyses, commit_hash):
    """Generate overview.md content."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        f"# {repo_name}",
        "",
        f"> 自动生成于 {now} | commit: {commit_hash}",
        "",
        "## 概述",
        "",
        description or "(从 README 未能提取描述)",
        "",
        "## 模块列表",
        "",
        "| 模块 | 路径 | 入口文件 | 导出数量 |",
        "|------|------|---------|---------|",
    ]

    for mod, analysis in zip(modules, analyses):
        entries = ", ".join(analysis["entry_files"][:2]) or "-"
        export_count = len(analysis["exports"])
        lines.append(f"| {mod['name']} | `{mod['path']}` | {entries} | {export_count} |")

    lines.append("")
    return "\n".join(lines)


def generate_wiki(repo_path, force=False, modules_only=False):
    """Generate .codewiki/ for a repository.

    Args:
        repo_path: absolute path to repo root
        force: overwrite existing wiki
        modules_only: only regenerate module files, preserve conversation supplements

    Returns: True if generated, False if skipped
    """
    wiki_dir = os.path.join(repo_path, ".codewiki")
    modules_dir = os.path.join(wiki_dir, "modules")

    # Check existing
    if os.path.exists(wiki_dir) and not force and not modules_only:
        print(f"Wiki already exists at {wiki_dir}. Use --force to overwrite.")
        return False

    # Detect modules
    modules = detect_modules(repo_path)
    if not modules:
        print("No modules detected. Generating minimal wiki.")
        modules = [{"name": Path(repo_path).name, "path": "."}]

    # Analyze each module
    analyses = [analyze_module(repo_path, m["path"]) for m in modules]

    # Gather metadata
    commit_hash = get_commit_hash(repo_path)
    repo_name = get_repo_name_from_remote(repo_path)
    description = get_repo_description(repo_path)
    patterns = detect_architecture_patterns(repo_path, modules)
    relationships = detect_relationships(repo_path, modules, analyses)
    now = datetime.now(timezone.utc).isoformat()

    # Find entry points at repo level
    entry_points = []
    for mod, analysis in zip(modules, analyses):
        for ef in analysis["entry_files"]:
            entry_points.append(os.path.join(mod["path"], ef).replace("\\", "/"))

    # Build index
    index = {
        "version": 1,
        "repo": repo_name,
        "generated_at": now,
        "code_commit": commit_hash,
        "modules": {},
        "architecture": {
            "patterns": patterns,
            "entry_points": entry_points[:10],
            "key_relationships": relationships,
        },
    }

    for mod, analysis in zip(modules, analyses):
        summary_parts = []
        if analysis["exports"]:
            summary_parts.append(f"exports: {', '.join(analysis['exports'][:3])}")
        if analysis["entry_files"]:
            summary_parts.append(f"entry: {analysis['entry_files'][0]}")
        summary = "; ".join(summary_parts) if summary_parts else f"{mod['path']} 模块"

        index["modules"][mod["name"]] = {
            "path": mod["path"],
            "file": f"modules/{mod['name']}.md",
            "summary": summary[:200],
            "stale": False,
            "last_updated": now,
            "source": "auto",
        }

    # Create directories
    os.makedirs(modules_dir, exist_ok=True)

    # Write index.json
    if not modules_only:
        with open(os.path.join(wiki_dir, "index.json"), "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, ensure_ascii=False)

    # Write overview.md
    if not modules_only:
        overview = generate_overview_md(repo_name, description, modules, analyses, commit_hash)
        with open(os.path.join(wiki_dir, "overview.md"), "w", encoding="utf-8") as f:
            f.write(overview)

    # Write module MDs
    for mod, analysis in zip(modules, analyses):
        md_path = os.path.join(modules_dir, f"{mod['name']}.md")

        if modules_only and os.path.exists(md_path):
            # Preserve conversation supplements
            existing = Path(md_path).read_text(encoding="utf-8", errors="replace")
            supplement_marker = "## 对话补充（L2/L3）"
            if supplement_marker in existing:
                supplement_section = existing[existing.index(supplement_marker):]
                # Check if there's actual content (not just the template comment)
                if "###" in supplement_section:
                    new_md = generate_module_md(mod["name"], mod["path"], analysis, commit_hash)
                    # Replace the supplement section in new_md with existing one
                    new_md = new_md[:new_md.index(supplement_marker)] + supplement_section
                    with open(md_path, "w", encoding="utf-8") as f:
                        f.write(new_md)
                    continue

        md_content = generate_module_md(mod["name"], mod["path"], analysis, commit_hash)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)

    # Set .git/info/exclude
    set_gitexclude(repo_path)

    module_names = [m["name"] for m in modules]
    print(f"CodeWiki generated at: {wiki_dir}")
    print(f"  Modules: {', '.join(module_names)}")
    print(f"  Commit: {commit_hash}")

    return True


# ── CLI ─────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate CodeWiki for a repository")
    parser.add_argument("repo_path", help="Path to cloned repository")
    parser.add_argument("--force", "-f", action="store_true",
                        help="Overwrite existing wiki")
    parser.add_argument("--modules-only", action="store_true",
                        help="Only regenerate module files, preserve conversation supplements")

    args = parser.parse_args()
    generate_wiki(args.repo_path, force=args.force, modules_only=args.modules_only)


if __name__ == "__main__":
    main()
```

**Step 4: Run all tests**

Run: `cd C:\Users\Administrator\.claude\skills\github-repo-scanner && PYTHONIOENCODING=utf-8 python -m pytest tests/test_generate_wiki.py -v`

Expected: All tests PASS (module detection + analysis + output generation)

**Step 5: Manual smoke test**

Run: `cd C:\Users\Administrator\.claude\skills\github-repo-scanner && PYTHONIOENCODING=utf-8 python tests/fixtures/create_fixtures.py && PYTHONIOENCODING=utf-8 python scripts/generate_wiki.py tests/fixtures/mock_monorepo --force`

Expected: Output shows wiki generated with 3 modules (core, renderer, utils).

Verify: Read `.codewiki/index.json` and `.codewiki/modules/core.md` to confirm correct content.

**Step 6: Commit**

```bash
git add scripts/generate_wiki.py tests/test_generate_wiki.py
git commit -m "feat(codewiki): complete generate_wiki.py with output generation"
```

---

## Task 5: `update_wiki.py` — Knowledge Backflow Script

Script for appending conversation supplements, updating relationships, and marking enriched.

**Files:**
- Create: `scripts/update_wiki.py`
- Create: `tests/test_update_wiki.py`

**Step 1: Write the failing tests**

```python
# tests/test_update_wiki.py
"""Tests for update_wiki.py"""
import json
import sys
import unittest
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))

from fixtures.create_fixtures import create_monorepo


class TestAppendSupplement(unittest.TestCase):

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.root = create_monorepo(self.tmpdir / "mono")
        # Generate wiki first
        from generate_wiki import generate_wiki
        generate_wiki(str(self.root))

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_append_supplement_to_module(self):
        from update_wiki import append_supplement
        append_supplement(
            str(self.root), "core",
            topic="架构分析",
            content="Core 模块使用依赖注入模式"
        )
        md = (self.root / ".codewiki" / "modules" / "core.md").read_text(encoding="utf-8")
        self.assertIn("### ", md)  # Has date-stamped heading
        self.assertIn("架构分析", md)
        self.assertIn("Core 模块使用依赖注入模式", md)

    def test_append_preserves_existing_content(self):
        from update_wiki import append_supplement
        original = (self.root / ".codewiki" / "modules" / "core.md").read_text(encoding="utf-8")
        append_supplement(str(self.root), "core", "测试", "测试内容")
        updated = (self.root / ".codewiki" / "modules" / "core.md").read_text(encoding="utf-8")
        # Original L1 content should still be present
        self.assertIn("## 职责", updated)
        self.assertIn("## 对外 API", updated)

    def test_multiple_supplements_append_in_order(self):
        from update_wiki import append_supplement
        append_supplement(str(self.root), "core", "第一次", "内容A")
        append_supplement(str(self.root), "core", "第二次", "内容B")
        md = (self.root / ".codewiki" / "modules" / "core.md").read_text(encoding="utf-8")
        pos_a = md.index("内容A")
        pos_b = md.index("内容B")
        self.assertLess(pos_a, pos_b)


class TestAddRelationship(unittest.TestCase):

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.root = create_monorepo(self.tmpdir / "mono")
        from generate_wiki import generate_wiki
        generate_wiki(str(self.root))

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_add_relationship(self):
        from update_wiki import add_relationship
        add_relationship(str(self.root), "utils", "core", "depends")
        with open(self.root / ".codewiki" / "index.json", encoding="utf-8") as f:
            index = json.load(f)
        rels = index["architecture"]["key_relationships"]
        added = [r for r in rels if r["from"] == "utils" and r["to"] == "core"]
        self.assertEqual(len(added), 1)

    def test_no_duplicate_relationships(self):
        from update_wiki import add_relationship
        add_relationship(str(self.root), "utils", "core", "depends")
        add_relationship(str(self.root), "utils", "core", "depends")
        with open(self.root / ".codewiki" / "index.json", encoding="utf-8") as f:
            index = json.load(f)
        rels = index["architecture"]["key_relationships"]
        added = [r for r in rels if r["from"] == "utils" and r["to"] == "core"]
        self.assertEqual(len(added), 1)


class TestMarkEnriched(unittest.TestCase):

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.root = create_monorepo(self.tmpdir / "mono")
        from generate_wiki import generate_wiki
        generate_wiki(str(self.root))

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_mark_enriched_updates_source(self):
        from update_wiki import mark_enriched
        mark_enriched(str(self.root), "core")
        with open(self.root / ".codewiki" / "index.json", encoding="utf-8") as f:
            index = json.load(f)
        self.assertEqual(index["modules"]["core"]["source"], "enriched")


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run tests to verify they fail**

Run: `cd C:\Users\Administrator\.claude\skills\github-repo-scanner && PYTHONIOENCODING=utf-8 python -m pytest tests/test_update_wiki.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'update_wiki'`

**Step 3: Implement `update_wiki.py`**

```python
# scripts/update_wiki.py
#!/usr/bin/env python3
"""Update CodeWiki with conversation supplements and relationship changes.

Usage:
    python update_wiki.py <repo_path> --module <name> --topic <topic> --content <text>
    python update_wiki.py <repo_path> --add-relationship "from->to:type"
    python update_wiki.py <repo_path> --module <name> --mark-enriched
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def _load_index(repo_path):
    """Load index.json from .codewiki/."""
    index_path = os.path.join(repo_path, ".codewiki", "index.json")
    if not os.path.exists(index_path):
        print(f"ERROR: No codewiki found at {repo_path}", file=sys.stderr)
        sys.exit(1)
    with open(index_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_index(repo_path, index):
    """Save index.json to .codewiki/."""
    index_path = os.path.join(repo_path, ".codewiki", "index.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)


def append_supplement(repo_path, module_name, topic, content):
    """Append a conversation supplement to a module's Markdown file.

    Adds a date-stamped section under '## 对话补充（L2/L3）'.
    """
    index = _load_index(repo_path)

    if module_name not in index["modules"]:
        print(f"ERROR: Module '{module_name}' not found in wiki.", file=sys.stderr)
        sys.exit(1)

    md_rel = index["modules"][module_name]["file"]
    md_path = os.path.join(repo_path, ".codewiki", md_rel)

    if not os.path.exists(md_path):
        print(f"ERROR: Module file not found: {md_path}", file=sys.stderr)
        sys.exit(1)

    md_content = Path(md_path).read_text(encoding="utf-8", errors="replace")

    # Build supplement entry
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    supplement = f"\n### {today} — {topic}\n\n{content}\n"

    # Find insertion point: at the end of the file (after the supplement section)
    marker = "## 对话补充（L2/L3）"
    if marker in md_content:
        # Append at end of file
        md_content = md_content.rstrip() + "\n" + supplement
    else:
        # Add the section if missing (shouldn't happen with generate_wiki, but be safe)
        md_content = md_content.rstrip() + f"\n\n{marker}\n{supplement}"

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    # Update last_updated in index
    index["modules"][module_name]["last_updated"] = datetime.now(timezone.utc).isoformat()
    _save_index(repo_path, index)

    print(f"Supplement added to {module_name}: {topic}")


def add_relationship(repo_path, from_module, to_module, rel_type="depends"):
    """Add an architecture relationship to index.json.

    Deduplicates: won't add if same from/to/type already exists.
    """
    index = _load_index(repo_path)

    rels = index.setdefault("architecture", {}).setdefault("key_relationships", [])

    # Check for duplicate
    for r in rels:
        if r["from"] == from_module and r["to"] == to_module and r["type"] == rel_type:
            print(f"Relationship already exists: {from_module} -> {to_module} ({rel_type})")
            return

    rels.append({"from": from_module, "to": to_module, "type": rel_type})
    _save_index(repo_path, index)

    print(f"Relationship added: {from_module} -> {to_module} ({rel_type})")


def mark_enriched(repo_path, module_name):
    """Mark a module's source as 'enriched' (has conversation supplements)."""
    index = _load_index(repo_path)

    if module_name not in index["modules"]:
        print(f"ERROR: Module '{module_name}' not found in wiki.", file=sys.stderr)
        sys.exit(1)

    index["modules"][module_name]["source"] = "enriched"
    index["modules"][module_name]["last_updated"] = datetime.now(timezone.utc).isoformat()
    _save_index(repo_path, index)

    print(f"Module '{module_name}' marked as enriched.")


def parse_relationship_string(rel_str):
    """Parse 'from->to:type' into (from, to, type).

    Examples:
        'scheduler->reconciler:depends' -> ('scheduler', 'reconciler', 'depends')
        'auth->api' -> ('auth', 'api', 'depends')
    """
    if "->" not in rel_str:
        print(f"ERROR: Invalid relationship format: '{rel_str}'", file=sys.stderr)
        print("Expected: 'from->to:type' (e.g. 'scheduler->reconciler:depends')", file=sys.stderr)
        sys.exit(1)

    from_part, rest = rel_str.split("->", 1)
    if ":" in rest:
        to_part, rel_type = rest.rsplit(":", 1)
    else:
        to_part = rest
        rel_type = "depends"

    return from_part.strip(), to_part.strip(), rel_type.strip()


# ── CLI ─────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Update CodeWiki")
    parser.add_argument("repo_path", help="Path to cloned repository")
    parser.add_argument("--module", "-m", help="Module name to update")
    parser.add_argument("--topic", "-t", help="Topic label for supplement")
    parser.add_argument("--content", "-c", help="Supplement content text")
    parser.add_argument("--add-relationship", dest="relationship",
                        help="Add relationship: 'from->to:type'")
    parser.add_argument("--mark-enriched", action="store_true",
                        help="Mark module as enriched")

    args = parser.parse_args()

    if args.relationship:
        from_mod, to_mod, rel_type = parse_relationship_string(args.relationship)
        add_relationship(args.repo_path, from_mod, to_mod, rel_type)
    elif args.mark_enriched and args.module:
        mark_enriched(args.repo_path, args.module)
    elif args.module and args.topic and args.content:
        append_supplement(args.repo_path, args.module, args.topic, args.content)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
```

**Step 4: Run tests**

Run: `cd C:\Users\Administrator\.claude\skills\github-repo-scanner && PYTHONIOENCODING=utf-8 python -m pytest tests/test_update_wiki.py -v`

Expected: All tests PASS

**Step 5: Commit**

```bash
git add scripts/update_wiki.py tests/test_update_wiki.py
git commit -m "feat(codewiki): add update_wiki.py for knowledge backflow"
```

---

## Task 6: Modify `clone_repo.py` — Stale Marking After Git Pull

Integrate stale detection into the existing git pull flow.

**Files:**
- Modify: `scripts/clone_repo.py:131-176` — modify `git_pull()` to record old/new hash and call stale marker
- Create: `tests/test_stale_marking.py`

**Step 1: Write the failing test**

```python
# tests/test_stale_marking.py
"""Tests for stale marking integration in clone_repo.py"""
import json
import os
import sys
import unittest
import subprocess
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))

from fixtures.create_fixtures import create_monorepo


class TestMarkStaleModules(unittest.TestCase):

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.root = create_monorepo(self.tmpdir / "mono")
        # Generate wiki
        from generate_wiki import generate_wiki
        generate_wiki(str(self.root))

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_mark_stale_flags_affected_module(self):
        from clone_repo import mark_stale_modules
        # Simulate: packages/core/src/app.js was changed
        changed_files = ["packages/core/src/app.js"]
        count = mark_stale_modules(str(self.root), changed_files)
        self.assertEqual(count, 1)

        with open(self.root / ".codewiki" / "index.json", encoding="utf-8") as f:
            index = json.load(f)
        self.assertTrue(index["modules"]["core"]["stale"])
        self.assertFalse(index["modules"]["renderer"]["stale"])

    def test_mark_stale_updates_commit_hash(self):
        from clone_repo import mark_stale_modules
        mark_stale_modules(str(self.root), ["packages/core/src/app.js"], new_commit="abc1234")
        with open(self.root / ".codewiki" / "index.json", encoding="utf-8") as f:
            index = json.load(f)
        self.assertEqual(index["code_commit"], "abc1234")

    def test_no_wiki_dir_is_noop(self):
        from clone_repo import mark_stale_modules
        # Remove wiki
        shutil.rmtree(self.root / ".codewiki")
        count = mark_stale_modules(str(self.root), ["packages/core/src/app.js"])
        self.assertEqual(count, 0)

    def test_unrelated_file_change_no_stale(self):
        from clone_repo import mark_stale_modules
        changed_files = [".github/workflows/ci.yml", "README.md"]
        count = mark_stale_modules(str(self.root), changed_files)
        self.assertEqual(count, 0)
        with open(self.root / ".codewiki" / "index.json", encoding="utf-8") as f:
            index = json.load(f)
        for mod in index["modules"].values():
            self.assertFalse(mod["stale"])


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run tests to verify they fail**

Run: `cd C:\Users\Administrator\.claude\skills\github-repo-scanner && PYTHONIOENCODING=utf-8 python -m pytest tests/test_stale_marking.py -v`

Expected: FAIL — `ImportError: cannot import name 'mark_stale_modules' from 'clone_repo'`

**Step 3: Add `mark_stale_modules()` to `clone_repo.py`**

Add this function before the `git_pull()` function (around line 130):

```python
# ── CodeWiki stale marking ─────────────────────────────────

def mark_stale_modules(repo_dir, changed_files, new_commit=None):
    """Mark codewiki modules as stale based on changed file paths.

    Args:
        repo_dir: path to the cloned repo
        changed_files: list of relative file paths that changed
        new_commit: new commit hash to set in index (optional)

    Returns: number of modules marked stale
    """
    index_path = os.path.join(repo_dir, ".codewiki", "index.json")
    if not os.path.exists(index_path):
        return 0

    try:
        with open(index_path, "r", encoding="utf-8") as f:
            index = json.load(f)
    except (OSError, json.JSONDecodeError):
        return 0

    modules = index.get("modules", {})
    stale_count = 0

    for mod_name, mod_info in modules.items():
        mod_path = mod_info.get("path", "")
        if not mod_path:
            continue
        # Normalize: ensure mod_path uses forward slashes and no trailing slash
        mod_path = mod_path.replace("\\", "/").rstrip("/")
        for changed in changed_files:
            changed_norm = changed.replace("\\", "/")
            if changed_norm.startswith(mod_path + "/"):
                mod_info["stale"] = True
                stale_count += 1
                break

    if new_commit:
        index["code_commit"] = new_commit

    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)

    return stale_count
```

**Step 4: Modify `git_pull()` to call stale marking**

Replace the `git_pull()` function in `clone_repo.py` with this version that records old/new hash:

```python
def git_pull(repo_dir, full_name):
    """Pull latest changes for a cloned repo. Marks stale wiki modules if changes detected."""
    print(f"Pulling latest for {full_name}...")

    # Record pre-pull commit hash
    old_hash = None
    try:
        old_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_dir, capture_output=True, text=True,
            encoding="utf-8", timeout=10
        )
        if old_result.returncode == 0:
            old_hash = old_result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    try:
        result = subprocess.run(
            ["git", "pull", "--ff-only"],
            cwd=repo_dir, capture_output=True, text=True,
            encoding="utf-8", timeout=120
        )
    except subprocess.TimeoutExpired:
        print(f"  WARNING: Pull timed out for {full_name}", file=sys.stderr)
        return False

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "not a git repository" in stderr.lower():
            print(f"  ERROR: {repo_dir} is not a git repository.", file=sys.stderr)
            return False
        print(f"  Fast-forward failed, attempting fetch + reset...")
        try:
            subprocess.run(
                ["git", "fetch", "origin"], cwd=repo_dir,
                capture_output=True, text=True, encoding="utf-8", timeout=120
            )
            branch_result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_dir,
                capture_output=True, text=True, encoding="utf-8"
            )
            branch = branch_result.stdout.strip() or "main"
            subprocess.run(
                ["git", "reset", "--hard", f"origin/{branch}"], cwd=repo_dir,
                capture_output=True, text=True, encoding="utf-8"
            )
            print(f"  Reset to origin/{branch} successfully.")
        except Exception as e:
            print(f"  WARNING: Could not sync {full_name}: {e}", file=sys.stderr)
            return False

    # Check for changes and mark stale wiki modules
    new_hash = None
    try:
        new_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_dir, capture_output=True, text=True,
            encoding="utf-8", timeout=10
        )
        if new_result.returncode == 0:
            new_hash = new_result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    if old_hash and new_hash and old_hash != new_hash:
        try:
            diff_result = subprocess.run(
                ["git", "diff", "--name-only", old_hash, new_hash],
                cwd=repo_dir, capture_output=True, text=True,
                encoding="utf-8", timeout=30
            )
            if diff_result.returncode == 0:
                changed_files = [f for f in diff_result.stdout.strip().split("\n") if f]
                if changed_files:
                    stale_count = mark_stale_modules(repo_dir, changed_files, new_commit=new_hash[:7])
                    if stale_count > 0:
                        print(f"  Wiki: {stale_count} module(s) marked as stale.")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        print(f"  Updated successfully.")
    else:
        output = result.stdout.strip() if result.returncode == 0 else ""
        if "Already up to date" in output or "Already up-to-date" in output:
            print(f"  Already up to date.")
        elif old_hash == new_hash:
            print(f"  Already up to date.")
        else:
            print(f"  Updated successfully.")

    return True
```

**Step 5: Run tests**

Run: `cd C:\Users\Administrator\.claude\skills\github-repo-scanner && PYTHONIOENCODING=utf-8 python -m pytest tests/test_stale_marking.py -v`

Expected: All tests PASS

Run existing clone_repo functionality to verify no regression:

Run: `cd C:\Users\Administrator\.claude\skills\github-repo-scanner && PYTHONIOENCODING=utf-8 python scripts/clone_repo.py --show-config`

Expected: Shows current config without errors.

**Step 6: Commit**

```bash
git add scripts/clone_repo.py tests/test_stale_marking.py
git commit -m "feat(codewiki): integrate stale marking into git pull flow"
```

---

## Task 7: Update `SKILL.md` and `analysis-guide.md`

Update documentation to include the codewiki workflow.

**Files:**
- Modify: `SKILL.md` — add Wiki Check step and Knowledge Harvest step
- Modify: `references/analysis-guide.md` — add wiki-assisted analysis section

**Step 1: Update SKILL.md**

In the **Workflow** section, update the flow diagram to include Step 3 (Wiki Check) and Step 5 (Knowledge Harvest). The new workflow section should be:

```markdown
## Workflow

```
User request
    |
    v
[Already cached?] ---yes---> Auto-pull latest --> Wiki Check --> Analyze
    |                                                  |
    no                                          [.codewiki/ exists?]
    |                                           yes/        \no
    v                                          |            |
[Discover or Direct?]                   Load index    Offer to generate
    |                \                      |            |
    v                 v                     v            v
Search GitHub     Parse owner/repo     Analyze w/    Generate wiki
(search_repos.py)     |                wiki context   (generate_wiki.py)
    |                 v                     |            |
    v            Clone to workspace         v            v
User picks repo  (clone_repo.py)     Knowledge      Analyze
    |                 |               Harvest
    v                 v                  |
Clone to workspace   Overview        [End of session]
(clone_repo.py)  (repo_overview.py)  Propose saving
    |                 |              findings to wiki
    v                 v              (update_wiki.py)
Overview          Analyze with
    |             Grep/Glob/Read
    v
Analyze with
Grep/Glob/Read
```
```

Add to the end of the **Step 3: Generate Overview** section a new **Step 3b**:

```markdown
### Step 3b: Wiki Check

After generating the overview, check if a CodeWiki exists for this repository:

**If `.codewiki/` exists:**
- Read `.codewiki/index.json` to understand available knowledge
- Note any modules marked as `stale: true` and inform the user
- During analysis (Step 4), consult wiki modules before deep source reading

**If `.codewiki/` does not exist:**
- After completing initial analysis, offer: "Would you like me to generate a CodeWiki for this repository? It will persist our understanding for future sessions."
- If yes:

```bash
PYTHONIOENCODING=utf-8 python scripts/generate_wiki.py <clone_path>
```

### Step 5: Knowledge Harvest (End of Session)

When the analysis conversation is wrapping up, review the session for valuable findings:

1. Identify new knowledge about the repository (module behaviors, architecture decisions, data flows)
2. **Filter:** Only include objective facts about the repo. Exclude comparative conclusions or business decisions
3. Propose specific updates to the user, listing target files and content
4. If approved, write updates:

```bash
# Append findings to a module
PYTHONIOENCODING=utf-8 python scripts/update_wiki.py <clone_path> \
    --module <name> --topic "<topic>" --content "<findings>"

# Add discovered relationships
PYTHONIOENCODING=utf-8 python scripts/update_wiki.py <clone_path> \
    --add-relationship "module_a->module_b:depends"

# Mark module as enriched
PYTHONIOENCODING=utf-8 python scripts/update_wiki.py <clone_path> \
    --module <name> --mark-enriched
```
```

**Step 2: Update `references/analysis-guide.md`**

Append a new section at the end:

```markdown
## Wiki-Assisted Analysis

When a `.codewiki/` directory exists for a repository, use it to accelerate analysis:

### Loading Wiki Context

1. **Read the index first:**
   ```
   Read: <clone_path>/.codewiki/index.json
   ```
   This gives you: module list, summaries, relationships, stale markers, architecture patterns.

2. **Load relevant modules on demand:**
   When the user's question maps to a specific module (check `modules` in index.json):
   ```
   Read: <clone_path>/.codewiki/modules/<module_name>.md
   ```

3. **Handle stale modules:**
   If a module has `"stale": true`, inform the user and verify key claims against current source code.

### When Wiki Is Absent

Fall back to standard analysis (sections above). After analysis, offer to generate a wiki:
```
PYTHONIOENCODING=utf-8 python scripts/generate_wiki.py <clone_path>
```

### Wiki Management Commands

```bash
# Generate wiki for a repo
PYTHONIOENCODING=utf-8 python scripts/generate_wiki.py <clone_path>

# Force regenerate (overwrites existing)
PYTHONIOENCODING=utf-8 python scripts/generate_wiki.py <clone_path> --force

# Regenerate modules only (preserves conversation supplements)
PYTHONIOENCODING=utf-8 python scripts/generate_wiki.py <clone_path> --modules-only

# Append knowledge from conversation
PYTHONIOENCODING=utf-8 python scripts/update_wiki.py <clone_path> --module <name> --topic "<topic>" --content "<text>"

# Add architecture relationship
PYTHONIOENCODING=utf-8 python scripts/update_wiki.py <clone_path> --add-relationship "from->to:type"

# Mark module as enriched
PYTHONIOENCODING=utf-8 python scripts/update_wiki.py <clone_path> --module <name> --mark-enriched
```
```

**Step 3: Verify SKILL.md is valid Markdown**

Read the updated file and check for formatting issues.

**Step 4: Commit**

```bash
git add SKILL.md references/analysis-guide.md
git commit -m "docs: update SKILL.md and analysis-guide.md with codewiki workflow"
```

---

## Task 8: Run All Tests — Full Integration Verification

Final sweep to ensure everything works together.

**Files:**
- No new files

**Step 1: Run all tests**

Run: `cd C:\Users\Administrator\.claude\skills\github-repo-scanner && PYTHONIOENCODING=utf-8 python -m pytest tests/ -v`

Expected: All tests PASS across all 3 test files.

**Step 2: End-to-end smoke test**

Run the full flow manually on a fixture:

```bash
cd C:\Users\Administrator\.claude\skills\github-repo-scanner

# 1. Create fixture
PYTHONIOENCODING=utf-8 python tests/fixtures/create_fixtures.py

# 2. Generate wiki
PYTHONIOENCODING=utf-8 python scripts/generate_wiki.py tests/fixtures/mock_monorepo

# 3. Verify output
cat tests/fixtures/mock_monorepo/.codewiki/index.json
cat tests/fixtures/mock_monorepo/.codewiki/overview.md
cat tests/fixtures/mock_monorepo/.codewiki/modules/core.md

# 4. Add a supplement
PYTHONIOENCODING=utf-8 python scripts/update_wiki.py tests/fixtures/mock_monorepo --module core --topic "测试补充" --content "Core 使用依赖注入模式管理生命周期"

# 5. Verify supplement was appended
cat tests/fixtures/mock_monorepo/.codewiki/modules/core.md

# 6. Add relationship
PYTHONIOENCODING=utf-8 python scripts/update_wiki.py tests/fixtures/mock_monorepo --add-relationship "renderer->utils:depends"

# 7. Verify relationship
cat tests/fixtures/mock_monorepo/.codewiki/index.json

# 8. Mark enriched
PYTHONIOENCODING=utf-8 python scripts/update_wiki.py tests/fixtures/mock_monorepo --module core --mark-enriched

# 9. Regenerate with --modules-only (should preserve supplement)
PYTHONIOENCODING=utf-8 python scripts/generate_wiki.py tests/fixtures/mock_monorepo --modules-only

# 10. Verify supplement was preserved
cat tests/fixtures/mock_monorepo/.codewiki/modules/core.md
```

Expected: Each step succeeds. Step 10 shows the "测试补充" content is still present after regeneration.

**Step 3: Clean up fixtures**

Run: `cd C:\Users\Administrator\.claude\skills\github-repo-scanner && PYTHONIOENCODING=utf-8 python -c "from tests.fixtures.create_fixtures import cleanup_fixtures; cleanup_fixtures()"`

**Step 4: Final commit**

```bash
git add -A
git commit -m "test: verify full codewiki integration"
```

---

## Summary

| Task | Description | New/Modified Files | Estimated Steps |
|------|-------------|-------------------|----------------|
| 1 | Test fixtures | `tests/fixtures/create_fixtures.py`, `tests/__init__.py` | 4 |
| 2 | Module detection | `scripts/generate_wiki.py` (partial), `tests/test_generate_wiki.py` | 5 |
| 3 | Static analysis | `scripts/generate_wiki.py` (extend) | 5 |
| 4 | Output generation | `scripts/generate_wiki.py` (complete), tests | 6 |
| 5 | update_wiki.py | `scripts/update_wiki.py`, `tests/test_update_wiki.py` | 5 |
| 6 | Stale marking | `scripts/clone_repo.py` (modify), `tests/test_stale_marking.py` | 6 |
| 7 | Documentation | `SKILL.md`, `references/analysis-guide.md` | 4 |
| 8 | Integration test | — | 4 |

**Total: 8 tasks, ~39 steps**

**Dependencies:** Task 1 → Tasks 2-6 (fixtures needed). Tasks 2-4 are sequential (building generate_wiki.py incrementally). Task 5 depends on Task 4 (needs generate_wiki to create test wikis). Task 6 depends on Task 4 (needs wiki to exist). Task 7 depends on Tasks 4-6 (documents the scripts). Task 8 depends on all.
