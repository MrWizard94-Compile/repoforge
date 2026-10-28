#!/usr/bin/env python3
"""RepoForge Lite — safe, standalone Python project bootstrapper.

One command creates a runnable local foundation with an isolated environment,
separated dependency inputs, a resolved lock, installable project metadata, a
behavior test, scoped Git commit, and an optional existing GitHub remote link.

    python repoforge_lite.py --directory my-project
    python repoforge_lite.py my-project --owner YOUR_GITHUB_NAME
    python repoforge_lite.py --directory my-project --dry-run

RepoForge Lite has no third-party runtime dependencies and supports Python 3.10+
on Windows, macOS, and Linux.

MIT License — Copyright (c) 2026 MrWizard94.
Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
of the Software, and to permit persons to whom the Software is furnished to do
so, subject to the following conditions: The above copyright notice and this
permission notice shall be included in all copies or substantial portions of
the Software. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.
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
from dataclasses import dataclass, field
from pathlib import Path

__version__ = "1.1.0"
MINIMUM_PYTHON = (3, 10)
RUNTIME_PACKAGES = ("requests", "python-dotenv", "rich")
DEVELOPMENT_PACKAGES = ("pytest",)
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

GITIGNORE = """\
# Environments and local configuration
.venv/
venv/
.env
.env.*

# Python build and tool state
__pycache__/
*.py[cod]
*.egg-info/
build/
dist/
.pytest_cache/
.ruff_cache/
.coverage

