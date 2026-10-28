#!/usr/bin/env python3
"""
RepoForge Pro — the opinionated Python project bootstrapper.

One command turns an empty directory into a working, git-connected Python project
foundation: virtual environment, curated dependencies for your project *type*,
.gitignore, README, LICENSE, installable packaging, meaningful smoke tests,
optional pre-commit hooks, a canonical WPAI Constitution pointer, and a
GitHub remote (created for you with an authenticated `gh` CLI).

    python repoforge.py my-tool --profile cli
    python repoforge.py my-api --profile fastapi --license mit --pre-commit
    python repoforge.py lab-01 --profile ml-experiment --skip-install
    python repoforge.py my-tool --no-constitution  # explicit governance opt-out
    python repoforge.py --list-profiles
    python repoforge.py my-tool --dry-run          # show the plan, touch nothing

Design principles:
  * Idempotent — safe to re-run in the same directory; existing files are never
    overwritten (see --force), existing git state is detected and respected.
  * Honest output — every action is announced; --dry-run prints the full plan.
  * Zero dependencies — standard library only, Python 3.10+.
  * Constitution-aware — a pointer to accepted WPAI Constitution, never an
    editable law copy or an automatically discovered local pack.

Copyright (c) 2026 MrWizard94. Sold under the RepoForge Pro license (LICENSE.txt).
"""

from __future__ import annotations

import argparse
import json
import keyword
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

__version__ = "1.1.0"
MINIMUM_PYTHON = (3, 10)
PRE_COMMIT_REQUIREMENT = "pre-commit==4.6.2"

CONFIG_PATH = Path.home() / ".repoforge.json"
CONFIG_KEYS = frozenset({"owner", "author", "license", "profile"})
RETIRED_CONFIG_KEY = "constitution_path"
MAX_CONFIG_BYTES = 64 * 1024

CONSTITUTION_SOURCE = "https://github.com/MrWizard94-Compile/Agents-Constitution"
REMOTE_URL_PREFIXES = ("https://", "http://", "ssh://", "git://", "git@")
GITHUB_SLUG_PATTERN = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
WINDOWS_RESERVED_NAMES = {
    "aux",
    "clock$",
    "con",
    "nul",
    "prn",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
}


# --------------------------------------------------------------------------- #
# Profiles — curated dependency sets and scaffolding per project type.        #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Profile:
    """A project archetype: what it needs and what it looks like on day one."""

    description: str
    runtime_packages: tuple[str, ...]
    development_packages: tuple[str, ...]
    # Directories created relative to the project root.
    dirs: tuple[str, ...] = ()
    # Workspace directories whose generated contents stay out of Git by default.
    ignored_dirs: tuple[str, ...] = ()
    # Extra files: relative path -> content factory name (resolved in scaffold_extras).
    extras: tuple[str, ...] = ()
    # Whether to scaffold a src/<package>/ layout with an entry module.
    src_layout: bool = False

    @property
    def packages(self) -> tuple[str, ...]:
        """All direct dependencies, retained as a convenient public view."""
        return self.runtime_packages + self.development_packages


