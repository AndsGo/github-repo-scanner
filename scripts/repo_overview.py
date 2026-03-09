#!/usr/bin/env python3
"""Generate a structural overview of a cloned repository.

Analyzes directory structure, file types, key files, and provides
a summary useful for understanding the codebase before deep analysis.

Usage:
    python repo_overview.py <repo_path> [--depth <n>] [--show-tree]

Examples:
    python repo_overview.py /path/to/cloned/repo
    python repo_overview.py /path/to/repo --depth 3 --show-tree
"""

import argparse
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Directories to skip during analysis
SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    ".tox", ".mypy_cache", ".pytest_cache", "dist", "build",
    ".next", ".nuxt", "target", "vendor", ".gradle", ".idea",
    ".vscode", ".vs", "bin", "obj", "coverage", ".cache",
    ".eggs", "*.egg-info",
}

# Key files that indicate project structure
KEY_FILES = {
    # Package/Build
    "package.json", "Cargo.toml", "go.mod", "pyproject.toml", "setup.py",
    "setup.cfg", "pom.xml", "build.gradle", "Makefile", "CMakeLists.txt",
    "Gemfile", "composer.json", "mix.exs", "pubspec.yaml",
    # Config
    "tsconfig.json", "webpack.config.js", "vite.config.ts", "vite.config.js",
    ".eslintrc.json", ".prettierrc", "tailwind.config.js",
    "docker-compose.yml", "Dockerfile", ".env.example",
    # Docs
    "README.md", "CHANGELOG.md", "CONTRIBUTING.md", "LICENSE",
    # CI/CD
    ".github/workflows", ".gitlab-ci.yml", ".travis.yml", "Jenkinsfile",
}

# Extension to language mapping
EXT_LANG = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
    ".tsx": "TypeScript (React)", ".jsx": "JavaScript (React)",
    ".rs": "Rust", ".go": "Go", ".java": "Java", ".kt": "Kotlin",
    ".rb": "Ruby", ".php": "PHP", ".cs": "C#", ".cpp": "C++",
    ".c": "C", ".h": "C/C++ Header", ".swift": "Swift",
    ".dart": "Dart", ".ex": "Elixir", ".exs": "Elixir",
    ".vue": "Vue", ".svelte": "Svelte", ".html": "HTML",
    ".css": "CSS", ".scss": "SCSS", ".less": "LESS",
    ".sql": "SQL", ".sh": "Shell", ".bash": "Shell",
    ".yml": "YAML", ".yaml": "YAML", ".toml": "TOML",
    ".json": "JSON", ".xml": "XML", ".md": "Markdown",
    ".proto": "Protocol Buffers", ".graphql": "GraphQL",
    ".tf": "Terraform", ".lua": "Lua", ".r": "R",
    ".scala": "Scala", ".zig": "Zig", ".nim": "Nim",
}


def should_skip(dirpath, dirname):
    """Check if a directory should be skipped."""
    return dirname in SKIP_DIRS or dirname.startswith(".")


def scan_repo(repo_path, max_depth=4):
    """Scan the repo and collect statistics."""
    stats = {
        "total_files": 0,
        "total_dirs": 0,
        "extensions": Counter(),
        "languages": Counter(),
        "key_files_found": [],
        "top_level_dirs": [],
        "largest_files": [],
        "file_lines": Counter(),
    }

    repo = Path(repo_path)
    if not repo.exists():
        print(f"ERROR: Path does not exist: {repo_path}", file=sys.stderr)
        sys.exit(1)

    # Top-level directory listing
    for item in sorted(repo.iterdir()):
        if item.is_dir() and item.name not in SKIP_DIRS and not item.name.startswith("."):
            stats["top_level_dirs"].append(item.name + "/")
        elif item.is_file():
            stats["top_level_dirs"].append(item.name)

    # Walk the tree
    for dirpath, dirnames, filenames in os.walk(repo_path):
        # Filter out skipped dirs
        dirnames[:] = [d for d in dirnames if not should_skip(dirpath, d)]

        rel_dir = os.path.relpath(dirpath, repo_path)
        depth = 0 if rel_dir == "." else rel_dir.count(os.sep) + 1
        if depth > max_depth:
            dirnames.clear()
            continue

        stats["total_dirs"] += len(dirnames)

        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(filepath, repo_path)
            stats["total_files"] += 1

            # Extension stats
            ext = Path(filename).suffix.lower()
            if ext:
                stats["extensions"][ext] += 1
                lang = EXT_LANG.get(ext)
                if lang:
                    stats["languages"][lang] += 1

            # Key files detection
            if filename in KEY_FILES:
                stats["key_files_found"].append(rel_path)
            # Check for workflow directories
            if ".github" in rel_path and filename.endswith((".yml", ".yaml")):
                stats["key_files_found"].append(rel_path)

            # Track file sizes
            try:
                size = os.path.getsize(filepath)
                stats["largest_files"].append((rel_path, size))
            except OSError:
                pass

    # Sort largest files
    stats["largest_files"].sort(key=lambda x: x[1], reverse=True)
    stats["largest_files"] = stats["largest_files"][:10]

    return stats


