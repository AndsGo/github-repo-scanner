#!/usr/bin/env python3
"""Manage a local cache of GitHub repositories with configurable workspace.

Features:
- Configurable workspace directory (e.g. D:\\git)
- Tracks last access time per repo for usage-based retention
- Auto-pulls latest changes before each use
- Time-based cleanup of stale repos

Usage:
    python clone_repo.py <repo> [--depth <n>] [--branch <branch>]
    python clone_repo.py --config <workspace_path>
    python clone_repo.py --list
    python clone_repo.py --pull <repo>
    python clone_repo.py --pull-all
    python clone_repo.py --stale [--days <n>]
    python clone_repo.py --remove <repo>
    python clone_repo.py --cleanup --days <n>

Examples:
    python clone_repo.py --config "D:\\git"
    python clone_repo.py facebook/react
    python clone_repo.py facebook/react --branch main
    python clone_repo.py --list
    python clone_repo.py --stale --days 30
    python clone_repo.py --cleanup --days 60
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".github-repo-scanner")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
METADATA_FILE = ".repos_metadata.json"


# ── Config ──────────────────────────────────────────────────

def load_config():
    """Load global config. Returns dict with 'workspace' key."""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_config(config):
    """Save global config."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def get_workspace():
    """Get workspace path from config, or use default."""
    config = load_config()
    ws = config.get("workspace", os.path.join(CONFIG_DIR, "repos"))
    os.makedirs(ws, exist_ok=True)
    return ws


def set_workspace(path):
    """Set workspace path in config."""
    path = os.path.abspath(path)
    os.makedirs(path, exist_ok=True)
    config = load_config()
    old_ws = config.get("workspace")
    config["workspace"] = path
    save_config(config)
    print(f"Workspace set to: {path}")
    if old_ws and old_ws != path:
        print(f"Previous workspace: {old_ws}")
        print("Note: existing repos in the old workspace are NOT moved automatically.")


# ── Metadata ────────────────────────────────────────────────

def _meta_path(workspace):
    return os.path.join(workspace, METADATA_FILE)


def load_metadata(workspace):
    mp = _meta_path(workspace)
    if os.path.exists(mp):
        with open(mp, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_metadata(workspace, metadata):
    with open(_meta_path(workspace), "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)


def touch_access(workspace, full_name):
    """Update last_access_time for a repo."""
    meta = load_metadata(workspace)
    if full_name in meta:
        meta[full_name]["last_access"] = datetime.now(timezone.utc).isoformat()
        meta[full_name]["access_count"] = meta[full_name].get("access_count", 0) + 1
        save_metadata(workspace, meta)


# ── Repo parsing ────────────────────────────────────────────

def parse_repo_input(repo_input):
    """Parse owner/repo or GitHub URL into (owner, name)."""
    url_pattern = r"(?:https?://)?(?:www\.)?github\.com/([^/]+)/([^/\s?.]+)"
    match = re.match(url_pattern, repo_input.strip().rstrip("/"))
    if match:
        return match.group(1), match.group(2).removesuffix(".git")

    parts = repo_input.strip().split("/")
    if len(parts) == 2 and all(parts):
        return parts[0], parts[1]

    print(f"ERROR: Invalid repo format: '{repo_input}'", file=sys.stderr)
    print("Use 'owner/repo' or a GitHub URL.", file=sys.stderr)
    sys.exit(1)


# ── Git operations ──────────────────────────────────────────

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

    with open(index_path, "r", encoding="utf-8") as f:
        index_data = json.load(f)

    modules = index_data.get("modules", {})
    stale_count = 0

    # Normalise changed file paths to forward slashes
    normalised_changed = [p.replace("\\", "/").rstrip("/") for p in changed_files]

    for mod_name, mod_info in modules.items():
        mod_path = mod_info.get("path", "").replace("\\", "/").rstrip("/")
        if not mod_path:
            continue
        prefix = mod_path + "/"
        for changed in normalised_changed:
            if changed.startswith(prefix) or changed == mod_path:
                mod_info["stale"] = True
                stale_count += 1
                break  # no need to check more files for this module

    if new_commit is not None:
        index_data["code_commit"] = new_commit

    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index_data, f, indent=2, ensure_ascii=False)

    return stale_count


def git_pull(repo_dir, full_name):
    """Pull latest changes for a cloned repo."""
    print(f"Pulling latest for {full_name}...")

    # Record pre-pull commit hash
    try:
        old_hash_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_dir, capture_output=True, text=True, encoding="utf-8"
        )
        old_hash = old_hash_result.stdout.strip() if old_hash_result.returncode == 0 else None
    except Exception:
        old_hash = None

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
        # Diverged or conflict — try fetch + reset to remote
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
            return True
        except Exception as e:
            print(f"  WARNING: Could not sync {full_name}: {e}", file=sys.stderr)
            return False

    output = result.stdout.strip()
    if "Already up to date" in output or "Already up-to-date" in output:
        print(f"  Already up to date.")
    else:
        print(f"  Updated successfully.")

    # Check for changed files and mark stale modules
    if old_hash:
        try:
            new_hash_result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_dir, capture_output=True, text=True, encoding="utf-8"
            )
            new_hash = new_hash_result.stdout.strip() if new_hash_result.returncode == 0 else None
        except Exception:
            new_hash = None

        if new_hash and new_hash != old_hash:
            try:
                diff_result = subprocess.run(
                    ["git", "diff", "--name-only", old_hash, new_hash],
                    cwd=repo_dir, capture_output=True, text=True, encoding="utf-8"
                )
                if diff_result.returncode == 0:
                    changed_files = [
                        f for f in diff_result.stdout.strip().splitlines() if f
                    ]
                    # Use short hash for code_commit
                    short_hash_result = subprocess.run(
                        ["git", "rev-parse", "--short", "HEAD"],
                        cwd=repo_dir, capture_output=True, text=True, encoding="utf-8"
                    )
                    short_hash = short_hash_result.stdout.strip() if short_hash_result.returncode == 0 else new_hash[:7]
                    stale_count = mark_stale_modules(repo_dir, changed_files, new_commit=short_hash)
                    if stale_count > 0:
                        print(f"  Wiki: {stale_count} module(s) marked as stale.")
            except Exception:
                pass  # stale marking is best-effort

    return True


