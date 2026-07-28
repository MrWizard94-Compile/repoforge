#!/usr/bin/env python3
"""
RepoForge Pro — the opinionated Python project bootstrapper.

One command turns an empty directory into a working, git-connected Python project:
virtual environment, curated dependencies for your project *type*, .gitignore,
README, LICENSE, pyproject.toml, a passing test, optional pre-commit hooks,
optional AGENTS Constitution pack integration, and a GitHub remote (created for
you when the `gh` CLI is available).

    python repoforge.py my-tool --profile cli
    python repoforge.py my-api --profile fastapi --license mit --pre-commit
    python repoforge.py lab-01 --profile ml-experiment --skip-install
    python repoforge.py my-tool --constitution ../QuillForge/AGENTS Constitution
    python repoforge.py my-tool --constitution PATH --constitution-vendor
    python repoforge.py --list-profiles
    python repoforge.py my-tool --dry-run          # show the plan, touch nothing

Design principles:
  * Idempotent — safe to re-run in the same directory; existing files are never
    overwritten (see --force), existing git state is detected and respected.
  * Honest output — every action is announced; --dry-run prints the full plan.
  * Zero dependencies — standard library only, Python 3.9+.
  * Constitution-aware — optional pointer (or vendored pack) to the universal
    AGENTS Constitution for human–AI engineering standards.

Copyright (c) 2026 MrWizard94. Sold under the RepoForge Pro license (LICENSE.txt).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

__version__ = "1.1.0"

CONFIG_PATH = Path.home() / ".repoforge.json"

# Relative path used when the constitution pack is vendored into a new project.
VENDORED_CONSTITUTION_DIR = Path("law") / "AGENTS-Constitution"

# Marker files that identify a valid AGENTS Constitution pack root (PACK.md).
CONSTITUTION_MARKERS = ("AGENTS.md", "PACK.md", "VERSION", "SOP.md")


# --------------------------------------------------------------------------- #
# Profiles — curated dependency sets and scaffolding per project type.        #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Profile:
    """A project archetype: what it needs and what it looks like on day one."""

    description: str
    packages: Tuple[str, ...]
    # Directories created relative to the project root.
    dirs: Tuple[str, ...] = ()
    # Extra files: relative path -> content factory name (resolved in scaffold_extras).
    extras: Tuple[str, ...] = ()
    # Whether to scaffold a src/<package>/ layout with an entry module.
    src_layout: bool = False


PROFILES: Dict[str, Profile] = {
    "minimal": Profile(
        description="Just the essentials: venv, git, pytest. No opinions.",
        packages=("pytest",),
    ),
    "general": Profile(
        description="Everyday scripting: HTTP, env files, terminal output, linting.",
        packages=("requests", "python-dotenv", "rich", "pytest", "ruff", "black"),
    ),
    "cli": Profile(
        description="Command-line tool with Typer + Rich, src layout, entry point.",
        packages=("typer", "rich", "pytest", "ruff", "black"),
        src_layout=True,
    ),
    "fastapi": Profile(
        description="Web API: FastAPI + Uvicorn + httpx test client, src layout.",
        packages=("fastapi", "uvicorn[standard]", "pydantic", "httpx", "pytest", "ruff"),
        src_layout=True,
    ),
    "data": Profile(
        description="Data analysis: NumPy, pandas, Matplotlib, Jupyter kernel.",
        packages=("numpy", "pandas", "matplotlib", "ipykernel", "pytest"),
        dirs=("data", "notebooks", "output"),
    ),
    "ml-experiment": Profile(
        description="Disciplined AI/ML research: experiment + claims registries, "
                    "results/plots layout, measured-iteration workflow.",
        packages=("numpy", "matplotlib", "pytest"),
        dirs=("experiments", "results", "plots", "references"),
        extras=("EXPERIMENT_LOG.md", "CLAIMS.md"),
    ),
    "automation": Profile(
        description="Scrapers and scheduled jobs: requests, BeautifulSoup, dotenv.",
        packages=("requests", "beautifulsoup4", "python-dotenv", "schedule", "pytest"),
        dirs=("logs",),
    ),
}


# --------------------------------------------------------------------------- #
# Execution engine — every mutation goes through here so --dry-run is total.  #
# --------------------------------------------------------------------------- #

@dataclass
class Runner:
    """Executes commands and writes files, honouring --dry-run and --force."""

    dry_run: bool = False
    force: bool = False
    skipped: List[str] = field(default_factory=list)

    def run(self, command: List[str], description: str, cwd: Path,
            fatal: bool = True) -> bool:
        """Run a subprocess; on failure either exit (fatal) or report and continue."""
        print(f"  -> {description}")
        if self.dry_run:
            print(f"     [dry-run] {' '.join(command)}")
            return True
        try:
            result = subprocess.run(
                command, cwd=str(cwd), check=True, text=True, capture_output=True
            )
            out = (result.stdout or "").strip()
            if out:
                print(f"     {out.splitlines()[0]}")
            return True
        except FileNotFoundError:
            message = f"'{command[0]}' is not installed or not on PATH."
            self._fail(description, message, fatal)
            return False
        except subprocess.CalledProcessError as error:
            message = (error.stderr or error.stdout or "").strip()
            self._fail(description, message, fatal)
            return False

    def write(self, path: Path, content: str, description: str) -> bool:
        """Write a file unless it already exists (respected unless --force)."""
        if path.exists() and not self.force:
            self.skipped.append(str(path))
            print(f"  -- {description}: exists, left untouched ({path.name})")
            return False
        print(f"  -> {description}")
        if not self.dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return True

    def mkdir(self, path: Path, description: str) -> None:
        if path.exists():
            return
        print(f"  -> {description}")
        if not self.dry_run:
            path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _fail(description: str, message: str, fatal: bool) -> None:
        print(f"  !! Failed: {description}")
        if message:
            print(f"     {message.splitlines()[0]}")
        if fatal:
            sys.exit(1)


# --------------------------------------------------------------------------- #
# Pure helpers — unit-testable, no side effects.                              #
# --------------------------------------------------------------------------- #

def build_remote_url(repo_name: Optional[str], repo_url: Optional[str],
                     owner: Optional[str]) -> Optional[str]:
    """Resolve the remote URL from a slug, owner/slug pair, or full URL.

    Returns None when no remote is wanted (no name and no URL given).
    """
    if repo_url:
        return repo_url
    if not repo_name:
        return None
    slug = repo_name.strip()
    if slug.startswith(("https://", "http://", "git@")):
        return slug
    if "/" in slug:
        return f"https://github.com/{slug}.git"
    if not owner:
        raise ValueError(
            "A bare repo name needs a GitHub owner. Pass --owner YOUR_NAME "
            "(and --save-defaults to remember it) or use owner/name form."
        )
    return f"https://github.com/{owner}/{slug}.git"


def package_name_from(project_name: str) -> str:
    """Derive a valid Python package name from a project/repo name."""
    name = re.sub(r"[^0-9a-zA-Z_]+", "_", project_name.strip().lower()).strip("_")
    if not name:
        name = "app"
    if name[0].isdigit():
        name = f"app_{name}"
    return name


def venv_python(venv_dir: Path) -> Path:
    """Path to the venv's Python interpreter, cross-platform."""
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def load_defaults() -> Dict[str, str]:
    """Read saved defaults from ~/.repoforge.json (missing/corrupt -> empty)."""
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_defaults(values: Dict[str, str]) -> None:
    merged = {**load_defaults(), **{k: v for k, v in values.items() if v}}
    CONFIG_PATH.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    print(f"  -> Saved defaults to {CONFIG_PATH}")


