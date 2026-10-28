# RepoForge Pro

**One command for a production-grade Python project foundation.**

RepoForge turns an empty directory into a runnable, installable, Git-connected
foundation for a specific kind of Python project. It creates the environment,
separates runtime and development dependencies, records a resolved lock,
generates meaningful behavior tests, and can add quality hooks, a WPAI
Constitution pointer, and a private GitHub remote.

```bash
python repoforge.py my-tool --directory my-tool --profile cli \
  --pre-commit --create-remote --push
```

RepoForge itself has no third-party runtime dependencies. It supports Python
3.10 and newer on Windows, macOS, and Linux; use a currently supported Python
patch release for production work.

## What a normal run produces

- An isolated virtual environment and installed editable project.
- `requirements.txt` for direct runtime inputs.
- `requirements-dev.txt` for the runtime inputs plus test and quality tools.
- `requirements.lock`, resolved from the installed environment for repeatable
  setup on the same platform.
- Installable `pyproject.toml` metadata for both `src/` and single-module layouts.
- A runnable entry point and behavior-focused smoke test.
- A scoped initial Git commit containing only files generated in that run.
- Optional pinned pre-commit hooks and a canonical WPAI Constitution pointer
  (enabled by default; `--no-constitution` opts out).

RepoForge supplies the engineering foundation. The generated project becomes a
finished product when its domain behavior, user experience, and release evidence
meet that project's requirements.

## Quickstart

Save reusable defaults and inspect the profiles in one command:

```bash
python repoforge.py --owner YOUR_GITHUB_NAME --author "Your Name" \
  --save-defaults --list-profiles
```

Preview a local-only FastAPI foundation. Dry-run includes configuration actions
and guarantees zero filesystem or subprocess mutations:

```bash
python repoforge.py --directory my-api --profile fastapi \
  --no-constitution --dry-run
```

Create it:

```bash
python repoforge.py --directory my-api --profile fastapi --no-constitution
```

After a normal run:

```bash
cd my-api
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pytest
```

Use `--skip-install` to create the environment without installing dependencies.
Use `--skip-venv` when another tool owns the environment. If `--pre-commit` is
combined with `--skip-venv`, the named environment must already exist.

## Profiles

| Profile | Foundation |
| --- | --- |
| `minimal` | Single-module entry point, pytest, packaging, and Git |
| `general` | Requests, dotenv, Rich, Ruff, Black, and pytest |
| `cli` | Typer and Rich CLI, `src/` layout, console entry point, and command test |
| `fastapi` | FastAPI, Uvicorn, `src/` layout, `/health`, and HTTP behavior test |
| `data` | NumPy, pandas, Matplotlib, Jupyter kernel, and data workspace folders |
| `ml-experiment` | Experiment and claims registries plus results and reference folders |
| `automation` | Requests, Beautiful Soup, dotenv, Schedule, logs, and tests |

```bash
python repoforge.py --list-profiles
```

## Dependency contract

On the first installed run, RepoForge installs `requirements-dev.txt`, installs
the generated project in editable mode, and writes the resolved environment to
`requirements.lock`. A rerun uses the existing lock and leaves it untouched.
`--force` intentionally rebuilds generated inputs and resolves a fresh lock.

The lock is an environment snapshot and may contain platform-specific packages.
Validate and regenerate it when changing operating systems or Python versions.

## Git and GitHub behavior

- With no repository name or `--repo-url`, the project remains local-only.
- A bare name expands through the saved or explicit `--owner` value.
- `owner/repository`, GitHub HTTPS, and GitHub SSH forms are accepted.
- `--create-remote` requires an authenticated `gh` session for `github.com` and
  creates a private repository.
- `--push` requires RepoForge's initial commit and pushes the current `HEAD`.
- `--no-commit` initializes Git while leaving generated files unstaged.
- Existing `origin` configuration is preserved.
- Existing staged and untracked user files are excluded from RepoForge commits.

RepoForge rejects unsafe virtual-environment paths, non-directory targets,
incompatible option combinations, missing Git identity, missing tools, and
unsupported remote-creation URLs before it writes project files.

## WPAI Constitution integration — pointer only