# Editors, operating systems, and logs
.idea/
.vscode/
.DS_Store
Thumbs.db
*.log
"""


@dataclass
class Runner:
    """Perform mutations through one path-confined, dry-run-aware boundary."""

    root: Path
    dry_run: bool = False
    force: bool = False
    skipped: list[str] = field(default_factory=list)
    stage_paths: list[Path] = field(default_factory=list)

    def checked_path(self, path: Path) -> Path:
        """Return *path* only when it resolves inside the project root."""
        root = self.root.resolve()
        candidate = path.resolve()
        try:
            candidate.relative_to(root)
        except ValueError as error:
            raise ValueError(
                f"Refusing to write outside the project directory: {path}"
            ) from error
        return path

    def track(self, path: Path) -> None:
        """Record a generated path once for precise Git staging."""
        checked = self.checked_path(path)
        if checked not in self.stage_paths:
            self.stage_paths.append(checked)

    def write(self, path: Path, content: str, description: str) -> bool:
        """Write one generated file while preserving existing work by default."""
        path = self.checked_path(path)
        if path.exists() and not self.force:
            self.skipped.append(str(path))
            print(f"  -- {description}: exists, left untouched ({path.name})")
            return False
        print(f"  -> {description}")
        self.track(path)
        if not self.dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return True

    def run(self, command: list[str], description: str, cwd: Path) -> None:
        """Run a required subprocess or terminate with a concise error."""
        print(f"  -> {description}")
        if self.dry_run:
            print(f"     [dry-run] {' '.join(command)}")
            return
        try:
            result = subprocess.run(
                command,
                cwd=str(cwd),
                check=True,
                text=True,
                capture_output=True,
            )
        except FileNotFoundError as error:
            raise RuntimeError(
                f"{command[0]!r} is not installed or not on PATH"
            ) from error
        except subprocess.CalledProcessError as error:
            detail = (error.stderr or error.stdout or "").strip().splitlines()
            reason = detail[0] if detail else f"exit code {error.returncode}"
            raise RuntimeError(f"{description} failed: {reason}") from error
        output = (result.stdout or "").strip().splitlines()
        if output:
            print(f"     {output[0]}")

    def capture(self, command: list[str], description: str, cwd: Path) -> str | None:
        """Run a required command and return stdout without breaking dry-run."""
        print(f"  -> {description}")
        if self.dry_run:
            print(f"     [dry-run] {' '.join(command)}")
            return None
        try:
            result = subprocess.run(
                command,
                cwd=str(cwd),
                check=True,
                text=True,
                capture_output=True,
            )
        except FileNotFoundError as error:
            raise RuntimeError(
                f"{command[0]!r} is not installed or not on PATH"
            ) from error
        except subprocess.CalledProcessError as error:
            detail = (error.stderr or error.stdout or "").strip().splitlines()
            reason = detail[0] if detail else f"exit code {error.returncode}"
            raise RuntimeError(f"{description} failed: {reason}") from error
        return result.stdout


def remote_url_from(name: str | None, owner: str | None) -> str | None:
    """Resolve an optional positional remote without invoking a shell."""
    if name is None:
        return None
    cleaned = name.strip()
    if not cleaned:
        raise ValueError("Repository name cannot be blank")
    if cleaned.startswith(REMOTE_URL_PREFIXES):
        return cleaned
    if "/" in cleaned:
        if GITHUB_SLUG_PATTERN.fullmatch(cleaned) is None:
            raise ValueError("GitHub names must use the form owner/repository")
        return f"https://github.com/{cleaned}.git"
    if not owner:
        raise ValueError(
            "A bare repository name requires --owner YOUR_GITHUB_NAME "
            "or an explicit owner/repository value"
        )
    slug = f"{owner.strip()}/{cleaned}"
    if GITHUB_SLUG_PATTERN.fullmatch(slug) is None:
        raise ValueError("GitHub owner and repository names contain invalid characters")
    return f"https://github.com/{slug}.git"


def package_name_from(project: str) -> str:
    """Derive a portable Python module name from the project name."""
    name = re.sub(r"[^0-9a-zA-Z_]+", "_", project.strip().lower()).strip("_")
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
    """Return the virtual environment interpreter path for this platform."""
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def has_origin(target: Path) -> bool:
    """Return whether an existing independent repository has an origin URL."""
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


def git_identity_ready(target: Path) -> bool:
    """Return whether a complete author/committer identity is available."""
    environment_keys = (
        "GIT_AUTHOR_NAME",
        "GIT_AUTHOR_EMAIL",
        "GIT_COMMITTER_NAME",
        "GIT_COMMITTER_EMAIL",
    )
    if all(os.environ.get(key) for key in environment_keys):
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


def validate_preflight(target: Path, *, dry_run: bool, commit: bool) -> None:
    """Reject invalid local state before creating project files."""
    if target.exists() and not target.is_dir():
        raise ValueError(f"Target exists and is not a directory: {target}")
    if dry_run:
        return
    if shutil.which("git") is None:
        raise ValueError("git is required but was not found on PATH")
    if commit and not git_identity_ready(target):
        raise ValueError(
            "git user.name/user.email are required; configure them or pass --no-commit"
        )


def readme_content(project: str) -> str:
    """Return the generated project quickstart."""
    return f"""\
# {project}

`{project}` is a runnable Python project foundation generated by RepoForge Lite.

## Setup

```bash
# Windows
.venv\\Scripts\\activate
# macOS / Linux
source .venv/bin/activate

python -m pip install -r requirements.lock
python -m pip install --no-deps --editable .
pytest
python main.py
```

If setup intentionally skipped dependency installation and no lock exists, install
`requirements-dev.txt` before installing the project editable.

---

_Generated by RepoForge Lite v{__version__}._
"""


def main_module_content(project: str) -> str:
    """Return a complete, testable entry module."""
    project_literal = json.dumps(project)
    return f'''\
"""Generated project entry point."""


def project_status() -> dict[str, str]:
    """Return stable bootstrap metadata for health checks and tests."""
    return {{"project": {project_literal}, "status": "ready"}}


def main() -> None:
    """Print a concise operational status."""
    status = project_status()
    print(f"{{status['project']}} is {{status['status']}}")


if __name__ == "__main__":
    main()
'''


def pyproject_content(project: str, package: str) -> str:
    """Return installable PEP 621 metadata for the generated single-module project."""
    description = json.dumps(
        f"Runnable Python foundation for {project}", ensure_ascii=False
    )
    dependencies = (
        "[" + ", ".join(json.dumps(value) for value in RUNTIME_PACKAGES) + "]"
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
dependencies = {dependencies}

[tool.pytest.ini_options]
addopts = ["-ra", "--strict-config", "--strict-markers"]
testpaths = ["tests"]
filterwarnings = ["error"]

[tool.setuptools]
py-modules = ["main"]
"""


