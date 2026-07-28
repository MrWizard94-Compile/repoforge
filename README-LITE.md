# RepoForge Lite

**One command: git repo + virtual environment + `.gitignore` + starter README + dependencies + GitHub remote.**

```bash
python repoforge_lite.py my-project --owner YOUR_GITHUB_NAME
```

Sixty seconds later you have a working, git-connected Python project. No dependencies to install — RepoForge Lite is a single standard-library file. Python 3.9+, Windows/macOS/Linux, MIT licensed.

## What it does

1. Creates the project directory and `git init` (default branch `main`)
2. Builds a `.venv` and installs a sensible starter set (`requests`, `python-dotenv`, `rich`, `pytest`)
3. Writes a real `.gitignore` (venv, env files, caches, editor junk)
4. Generates a starter README
5. Links your GitHub remote (`https://github.com/<owner>/<project>.git`)
6. Makes the first commit

Re-runnable and careful: it won't clobber an existing project.

## Install

There isn't one. Download `repoforge_lite.py`, put it anywhere, run it with Python 3.9+.

```bash
curl -O https://raw.githubusercontent.com/MrWizard94-Compile/repoforge/main/repoforge_lite.py
python repoforge_lite.py my-project --owner you
```

## Want more? RepoForge Pro

Lite bootstraps *a* project. **Pro bootstraps your kind of project:**

- **7 opinionated profiles:** `minimal` · `general` · `cli` (Typer) · `fastapi` · `data` · `ml-experiment` · `automation`
- The `ml-experiment` profile ships experiment + claims registries with falsification discipline — from a real AI research workflow
- LICENSE + `pyproject.toml` + passing pytest scaffold per project
- Pre-commit hooks (ruff + black), `--dry-run`, saved defaults, `gh` repo auto-creation with `--create-remote --push`
- Idempotent by design, ships with its own 23-test suite

**→ [Get RepoForge Pro — $14 launch price](https://wpaistudio.gumroad.com/l/repoforge)** (regular $19 after launch week).

---

Built by [WPAI](https://github.com/MrWizard94-Compile) — human-directed, AI-assisted, fully disclosed. *Forging the future of creative media.*