By default, RepoForge writes a project-root `AGENTS.md` pointer to accepted
`main` of [WPAI Constitution](https://github.com/MrWizard94-Compile/Agents-Constitution).
It never copies editable law or searches neighboring/ancestor folders for packs.
The agent uses the installed `wpai-constitution` skill to freeze one accepted
commit and verify `SOURCE.json`, provenance and file hashes before loading that
revision's instructions. When GitHub is unavailable, only the frozen skill's
permitted, previously verified mirror fallback is allowed, with degraded sync
disclosed. Without a permitted verified source, report the limitation rather
than treating another local folder as law.

```bash
# Canonical pointer; no local pack or network access needed to generate it
python repoforge.py --directory my-tool --profile cli

# Explicit opt-out
python repoforge.py --directory my-tool --no-constitution

# Save ordinary product defaults and list profiles
python repoforge.py --owner YOUR_GITHUB_NAME --save-defaults --list-profiles
```

`--constitution PATH` and `--constitution-vendor` are retired. They return exit
code 2 before any configuration or project writes, including when combined with
`--force`, `--dry-run`, `--save-defaults`, `--list-profiles` or the opt-out.
Remove these flags; no replacement path selector is needed.

Non-empty `REPOFORGE_CONSTITUTION` and saved `constitution_path` settings also
produce an actionable error while governance is enabled. Their target paths
are not opened or selected. Unset the environment variable and remove the
retired saved key. Alternatively, `--no-constitution` explicitly opts out and
ignores those implicit settings. An explicit
`--no-constitution --save-defaults --list-profiles` saves normal defaults and
removes the retired key; ordinary runs never rewrite configuration implicitly.

An existing `AGENTS.md` is preserved unless `--force` is explicit. Preserving
it is not verified migration: RepoForge reports that the canonical pointer was
not installed. A known previous `law/AGENTS-Constitution/` tree blocks enabled
generation before writes, even with `--force`; preserve and migrate it explicitly.
The opt-out leaves such existing data untouched, not audited or retired.
RepoForge never recursively deletes an old law tree to make a rerun succeed.

Pointer creation does not download law, install a skill, start an agent or
prove current accepted source verification. Reopen the generated entry through
the intended agent and verify its actual frozen-source response separately.

## Safety model

- Existing generated-path files remain untouched unless `--force` is explicit.
- Every project write is confined to the resolved target directory.
- Dry-run does not create the target, save defaults, write files, or run mutating
  subprocesses.
- Git stages and commits the exact generated path list instead of `git add .`.
- User configuration writes use atomic replacement and contain no credentials.
- Release ZIPs use an exact allowlist and reject unsafe or extra members.

RepoForge executes package-manager, Git, GitHub CLI, and hook commands requested
by the operator. Review dependency inputs and existing project guidance before
using them in an existing or sensitive repository. Governance does not authorize
commits, pushes, publication, spending, distribution, deletion or scope changes.

## Test and release verification

The customer suite covers pure helpers, input validation, generated source
compilation, dry-run, default persistence, real Git reruns, user-staged-file
isolation, no-commit behavior, release reproducibility, archive integrity, and
WPAI Constitution pointers, retired-option rejection before writes, stale-setting
migration, opt-out, preserved guidance and user index, all seven generated
profiles, and fresh-process generation from the verified customer archive.

```bash
python -m pip install -r requirements-dev.txt
ruff format --check repoforge.py repoforge_lite.py build_release.py tests
ruff check repoforge.py repoforge_lite.py build_release.py tests
mypy
python -X utf8 -W error -m pytest tests -q

python build_release.py --edition pro
python build_release.py --edition pro --check
python build_release.py --edition lite
python build_release.py --edition lite --check
```

The pinned source gate uses pytest 9.1.1, Ruff 0.16.6, and mypy 2.3.1. The
standard-library release builder writes members in a fixed order with stable
timestamps, permissions, and compression. It embeds `MANIFEST.json` with every
customer file's SHA-256 and byte length, validates the complete archive, and
atomically replaces the output. Build and check commands print machine-readable
edition, version, member count, path, and archive-hash evidence.

The Pro archive includes the complete Pro test and release toolchain plus the
MIT-licensed Lite edition. The separate Lite archive is a minimal public bundle
containing its executable source, documentation, license, and integrity manifest.

## License and support

The personal license permits use for any number of the purchaser's own projects,
including commercial projects. It does not permit redistribution or resale of
RepoForge itself. See `LICENSE.txt` for the complete terms.

For support, use the store contact and include the command, Python version,
operating system, and complete console output.

---

_RepoForge Pro v1.1.0_
