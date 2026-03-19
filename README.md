# GitHub Repo Scanner

Scan, search, clone, and analyze remote GitHub repositories as if they were local codebases. This skill keeps a local cache of repositories, can generate a persistent `.codewiki/` knowledge layer, and includes helpers for repo discovery, overview generation, and wiki maintenance.

## What This Skill Does

- Search GitHub repositories by keyword, language, and sort order.
- Clone a repository into a configurable local cache.
- Reuse cached repositories and pull the latest changes automatically.
- Generate a structural overview of a cloned repository.
- Create a `.codewiki/` knowledge base for future analysis sessions.
- Update wiki modules with conversation findings and architecture relationships.
- Track stale wiki modules when upstream code changes.

## Repository Layout

```text
.github-repo-scanner/
  SKILL.md
  docs/
  references/
  scripts/
  tests/
```

Key paths:

- `SKILL.md`: operational instructions for using the skill.
- `scripts/clone_repo.py`: clone, sync, and cache management.
- `scripts/search_repos.py`: GitHub repository search via `gh` CLI.
- `scripts/repo_overview.py`: high-level repository summary.
- `scripts/generate_wiki.py`: generate `.codewiki/` from a cloned repo.
- `scripts/update_wiki.py`: append wiki notes and relationships.
- `references/analysis-guide.md`: deeper analysis patterns for repo review.
- `references/config-example.json`: example cache config.
- `references/metadata-example.json`: example repo metadata file.
- `tests/`: coverage for wiki generation and stale-marking behavior.

## Prerequisites

- Python 3.9+
- `git`
- `gh` CLI for repository search features in `search_repos.py`

On Windows, use `PYTHONIOENCODING=utf-8` when invoking the scripts to avoid console encoding problems.

## Initial Setup

Configure the local cache directory used for cloned repositories:

```powershell
$env:PYTHONIOENCODING='utf-8'
python scripts/clone_repo.py --config "D:\git"
```

Show the active configuration:

```powershell
$env:PYTHONIOENCODING='utf-8'
python scripts/clone_repo.py --show-config
```

If no config is written, the default cache location is:

```text
%USERPROFILE%\.github-repo-scanner\repos
```

## Typical Workflow

### 1. Search for a Repository

```powershell
$env:PYTHONIOENCODING='utf-8'
python scripts/search_repos.py "vector database" --language python --sort stars --limit 10
```

Show detailed metadata for a single repository:

```powershell
$env:PYTHONIOENCODING='utf-8'
python scripts/search_repos.py "placeholder" --info owner/repo
```

### 2. Clone or Sync a Repository

```powershell
$env:PYTHONIOENCODING='utf-8'
python scripts/clone_repo.py owner/repo --depth 1
```

Notes:

- Accepts either `owner/repo` or a GitHub URL.
- If the repo is already cached, the script runs `git pull` and refreshes access metadata.
- The final output line includes `CLONE_PATH=<path>`, which should be used for later analysis steps.

### 3. Generate an Overview

```powershell
$env:PYTHONIOENCODING='utf-8'
python scripts/repo_overview.py <clone_path> --show-tree
```

This reports repository structure, major files, language mix, and other quick-orientation data.

### 4. Generate a CodeWiki

```powershell
$env:PYTHONIOENCODING='utf-8'
python scripts/generate_wiki.py <clone_path>
```

Useful options:

- `--force`: overwrite an existing `.codewiki/`
- `--modules-only`: regenerate module markdown while preserving conversation notes

Generated artifacts typically include:

- `.codewiki/index.json`
- `.codewiki/overview.md`
- `.codewiki/modules/*.md`

### 5. Feed Findings Back into the Wiki

Append new repository knowledge to a module:

```powershell
$env:PYTHONIOENCODING='utf-8'
python scripts/update_wiki.py <clone_path> --module core --topic "Auth flow" --content "Requests enter through the API layer and are normalized before token validation."
```

Add a relationship:

```powershell
$env:PYTHONIOENCODING='utf-8'
python scripts/update_wiki.py <clone_path> --add-relationship "api->core:depends"
```

Mark a module as enriched:

```powershell
$env:PYTHONIOENCODING='utf-8'
python scripts/update_wiki.py <clone_path> --module core --mark-enriched
```

## Cache Management

List cached repositories:

```powershell
$env:PYTHONIOENCODING='utf-8'
python scripts/clone_repo.py --list
```

Show stale repositories:

```powershell
$env:PYTHONIOENCODING='utf-8'
python scripts/clone_repo.py --stale --days 30
```

Pull latest changes for every cached repository:

```powershell
$env:PYTHONIOENCODING='utf-8'
python scripts/clone_repo.py --pull-all
```

Remove repositories not used recently:

```powershell
$env:PYTHONIOENCODING='utf-8'
python scripts/clone_repo.py --cleanup --days 60
```

Remove a specific cached repository:

```powershell
$env:PYTHONIOENCODING='utf-8'
python scripts/clone_repo.py --remove owner/repo
```

## CodeWiki Behavior

The wiki system is designed to persist repository understanding across sessions.

- `generate_wiki.py` builds module summaries, entry points, exports, imports, and architecture relationships.
- `update_wiki.py` appends conversation-derived facts into the `Conversation Notes (L2/L3)` section of module markdown.
- `clone_repo.py` marks wiki modules as stale when pulled upstream changes affect their mapped paths.
- `.codewiki/` is added to `.git/info/exclude` so the generated knowledge layer does not get committed accidentally.

## Tests

Run the test suite from this folder:

```powershell
pytest
```

Targeted examples:

```powershell
pytest tests/test_generate_wiki.py
pytest tests/test_update_wiki.py
pytest tests/test_stale_marking.py
```

## References

- `references/analysis-guide.md` for analysis patterns and review heuristics
- `references/config-example.json` for cache configuration format
- `references/metadata-example.json` for repository metadata structure
- `docs/plans/` for design and implementation notes around CodeWiki support

## Notes

- This skill is best used when the repository is not already cloned locally.
- If the user only needs high-level repository metadata, `gh repo view owner/repo` is often faster than cloning.
- For contribution workflows or pull request work, a normal user-managed clone is usually more appropriate than the cache-oriented flow here.