# --------------------------------------------------------------------------- #
# AGENTS Constitution integration (universal portable pack).                  #
# --------------------------------------------------------------------------- #

def is_constitution_pack(path: Path) -> bool:
    """True when *path* looks like an AGENTS Constitution pack root."""
    if not path.is_dir():
        return False
    return all((path / marker).is_file() for marker in CONSTITUTION_MARKERS)


def discover_constitution_pack(
    explicit: Optional[str] = None,
    *,
    start: Optional[Path] = None,
) -> Optional[Path]:
    """Resolve a constitution pack path.

    Order:
      1. *explicit* argument (CLI ``--constitution``)
      2. Environment variable ``REPOFORGE_CONSTITUTION``
      3. ``constitution_path`` in ``~/.repoforge.json``
      4. Auto-discover near *start* (default: this file's parent and parents):
         folders named ``AGENTS Constitution`` / ``AGENTS-Constitution`` that
         pass :func:`is_constitution_pack`, and sibling trees under common
         monorepo layouts (e.g. ``../QuillForge/AGENTS Constitution``).
    """
    candidates: List[Path] = []

    if explicit:
        candidates.append(Path(explicit).expanduser())
    env = __import__("os").environ.get("REPOFORGE_CONSTITUTION")
    if env:
        candidates.append(Path(env).expanduser())
    saved = load_defaults().get("constitution_path")
    if saved:
        candidates.append(Path(saved).expanduser())

    for raw in candidates:
        resolved = raw.resolve()
        if is_constitution_pack(resolved):
            return resolved

    # Auto-discovery only when nothing explicit failed (or nothing given).
    if explicit or env or saved:
        # Caller asked for a specific path that was invalid — return None so
        # the CLI can report an honest error rather than silently searching.
        if explicit or env:
            return None

    root = (start or Path(__file__).resolve().parent).resolve()
    search_roots = [root, *root.parents]
    names = ("AGENTS Constitution", "AGENTS-Constitution", "agents-constitution")
    for base in search_roots[:6]:
        for name in names:
            candidate = (base / name).resolve()
            if is_constitution_pack(candidate):
                return candidate
        # Sibling monorepo: Software/QuillForge/AGENTS Constitution
        sibling = (base / "QuillForge" / "AGENTS Constitution").resolve()
        if is_constitution_pack(sibling):
            return sibling
        sibling_alt = (base / "QuillForge" / "AGENTS-Constitution").resolve()
        if is_constitution_pack(sibling_alt):
            return sibling_alt
    return None


