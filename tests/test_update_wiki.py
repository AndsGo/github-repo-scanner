"""Tests for scripts/update_wiki.py -- codewiki knowledge backflow."""

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
from update_wiki import (
    append_supplement,
    add_relationship,
    mark_enriched,
    parse_relationship_string,
    _load_index,
)


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
# TestAppendSupplement
# ===================================================================

class TestAppendSupplement(unittest.TestCase):
    """Tests for appending conversation supplements to module .md files."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.repo = create_monorepo(self.tmpdir / "mono")
        generate_wiki(self.repo, force=True)

    def tearDown(self):
        _force_rmtree(self.tmpdir)

    # ---------------------------------------------------------------
    def test_append_supplement_to_module(self):
        """Append to core -> .md contains date heading, topic, content."""
        append_supplement(
            self.repo, "core", "Architecture insight",
            "The core module uses a factory pattern for createApp."
        )

        md = (self.repo / ".codewiki" / "modules" / "core.md").read_text(
            encoding="utf-8"
        )
        # Should contain the topic
        self.assertIn("Architecture insight", md)
        # Should contain the content
        self.assertIn("factory pattern for createApp", md)
        # Should contain a date-stamped heading (### YYYY-MM-DD -- <topic>)
        self.assertRegex(md, r"### \d{4}-\d{2}-\d{2} -- Architecture insight")

    # ---------------------------------------------------------------
    def test_append_preserves_existing_content(self):
        """Append -> original L1 sections still present."""
        append_supplement(
            self.repo, "core", "Some topic", "Some content."
        )

        md = (self.repo / ".codewiki" / "modules" / "core.md").read_text(
            encoding="utf-8"
        )
        # All original sections should still be present
        self.assertIn("# core", md)
        self.assertIn("## Entry Points", md)
        self.assertIn("## Key Files", md)
        self.assertIn("## Exports (API)", md)
        self.assertIn("## Conversation Notes (L2/L3)", md)

    # ---------------------------------------------------------------
    def test_multiple_supplements_append_in_order(self):
        """Append twice -> first appears before second."""
        append_supplement(
            self.repo, "core", "First topic", "First content."
        )
        append_supplement(
            self.repo, "core", "Second topic", "Second content."
        )

        md = (self.repo / ".codewiki" / "modules" / "core.md").read_text(
            encoding="utf-8"
        )
        pos_first = md.index("First topic")
        pos_second = md.index("Second topic")
        self.assertLess(
            pos_first, pos_second,
            "First supplement should appear before second"
        )


# ===================================================================
# TestAddRelationship
# ===================================================================

class TestAddRelationship(unittest.TestCase):
    """Tests for adding architecture relationships to index.json."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.repo = create_monorepo(self.tmpdir / "mono")
        generate_wiki(self.repo, force=True)

    def tearDown(self):
        _force_rmtree(self.tmpdir)

    # ---------------------------------------------------------------
    def test_add_relationship(self):
        """Add utils->core -> found in index.json relationships."""
        add_relationship(self.repo, "utils", "core", "depends")

        index = _load_index(self.repo)
        rels = index["architecture"]["key_relationships"]
        matching = [
            r for r in rels
            if r["from"] == "utils" and r["to"] == "core" and r["type"] == "depends"
        ]
        self.assertEqual(len(matching), 1, "Should find exactly one matching relationship")

    # ---------------------------------------------------------------
    def test_no_duplicate_relationships(self):
        """Add same relationship twice -> only one in list."""
        add_relationship(self.repo, "utils", "core", "depends")
        add_relationship(self.repo, "utils", "core", "depends")

        index = _load_index(self.repo)
        rels = index["architecture"]["key_relationships"]
        matching = [
            r for r in rels
            if r["from"] == "utils" and r["to"] == "core" and r["type"] == "depends"
        ]
        self.assertEqual(len(matching), 1, "Should not have duplicate relationships")


# ===================================================================
# TestMarkEnriched
# ===================================================================

class TestMarkEnriched(unittest.TestCase):
    """Tests for marking modules as enriched."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.repo = create_monorepo(self.tmpdir / "mono")
        generate_wiki(self.repo, force=True)

    def tearDown(self):
        _force_rmtree(self.tmpdir)

    # ---------------------------------------------------------------
    def test_mark_enriched_updates_source(self):
        """Mark core -> source becomes 'enriched'."""
        # Before: source should be "auto"
        index = _load_index(self.repo)
        self.assertEqual(index["modules"]["core"]["source"], "auto")

        mark_enriched(self.repo, "core")

        index = _load_index(self.repo)
        self.assertEqual(index["modules"]["core"]["source"], "enriched")


# ===================================================================
# TestParseRelationshipString
# ===================================================================

class TestParseRelationshipString(unittest.TestCase):
    """Tests for parsing relationship strings."""

    def test_full_format(self):
        """Parse 'from->to:type' returns correct tuple."""
        result = parse_relationship_string("utils->core:depends")
        self.assertEqual(result, ("utils", "core", "depends"))

    def test_no_type_defaults_to_depends(self):
        """Parse 'from->to' (no type) defaults to 'depends'."""
        result = parse_relationship_string("utils->core")
        self.assertEqual(result, ("utils", "core", "depends"))

    def test_custom_type(self):
        """Parse 'a->b:extends' returns custom type."""
        result = parse_relationship_string("a->b:extends")
        self.assertEqual(result, ("a", "b", "extends"))

    def test_invalid_raises(self):
        """Invalid string raises ValueError."""
        with self.assertRaises(ValueError):
            parse_relationship_string("not-a-valid-string")


if __name__ == "__main__":
    unittest.main()
