"""Tests for scripts/generate_wiki.py — codewiki generation."""

import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path

# ---------------------------------------------------------------------------
# Import helpers
# ---------------------------------------------------------------------------

# Make fixtures importable
sys.path.insert(0, str(Path(__file__).parent))
from fixtures.create_fixtures import create_monorepo, create_single_repo, create_flat_repo

# Make scripts/ importable
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from generate_wiki import detect_modules, analyze_module, generate_wiki


# ---------------------------------------------------------------------------
# Windows-safe cleanup
# ---------------------------------------------------------------------------

def _force_rmtree(path):
    """Remove a directory tree, handling read-only files on Windows."""
    def _on_error(func, fpath, exc_info):
        os.chmod(fpath, stat.S_IWRITE)
        func(fpath)
    if os.path.exists(path):
        shutil.rmtree(path, onerror=_on_error)


# ===================================================================
# TestDetectModules
# ===================================================================

class TestDetectModules(unittest.TestCase):
    """Tests for module boundary detection logic."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        _force_rmtree(self.tmpdir)

    # ---------------------------------------------------------------
    def test_monorepo_detects_packages(self):
        """Monorepo fixture detects {core, renderer, utils} under packages/."""
        root = create_monorepo(self.tmpdir / "mono")
        modules = detect_modules(root)
        names = {m["name"] for m in modules}
        self.assertEqual(names, {"core", "renderer", "utils"})
        for m in modules:
            self.assertTrue(m["path"].startswith("packages/"),
                            f"{m['name']} path should start with packages/")

    # ---------------------------------------------------------------
    def test_single_repo_detects_src_dirs(self):
        """Single-repo fixture detects {auth, api, models} under src/."""
        root = create_single_repo(self.tmpdir / "single")
        modules = detect_modules(root)
        names = {m["name"] for m in modules}
        self.assertEqual(names, {"auth", "api", "models"})
        for m in modules:
            self.assertTrue(m["path"].startswith("src/"),
                            f"{m['name']} path should start with src/")

    # ---------------------------------------------------------------
    def test_flat_repo_fallback(self):
        """Flat-repo fixture detects helpers (scripts/ has only .sh, no code)."""
        root = create_flat_repo(self.tmpdir / "flat")
        modules = detect_modules(root)
        names = {m["name"] for m in modules}
        self.assertIn("helpers", names)
        # scripts/ contains only .sh files — not a code module
        self.assertNotIn("scripts", names)


# ===================================================================
# TestAnalyzeModule
# ===================================================================

class TestAnalyzeModule(unittest.TestCase):
    """Tests for static analysis of individual modules."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        _force_rmtree(self.tmpdir)

    # ---------------------------------------------------------------
    def test_js_monorepo_entry_and_exports(self):
        """Monorepo core module finds src/index.js as entry, has exports."""
        root = create_monorepo(self.tmpdir / "mono")
        modules = detect_modules(root)
        core = [m for m in modules if m["name"] == "core"][0]
        analysis = analyze_module(root, core)

        # entry file
        self.assertTrue(
            any("index.js" in ef for ef in analysis["entry_files"]),
            f"Expected index.js in entry_files, got {analysis['entry_files']}"
        )

        # exports
        self.assertTrue(len(analysis["exports"]) > 0,
                        "Expected at least one export")

    # ---------------------------------------------------------------
    def test_python_imports_detected(self):
        """Single-repo auth module finds __init__.py as entry, has imports."""
        root = create_single_repo(self.tmpdir / "single")
        modules = detect_modules(root)
        auth = [m for m in modules if m["name"] == "auth"][0]
        analysis = analyze_module(root, auth)

        # entry file
        self.assertTrue(
            any("__init__.py" in ef for ef in analysis["entry_files"]),
            f"Expected __init__.py in entry_files, got {analysis['entry_files']}"
        )

        # imports
        self.assertTrue(len(analysis["internal_imports"]) > 0,
                        "Expected at least one import")

    # ---------------------------------------------------------------
    def test_key_files_sorted_by_size(self):
        """Monorepo core key_files list is sorted by size descending."""
        root = create_monorepo(self.tmpdir / "mono")
        modules = detect_modules(root)
        core = [m for m in modules if m["name"] == "core"][0]
        analysis = analyze_module(root, core)

        sizes = [s for _, s in analysis["key_files"]]
        self.assertEqual(sizes, sorted(sizes, reverse=True),
                         "key_files should be sorted by size descending")