def relative_pack_path(from_dir: Path, pack_root: Path) -> str:
    """POSIX-style relative path from *from_dir* to *pack_root* for markdown links."""
    try:
        rel = Path(os_path_relpath(pack_root, from_dir))
    except ValueError:
        # Different drives on Windows — fall back to absolute POSIX-ish path.
        return pack_root.resolve().as_posix()
    return rel.as_posix()


def os_path_relpath(path: Path, start: Path) -> str:
    """os.path.relpath wrapper (keeps stdlib-only footprint)."""
    import os
    return os.path.relpath(str(path.resolve()), str(start.resolve()))


def agents_pointer_content(project: str, pack_rel: str) -> str:
    """Level-4 project AGENTS.md pointer into a constitution pack."""
    # Ensure trailing slash for directory-style links in docs.
    pack = pack_rel.rstrip("/")
    return f"""\
# AGENTS — Project Entry Point ({project})

This file is **Level 4 project law entry only**. It points at the universal
AGENTS Constitution pack. It does not duplicate the constitution.

**Pack path (relative):** `{pack}/`
**Bootstrapped by:** RepoForge v{__version__}

---

## Binding pack

| Role | Path |
|------|------|
| **Constitution (SOUL)** | [{pack}/AGENTS.md]({pack}/AGENTS.md) |
| **Process (SOP)** | [{pack}/SOP.md]({pack}/SOP.md) |
| **Pack identity** | [{pack}/PACK.md]({pack}/PACK.md) |
| **Adopt / move** | [{pack}/ADOPT.md]({pack}/ADOPT.md) |
| **Integrity** | [{pack}/INTEGRITY.md]({pack}/INTEGRITY.md) |

---

## Always load (via pack)

* Pack `AGENTS.md`
* Pack `SOP.md`
* Pack `constitution/03-DEFINITION-OF-DONE.md`
* Pack `standards/ENGINEERING.md`
* Pack `standards/TESTING.md`
* Pack `standards/DOCUMENTATION.md`

Then load pack modules per the applicability matrix in pack `AGENTS.md`.

---

## Verify pack

```bash
# From pack root (PowerShell)
pwsh -File "{pack}/tools/verify-pack.ps1"
```

Must exit `0` after pack install, move, or update.

---

## Project-local law (Level 4)

* README / product docs in this repository
* Architecture notes and ADRs as the project grows
* Overrides: pack `templates/PROJECT-OVERRIDE.template.md`

Project law may **tighten** standards. It may not weaken `CONST-*`,
`ENG-WARN-001`, `TEST-BEHAVIOR-001`, or `SEC-INPUT-001` without a documented
override.

---

_Generated by RepoForge — edit freely; keep the pack pointer accurate if the pack moves._
"""


