#!/usr/bin/env python3
"""Update a .codewiki/ directory with knowledge backflow.

Supports appending conversation supplements, adding architecture relationships,
and marking modules as enriched.

Usage:
    python update_wiki.py <repo_path> --module <name> --topic <topic> --content <text>
    python update_wiki.py <repo_path> --add-relationship "from->to:type"
    python update_wiki.py <repo_path> --module <name> --mark-enriched
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# The section heading used for conversation supplements in generated .md files.
# Must match what generate_wiki.py produces.
# ---------------------------------------------------------------------------

L2L3_HEADING = "## Conversation Notes (L2/L3)"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_index(repo_path):
    """Load and return the parsed .codewiki/index.json.

    Parameters
    ----------
    repo_path : str or Path
        Root of the repository.

    Returns
    -------
    dict
        Parsed index data.

    Raises
    ------
    FileNotFoundError
        If index.json does not exist.
    json.JSONDecodeError
        If the file is not valid JSON.
    """
    index_path = Path(repo_path) / ".codewiki" / "index.json"
    if not index_path.exists():
        raise FileNotFoundError(f"Index not found: {index_path}")
    return json.loads(index_path.read_text(encoding="utf-8"))


def _save_index(repo_path, data):
    """Write *data* to .codewiki/index.json.

    Parameters
    ----------
    repo_path : str or Path
        Root of the repository.
    data : dict
        Index data to serialise.
    """
    index_path = Path(repo_path) / ".codewiki" / "index.json"
    index_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def append_supplement(repo_path, module_name, topic, content):
    """Append a date-stamped conversation supplement to a module's .md file.

    Parameters
    ----------
    repo_path : str or Path
        Root of the repository.
    module_name : str
        Name of the module (must exist in index.json).
    topic : str
        Short topic/title for the supplement entry.
    content : str
        Body text of the supplement.

    Raises
    ------
    FileNotFoundError
        If the index or module .md file does not exist.
    KeyError
        If *module_name* is not present in the index.
    """
    repo_path = Path(repo_path)
    index = _load_index(repo_path)

    if module_name not in index.get("modules", {}):
        raise KeyError(f"Module '{module_name}' not found in index.json")

    md_file = repo_path / ".codewiki" / index["modules"][module_name]["file"]
    if not md_file.exists():
        raise FileNotFoundError(f"Module markdown not found: {md_file}")

    md_text = md_file.read_text(encoding="utf-8")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = f"\n### {today} -- {topic}\n\n{content}\n"

    # Find the L2/L3 heading and append after it (and any existing content)
    if L2L3_HEADING in md_text:
        # Append at the very end of the file (everything after the heading
        # belongs to that section since it is the last section).
        if md_text.endswith("\n"):
            md_text = md_text + entry
        else:
            md_text = md_text + "\n" + entry
    else:
        # Heading not found -- add it and the entry at the end
        md_text = md_text.rstrip("\n") + "\n\n" + L2L3_HEADING + "\n" + entry

    md_file.write_text(md_text, encoding="utf-8")

    # Update last_updated in index
    index["modules"][module_name]["last_updated"] = datetime.now(
        timezone.utc
    ).isoformat()
    _save_index(repo_path, index)


def add_relationship(repo_path, from_module, to_module, rel_type="depends"):
    """Add an architecture relationship to index.json if not a duplicate.

    Parameters
    ----------
    repo_path : str or Path
        Root of the repository.
    from_module : str
        Source module name.
    to_module : str
        Target module name.
    rel_type : str, optional
        Relationship type (default ``"depends"``).
    """
    repo_path = Path(repo_path)
    index = _load_index(repo_path)

    rels = index.setdefault("architecture", {}).setdefault(
        "key_relationships", []
    )

    # Check for duplicates
    for r in rels:
        if (
            r.get("from") == from_module
            and r.get("to") == to_module
            and r.get("type") == rel_type
        ):
            return  # already exists

    rels.append({"from": from_module, "to": to_module, "type": rel_type})
    _save_index(repo_path, index)


def mark_enriched(repo_path, module_name):
    """Mark a module's source as ``"enriched"`` in index.json.

    Parameters
    ----------
    repo_path : str or Path
        Root of the repository.
    module_name : str
        Name of the module.

    Raises
    ------
    KeyError
        If *module_name* is not present in the index.
    """
    repo_path = Path(repo_path)
    index = _load_index(repo_path)

    if module_name not in index.get("modules", {}):
        raise KeyError(f"Module '{module_name}' not found in index.json")

    index["modules"][module_name]["source"] = "enriched"
    index["modules"][module_name]["last_updated"] = datetime.now(
        timezone.utc
    ).isoformat()
    _save_index(repo_path, index)


def parse_relationship_string(rel_str):
    """Parse a relationship string of the form ``"from->to:type"``.

    If ``:type`` is omitted the default type is ``"depends"``.

    Parameters
    ----------
    rel_str : str
        e.g. ``"utils->core:depends"`` or ``"utils->core"``.

    Returns
    -------
    tuple of (str, str, str)
        ``(from_module, to_module, rel_type)``

    Raises
    ------
    ValueError
        If the string cannot be parsed.
    """
    m = re.match(r"^([^->]+)->([^:]+)(?::(.+))?$", rel_str)
    if not m:
        raise ValueError(
            f"Cannot parse relationship string: '{rel_str}'. "
            "Expected format: 'from->to' or 'from->to:type'"
        )
    from_mod = m.group(1).strip()
    to_mod = m.group(2).strip()
    rel_type = m.group(3).strip() if m.group(3) else "depends"
    return (from_mod, to_mod, rel_type)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Update a .codewiki/ knowledge base with conversation insights."
    )
    parser.add_argument("repo_path", type=str, help="Path to the cloned repo")
    parser.add_argument("--module", type=str, help="Module name")
    parser.add_argument("--topic", type=str, help="Supplement topic (with --module)")
    parser.add_argument(
        "--content", type=str, help="Supplement content (with --module --topic)"
    )
    parser.add_argument(
        "--add-relationship",
        type=str,
        dest="add_relationship",
        help='Add relationship, e.g. "from->to:type"',
    )
    parser.add_argument(
        "--mark-enriched",
        action="store_true",
        dest="mark_enriched",
        help="Mark module as enriched (with --module)",
    )
    args = parser.parse_args()

    repo = Path(args.repo_path).resolve()
    if not repo.is_dir():
        print(f"Error: {repo} is not a directory.", file=sys.stderr)
        sys.exit(1)

    # --- Add relationship ---------------------------------------------------
    if args.add_relationship:
        from_mod, to_mod, rel_type = parse_relationship_string(
            args.add_relationship
        )
        add_relationship(repo, from_mod, to_mod, rel_type)
        print(f"Added relationship: {from_mod} -> {to_mod} ({rel_type})")
        sys.exit(0)

    # --- Module-level operations require --module ---------------------------
    if not args.module:
        parser.error("One of --module or --add-relationship is required.")

    # --- Mark enriched ------------------------------------------------------
    if args.mark_enriched:
        mark_enriched(repo, args.module)
        print(f"Marked module '{args.module}' as enriched.")
        sys.exit(0)

    # --- Append supplement --------------------------------------------------
    if args.topic and args.content:
        append_supplement(repo, args.module, args.topic, args.content)
        print(f"Appended supplement to '{args.module}': {args.topic}")
        sys.exit(0)

    parser.error(
        "Provide --topic and --content (supplement), --mark-enriched, "
        "or --add-relationship."
    )


if __name__ == "__main__":
    main()