def clone_repo(owner, name, branch=None, depth=None):
    """Clone a repo into workspace. Returns clone path."""
    ws = get_workspace()
    repo_dir = os.path.join(ws, owner, name)
    full_name = f"{owner}/{name}"

    if os.path.exists(repo_dir):
        print(f"Repository already cached at: {repo_dir}")
        git_pull(repo_dir, full_name)
        touch_access(ws, full_name)
        print(f"CLONE_PATH={repo_dir}")
        return repo_dir

    url = f"https://github.com/{owner}/{name}.git"
    cmd = ["git", "clone"]
    if depth:
        cmd.extend(["--depth", str(depth)])
    if branch:
        cmd.extend(["--branch", branch])
    cmd.extend([url, repo_dir])

    print(f"Cloning {full_name}...")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=300)
    except subprocess.TimeoutExpired:
        print("ERROR: Clone timed out after 5 minutes.", file=sys.stderr)
        if os.path.exists(repo_dir):
            shutil.rmtree(repo_dir, ignore_errors=True)
        sys.exit(1)

    if result.returncode != 0:
        print(f"ERROR: Clone failed:\n{result.stderr}", file=sys.stderr)
        if os.path.exists(repo_dir):
            shutil.rmtree(repo_dir, ignore_errors=True)
        sys.exit(1)

    # If shallow clone, unshallow so future pulls work
    if depth:
        print("Converting shallow clone to full fetch capability...")
        subprocess.run(
            ["git", "config", "remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*"],
            cwd=repo_dir, capture_output=True, text=True, encoding="utf-8"
        )

    now = datetime.now(timezone.utc).isoformat()
    meta = load_metadata(ws)
    meta[full_name] = {
        "path": repo_dir,
        "branch": branch,
        "url": url,
        "cloned_at": now,
        "last_access": now,
        "access_count": 1,
    }
    save_metadata(ws, meta)

    print(f"Cloned successfully to: {repo_dir}")
    print(f"CLONE_PATH={repo_dir}")
    return repo_dir


# ── Workspace management ────────────────────────────────────

def list_repos():
    """List all cached repos with usage stats."""
    ws = get_workspace()
    meta = load_metadata(ws)

    print(f"\nWorkspace: {ws}")

    if not meta:
        print("No repositories cached yet.\n")
        return

    print(f"\n{'#':<4} {'Repository':<35} {'Accessed':<12} {'Count':<7} {'Last Access'}")
    print("-" * 100)

    now = datetime.now(timezone.utc)
    for i, (repo, info) in enumerate(sorted(meta.items()), 1):
        path = info.get("path", "")
        exists = os.path.exists(path)
        count = info.get("access_count", 0)

        last_str = info.get("last_access", "")
        days_ago = "?"
        if last_str:
            try:
                last_dt = datetime.fromisoformat(last_str)
                delta = now - last_dt
                days_ago = f"{delta.days}d ago"
            except (ValueError, TypeError):
                days_ago = "unknown"

        status = "" if exists else " [MISSING]"
        print(f"{i:<4} {repo:<35} {days_ago:<12} {count:<7} {last_str[:19]}{status}")

    print(f"\nTotal: {len(meta)} repos cached.\n")