def copy_constitution_pack(runner: Runner, source: Path, dest: Path) -> None:
    """Copy a constitution pack tree into *dest* (skips reports/ and _archive_*)."""
    if dest.exists() and not runner.force:
        print(f"  -- Constitution pack already present at {dest}, leaving it")
        runner.skipped.append(str(dest))
        return
    print(f"  -> Vendoring AGENTS Constitution pack -> {dest}")
    if runner.dry_run:
        print(f"     [dry-run] copytree {source} -> {dest}")
        return
    if dest.exists() and runner.force:
        shutil.rmtree(dest)
    ignore = shutil.ignore_patterns(
        "reports", "_archive*", "__pycache__", ".pytest_cache", "*.pyc"
    )
    shutil.copytree(source, dest, ignore=ignore)


def setup_constitution(
    runner: Runner,
    target: Path,
    project: str,
    pack_root: Optional[Path],
    *,
    vendor: bool,
    enabled: bool,
) -> None:
    """Attach AGENTS Constitution to a bootstrapped project."""
    if not enabled:
        print("  -- AGENTS Constitution skipped (--no-constitution)")
        return
    if pack_root is None:
        print("  -- AGENTS Constitution pack not found "
              "(pass --constitution PATH, set REPOFORGE_CONSTITUTION, "
              "or save constitution_path via --save-defaults)")
        return
    if not is_constitution_pack(pack_root):
        print(f"  !! Not a valid constitution pack: {pack_root}")
        print("     Need AGENTS.md, PACK.md, VERSION, SOP.md at pack root.")
        return

    print(f"  -> AGENTS Constitution: {pack_root}")
    if vendor:
        dest = target / VENDORED_CONSTITUTION_DIR
        runner.mkdir(dest.parent, f"Creating {dest.parent.as_posix()}/")
        copy_constitution_pack(runner, pack_root, dest)
        pack_rel = VENDORED_CONSTITUTION_DIR.as_posix()
    else:
        pack_rel = relative_pack_path(target, pack_root)

    runner.write(
        target / "AGENTS.md",
        agents_pointer_content(project, pack_rel),
        "Writing AGENTS.md (constitution project pointer)",
    )


# --------------------------------------------------------------------------- #
# File content generators.                                                    #
# --------------------------------------------------------------------------- #

GITIGNORE = """\
# Environments
.venv/
venv/
.env

# Python artefacts
__pycache__/
*.py[cod]
*.egg-info/
build/
dist/

# Tooling caches
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/

# Editors & OS
.idea/
.vscode/
.DS_Store
Thumbs.db

# Logs
*.log
"""

MIT_LICENSE = """\
MIT License

Copyright (c) {year} {author}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

PRE_COMMIT_CONFIG = """\
# Run `pre-commit install` once, then hooks run on every commit.
# Refresh hook versions any time with `pre-commit autoupdate`.
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.4
    hooks:
      - id: ruff
        args: [--fix]
  - repo: https://github.com/psf/black
    rev: 24.4.2
    hooks:
      - id: black
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: end-of-file-fixer
      - id: trailing-whitespace
      - id: check-merge-conflict
"""

EXPERIMENT_LOG = """\
# Experiment Log

> One entry per experiment. Never delete entries — failed experiments are data.
> Registry discipline: an experiment without a hypothesis is a demo, not an experiment.

