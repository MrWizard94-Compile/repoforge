#!/usr/bin/env python3
"""
RepoForge Lite — free Python project bootstrapper.

One command: git repo + virtual environment + sensible .gitignore + starter
README + dependency install + GitHub remote link.

    python repoforge_lite.py my-project --owner YOUR_GITHUB_NAME

Standard library only, Python 3.9+, Windows/macOS/Linux.

Want project-type profiles (cli / fastapi / data / ml-experiment / automation),
LICENSE + pyproject + test scaffolding, pre-commit hooks, `gh` repo creation,
saved defaults, --dry-run, and a full test suite? That's RepoForge Pro.

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
import subprocess
import sys
from pathlib import Path

PACKAGES = ["requests", "python-dotenv", "rich", "pytest"]

GITIGNORE = """\
.venv/
venv/
.env
__pycache__/
*.py[cod]
.pytest_cache/
.idea/
.vscode/
.DS_Store
*.log
"""


def run(command, description, cwd, fatal=True):
    print(f"  -> {description}")
    try:
        subprocess.run(command, cwd=str(cwd), check=True, text=True,
                       capture_output=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as error:
        detail = ""
        if isinstance(error, subprocess.CalledProcessError):
            detail = (error.stderr or "").strip().splitlines()
            detail = detail[0] if detail else ""
        print(f"  !! Failed: {description}" + (f" — {detail}" if detail else ""))
        if fatal:
            sys.exit(1)
        return False


def remote_url_from(name, owner):
    if not name:
        return None
    if name.startswith(("https://", "http://", "git@")):
        return name
    if "/" in name:
        return f"https://github.com/{name}.git"
    if not owner:
        print("Error: bare repo names need --owner YOUR_GITHUB_NAME "
              "(or pass owner/name).")
        sys.exit(2)
    return f"https://github.com/{owner}/{name}.git"


def main():
    parser = argparse.ArgumentParser(
        prog="repoforge-lite",
        description="Bootstrap a Python project: git + venv + deps + remote.",
        epilog="Profiles, scaffolding, pre-commit, gh integration and more "
               "live in RepoForge Pro.",
    )
    parser.add_argument("repo_name", nargs="?",
                        help="Repo slug, owner/slug, or full git URL. "
                             "Omit for a local-only repo.")
    parser.add_argument("--owner", help="GitHub owner for bare repo slugs.")
    parser.add_argument("--directory", "-d", default=".")
    parser.add_argument("--skip-install", action="store_true",
                        help="Skip installing the starter dependencies.")
    args = parser.parse_args()

    target = Path(args.directory).resolve()
    target.mkdir(parents=True, exist_ok=True)
    remote = remote_url_from(args.repo_name, args.owner)
    name = target.name if not args.repo_name else \
        args.repo_name.split("/")[-1].removesuffix(".git")

    print(f"RepoForge Lite — {name}\n")

    gitignore = target / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(GITIGNORE, encoding="utf-8")
        print("  -> Writing .gitignore")
    requirements = target / "requirements.txt"
    if not requirements.exists():
        requirements.write_text("\n".join(PACKAGES) + "\n", encoding="utf-8")
        print("  -> Writing requirements.txt")
    readme = target / "README.md"
    if not readme.exists():
        readme.write_text(f"# {name}\n\n<!-- What this project does. -->\n",
                          encoding="utf-8")
        print("  -> Writing README.md")

    venv_dir = target / ".venv"
    if not venv_dir.exists():
        run([sys.executable, "-m", "venv", str(venv_dir)],
            "Creating virtual environment", target)
    python = venv_dir / ("Scripts/python.exe" if sys.platform == "win32"
                         else "bin/python")
    if not args.skip_install:
        run([str(python), "-m", "pip", "install", "--upgrade", "pip", "--quiet"],
            "Upgrading pip", target)
        run([str(python), "-m", "pip", "install", "-r", "requirements.txt",
             "--quiet"], "Installing starter dependencies", target)

    if not (target / ".git").exists():
        run(["git", "init"], "Initializing git repository", target)
        run(["git", "branch", "-M", "main"], "Setting branch to main", target)
    run(["git", "add", "."], "Staging files", target)
    if subprocess.run(["git", "diff", "--cached", "--quiet"],
                      cwd=str(target)).returncode != 0:
        run(["git", "commit", "-m", "Initial commit"], "Creating initial commit",
            target, fatal=False)
    if remote and subprocess.run(["git", "remote", "get-url", "origin"],
                                 cwd=str(target),
                                 capture_output=True).returncode != 0:
        run(["git", "remote", "add", "origin", remote],
            f"Linking remote {remote}", target)

    print(f"\n[SUCCESS] {name} is ready.")
    print("Liked this? RepoForge Pro adds project-type profiles, full "
          "scaffolding,\npre-commit hooks, gh repo creation, and a test suite.")


if __name__ == "__main__":
    main()
