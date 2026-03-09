"""Tests for stale module marking in scripts/clone_repo.py."""

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
from fixtures.create_fixtures import create_monorepo

# Make scripts/ importable
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from generate_wiki import generate_wiki
from clone_repo import mark_stale_modules


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
# TestMarkStaleModules
# ===================================================================

class TestMarkStaleModules(unittest.TestCase):
    """Tests for mark_stale_modules() in clone_repo.py."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.repo_dir = Path(self.tmpdir) / "mono"
        # Create monorepo fixture and generate wiki
        create_monorepo(self.repo_dir)
        generate_wiki(self.repo_dir, force=True)

    def tearDown(self):
        _force_rmtree(self.tmpdir)

    def _load_index(self):
        """Load and return the .codewiki/index.json data."""
        index_path = self.repo_dir / ".codewiki" / "index.json"
        return json.loads(index_path.read_text(encoding="utf-8"))

    # ---------------------------------------------------------------
    def test_mark_stale_flags_affected_module(self):
        """Changed files in packages/core/ mark core as stale, not renderer."""
        changed = ["packages/core/src/app.js"]
        count = mark_stale_modules(str(self.repo_dir), changed)

        self.assertEqual(count, 1)

        data = self._load_index()
        self.assertTrue(data["modules"]["core"]["stale"])
        self.assertFalse(data["modules"]["renderer"]["stale"])
        self.assertFalse(data["modules"]["utils"]["stale"])

    # ---------------------------------------------------------------
    def test_mark_stale_updates_commit_hash(self):
        """Providing new_commit updates code_commit in index.json."""
        changed = ["packages/core/src/app.js"]
        mark_stale_modules(str(self.repo_dir), changed, new_commit="abc1234")

        data = self._load_index()
        self.assertEqual(data["code_commit"], "abc1234")

    # ---------------------------------------------------------------
    def test_no_wiki_dir_is_noop(self):
        """If .codewiki/ does not exist, return 0 and do nothing."""
        # Remove the .codewiki directory
        wiki_dir = self.repo_dir / ".codewiki"
        _force_rmtree(str(wiki_dir))

        changed = ["packages/core/src/app.js"]
        count = mark_stale_modules(str(self.repo_dir), changed)
        self.assertEqual(count, 0)

    # ---------------------------------------------------------------
    def test_unrelated_file_change_no_stale(self):
        """Changes to .github/workflows/ci.yml and README.md mark no modules stale."""
        changed = [".github/workflows/ci.yml", "README.md"]
        count = mark_stale_modules(str(self.repo_dir), changed)

        self.assertEqual(count, 0)

        data = self._load_index()
        for mod_name, mod_info in data["modules"].items():
            self.assertFalse(
                mod_info["stale"],
                f"Module '{mod_name}' should not be stale for unrelated file changes"
            )


if __name__ == "__main__":
    unittest.main()