| ID | Date | Hypothesis tested | Config / seed | Result (measured) | Verdict |
|----|------|-------------------|---------------|-------------------|---------|
| EXP-001 | {date} | _e.g. "X improves Y by >10% on Z"_ | | | pending |

## EXP-001 — <title>

**Hypothesis:** <falsifiable claim>
**Setup:** <exact command / config / seed>
**Result:** <numbers, not adjectives>
**Verdict:** supported / falsified / inconclusive
**Next:** <what this changes about EXP-002>
"""

CLAIMS_REGISTRY = """\
# Claims Registry

> Every claim this project makes, with its evidence class and how to falsify it.
> Classes: **Established** (measured, reproducible) · **Supported** (measured once) ·
> **Working Hypothesis** (believed, untested) · **Falsified** (keep it — it's a result).

| Claim | Class | Evidence (experiment IDs) | Falsification condition |
|-------|-------|---------------------------|-------------------------|
| | Working Hypothesis | | |
"""


def readme_content(project: str, profile_name: str, profile: Profile,
                   package: str) -> str:
    run_hint = {
        "cli": f"python -m {package} --help",
        "fastapi": f"uvicorn {package}.main:app --reload",
    }.get(profile_name, "python main.py")
    return f"""\
# {project}

<!-- One sentence: what this project does and for whom. -->

## Quickstart

```bash
# Windows
.venv\\Scripts\\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
{run_hint}
```

## Tests

```bash
pytest
```

## Project layout

Bootstrapped with [RepoForge](https://github.com/) using the `{profile_name}` profile:
{profile.description}

## Engineering standards

If this project includes an `AGENTS.md` pointer, it links to the universal
**AGENTS Constitution** pack (quality law + SOP). Load that pack for AI-assisted
work; run the pack's `tools/verify-pack.ps1` after moving the pack.

---
_Generated by RepoForge v{__version__} — edit freely, this file is yours._
"""


def pyproject_content(project: str, package: str) -> str:
    return f"""\
[project]
name = "{package}"
version = "0.1.0"
description = ""
requires-python = ">=3.9"

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
line-length = 100

[tool.black]
line-length = 100
"""


def sample_test_content(package: str, src_layout: bool) -> str:
    if src_layout:
        return f"""\
\"\"\"Smoke test — proves the package imports and pytest is wired up.\"\"\"

import {package}


def test_package_imports():
    assert {package} is not None
"""
    return """\
\"\"\"Smoke test — proves pytest is wired up. Replace with real tests.\"\"\"


def test_truth():
    assert True
"""


def entry_module_content(profile_name: str, package: str) -> str:
    if profile_name == "cli":
        return f"""\
\"\"\"Entry point for the {package} CLI. Run: python -m {package} --help\"\"\"

import typer

app = typer.Typer(help="{package} command-line tool")


@app.command()
def hello(name: str = "world") -> None:
    \"\"\"Example command — replace with your own.\"\"\"
    typer.echo(f"Hello, {{name}}!")


if __name__ == "__main__":
    app()
"""
    return f"""\
\"\"\"FastAPI application. Run: uvicorn {package}.main:app --reload\"\"\"

from fastapi import FastAPI

app = FastAPI(title="{package}")


@app.get("/health")
def health() -> dict:
    return {{"status": "ok"}}
"""


# --------------------------------------------------------------------------- #
# Setup phases.                                                               #
# --------------------------------------------------------------------------- #

def scaffold_project(runner: Runner, target: Path, project: str,
                     profile_name: str, license_choice: str, author: str) -> None:
    import datetime

    profile = PROFILES[profile_name]
    package = package_name_from(project)

    runner.write(target / ".gitignore", GITIGNORE, "Writing .gitignore")
    runner.write(target / "requirements.txt",
                 "\n".join(profile.packages) + "\n",
                 f"Writing requirements.txt ({profile_name}: "
                 f"{len(profile.packages)} packages)")
    runner.write(target / "README.md",
                 readme_content(project, profile_name, profile, package),
                 "Writing README.md")
    runner.write(target / "pyproject.toml", pyproject_content(project, package),
                 "Writing pyproject.toml")

    if license_choice == "mit":
        runner.write(target / "LICENSE",
                     MIT_LICENSE.format(year=datetime.date.today().year,
                                        author=author or "the author"),
                     "Writing LICENSE (MIT)")

    for directory in profile.dirs:
        runner.mkdir(target / directory, f"Creating {directory}/")

    if profile.src_layout:
        pkg_dir = target / "src" / package
        runner.write(pkg_dir / "__init__.py",
                     f'"""{package} package."""\n\n__version__ = "0.1.0"\n',
                     f"Creating src/{package}/__init__.py")
        entry_name = "main.py" if profile_name == "fastapi" else "__main__.py"
        runner.write(pkg_dir / entry_name,
                     entry_module_content(profile_name, package),
                     f"Creating src/{package}/{entry_name}")

    runner.write(target / "tests" / "test_smoke.py",
                 sample_test_content(package, profile.src_layout),
                 "Creating tests/test_smoke.py")

    today = datetime.date.today().isoformat()
    for extra in profile.extras:
        content = {"EXPERIMENT_LOG.md": EXPERIMENT_LOG.format(date=today),
                   "CLAIMS.md": CLAIMS_REGISTRY}[extra]
        runner.write(target / extra, content, f"Writing {extra}")


def setup_environment(runner: Runner, target: Path, venv_name: str,
                      skip_install: bool) -> None:
    venv_dir = target / venv_name
    if venv_dir.exists():
        print(f"  -- Virtual environment exists ({venv_name}/), reusing it")
    else:
        runner.run([sys.executable, "-m", "venv", str(venv_dir)],
                   f"Creating virtual environment ({venv_name}/)", cwd=target)
    if skip_install:
        print("  -- Skipping dependency install (--skip-install)")
        return
    python = venv_python(venv_dir)
    runner.run([str(python), "-m", "pip", "install", "--upgrade", "pip", "--quiet"],
               "Upgrading pip", cwd=target)
    runner.run([str(python), "-m", "pip", "install", "-r", "requirements.txt",
                "--quiet"],
               "Installing profile dependencies", cwd=target)


def git_identity_ready(target: Path) -> bool:
    """True when git has a user.name and user.email available for commits."""
    for key in ("user.name", "user.email"):
        probe = subprocess.run(["git", "config", "--get", key], cwd=str(target),
                               text=True, capture_output=True)
        if probe.returncode != 0 or not probe.stdout.strip():
            return False
    return True


def setup_git(runner: Runner, target: Path, remote_url: Optional[str],
              create_remote: bool, push: bool) -> None:
    if (target / ".git").exists():
        print("  -- Git repository exists, reusing it")
    else:
        runner.run(["git", "init"], "Initializing git repository", cwd=target)
        runner.run(["git", "branch", "-M", "main"], "Setting primary branch to main",
                   cwd=target)

    runner.run(["git", "add", "."], "Staging files", cwd=target)

    if runner.dry_run:
        runner.run(["git", "commit", "-m", "Initial commit (RepoForge)"],
                   "Creating initial commit", cwd=target)
    else:
        staged = subprocess.run(["git", "diff", "--cached", "--quiet"],
                                cwd=str(target))
        if staged.returncode == 0:
            print("  -- Nothing new to commit")
        elif not git_identity_ready(target):
            print("  !! git user.name/user.email not configured — skipping commit.")
            print('     Fix: git config --global user.name "You" && '
                  'git config --global user.email "you@example.com"')
        else:
            runner.run(["git", "commit", "-m", "Initial commit (RepoForge)"],
                       "Creating initial commit", cwd=target)

    if not remote_url:
        print("  -- No remote requested (pass a repo name or --repo-url to add one)")
        return

    has_origin = subprocess.run(["git", "remote", "get-url", "origin"],
                                cwd=str(target), capture_output=True
                                ).returncode == 0 if not runner.dry_run else False
    if has_origin:
        print("  -- Remote 'origin' already configured, leaving it as is")
        return

    if create_remote and shutil.which("gh"):
        slug = remote_url.removeprefix("https://github.com/").removesuffix(".git")
        command = ["gh", "repo", "create", slug, "--private", "--source", ".",
                   "--remote", "origin"]
        if push:
            command.append("--push")
        made = runner.run(command, f"Creating GitHub repo {slug} via gh CLI",
                          cwd=target, fatal=False)
        if made:
            return
        print("     Falling back to plain remote add.")
    elif create_remote:
        print("  -- gh CLI not found; adding remote without creating the GitHub repo")

    runner.run(["git", "remote", "add", "origin", remote_url],
               f"Linking remote {remote_url}", cwd=target)
    if push:
        runner.run(["git", "push", "-u", "origin", "main"], "Pushing to origin",
                   cwd=target, fatal=False)


def setup_pre_commit(runner: Runner, target: Path, venv_name: str) -> None:
    runner.write(target / ".pre-commit-config.yaml", PRE_COMMIT_CONFIG,
                 "Writing .pre-commit-config.yaml")
    python = venv_python(target / venv_name)
    if runner.dry_run or python.exists():
        runner.run([str(python), "-m", "pip", "install", "pre-commit", "--quiet"],
                   "Installing pre-commit into the venv", cwd=target, fatal=False)
        runner.run([str(python), "-m", "pre_commit", "install"],
                   "Activating pre-commit hooks", cwd=target, fatal=False)
    else:
        print("  -- venv missing; run 'pre-commit install' after creating one")


# --------------------------------------------------------------------------- #
# CLI.                                                                        #
# --------------------------------------------------------------------------- #

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    defaults = load_defaults()
    parser = argparse.ArgumentParser(
        prog="repoforge",
        description="Bootstrap a production-ready Python project in one command.",
        epilog="Profiles: " + ", ".join(PROFILES) + ".  "
               "Use --list-profiles for details.",
    )
    parser.add_argument("repo_name", nargs="?",
                        help="Repo slug (my-tool), owner/slug, or full git URL. "
                             "Omit to skip the remote.")
    parser.add_argument("--repo-url", help="Explicit remote URL (overrides repo_name).")
    parser.add_argument("--directory", "-d", default=".",
                        help="Target directory (default: current directory).")
    parser.add_argument("--profile", "-p", default=defaults.get("profile", "general"),
                        choices=sorted(PROFILES),
                        help="Project profile (default: %(default)s).")
    parser.add_argument("--owner", default=defaults.get("owner"),
                        help="GitHub owner used to expand bare repo slugs.")
    parser.add_argument("--author", default=defaults.get("author"),
                        help="Name used in the LICENSE file.")
    parser.add_argument("--license", default=defaults.get("license", "mit"),
                        choices=["mit", "none"],
                        help="License to scaffold (default: %(default)s).")
    parser.add_argument("--venv-name", default=".venv",
                        help="Virtual environment directory name.")
    parser.add_argument("--skip-venv", action="store_true",
                        help="Skip virtual environment creation.")
    parser.add_argument("--skip-install", action="store_true",
                        help="Create the venv but skip installing dependencies.")
    parser.add_argument("--pre-commit", action="store_true",
                        help="Scaffold and install pre-commit hooks (ruff + black).")
    parser.add_argument("--create-remote", action="store_true",
                        help="Create the GitHub repository via the gh CLI.")
    parser.add_argument("--push", action="store_true",
                        help="Push the initial commit to origin.")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite files RepoForge would otherwise leave alone.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the full plan without changing anything.")
    parser.add_argument("--constitution",
                        default=defaults.get("constitution_path"),
                        metavar="PATH",
                        help="Path to an AGENTS Constitution pack root "
                             "(AGENTS.md + PACK.md + VERSION + SOP.md). "
                             "Also: REPOFORGE_CONSTITUTION env or saved default.")
    parser.add_argument("--constitution-vendor", action="store_true",
                        help="Copy the constitution pack into "
                             "law/AGENTS-Constitution/ (self-contained project).")
    parser.add_argument("--no-constitution", action="store_true",
                        help="Do not attach AGENTS Constitution "
                             "(even if a pack is discoverable).")
    parser.add_argument("--save-defaults", action="store_true",
                        help="Remember --owner/--author/--license/--profile/"
                             "--constitution in ~/.repoforge.json.")
    parser.add_argument("--list-profiles", action="store_true",
                        help="Show all profiles and exit.")
    parser.add_argument("--version", action="version",
                        version=f"RepoForge {__version__}")
    return parser.parse_args(argv)


def list_profiles() -> None:
    width = max(len(name) for name in PROFILES)
    print("Available profiles:\n")
    for name, profile in PROFILES.items():
        print(f"  {name:<{width}}  {profile.description}")
        print(f"  {'':<{width}}  packages: {', '.join(profile.packages)}\n")


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)

    if args.list_profiles:
        list_profiles()
        return

    if args.save_defaults:
        save_defaults({
            "owner": args.owner,
            "author": args.author,
            "license": args.license,
            "profile": args.profile,
            "constitution_path": args.constitution,
        })

    try:
        remote_url = build_remote_url(args.repo_name, args.repo_url, args.owner)
    except ValueError as error:
        print(f"Error: {error}")
        sys.exit(2)

    target = Path(args.directory).resolve()
    project = args.repo_name.split("/")[-1].removesuffix(".git") \
        if args.repo_name and not args.repo_name.startswith(("http", "git@")) \
        else target.name

    constitution_enabled = not args.no_constitution
    pack_root: Optional[Path] = None
    if constitution_enabled:
        pack_root = discover_constitution_pack(
            args.constitution,
            start=Path(__file__).resolve().parent,
        )
        if args.constitution and pack_root is None:
            print(f"Error: --constitution path is not a valid AGENTS Constitution pack: "
                  f"{args.constitution}")
            print("       Expected files at pack root: "
                  + ", ".join(CONSTITUTION_MARKERS))
            sys.exit(2)

    runner = Runner(dry_run=args.dry_run, force=args.force)
    mode = " (dry run)" if args.dry_run else ""
    print(f"RepoForge {__version__}{mode}")
    print(f"Project:   {project}  [{args.profile}]")
    print(f"Directory: {target}")
    print(f"Remote:    {remote_url or '(none)'}")
    if constitution_enabled and pack_root:
        mode_c = "vendor" if args.constitution_vendor else "pointer"
        print(f"Constitution: {pack_root}  [{mode_c}]")
    elif constitution_enabled:
        print("Constitution: (not found — will skip; pass --constitution PATH)")
    else:
        print("Constitution: disabled")
    print()

    if not args.dry_run:
        target.mkdir(parents=True, exist_ok=True)

    print("[1/5] Scaffolding")
    scaffold_project(runner, target, project, args.profile, args.license,
                     args.author or "")

    print("\n[2/5] AGENTS Constitution")
    setup_constitution(
        runner,
        target,
        project,
        pack_root,
        vendor=args.constitution_vendor,
        enabled=constitution_enabled,
    )

    print("\n[3/5] Environment")
    if args.skip_venv:
        print("  -- Skipping virtual environment (--skip-venv)")
    else:
        setup_environment(runner, target, args.venv_name, args.skip_install)

    print("\n[4/5] Git")
    setup_git(runner, target, remote_url, args.create_remote, args.push)

    print("\n[5/5] Quality hooks")
    if args.pre_commit:
        setup_pre_commit(runner, target, args.venv_name)
    else:
        print("  -- Pre-commit not requested (add --pre-commit to enable)")

    print(f"\n[SUCCESS] {project} is ready{mode}.")
    if runner.skipped:
        print(f"Left untouched (already existed): {len(runner.skipped)} file(s). "
              f"Use --force to overwrite.")
    activate = f"{args.venv_name}\\Scripts\\activate" if sys.platform == "win32" \
        else f"source {args.venv_name}/bin/activate"
    print(f"Next: cd {target}  &&  {activate}  &&  pytest")
    if constitution_enabled and pack_root and not args.constitution_vendor:
        print("       AI agents: load this project's AGENTS.md → constitution pack.")


if __name__ == "__main__":
    main()