PROFILES: dict[str, Profile] = {
    "minimal": Profile(
        description="Just the essentials: venv, git, pytest. No opinions.",
        runtime_packages=(),
        development_packages=("pytest",),
    ),
    "general": Profile(
        description="Everyday scripting: HTTP, env files, terminal output, linting.",
        runtime_packages=("requests", "python-dotenv", "rich"),
        development_packages=("pytest", "ruff", "black"),
    ),
    "cli": Profile(
        description="Command-line tool with Typer + Rich, src layout, entry point.",
        runtime_packages=("typer", "rich"),
        development_packages=("pytest", "ruff", "black"),
        src_layout=True,
    ),
    "fastapi": Profile(
        description="Web API: FastAPI + Uvicorn + HTTPX2 test client, src layout.",
        runtime_packages=(
            "fastapi",
            "uvicorn[standard]",
            "pydantic",
            # 2026-09-09: Starlette 1.6.0 still imports an alias deprecated in
            # AnyIO 4.15; this ceiling keeps warnings-as-errors clean.
            "anyio>=4.14.2,<4.15",
        ),
        development_packages=("httpx2", "pytest", "ruff"),
        src_layout=True,
    ),
    "data": Profile(
        description="Data analysis: NumPy, pandas, Matplotlib, Jupyter kernel.",
        runtime_packages=("numpy", "pandas", "matplotlib", "ipykernel"),
        development_packages=("pytest",),
        dirs=("data", "notebooks", "output"),
        ignored_dirs=("data", "output"),
    ),
    "ml-experiment": Profile(
        description="Disciplined AI/ML research: experiment + claims registries, "
        "results/plots layout, measured-iteration workflow.",
        runtime_packages=("numpy", "matplotlib"),
        development_packages=("pytest",),
        dirs=("experiments", "results", "plots", "references"),
        ignored_dirs=("results", "plots"),
        extras=("EXPERIMENT_LOG.md", "CLAIMS.md"),
    ),
    "automation": Profile(
        description="Scrapers and scheduled jobs: requests, BeautifulSoup, dotenv.",
        runtime_packages=("requests", "beautifulsoup4", "python-dotenv", "schedule"),
        development_packages=("pytest",),
        dirs=("logs",),
        ignored_dirs=("logs",),
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
    root: Path | None = None
    skipped: list[str] = field(default_factory=list)
    stage_paths: list[Path] = field(default_factory=list)

    def checked_path(self, path: Path) -> Path:
        """Return a path confined to the configured project root."""
        if self.root is None:
            return path
        root = self.root.resolve()
        candidate = path.resolve()
        try:
            candidate.relative_to(root)
        except ValueError as error:
            raise ValueError(
                f"Refusing to write outside the project directory: {path}"
            ) from error
        return path

    def track_for_git(self, path: Path) -> None:
        """Record a generated path for precise staging later in the run."""
        checked = self.checked_path(path)
        if checked not in self.stage_paths:
            self.stage_paths.append(checked)

    def run(
        self, command: list[str], description: str, cwd: Path, fatal: bool = True
    ) -> bool:
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

    def capture(
        self, command: list[str], description: str, cwd: Path, fatal: bool = True
    ) -> str | None:
        """Run a command and return stdout while preserving dry-run semantics."""
        print(f"  -> {description}")
        if self.dry_run:
            print(f"     [dry-run] {' '.join(command)}")
            return None
        try:
            result = subprocess.run(
                command, cwd=str(cwd), check=True, text=True, capture_output=True
            )
            return result.stdout
        except FileNotFoundError:
            message = f"'{command[0]}' is not installed or not on PATH."
            self._fail(description, message, fatal)
            return None
        except subprocess.CalledProcessError as error:
            message = (error.stderr or error.stdout or "").strip()
            self._fail(description, message, fatal)
            return None

    def write(self, path: Path, content: str, description: str) -> bool:
        """Write a file unless it already exists (respected unless --force)."""
        path = self.checked_path(path)
        if path.exists() and not self.force:
            self.skipped.append(str(path))
            print(f"  -- {description}: exists, left untouched ({path.name})")
            return False
        print(f"  -> {description}")
        self.track_for_git(path)
        if not self.dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return True

    def mkdir(self, path: Path, description: str) -> None:
        path = self.checked_path(path)
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


def build_remote_url(
    repo_name: str | None, repo_url: str | None, owner: str | None
) -> str | None:
    """Resolve the remote URL from a slug, owner/slug pair, or full URL.

    Returns None when no remote is wanted (no name and no URL given).
    """
    if repo_url is not None:
        cleaned_url = repo_url.strip()
        if not cleaned_url:
            raise ValueError("--repo-url cannot be blank")
        return cleaned_url
    if not repo_name:
        return None
    slug = repo_name.strip()
    if not slug:
        raise ValueError("Repository name cannot be blank")
    if slug.startswith(REMOTE_URL_PREFIXES):
        return slug
    if "/" in slug:
        if GITHUB_SLUG_PATTERN.fullmatch(slug) is None:
            raise ValueError(
                "GitHub repository names must use the form owner/repository"
            )
        return f"https://github.com/{slug}.git"
    if not owner:
        raise ValueError(
            "A bare repo name needs a GitHub owner. Pass --owner YOUR_NAME "
            "(and --save-defaults to remember it) or use owner/name form."
        )
    github_slug = f"{owner.strip()}/{slug}"
    if GITHUB_SLUG_PATTERN.fullmatch(github_slug) is None:
        raise ValueError("GitHub owner and repository names contain invalid characters")
    return f"https://github.com/{github_slug}.git"


def github_slug_from_remote(remote_url: str) -> str | None:
    """Return ``owner/repo`` for a supported GitHub HTTPS or SSH remote."""
    patterns = (
        r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$",
        r"^git@github\.com:([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?$",
        r"^ssh://git@github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, remote_url)
        if match:
            return f"{match.group(1)}/{match.group(2)}"
    return None


def package_name_from(project_name: str) -> str:
    """Derive a valid Python package name from a project/repo name."""
    name = re.sub(r"[^0-9a-zA-Z_]+", "_", project_name.strip().lower()).strip("_")
    if not name:
        name = "app"
    if (
        name[0].isdigit()
        or keyword.iskeyword(name)
        or name.casefold() in WINDOWS_RESERVED_NAMES
    ):
        name = f"app_{name}"
    return name


def venv_python(venv_dir: Path) -> Path:
    """Path to the venv's Python interpreter, cross-platform."""
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def load_defaults() -> dict[str, str]:
    """Read saved defaults from ~/.repoforge.json (missing/corrupt -> empty)."""
    try:
        if CONFIG_PATH.stat().st_size > MAX_CONFIG_BYTES:
            return {}
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        return {
            key: value
            for key, value in data.items()
            if (key in CONFIG_KEYS or key == RETIRED_CONFIG_KEY)
            and isinstance(value, str)
            and value
        }
    except (OSError, json.JSONDecodeError):
        return {}


def save_defaults(values: Mapping[str, str | None], *, dry_run: bool = False) -> None:
    """Atomically merge saved defaults, or only describe the write in dry-run mode."""
    merged = {
        **load_defaults(),
        **{key: value for key, value in values.items() if value},
    }
    merged = {key: value for key, value in merged.items() if key in CONFIG_KEYS}
    if dry_run:
        print(f"  -> Would save defaults to {CONFIG_PATH} [dry-run]")
        return

    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(merged, indent=2, sort_keys=True) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{CONFIG_PATH.name}.",
            suffix=".tmp",
            dir=CONFIG_PATH.parent,
            delete=False,
        ) as temporary:
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        if os.name != "nt":
            temporary_path.chmod(0o600)
        temporary_path.replace(CONFIG_PATH)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    print(f"  -> Saved defaults to {CONFIG_PATH}")


# --------------------------------------------------------------------------- #
# WPAI Constitution integration — pointers only, no local law discovery.       #
# --------------------------------------------------------------------------- #


def validate_constitution_options(
    explicit: str | None,
    *,
    vendor: bool,
    enabled: bool,
    saved_path: str | None,
) -> None:
    """Reject retired selectors before configuration or project mutations."""
    if vendor:
        raise ValueError(
            "--constitution-vendor is retired; RepoForge writes a canonical "
            "WPAI Constitution pointer, never editable law. Remove the flag; "
            "use --no-constitution to opt out."
        )
    if explicit is not None:
        raise ValueError(
            "--constitution PATH is retired; RepoForge writes a canonical "
            "WPAI Constitution pointer without a local pack. Remove the option; "
            "use --no-constitution to opt out."
        )
    if enabled and (os.environ.get("REPOFORGE_CONSTITUTION") or saved_path):
        raise ValueError(
            "Local constitution path settings are retired in pointer-only mode. "
            "Unset REPOFORGE_CONSTITUTION and remove constitution_path from "
            "~/.repoforge.json, or pass --no-constitution to opt out. "
            "--no-constitution --save-defaults explicitly retires the saved key."
        )


def agents_pointer_content() -> str:
    """Render a stable loader, not law or a claim of verified acceptance."""
    return f"""\
# Project agent entry

The accepted `main` of
[WPAI Constitution]({CONSTITUTION_SOURCE})
is the sole editable source of constitutional law. This project file is a
pointer and product-context entry, not a second constitution.
Bootstrapped by RepoForge v{__version__}.

## Load and verify

Use the installed `wpai-constitution` skill. Resolve and record one verified
accepted full commit SHA for the invocation. Read `SKILL.md`, `SOURCE.json`,
`references/always-load.md` and all named/applicable law from that same frozen
revision. Verify source identity and file hashes against its manifest.
Do not treat a nearby folder, archived pack or generated mirror as fresh law;
mirrors are distributions, not authority.

If GitHub is unavailable, follow only the fallback permitted by the frozen
skill: a previously verified generated mirror with matching provenance and
file hashes. Disclose degraded synchronization and the frozen revision; do not
claim freshness. If no permitted verified source is available, report that
limitation before governed work instead of substituting local law.

## Product context and authority

Read this project's README, declared stack and commands, architecture,
acceptance criteria and data boundaries before acting. Keep product facts here
or in project docs, and amendments in canonical PRs rather than copied law.

This pointer does not grant human authorization to commit, push, publish,
spend, distribute, delete or change scope. Obtain the authority required for
the requested action. RepoForge does not download law, install the skill,
verify accepted GitHub state or invoke agents. Creating this file alone does
not prove an installed agent loaded it or a project passed delivery gates.
"""


def setup_constitution(runner: Runner, target: Path, *, enabled: bool) -> bool:
    """Write the canonical pointer, honestly reporting preserved user guidance."""
    if not enabled:
        print("  -- WPAI Constitution skipped (--no-constitution)")
        return False
    installed = runner.write(
        target / "AGENTS.md",
        agents_pointer_content(),
        "Writing AGENTS.md (canonical WPAI Constitution pointer)",
    )
    if not installed:
        print(
            "  -- Existing AGENTS.md preserved; canonical pointer was not installed. "
            "Its authority is not verified. Review and migrate it explicitly."
        )
    return installed


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
    rev: v0.16.6
    hooks:
      - id: ruff-check
        args: [--fix]
  - repo: https://github.com/psf/black-pre-commit-mirror
    rev: 26.5.1
    hooks:
      - id: black
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v6.0.0
    hooks:
      - id: end-of-file-fixer
      - id: trailing-whitespace
      - id: check-merge-conflict
      - id: check-toml
      - id: check-yaml
"""

EXPERIMENT_LOG = """\
# Experiment Log

> One entry per experiment. Never delete entries — failed experiments are data.
> Registry discipline: an experiment without a hypothesis is a demo, not an experiment.

| ID | Date | Hypothesis tested | Config / seed | Result (measured) | Verdict |
|----|------|-------------------|---------------|-------------------|---------|

## Entry contract

- Assign the next sequential `EXP-NNN` identifier and record the run date.
- State one measurable, falsifiable hypothesis before execution.
- Preserve the exact command, configuration, data identity, and random seed.
- Record measured results with units and the supported, falsified, or
  inconclusive verdict.
- Explain how the result changes the next experiment.
"""

CLAIMS_REGISTRY = """\
# Claims Registry

> Every claim this project makes, with its evidence class and how to falsify it.
> Classes: **Established** (measured, reproducible) · **Supported** (measured once) ·
> **Working Hypothesis** (believed, untested) · **Falsified** (keep it — it's a result).

| Claim | Class | Evidence (experiment IDs) | Falsification condition |
|-------|-------|---------------------------|-------------------------|

Add a claim only when its class, evidence references, and falsification condition
are explicit. Keep falsified claims as durable negative evidence.
"""


def readme_content(
    project: str, profile_name: str, profile: Profile, package: str
) -> str:
    run_hint = {
        "cli": f"python -m {package} --help",
        "fastapi": f"uvicorn {package}.main:app --reload",
    }.get(profile_name, "python main.py")
    return f"""\
# {project}

`{project}` is a runnable `{profile_name}` Python project foundation generated by
RepoForge. Extend the working entry point with the product's domain behavior.

## Quickstart

```bash
# Windows
.venv\\Scripts\\activate
# macOS / Linux
source .venv/bin/activate

# Use the resolved lock when present (normal RepoForge run).
python -m pip install -r requirements.lock
# If setup intentionally skipped installation and no lock exists, use:
# python -m pip install -r requirements-dev.txt
python -m pip install --no-deps --editable .
{run_hint}
```

## Tests

```bash
pytest
```

## Project layout

Bootstrapped with RepoForge v{__version__} using the `{profile_name}` profile:
{profile.description}

`requirements.txt` records direct runtime inputs. `requirements-dev.txt` adds
development tools. A normal RepoForge run also writes `requirements.lock` from
the resolved environment; keep that file to reproduce the validated dependency set.

## Engineering standards

If this project includes an `AGENTS.md` pointer, use the installed
`wpai-constitution` skill to freeze and verify accepted
[WPAI Constitution]({CONSTITUTION_SOURCE}) for AI-assisted work. Law is not
copied into this project. Follow only the skill's permitted verified offline
fallback when GitHub is unavailable; pointer creation is not runtime acceptance.

---
_Generated by RepoForge v{__version__} — edit freely, this file is yours._
"""


def toml_array(values: tuple[str, ...]) -> str:
    """Render a compact TOML string array from trusted profile values."""
    return "[" + ", ".join(json.dumps(value) for value in values) + "]"


def pyproject_content(
    project: str, package: str, profile_name: str, profile: Profile
) -> str:
    description = json.dumps(
        f"Runnable {profile_name} Python foundation for {project}", ensure_ascii=False
    )
    packaging = (
        '[tool.setuptools]\npackage-dir = {"" = "src"}\n\n'
        '[tool.setuptools.packages.find]\nwhere = ["src"]\n'
        if profile.src_layout
        else '[tool.setuptools]\npy-modules = ["main"]\n'
    )
    script = (
        f'\n[project.scripts]\n{package} = "{package}.__main__:app"\n'
        if profile_name == "cli"
        else ""
    )
    return f"""\
[build-system]
requires = ["setuptools>=80,<81"]
build-backend = "setuptools.build_meta"

[project]
name = "{package}"
version = "0.1.0"
description = {description}
readme = "README.md"
requires-python = ">=3.10"
dependencies = {toml_array(profile.runtime_packages)}
{script}
[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E4", "E7", "E9", "F", "I", "B", "UP"]

[tool.black]
line-length = 100
target-version = ["py310"]

{packaging}"""


def sample_test_content(package: str, profile_name: str) -> str:
    if profile_name == "cli":
        return f"""\
\"\"\"Behavior test for the generated command-line entry point.\"\"\"

from typer.testing import CliRunner

from {package}.__main__ import app


runner = CliRunner()


def test_status_command_reports_ready():
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "{package} is ready"
"""
    if profile_name == "fastapi":
        return f"""\
\"\"\"Behavior test for the generated health endpoint.\"\"\"

from fastapi.testclient import TestClient

from {package}.main import app


def test_health_endpoint():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {{"status": "ok"}}
"""
    return """\
\"\"\"Behavior test for the generated project status entry point.\"\"\"

import main


def test_project_status_reports_ready():
    assert main.project_status()["status"] == "ready"
"""


def entry_module_content(profile_name: str, package: str) -> str:
    if profile_name == "cli":
        return f"""\
\"\"\"Entry point for the {package} CLI. Run: python -m {package} --help\"\"\"

import typer

app = typer.Typer(help="{package} command-line tool", no_args_is_help=True)


@app.callback()
def main() -> None:
    \"\"\"Run {package} commands.\"\"\"


@app.command()
def status() -> None:
    \"\"\"Confirm that the generated command-line foundation is operational.\"\"\"
    typer.echo("{package} is ready")


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


def main_module_content(project: str, profile_name: str) -> str:
    """Create a complete, testable entry point for non-src project profiles."""
    project_literal = json.dumps(project)
    profile_literal = json.dumps(profile_name)
    return f'''\
"""Generated project entry point."""


def project_status() -> dict[str, str]:
    """Return stable bootstrap metadata for health checks and tests."""
    return {{
        "project": {project_literal},
        "profile": {profile_literal},
        "status": "ready",
    }}


def main() -> None:
    """Print a concise operational status."""
    status = project_status()
    print(f"{{status['project']}} [{{status['profile']}}] is {{status['status']}}")


if __name__ == "__main__":
    main()
'''


# --------------------------------------------------------------------------- #
# Setup phases.                                                               #
# --------------------------------------------------------------------------- #


def scaffold_project(
    runner: Runner,
    target: Path,
    project: str,
    profile_name: str,
    license_choice: str,
    author: str,
    pre_commit: bool = False,
) -> None:
    profile = PROFILES[profile_name]
    package = package_name_from(project)

    runner.write(target / ".gitignore", GITIGNORE, "Writing .gitignore")
    runner.write(
        target / "requirements.txt",
        "\n".join(profile.runtime_packages)
        + ("\n" if profile.runtime_packages else ""),
        f"Writing requirements.txt ({profile_name}: "
        f"{len(profile.runtime_packages)} runtime packages)",
    )
    development_packages = list(profile.development_packages)
    if pre_commit:
        development_packages.append(PRE_COMMIT_REQUIREMENT)
    runner.write(
        target / "requirements-dev.txt",
        "-r requirements.txt\n" + "\n".join(development_packages) + "\n",
        f"Writing requirements-dev.txt ({len(development_packages)} "
        "development packages)",
    )
    runner.write(
        target / "README.md",
        readme_content(project, profile_name, profile, package),
        "Writing README.md",
    )
    runner.write(
        target / "pyproject.toml",
        pyproject_content(project, package, profile_name, profile),
        "Writing pyproject.toml",
    )

    if license_choice == "mit":
        runner.write(
            target / "LICENSE",
            MIT_LICENSE.format(
                year=datetime.now(timezone.utc).year, author=author or "the author"
            ),
            "Writing LICENSE (MIT)",
        )

    for directory in profile.dirs:
        runner.mkdir(target / directory, f"Creating {directory}/")
        ignored = directory in profile.ignored_dirs
        marker = ".gitignore" if ignored else ".gitkeep"
        content = "*\n!.gitignore\n" if ignored else ""
        runner.write(
            target / directory / marker,
            content,
            f"Preserving {directory}/ in Git"
            + (" while ignoring generated contents" if ignored else ""),
        )

    if profile.src_layout:
        pkg_dir = target / "src" / package
        runner.write(
            pkg_dir / "__init__.py",
            f'"""{package} package."""\n\n__version__ = "0.1.0"\n',
            f"Creating src/{package}/__init__.py",
        )
        entry_name = "main.py" if profile_name == "fastapi" else "__main__.py"
        runner.write(
            pkg_dir / entry_name,
            entry_module_content(profile_name, package),
            f"Creating src/{package}/{entry_name}",
        )
    else:
        runner.write(
            target / "main.py",
            main_module_content(project, profile_name),
            "Creating main.py",
        )

    runner.write(
        target / "tests" / "test_smoke.py",
        sample_test_content(package, profile_name),
        "Creating tests/test_smoke.py",
    )

    for extra in profile.extras:
        content = {
            "EXPERIMENT_LOG.md": EXPERIMENT_LOG,
            "CLAIMS.md": CLAIMS_REGISTRY,
        }[extra]
        runner.write(target / extra, content, f"Writing {extra}")


def setup_environment(
    runner: Runner, target: Path, venv_name: str, skip_install: bool
) -> None:
    """Create the environment, install the project, and capture a resolved lock."""
    venv_dir = target / venv_name
    if venv_dir.exists():
        print(f"  -- Virtual environment exists ({venv_name}/), reusing it")
    else:
        runner.run(
            [sys.executable, "-m", "venv", str(venv_dir)],
            f"Creating virtual environment ({venv_name}/)",
            cwd=target,
        )
    if skip_install:
        print("  -- Skipping dependency install (--skip-install)")
        return
    python = venv_python(venv_dir)
    runner.run(
        [str(python), "-m", "pip", "install", "--upgrade", "pip", "--quiet"],
        "Upgrading pip",
        cwd=target,
    )
    lock_path = target / "requirements.lock"
    use_existing_lock = lock_path.is_file() and not runner.force
    requirement_file = (
        "requirements.lock" if use_existing_lock else "requirements-dev.txt"
    )
    runner.run(
        [str(python), "-m", "pip", "install", "-r", requirement_file, "--quiet"],
        f"Installing dependencies from {requirement_file}",
        cwd=target,
    )
    runner.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--editable",
            ".",
            "--quiet",
        ],
        "Installing the generated project in editable mode",
        cwd=target,
    )
    if use_existing_lock:
        print("  -- Existing requirements.lock preserved and used")
        return

    frozen = runner.capture(
        [str(python), "-m", "pip", "freeze", "--local", "--exclude-editable"],
        "Resolving requirements.lock from the installed environment",
        cwd=target,
    )
    lock_content = ""
    if frozen is not None:
        lock_lines = sorted(
            (line.strip() for line in frozen.splitlines() if line.strip()),
            key=str.casefold,
        )
        lock_content = "\n".join(lock_lines) + ("\n" if lock_lines else "")
    runner.write(lock_path, lock_content, "Writing resolved requirements.lock")


def git_identity_ready(target: Path) -> bool:
    """True when git has a user.name and user.email available for commits."""
    if all(
        os.environ.get(name)
        for name in (
            "GIT_AUTHOR_NAME",
            "GIT_AUTHOR_EMAIL",
            "GIT_COMMITTER_NAME",
            "GIT_COMMITTER_EMAIL",
        )
    ):
        return True
    existing_repository = (target / ".git").exists()
    for key in ("user.name", "user.email"):
        command = ["git", "config"]
        if not existing_repository:
            command.append("--global")
        command.extend(("--get", key))
        try:
            probe = subprocess.run(
                command,
                cwd=str(target) if target.is_dir() else None,
                check=False,
                text=True,
                capture_output=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        if probe.returncode != 0 or not probe.stdout.strip():
            return False
    return True


def has_origin(target: Path) -> bool:
    """Return whether an existing independent repository has an origin."""
    if not (target / ".git").exists():
        return False
    try:
        probe = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=str(target),
            check=False,
            text=True,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return probe.returncode == 0 and bool(probe.stdout.strip())


def gh_authenticated() -> bool:
    """Return whether GitHub CLI has a usable github.com authentication context."""
    try:
        probe = subprocess.run(
            ["gh", "auth", "status", "--hostname", "github.com"],
            check=False,
            text=True,
            capture_output=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return probe.returncode == 0


def validate_venv_name(venv_name: str) -> None:
    """Reject virtual-environment names that can escape or alias the project root."""
    windows_stem = venv_name.split(".", 1)[0].casefold()
    if (
        not venv_name
        or venv_name in (".", "..")
        or re.fullmatch(r"[A-Za-z0-9._-]+", venv_name) is None
        or windows_stem in WINDOWS_RESERVED_NAMES
    ):
        raise ValueError(
            "--venv-name must be one safe directory name using letters, numbers, "
            "'.', '_', or '-'"
        )


def validate_run_preflight(
    target: Path,
    remote_url: str | None,
    *,
    dry_run: bool,
    commit: bool,
    create_remote: bool,
    push: bool,
    pre_commit: bool = False,
    skip_venv: bool = False,
    venv_name: str = ".venv",
    constitution_enabled: bool = True,
) -> None:
    """Reject impossible requests before RepoForge writes any project file."""
    if target.exists() and not target.is_dir():
        raise ValueError(f"Target exists and is not a directory: {target}")
    validate_venv_name(venv_name)
    if constitution_enabled and (target / "law" / "AGENTS-Constitution").exists():
        raise ValueError(
            "A retired vendored law tree remains at law/AGENTS-Constitution. "
            "Preserve and migrate it explicitly before enabling the pointer; "
            "--force will not delete it. --no-constitution opts out without "
            "removing or validating the existing tree."
        )
    origin_exists = has_origin(target)
    if push and not commit:
        raise ValueError(
            "--push requires the default initial commit; remove --no-commit"
        )
    if create_remote and not remote_url and not origin_exists:
        raise ValueError("--create-remote requires a repository name or --repo-url")
    if push and not remote_url and not origin_exists:
        raise ValueError(
            "--push requires a repository name, --repo-url, or existing origin"
        )
    if (
        create_remote
        and remote_url
        and not origin_exists
        and github_slug_from_remote(remote_url) is None
    ):
        raise ValueError("--create-remote supports GitHub HTTPS or SSH remotes only")
    if pre_commit and skip_venv and not venv_python(target / venv_name).is_file():
        raise ValueError(
            "--pre-commit with --skip-venv requires an existing virtual environment"
        )
    if dry_run:
        return
    if shutil.which("git") is None:
        raise ValueError("git is required but was not found on PATH")
    if commit and not git_identity_ready(target):
        raise ValueError(
            "git user.name/user.email are required for the initial commit; "
            "configure them or pass --no-commit"
        )
    if create_remote and not origin_exists:
        if shutil.which("gh") is None:
            raise ValueError("--create-remote requires the GitHub gh CLI")
        if not gh_authenticated():
            raise ValueError(
                "--create-remote requires an authenticated gh session for github.com"
            )


def generated_git_pathspecs(runner: Runner, target: Path) -> list[str]:
    """Return unique, project-relative pathspecs for files generated this run."""
    root = target.resolve()
    pathspecs: list[str] = []
    for path in runner.stage_paths:
        checked = runner.checked_path(path).resolve()
        try:
            relative = checked.relative_to(root).as_posix()
        except ValueError as error:
            raise ValueError(f"Generated path escaped project root: {path}") from error
        if relative not in pathspecs:
            pathspecs.append(relative)
    return pathspecs


def setup_git(
    runner: Runner,
    target: Path,
    remote_url: str | None,
    create_remote: bool,
    push: bool,
    commit: bool,
) -> None:
    if (target / ".git").exists():
        print("  -- Git repository exists, reusing it")
    else:
        runner.run(["git", "init"], "Initializing git repository", cwd=target)
        runner.run(
            ["git", "branch", "-M", "main"],
            "Setting primary branch to main",
            cwd=target,
        )

    pathspecs = generated_git_pathspecs(runner, target)
    if not commit:
        print(
            "  -- Initial commit disabled (--no-commit); "
            "generated files remain unstaged"
        )
    elif pathspecs:
        runner.run(
            ["git", "add", "--", *pathspecs],
            f"Staging {len(pathspecs)} generated path(s)",
            cwd=target,
        )
        if runner.dry_run:
            runner.run(
                ["git", "commit", "-m", "Initial commit (RepoForge)", "--", *pathspecs],
                "Creating initial commit",
                cwd=target,
            )
        else:
            staged = subprocess.run(
                ["git", "diff", "--cached", "--quiet", "--", *pathspecs],
                cwd=str(target),
                check=False,
            )
            if staged.returncode == 0:
                print("  -- Nothing generated is staged for commit")
            else:
                runner.run(
                    [
                        "git",
                        "commit",
                        "-m",
                        "Initial commit (RepoForge)",
                        "--",
                        *pathspecs,
                    ],
                    "Creating initial commit",
                    cwd=target,
                )
    else:
        print("  -- No generated files to stage")

    if not remote_url:
        print("  -- No remote requested (pass a repo name or --repo-url to add one)")
        return

    origin_exists = has_origin(target) if not runner.dry_run else False
    if origin_exists:
        print("  -- Remote 'origin' already configured, leaving it as is")
        if push:
            runner.run(
                ["git", "push", "-u", "origin", "HEAD"],
                "Pushing current branch to origin",
                cwd=target,
            )
        return

    if create_remote:
        slug = github_slug_from_remote(remote_url)
        if slug is None:
            raise ValueError("Unable to derive a GitHub owner/repository slug")
        command = [
            "gh",
            "repo",
            "create",
            slug,
            "--private",
            "--source",
            ".",
            "--remote",
            "origin",
        ]
        if push:
            command.append("--push")
        runner.run(command, f"Creating GitHub repo {slug} via gh CLI", cwd=target)
        return

    runner.run(
        ["git", "remote", "add", "origin", remote_url],
        f"Linking remote {remote_url}",
        cwd=target,
    )
    if push:
        runner.run(
            ["git", "push", "-u", "origin", "HEAD"],
            "Pushing current branch to origin",
            cwd=target,
        )


def setup_pre_commit(runner: Runner, target: Path, venv_name: str) -> None:
    """Write the hook contract and install the pinned pre-commit runner."""
    runner.write(
        target / ".pre-commit-config.yaml",
        PRE_COMMIT_CONFIG,
        "Writing .pre-commit-config.yaml",
    )
    python = venv_python(target / venv_name)
    if not runner.dry_run and not python.is_file():
        raise ValueError(
            "Virtual-environment Python is missing; cannot install pre-commit: "
            f"{python}"
        )
    runner.run(
        [str(python), "-m", "pip", "install", PRE_COMMIT_REQUIREMENT, "--quiet"],
        f"Installing {PRE_COMMIT_REQUIREMENT} into the venv",
        cwd=target,
    )


def activate_pre_commit(runner: Runner, target: Path, venv_name: str) -> None:
    """Activate hooks after Git has committed the generated hook configuration."""
    python = venv_python(target / venv_name)
    runner.run(
        [str(python), "-m", "pre_commit", "install"],
        "Activating pre-commit hooks",
        cwd=target,
    )


# --------------------------------------------------------------------------- #
# CLI.                                                                        #
# --------------------------------------------------------------------------- #


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    defaults = load_defaults()
    parser = argparse.ArgumentParser(
        prog="repoforge",
        description=(
            "Bootstrap a production-ready Python project foundation in one command."
        ),
        epilog="Profiles: " + ", ".join(PROFILES) + ".  "
        "Use --list-profiles for details.",
    )
    parser.add_argument(
        "repo_name",
        nargs="?",
        help="Repo slug (my-tool), owner/slug, or full git URL. "
        "Omit to skip the remote.",
    )
    parser.add_argument("--repo-url", help="Explicit remote URL (overrides repo_name).")
    parser.add_argument(
        "--directory",
        "-d",
        default=".",
        help="Target directory (default: current directory).",
    )
    parser.add_argument(
        "--profile",
        "-p",
        default=defaults.get("profile", "general"),
        choices=sorted(PROFILES),
        help="Project profile (default: %(default)s).",
    )
    parser.add_argument(
        "--owner",
        default=defaults.get("owner"),
        help="GitHub owner used to expand bare repo slugs.",
    )
    parser.add_argument(
        "--author",
        default=defaults.get("author"),
        help="Name used in the LICENSE file.",
    )
    parser.add_argument(
        "--license",
        default=defaults.get("license", "mit"),
        choices=["mit", "none"],
        help="License to scaffold (default: %(default)s).",
    )
    parser.add_argument(
        "--venv-name", default=".venv", help="Virtual environment directory name."
    )
    parser.add_argument(
        "--skip-venv", action="store_true", help="Skip virtual environment creation."
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Create the venv but skip installing dependencies.",
    )
    parser.add_argument(
        "--pre-commit",
        action="store_true",
        help="Scaffold and install pre-commit hooks (ruff + black).",
    )
    parser.add_argument(
        "--create-remote",
        action="store_true",
        help="Create the GitHub repository via the gh CLI.",
    )
    parser.add_argument(
        "--push", action="store_true", help="Push the initial commit to origin."
    )
    parser.add_argument(
        "--no-commit",
        action="store_true",
        help="Initialize Git but leave generated files unstaged and uncommitted.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite files RepoForge would otherwise leave alone.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the full plan without changing anything.",
    )
    parser.add_argument(
        "--constitution",
        metavar="PATH",
        help="Retired local-pack selector; remove it to use the canonical pointer.",
    )
    parser.add_argument(
        "--constitution-vendor",
        action="store_true",
        help="Retired; editable law vendoring is rejected before writes.",
    )
    parser.add_argument(
        "--no-constitution",
        action="store_true",
        help="Do not create a WPAI Constitution pointer; ignore stale path settings.",
    )
    parser.add_argument(
        "--save-defaults",
        action="store_true",
        help="Remember --owner/--author/--license/--profile in ~/.repoforge.json.",
    )
    parser.add_argument(
        "--list-profiles", action="store_true", help="Show all profiles and exit."
    )
    parser.add_argument(
        "--version", action="version", version=f"RepoForge {__version__}"
    )
    parser.set_defaults(saved_constitution_path=defaults.get(RETIRED_CONFIG_KEY))
    return parser.parse_args(argv)


def list_profiles() -> None:
    width = max(len(name) for name in PROFILES)
    print("Available profiles:\n")
    for name, profile in PROFILES.items():
        print(f"  {name:<{width}}  {profile.description}")
        print(f"  {'':<{width}}  packages: {', '.join(profile.packages)}\n")


def main(argv: list[str] | None = None) -> None:
    if sys.version_info < MINIMUM_PYTHON:
        required = ".".join(str(part) for part in MINIMUM_PYTHON)
        print(f"Error: RepoForge {__version__} requires Python {required} or newer")
        sys.exit(2)

    args = parse_args(argv)
    constitution_enabled = not args.no_constitution
    try:
        validate_constitution_options(
            args.constitution,
            vendor=args.constitution_vendor,
            enabled=constitution_enabled,
            saved_path=args.saved_constitution_path,
        )
    except ValueError as error:
        print(f"Error: {error}")
        sys.exit(2)

    if args.list_profiles:
        if args.save_defaults:
            save_defaults(
                {
                    "owner": args.owner,
                    "author": args.author,
                    "license": args.license,
                    "profile": args.profile,
                },
                dry_run=args.dry_run,
            )
        list_profiles()
        return

    try:
        remote_url = build_remote_url(args.repo_name, args.repo_url, args.owner)
    except ValueError as error:
        print(f"Error: {error}")
        sys.exit(2)

    target = Path(args.directory).resolve()
    project = (
        args.repo_name.split("/")[-1].removesuffix(".git")
        if args.repo_name and not args.repo_name.startswith(REMOTE_URL_PREFIXES)
        else target.name
    )
    if not project.strip():
        print(
            "Error: Unable to derive a project name; pass a repo name or "
            "target directory"
        )
        sys.exit(2)

    try:
        validate_run_preflight(
            target,
            remote_url,
            dry_run=args.dry_run,
            commit=not args.no_commit,
            create_remote=args.create_remote,
            push=args.push,
            pre_commit=args.pre_commit,
            skip_venv=args.skip_venv,
            venv_name=args.venv_name,
            constitution_enabled=constitution_enabled,
        )
    except ValueError as error:
        print(f"Error: {error}")
        sys.exit(2)

    if args.save_defaults:
        save_defaults(
            {
                "owner": args.owner,
                "author": args.author,
                "license": args.license,
                "profile": args.profile,
            },
            dry_run=args.dry_run,
        )

    runner = Runner(dry_run=args.dry_run, force=args.force, root=target)
    mode = " (dry run)" if args.dry_run else ""
    print(f"RepoForge {__version__}{mode}")
    print(f"Project:   {project}  [{args.profile}]")
    print(f"Directory: {target}")
    print(f"Remote:    {remote_url or '(none)'}")
    if constitution_enabled:
        print(f"Constitution: {CONSTITUTION_SOURCE}  [pointer only]")
    else:
        print("Constitution: disabled")
    print()

    if not args.dry_run:
        target.mkdir(parents=True, exist_ok=True)

    print("[1/6] Scaffolding")
    scaffold_project(
        runner,
        target,
        project,
        args.profile,
        args.license,
        args.author or "",
        pre_commit=args.pre_commit,
    )

    print("\n[2/6] WPAI Constitution")
    pointer_installed = setup_constitution(
        runner,
        target,
        enabled=constitution_enabled,
    )

    print("\n[3/6] Environment")
    if args.skip_venv:
        print("  -- Skipping virtual environment (--skip-venv)")
    else:
        setup_environment(runner, target, args.venv_name, args.skip_install)

    print("\n[4/6] Quality configuration")
    if args.pre_commit:
        setup_pre_commit(runner, target, args.venv_name)
    else:
        print("  -- Pre-commit not requested (add --pre-commit to enable)")

    print("\n[5/6] Git")
    setup_git(
        runner,
        target,
        remote_url,
        args.create_remote,
        args.push,
        commit=not args.no_commit,
    )

    print("\n[6/6] Quality hook activation")
    if args.pre_commit:
        activate_pre_commit(runner, target, args.venv_name)
    else:
        print("  -- No hooks to activate")

    print(f"\n[SUCCESS] {project} is ready{mode}.")
    if runner.skipped:
        print(
            f"Left untouched (already existed): {len(runner.skipped)} file(s). "
            f"Use --force to overwrite."
        )
    activate = (
        f"{args.venv_name}\\Scripts\\activate"
        if sys.platform == "win32"
        else f"source {args.venv_name}/bin/activate"
    )
    if args.skip_venv:
        print(
            f"Next: cd {target} and create an environment, install "
            "requirements-dev.txt, install the project editable, then run pytest"
        )
    elif args.skip_install:
        print(
            f"Next: cd {target}  &&  {activate}  &&  "
            "python -m pip install -r requirements-dev.txt  &&  "
            "python -m pip install --no-deps --editable .  &&  pytest"
        )
    else:
        print(f"Next: cd {target}  &&  {activate}  &&  pytest")
    if pointer_installed:
        print("       AI agents: verify accepted WPAI Constitution via AGENTS.md.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        print(f"Error: {error}")
        sys.exit(1)