# ===================================================================
# TestGenerateWiki
# ===================================================================

class TestGenerateWiki(unittest.TestCase):
    """Tests for the full wiki generation pipeline."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        _force_rmtree(self.tmpdir)

    # ---------------------------------------------------------------
    def test_generates_codewiki_dir(self):
        """Monorepo generates .codewiki/ with index.json, overview.md, modules/."""
        root = create_monorepo(self.tmpdir / "mono")
        result = generate_wiki(root, force=True)
        self.assertTrue(result)

        wiki = root / ".codewiki"
        self.assertTrue(wiki.is_dir())
        self.assertTrue((wiki / "index.json").exists())
        self.assertTrue((wiki / "overview.md").exists())
        self.assertTrue((wiki / "modules").is_dir())

    # ---------------------------------------------------------------
    def test_index_json_has_correct_structure(self):
        """Monorepo index.json has version=1, modules dict with core, stale=false, source=auto."""
        root = create_monorepo(self.tmpdir / "mono")
        generate_wiki(root, force=True)

        data = json.loads(
            (root / ".codewiki" / "index.json").read_text(encoding="utf-8")
        )
        self.assertEqual(data["version"], 1)
        self.assertIn("modules", data)
        self.assertIn("core", data["modules"])
        self.assertFalse(data["modules"]["core"]["stale"])
        self.assertEqual(data["modules"]["core"]["source"], "auto")

    # ---------------------------------------------------------------
    def test_module_md_has_template_sections(self):
        """Monorepo core.md contains all 5 section headings."""
        root = create_monorepo(self.tmpdir / "mono")
        generate_wiki(root, force=True)

        md = (root / ".codewiki" / "modules" / "core.md").read_text(encoding="utf-8")
        self.assertIn("# core", md)
        self.assertIn("## Entry Points", md)
        self.assertIn("## Key Files", md)
        self.assertIn("## Exports (API)", md)
        self.assertIn("## Conversation Notes (L2/L3)", md)

    # ---------------------------------------------------------------
    def test_force_overwrites_existing(self):
        """Generate -> tamper -> generate with force -> restored."""
        root = create_monorepo(self.tmpdir / "mono")
        generate_wiki(root, force=True)

        # Tamper
        idx = root / ".codewiki" / "index.json"
        idx.write_text('{"tampered": true}', encoding="utf-8")

        # Regenerate with force
        result = generate_wiki(root, force=True)
        self.assertTrue(result)

        data = json.loads(idx.read_text(encoding="utf-8"))
        self.assertEqual(data["version"], 1)
        self.assertNotIn("tampered", data)

    # ---------------------------------------------------------------
    def test_skips_if_exists_without_force(self):
        """Generate twice without force -> second returns False."""
        root = create_monorepo(self.tmpdir / "mono")
        result1 = generate_wiki(root, force=True)
        self.assertTrue(result1)

        result2 = generate_wiki(root, force=False)
        self.assertFalse(result2)

    # ---------------------------------------------------------------
    def test_single_repo_generates_wiki(self):
        """Single repo generates auth.md and api.md."""
        root = create_single_repo(self.tmpdir / "single")
        generate_wiki(root, force=True)

        modules_dir = root / ".codewiki" / "modules"
        self.assertTrue((modules_dir / "auth.md").exists())
        self.assertTrue((modules_dir / "api.md").exists())

    # ---------------------------------------------------------------
    def test_gitexclude_is_set(self):
        """Monorepo .git/info/exclude contains '.codewiki'."""
        root = create_monorepo(self.tmpdir / "mono")
        generate_wiki(root, force=True)

        exclude = root / ".git" / "info" / "exclude"
        self.assertTrue(exclude.exists(), ".git/info/exclude should exist")
        content = exclude.read_text(encoding="utf-8", errors="replace")
        self.assertIn(".codewiki", content)


if __name__ == "__main__":
    unittest.main()
