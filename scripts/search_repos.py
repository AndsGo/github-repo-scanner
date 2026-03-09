#!/usr/bin/env python3
"""Search GitHub repositories by keyword, topic, or language.

Usage:
    python search_repos.py <query> [--language <lang>] [--sort <sort>] [--limit <n>]

Examples:
    python search_repos.py "machine learning"
    python search_repos.py "web framework" --language python --sort stars --limit 10
    python search_repos.py "react component library" --sort updated
"""

import argparse
import json
import subprocess
import sys


def search_repos(query, language=None, sort="stars", limit=10):
    """Search GitHub repos using gh CLI."""
    cmd = ["gh", "search", "repos", query, "--json",
           "fullName,description,stargazersCount,language,updatedAt,url,isArchived",
           "--limit", str(limit), "--sort", sort]

    if language:
        cmd.extend(["--language", language])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=30)
    except FileNotFoundError:
        print("ERROR: 'gh' CLI not found. Install it: https://cli.github.com/", file=sys.stderr)
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print("ERROR: Search timed out after 30s.", file=sys.stderr)
        sys.exit(1)

    if result.returncode != 0:
        print(f"ERROR: gh search failed:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)

    repos = json.loads(result.stdout)
    return repos


def format_results(repos):
    """Format search results as a readable table."""
    if not repos:
        print("No repositories found.")
        return

    print(f"\n{'#':<4} {'Repository':<45} {'Stars':<8} {'Language':<15} {'Description'}")
    print("-" * 120)

    for i, repo in enumerate(repos, 1):
        name = repo.get("fullName", "")[:44]
        stars = repo.get("stargazersCount", 0)
        lang = (repo.get("language") or "N/A")[:14]
        desc = (repo.get("description") or "")[:50]
        archived = " [ARCHIVED]" if repo.get("isArchived") else ""
        print(f"{i:<4} {name:<45} {stars:<8} {lang:<15} {desc}{archived}")

    print(f"\nTotal: {len(repos)} repositories found.\n")


def get_repo_info(full_name):
    """Get detailed info for a specific repo."""
    cmd = ["gh", "repo", "view", full_name, "--json",
           "name,owner,description,stargazerCount,forkCount,primaryLanguage,"
           "languages,licenseInfo,createdAt,updatedAt,defaultBranchRef,"
           "diskUsage,isArchived,url,homepageUrl,repositoryTopics"]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=30)
    except FileNotFoundError:
        print("ERROR: 'gh' CLI not found.", file=sys.stderr)
        sys.exit(1)

    if result.returncode != 0:
        print(f"ERROR: Failed to get repo info:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)

    return json.loads(result.stdout)


def format_repo_info(info):
    """Format detailed repo info."""
    owner = info.get("owner", {}).get("login", "unknown")
    name = info.get("name", "unknown")
    print(f"\n=== {owner}/{name} ===")
    print(f"  URL:         {info.get('url', 'N/A')}")
    print(f"  Description: {info.get('description', 'N/A')}")
    print(f"  Stars:       {info.get('stargazerCount', 0)}")
    print(f"  Forks:       {info.get('forkCount', 0)}")
    primary_lang = info.get("primaryLanguage")
    if primary_lang:
        print(f"  Language:    {primary_lang.get('name', 'N/A')}")
    languages = info.get("languages", [])
    if languages:
        lang_names = [l.get("node", {}).get("name", "") for l in languages if l.get("node")]
        if lang_names:
            print(f"  All langs:   {', '.join(lang_names)}")
    license_info = info.get("licenseInfo")
    if license_info:
        print(f"  License:     {license_info.get('name', 'N/A')}")
    branch = info.get("defaultBranchRef", {})
    if branch:
        print(f"  Branch:      {branch.get('name', 'main')}")
    disk = info.get("diskUsage", 0)
    if disk:
        mb = disk / 1024
        print(f"  Size:        {mb:.1f} MB")
    topics = info.get("repositoryTopics", [])
    if topics:
        topic_names = [t.get("name", "") for t in topics if t.get("name")]
        if topic_names:
            print(f"  Topics:      {', '.join(topic_names)}")
    if info.get("isArchived"):
        print("  Status:      ARCHIVED")
    print()


def main():
    parser = argparse.ArgumentParser(description="Search GitHub repositories")
    parser.add_argument("query", help="Search query string")
    parser.add_argument("--language", "-l", help="Filter by programming language")
    parser.add_argument("--sort", "-s", default="stars",
                        choices=["stars", "forks", "updated", "help-wanted-issues"],
                        help="Sort results by (default: stars)")
    parser.add_argument("--limit", "-n", type=int, default=10,
                        help="Max results to return (default: 10)")
    parser.add_argument("--info", "-i", help="Get detailed info for a specific repo (owner/name)")

    args = parser.parse_args()

    if args.info:
        info = get_repo_info(args.info)
        format_repo_info(info)
    else:
        repos = search_repos(args.query, language=args.language, sort=args.sort, limit=args.limit)
        format_results(repos)


if __name__ == "__main__":
    main()