def generate_tree(repo_path, max_depth=2, prefix=""):
    """Generate a directory tree string."""
    repo = Path(repo_path)
    lines = [repo.name + "/"]

    def _tree(path, prefix, depth):
        if depth > max_depth:
            return
        entries = sorted(path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        entries = [e for e in entries if not should_skip(str(path), e.name)]
        for i, entry in enumerate(entries):
            is_last = i == len(entries) - 1
            connector = "`-- " if is_last else "|-- "
            if entry.is_dir():
                lines.append(f"{prefix}{connector}{entry.name}/")
                extension = "    " if is_last else "|   "
                _tree(entry, prefix + extension, depth + 1)
            else:
                lines.append(f"{prefix}{connector}{entry.name}")

    _tree(repo, "", 0)
    return "\n".join(lines)


def format_size(size_bytes):
    """Format byte size to human readable."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def print_overview(repo_path, stats, show_tree=False):
    """Print formatted overview."""
    repo_name = Path(repo_path).name

    print(f"\n{'='*60}")
    print(f"  Repository Overview: {repo_name}")
    print(f"{'='*60}\n")

    # Summary
    print(f"  Files: {stats['total_files']}  |  Directories: {stats['total_dirs']}")
    print()

    # Languages
    if stats["languages"]:
        print("  Languages:")
        total_code = sum(stats["languages"].values())
        for lang, count in stats["languages"].most_common(10):
            pct = (count / total_code) * 100
            bar = "#" * int(pct / 3)
            print(f"    {lang:<25} {count:>5} files ({pct:>5.1f}%) {bar}")
        print()

    # Top-level structure
    print("  Top-level structure:")
    for item in stats["top_level_dirs"]:
        print(f"    {item}")
    print()

    # Key files
    if stats["key_files_found"]:
        print("  Key files detected:")
        for f in sorted(stats["key_files_found"]):
            print(f"    {f}")
        print()

    # Largest files
    if stats["largest_files"]:
        print("  Largest files:")
        for path, size in stats["largest_files"][:5]:
            print(f"    {format_size(size):>10}  {path}")
        print()

    # File types
    if stats["extensions"]:
        print("  File extensions (top 15):")
        for ext, count in stats["extensions"].most_common(15):
            print(f"    {ext:<10} {count:>5} files")
        print()

    # Tree
    if show_tree:
        print("  Directory tree:")
        tree = generate_tree(repo_path, max_depth=2)
        for line in tree.split("\n"):
            print(f"    {line}")
        print()

    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Generate repository overview")
    parser.add_argument("repo_path", help="Path to cloned repository")
    parser.add_argument("--depth", "-d", type=int, default=4,
                        help="Max scan depth (default: 4)")
    parser.add_argument("--show-tree", "-t", action="store_true",
                        help="Show directory tree")

    args = parser.parse_args()

    stats = scan_repo(args.repo_path, max_depth=args.depth)
    print_overview(args.repo_path, stats, show_tree=args.show_tree)


if __name__ == "__main__":
    main()
