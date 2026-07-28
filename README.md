# RepoForge Pro

**One command. A production-ready Python project.**

RepoForge turns an empty directory into a working, git-connected project in under a
minute: virtual environment, dependencies curated for your project *type*, `.gitignore`,
README, LICENSE, `pyproject.toml`, a passing test, optional pre-commit hooks, and a
GitHub remote — created for you when the `gh` CLI is installed.

```bash
python repoforge.py my-tool --profile cli --pre-commit --create-remote --push
```

No dependencies. One file. Python 3.9+. Windows, macOS, Linux.

### AGENTS Constitution (integrated)

RepoForge can attach the universal **AGENTS Constitution** pack to every new project
(project-root `AGENTS.md` pointer, or a vendored copy under `law/AGENTS-Constitution/`).

```bash
# Pointer to an existing pack (relative path written into AGENTS.md)
python repoforge.py my-tool --profile cli --constitution "../QuillForge/AGENTS Constitution"

# Self-contained: copy the pack into the project
python repoforge.py my-tool --constitution PATH --constitution-vendor

# Opt out
python repoforge.py my-tool --no-constitution

# Remember default pack path
python repoforge.py --constitution "D:/law/AGENTS-Constitution" --save-defaults --list-profiles
```

Resolution order: `--constitution` → `REPOFORGE_CONSTITUTION` env →
`constitution_path` in `~/.repoforge.json` → auto-discover nearby
`AGENTS Constitution` / `QuillForge/AGENTS Constitution` packs.

---

## Why this instead of `uv init` or cookiecutter?

Those give you an empty shell. RepoForge gives you **opinions that come from shipping**:
each profile is a curated environment for a *kind* of work, including a
research-grade `ml-experiment` profile with experiment and claims registries built on a
real measured-iteration workflow — not a generic "data science template."

## Profiles

| Profile | What you get |
|---------|--------------|
| `minimal` | venv + git + pytest. No opinions. |
| `general` | Everyday scripting: requests, dotenv, rich, ruff, black, pytest |
| `cli` | Typer + Rich command-line app, `src/` layout, runnable entry point |
| `fastapi` | FastAPI + Uvicorn + httpx test client, `src/` layout, `/health` route |
| `data` | NumPy, pandas, Matplotlib, Jupyter kernel + `data/ notebooks/ output/` |
| `ml-experiment` | Research discipline: `EXPERIMENT_LOG.md` + `CLAIMS.md` registries, `experiments/ results/ plots/ references/` |
| `automation` | Scrapers & scheduled jobs: requests, BeautifulSoup, schedule, dotenv |

```bash
python repoforge.py --list-profiles     # full details
```

## Quickstart

```bash
# 1. First time: save your defaults (stored in ~/.repoforge.json)
python repoforge.py --owner YOUR_GITHUB_NAME --author "Your Name" --save-defaults --list-profiles

# 2. Bootstrap a project
mkdir my-api && cd my-api
python ../repoforge.py my-api --profile fastapi

# 3. Or preview first — dry-run prints the full plan, touches nothing
python repoforge.py my-api --profile fastapi --dry-run
```

Remote handling, in order of convenience:
- `repoforge.py my-tool --create-remote --push` — creates the private GitHub repo via `gh` and pushes
- `repoforge.py my-tool` — links `https://github.com/<owner>/my-tool.git` (repo must exist)
- `repoforge.py someone/their-repo` or `--repo-url git@...` — explicit targets
- `repoforge.py` (no name) — local-only, no remote

## Safe by design

- **Idempotent** — re-run any time; existing files are *never* overwritten (`--force` if you mean it), existing git repos/remotes/commits are detected and respected.
- **`--dry-run`** — prints every action it would take, guaranteed zero changes.
- **Honest failures** — missing git identity, missing `gh`, network issues: clear one-line messages, no stack traces.

## Tested

Ships with a pytest suite (unit, end-to-end, and AGENTS Constitution integration).
`pytest tests/ -v` — about 40 seconds, no network needed.

## FAQ

**Does it work with uv/poetry?** RepoForge uses stock `venv` + `pip` so it runs anywhere
Python does. Use `--skip-venv` and manage the environment with your tool of choice —
all scaffolding still applies.

**Can I add my own profiles?** Yes — profiles are a plain dict at the top of the file
(`PROFILES`). Copy one, edit the package list and scaffold dirs. It's your file.

**License?** Personal license: use it for any number of your own projects, commercial or
not. Don't redistribute or resell the tool itself. See LICENSE.txt.

**Support:** replies within 72h via the store's contact — include the full console output.

---
_v1.0.0 — built by a developer who bootstraps a lot of repos._
