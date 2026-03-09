"""Create mock repo structures for testing codewiki generation."""
import os
import json
import shutil
import stat
import subprocess
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent


def _force_rmtree(path):
    """Remove a directory tree, handling read-only files (e.g. .git objects on Windows)."""
    def _on_error(func, fpath, exc_info):
        # Clear the read-only flag and retry
        os.chmod(fpath, stat.S_IWRITE)
        func(fpath)
    shutil.rmtree(path, onerror=_on_error)


def create_monorepo(base=None):
    """Create a mock monorepo (like React) with packages/."""
    root = base or FIXTURES_DIR / "mock_monorepo"
    if root.exists():
        _force_rmtree(root)
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
        _force_rmtree(root)
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
        _force_rmtree(root)
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
            _force_rmtree(p)


if __name__ == "__main__":
    print("Creating monorepo fixture...")
    print(f"  -> {create_monorepo()}")
    print("Creating single-repo fixture...")
    print(f"  -> {create_single_repo()}")
    print("Creating flat-repo fixture...")
    print(f"  -> {create_flat_repo()}")
    print("Done.")