SMOKE_TEST = """\
\"\"\"Behavior test for the generated project status entry point.\"\"\"

import main


def test_project_status_reports_ready():
    assert main.project_status()["status"] == "ready"
"""


def scaffold(runner: Runner, target: Path, project: str) -> None:
    """Write the complete Lite project foundation."""
    package = package_name_from(project)
    runner.write(target / ".gitignore", GITIGNORE, "Writing .gitignore")
    runner.write(
        target / "requirements.txt",
        "\n".join(RUNTIME_PACKAGES) + "\n",
        "Writing runtime requirements",
    )
    runner.write(
        target / "requirements-dev.txt",
        "-r requirements.txt\n" + "\n".join(DEVELOPMENT_PACKAGES) + "\n",
        "Writing development requirements",
    )
    runner.write(target / "README.md", readme_content(project), "Writing README.md")
    runner.write(target / "main.py", main_module_content(project), "Writing main.py")
    runner.write(
        target / "pyproject.toml",
        pyproject_content(project, package),
        "Writing pyproject.toml",
    )
    runner.write(
        target / "tests" / "test_smoke.py",
        SMOKE_TEST,
        "Writing behavior test",
    )


def setup_environment(
    runner: Runner, target: Path, *, skip_venv: bool, skip_install: bool
) -> None:
    """Create/install the environment and capture a resolved dependency lock."""
    if skip_venv:
        print("  -- Skipping virtual environment (--skip-venv)")
        return
    venv_dir = target / ".venv"
    if venv_dir.exists():
        print("  -- Virtual environment exists, reusing it")
    else:
        runner.run(
            [sys.executable, "-m", "venv", str(venv_dir)],
            "Creating virtual environment",
            target,
        )
    if skip_install:
        print("  -- Skipping dependency install (--skip-install)")
        return

    python = venv_python(venv_dir)
    runner.run(
        [str(python), "-m", "pip", "install", "--upgrade", "pip", "--quiet"],
        "Upgrading pip",
        target,
    )
    lock_path = target / "requirements.lock"
    use_lock = lock_path.is_file() and not runner.force
    requirement_file = "requirements.lock" if use_lock else "requirements-dev.txt"
    runner.run(
        [str(python), "-m", "pip", "install", "-r", requirement_file, "--quiet"],
        f"Installing dependencies from {requirement_file}",
        target,
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
        target,
    )
    if use_lock:
        print("  -- Existing requirements.lock preserved and used")
        return
    frozen = runner.capture(
        [str(python), "-m", "pip", "freeze", "--local", "--exclude-editable"],
        "Resolving requirements.lock",
        target,
    )
    lines = (
        sorted(
            (line.strip() for line in frozen.splitlines() if line.strip()),
            key=str.casefold,
        )
        if frozen is not None
        else []
    )
    runner.write(
        lock_path,
        "\n".join(lines) + ("\n" if lines else ""),
        "Writing resolved requirements.lock",
    )


