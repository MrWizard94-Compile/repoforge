# RepoForge Pro — Gumroad Listing Kit

## Product name
**RepoForge Pro — One-Command Python Project Bootstrapper**

## Subtitle / tagline
Stop copy-pasting your last project's setup. One command: venv, curated deps for
your project type, git, GitHub remote, tests, hooks — done.

## Price
- Launch: **$14** (first 2 weeks, "launch price" badge)
- Standard: **$19**
- Suggested tip-enabled "pay what you want above $14" is an option for launch week only.

## Cover image
`RepoForgeALT.png` (already in this folder). Add 2–3 screenshots: terminal run of
`repoforge.py my-api --profile fastapi`, `--list-profiles` output, and the resulting
project tree in VS Code.

## Description (paste into Gumroad)

---

**Every new Python project starts with the same 20 minutes of ritual.** Make the venv.
Copy a .gitignore from the last repo. Pip install the usual suspects. git init, branch
-M main, first commit, create the GitHub repo, add the remote... You've done it a
hundred times. That's the problem.

**RepoForge Pro does it in one command:**

```
python repoforge.py my-api --profile fastapi --pre-commit --create-remote --push
```

Sixty seconds later you have a working FastAPI project: virtual environment, curated
dependencies, src/ layout with a running /health endpoint, README, MIT license,
pyproject.toml, a passing pytest suite, ruff+black pre-commit hooks, and a private
GitHub repo with your first commit already pushed.

**Seven battle-tested profiles** — not a blank template, an opinionated setup per
project *type*: `minimal` · `general` · `cli` (Typer) · `fastapi` · `data` ·
`ml-experiment` · `automation`

The `ml-experiment` profile is one you won't find anywhere else: experiment and claims
registries with falsification-condition discipline, from a real AI research workflow —
your future self will know exactly which run produced which number.

**Built like a real tool, because it is one:**
- Standard library only — nothing to install, one file you can read and modify
- Idempotent — re-run safely, your files are never overwritten
- `--dry-run` shows the full plan without touching anything
- Saved defaults (`--save-defaults`): set your GitHub owner and license once
- Ships with its own 23-test pytest suite
- Windows, macOS, Linux · Python 3.9+

**What you get:** `repoforge.py`, full test suite, documentation, personal license
(unlimited use on your own projects, commercial included).

*Try RepoForge Lite free (link) — if it saves you time, Pro is the version that saves
you the other 15 minutes.*

---

## Tags (Gumroad)
python, developer tools, cli, automation, boilerplate, project template, git, productivity

## FAQ block
- **Refunds?** 14 days, no questions — if it doesn't fit your workflow, get your money back.
- **Updates?** v1.x updates are free; you'll get Gumroad notifications.
- **Team use?** One license per developer; contact for team pricing.

## Launch checklist
1. Upload zip: `repoforge.py`, `tests/`, `README.md`, `LICENSE.txt` (exclude Lite + this file + PNG source).
2. Publish Lite to a public GitHub repo (MIT) with README pointing to the Gumroad page — this is the funnel and the trust signal.
3. Enable Gumroad email collection + a 10%-off follow-up for Lite users.
4. Launch posts (value-first, no spam): r/Python "Saturday showcase" thread, dev.to
   walkthrough ("what my bootstrapper does that uv init doesn't"), Hacker News Show HN
   (Tue–Thu, ~9am ET). Lead with the free Lite version everywhere; mention Pro once.