def show_stale(days=30):
    """Show repos not accessed within N days."""
    ws = get_workspace()
    meta = load_metadata(ws)
    now = datetime.now(timezone.utc)
    stale = []

    for repo, info in meta.items():
        last_str = info.get("last_access", "")
        if last_str:
            try:
                last_dt = datetime.fromisoformat(last_str)
                delta = now - last_dt
                if delta.days >= days:
                    stale.append((repo, delta.days, info))
            except (ValueError, TypeError):
                stale.append((repo, -1, info))

    if not stale:
        print(f"No repos inactive for {days}+ days.")
        return

    print(f"\nStale repos (unused for {days}+ days):\n")
    for repo, d, info in sorted(stale, key=lambda x: -x[1]):
        age = f"{d}d ago" if d >= 0 else "unknown"
        print(f"  {repo:<35} last accessed: {age}")
    print(f"\nTo clean up: python clone_repo.py --cleanup --days {days}\n")


def pull_all():
    """Pull latest for all cached repos."""
    ws = get_workspace()
    meta = load_metadata(ws)

    if not meta:
        print("No repositories cached.")
        return

    print(f"Pulling latest for {len(meta)} repos...\n")
    for repo, info in meta.items():
        path = info.get("path", "")
        if os.path.exists(path):
            git_pull(path, repo)
        else:
            print(f"  SKIP: {repo} — path missing: {path}")
    print("\nDone.")


def remove_repo(repo_input):
    """Remove a specific cached repo."""
    ws = get_workspace()
    owner, name = parse_repo_input(repo_input)
    full_name = f"{owner}/{name}"

    meta = load_metadata(ws)
    if full_name not in meta:
        print(f"Repository '{full_name}' not found in workspace.")
        return

    repo_dir = meta[full_name].get("path", "")
    if os.path.exists(repo_dir):
        shutil.rmtree(repo_dir, ignore_errors=True)
        print(f"Removed: {repo_dir}")

    del meta[full_name]
    save_metadata(ws, meta)
    print(f"Repository '{full_name}' removed.")


def cleanup(days):
    """Remove repos not accessed within N days."""
    ws = get_workspace()
    meta = load_metadata(ws)
    now = datetime.now(timezone.utc)
    removed = []

    for repo, info in list(meta.items()):
        last_str = info.get("last_access", "")
        try:
            last_dt = datetime.fromisoformat(last_str)
            delta = now - last_dt
            if delta.days >= days:
                path = info.get("path", "")
                if os.path.exists(path):
                    shutil.rmtree(path, ignore_errors=True)
                del meta[repo]
                removed.append(repo)
        except (ValueError, TypeError):
            pass

    save_metadata(ws, meta)
    if removed:
        print(f"Cleaned {len(removed)} repos inactive for {days}+ days:")
        for r in removed:
            print(f"  - {r}")
    else:
        print(f"No repos inactive for {days}+ days.")


# ── CLI ─────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Manage cached GitHub repos")
    parser.add_argument("repo", nargs="?", help="Repository (owner/repo or GitHub URL)")
    parser.add_argument("--branch", "-b", help="Branch to clone")
    parser.add_argument("--depth", "-d", type=int, help="Shallow clone depth")
    parser.add_argument("--config", metavar="PATH", help="Set workspace directory path")
    parser.add_argument("--show-config", action="store_true", help="Show current config")
    parser.add_argument("--list", action="store_true", help="List cached repos")
    parser.add_argument("--pull", metavar="REPO", help="Pull latest for a specific repo")
    parser.add_argument("--pull-all", action="store_true", help="Pull latest for all repos")
    parser.add_argument("--stale", action="store_true", help="Show repos not accessed recently")
    parser.add_argument("--days", type=int, default=30, help="Days threshold for --stale/--cleanup")
    parser.add_argument("--remove", "-r", metavar="REPO", help="Remove a cached repo")
    parser.add_argument("--cleanup", action="store_true", help="Remove repos inactive for --days")

    args = parser.parse_args()

    if args.config:
        set_workspace(args.config)
    elif args.show_config:
        config = load_config()
        ws = config.get("workspace", f"{CONFIG_DIR}/repos (default)")
        print(f"Workspace: {ws}")
        print(f"Config file: {CONFIG_FILE}")
    elif args.list:
        list_repos()
    elif args.pull:
        ws = get_workspace()
        owner, name = parse_repo_input(args.pull)
        full_name = f"{owner}/{name}"
        meta = load_metadata(ws)
        if full_name in meta:
            path = meta[full_name].get("path", "")
            if os.path.exists(path):
                git_pull(path, full_name)
                touch_access(ws, full_name)
            else:
                print(f"Path missing: {path}")
        else:
            print(f"Repository '{full_name}' not in workspace.")
    elif args.pull_all:
        pull_all()
    elif args.stale:
        show_stale(args.days)
    elif args.cleanup:
        cleanup(args.days)
    elif args.remove:
        remove_repo(args.remove)
    elif args.repo:
        owner, name = parse_repo_input(args.repo)
        clone_repo(owner, name, branch=args.branch, depth=args.depth)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
