# Deep Analysis Guide

Patterns and techniques for thorough codebase analysis after cloning a GitHub repository.

## Table of Contents

1. [Architecture Analysis](#architecture-analysis)
2. [Dependency Analysis](#dependency-analysis)
3. [Code Quality Patterns](#code-quality-patterns)
4. [Security Scanning Patterns](#security-scanning-patterns)
5. [Common Grep Patterns by Language](#common-grep-patterns-by-language)

---

## Architecture Analysis

### Identify the Framework/Stack

```
# JavaScript/TypeScript
Read package.json → check "dependencies" and "devDependencies"
Look for: next.config.*, vite.config.*, webpack.config.*, angular.json, vue.config.*

# Python
Read pyproject.toml or setup.py or requirements.txt
Look for: django, flask, fastapi, sqlalchemy patterns

# Rust
Read Cargo.toml → check [dependencies]

# Go
Read go.mod → check require block
```

### Identify Entry Points

| Stack | Entry point patterns |
|-------|---------------------|
| Node.js | `package.json` → `"main"` or `"scripts.start"` |
| Python | `__main__.py`, `app.py`, `main.py`, `manage.py` |
| Go | `func main()` in `main.go` or `cmd/` |
| Rust | `fn main()` in `src/main.rs` or `src/bin/` |
| Java | `public static void main` |

### Map Module Boundaries

Use Glob to find top-level directories, then Read key files:

1. Check `src/` structure (feature-based vs layer-based)
2. Look for barrel files (`index.ts`, `__init__.py`, `mod.rs`)
3. Identify shared/common modules vs domain modules

### Identify API Surface

```
# REST endpoints
Grep for: @app.route, @router, app.get, app.post, express.Router, @GetMapping, @PostMapping

# GraphQL
Grep for: type Query, type Mutation, @Query, @Mutation

# gRPC
Look for: .proto files, service definitions
```

## Dependency Analysis

### Direct Dependencies

Read the primary manifest file to understand what external libraries are used:
- `package.json` (Node)
- `pyproject.toml` / `requirements.txt` (Python)
- `Cargo.toml` (Rust)
- `go.mod` (Go)

### Internal Dependencies (Import Graph)

| Language | Grep pattern |
|----------|-------------|
| JS/TS | `import.*from ['"]\.\/` or `require\(['"]\.` |
| Python | `from \. import` or `from \w+ import` |
| Go | import with module path |
| Rust | `use crate::` or `mod` |

### Database/Storage Dependencies

| What | Pattern |
|------|---------|
| Schema | `CREATE TABLE`, `mongoose.model`, `@Entity`, `db.collection` |
| Dirs | `migrations/`, `schema/`, `models/` |
| Config | `database.yml`, `.env` with `DB_` prefixes |

## Code Quality Patterns

### Test Coverage Indicators

```
# Find test files
Glob: **/*test*, **/*spec*, **/test_*, **/__tests__/**

# Test frameworks
Grep for: describe(, it(, test(, #[test], func Test, def test_

# Check for CI test steps
Read: .github/workflows/*.yml → look for "test" steps
```

### Error Handling Patterns

| Language | Grep pattern |
|----------|-------------|
| JS/TS | `try\s*\{`, `\.catch\(`, `throw new` |
| Python | `try:`, `except`, `raise` |
| Go | `if err != nil` |
| Rust | `Result<`, `unwrap\(\)`, `expect\(`, `\?;` |

### Configuration Management

| Language | Grep pattern |
|----------|-------------|
| JS/TS | `process.env` |
| Python | `os.environ`, `settings.py` |
| Go | `os.Getenv` |
| Rust | `std::env` |
| Config files | `.env.example`, `config/` |

## Security Scanning Patterns

### Common Issues to Check

| Risk | Grep pattern |
|------|-------------|
| Hardcoded secrets | `password\s*=\s*['"]\w`, `api_key\s*=\s*['"]\w`, `secret\s*=\s*['"]\w` |
| AWS keys | `AKIA[0-9A-Z]{16}`, `-----BEGIN.*PRIVATE KEY` |
| SQL injection | `f".*SELECT.*{`, `.format.*SELECT`, string concat with queries |
| XSS | `dangerouslySetInnerHTML`, `innerHTML\s*=`, `v-html`, `\|safe` |
| Command injection | `os.system\(`, `subprocess.*shell=True`, `exec\(`, `eval\(` |
| Auth patterns | `jwt`, `bearer`, `oauth`, `session`, `cookie`, `token` |
| Auth dirs | `auth/`, `middleware/auth`, `guards/` |

## Common Grep Patterns by Language

| Language | What | Pattern |
|----------|------|---------|
| Python | Classes | `class\s+\w+` |
| Python | Functions | `def\s+\w+` |
| Python | Decorators | `@\w+` |
| Python | Async | `async\s+def` |
| JS/TS | Components | `(function\|const)\s+\w+.*=.*=>` |
| JS/TS | Hooks | `use[A-Z]\w+\(` |
| JS/TS | Types | `(type\|interface)\s+\w+` |
| JS/TS | Exports | `export\s+(default\s+)?(function\|class\|const)` |
| Rust | Structs | `pub\s+struct\s+\w+` |
| Rust | Impl | `impl\s+\w+` |
| Rust | Traits | `pub\s+trait\s+\w+` |
| Rust | Macros | `macro_rules!\s+\w+` |
| Go | Structs | `type\s+\w+\s+struct` |
| Go | Interfaces | `type\s+\w+\s+interface` |
| Go | Functions | `func\s+(\(\w+\s+\*?\w+\)\s+)?\w+` |
| Go | Handlers | `func.*http\.Handler` |

## Wiki-Assisted Analysis

When a `.codewiki/` directory exists for a repository, use it to accelerate analysis.

### Loading Wiki Context

1. **Read the index first:**
   ```
   Read: <clone_path>/.codewiki/index.json
   ```
   This gives you: module list with summaries, inter-module relationships, stale markers, and architecture patterns.

2. **Load relevant modules on demand:**
   When the user's question maps to a specific module (check `modules` in index.json):
   ```
   Read: <clone_path>/.codewiki/modules/<module_name>.md
   ```
   Module files contain: entry points, key files, exports, and conversation notes from prior sessions.

3. **Handle stale modules:**
   If a module has `"stale": true`, inform the user and verify key claims against current source code.

### When Wiki Is Absent

Fall back to standard analysis (sections above). After analysis, offer to generate a wiki:
```bash
PYTHONIOENCODING=utf-8 python scripts/generate_wiki.py <clone_path>
```

### Wiki Management Commands

```bash
# Generate wiki for a repo
PYTHONIOENCODING=utf-8 python scripts/generate_wiki.py <clone_path>

# Force regenerate (overwrites existing)
PYTHONIOENCODING=utf-8 python scripts/generate_wiki.py <clone_path> --force

# Regenerate modules only (preserves conversation notes)
PYTHONIOENCODING=utf-8 python scripts/generate_wiki.py <clone_path> --modules-only

# Append knowledge from conversation
PYTHONIOENCODING=utf-8 python scripts/update_wiki.py <clone_path> \
    --module <name> --topic "<topic>" --content "<text>"

# Add architecture relationship
PYTHONIOENCODING=utf-8 python scripts/update_wiki.py <clone_path> \
    --add-relationship "from->to:type"

# Mark module as enriched
PYTHONIOENCODING=utf-8 python scripts/update_wiki.py <clone_path> \
    --module <name> --mark-enriched
```