def generated_pathspecs(runner: Runner, target: Path) -> list[str]:
    """Return unique project-relative paths generated during this run."""
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
    remote: str | None,
    *,
    commit: bool,
) -> None:
    """Initialize Git and commit only files generated by RepoForge Lite."""
    if (target / ".git").exists():
        print("  -- Git repository exists, reusing it")
    else:
        runner.run(["git", "init"], "Initializing Git repository", target)
        runner.run(["git", "branch", "-M", "main"], "Setting branch to main", target)

    pathspecs = generated_pathspecs(runner, target)
    if not commit:
        print("  -- Initial commit disabled; generated files remain unstaged")
    elif pathspecs:
        runner.run(
            ["git", "add", "--", *pathspecs],
            f"Staging {len(pathspecs)} generated path(s)",
            target,
        )
        if runner.dry_run:
            runner.run(
                [
                    "git",
                    "commit",
                    "-m",
                    "Initial commit (RepoForge Lite)",
                    "--",
                    *pathspecs,
                ],
                "Creating scoped initial commit",
                target,
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
                        "Initial commit (RepoForge Lite)",
                        "--",
                        *pathspecs,
                    ],
                    "Creating scoped initial commit",
                    target,
                )
    else:
        print("  -- No generated files to stage")

    if remote is None:
        print("  -- No remote requested")
    elif has_origin(target):
        print("  -- Existing origin preserved")
    else:
        runner.run(
            ["git", "remote", "add", "origin", remote],
            f"Linking remote {remote}",
            target,
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the public Lite command-line contract."""
    parser = argparse.ArgumentParser(
        prog="repoforge-lite",
        description="Bootstrap a safe, runnable Python project foundation.",
        epilog=(
            "Profiles, WPAI Constitution pointers, pinned hooks, saved defaults, "
            "and GitHub repository creation live in RepoForge Pro."
        ),
    )
    parser.add_argument(
        "repo_name",
        nargs="?",
        help="Repository slug, owner/slug, or full Git URL; omit for local-only",
    )
    parser.add_argument("--owner", help="GitHub owner for a bare repository slug")
    parser.add_argument(
        "--directory",
        "-d",
        help="Target directory (default: repository slug, or current directory)",
    )
    parser.add_argument(
        "--skip-venv", action="store_true", help="Skip virtual-environment creation"
    )
    parser.add_argument(
        "--skip-install", action="store_true", help="Skip dependency installation"
    )
    parser.add_argument(
        "--no-commit",
        action="store_true",
        help="Initialize Git but leave generated files unstaged",
    )
    parser.add_argument(
        "--force", action="store_true", help="Overwrite generated-path files"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the plan without changing anything",
    )
    parser.add_argument(
        "--version", action="version", version=f"RepoForge Lite {__version__}"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Run the complete Lite bootstrap workflow."""
    if sys.version_info < MINIMUM_PYTHON:
        required = ".".join(str(part) for part in MINIMUM_PYTHON)
        raise ValueError(f"RepoForge Lite requires Python {required} or newer")
    args = parse_args(argv)
    remote = remote_url_from(args.repo_name, args.owner)
    repository_project = (
        args.repo_name.split("/")[-1].removesuffix(".git")
        if args.repo_name and not args.repo_name.startswith(REMOTE_URL_PREFIXES)
        else None
    )
    target = Path(args.directory or repository_project or ".").resolve()
    project = repository_project or target.name
    if not project.strip():
        raise ValueError(
            "Unable to derive a project name; pass a repository name or "
            "target directory"
        )
    validate_preflight(target, dry_run=args.dry_run, commit=not args.no_commit)

    runner = Runner(root=target, dry_run=args.dry_run, force=args.force)
    mode = " (dry run)" if args.dry_run else ""
    print(f"RepoForge Lite {__version__}{mode}")
    print(f"Project:   {project}")
    print(f"Directory: {target}")
    print(f"Remote:    {remote or '(none)'}\n")
    if not args.dry_run:
        target.mkdir(parents=True, exist_ok=True)

    print("[1/3] Project foundation")
    scaffold(runner, target, project)
    print("\n[2/3] Environment")
    setup_environment(
        runner,
        target,
        skip_venv=args.skip_venv,
        skip_install=args.skip_install,
    )
    print("\n[3/3] Git")
    setup_git(runner, target, remote, commit=not args.no_commit)

    print(f"\n[SUCCESS] {project} is ready{mode}.")
    if runner.skipped:
        print(
            f"Left untouched: {len(runner.skipped)} existing file(s). "
            "Use --force only when replacement is intended."
        )
    print(
        "RepoForge Pro adds project profiles, WPAI Constitution pointers, "
        "pinned hooks, saved defaults, private GitHub creation, and push."
    )


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Error: {error}")
        sys.exit(1)
