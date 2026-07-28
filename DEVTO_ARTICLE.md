---
title: What my project bootstrapper does that `uv init` doesn't (and why I stopped using cookiecutter)
tags: python, productivity, devtools, showdev
cover_image: <upload RepoForgeALT.png and paste the dev.to URL here>
---

## The 20-minute tax

Every new Python project, same liturgy:

```bash
python -m venv .venv
.venv\Scripts\activate          # I'm on Windows, hold your condolences
# go find the .gitignore from the last project, copy it, wonder if it was the good one
pip install requests python-dotenv rich pytest   # the usual suspects
git init
git branch -M main
git add . && git commit -m "Initial commit"
# alt-tab to browser, create the GitHub repo, copy the URL
git remote add origin https://github.com/me/thing.git
git push -u origin main
# ...now what was I actually going to build?
```

None of this is hard. All of it is friction. And I noticed something worse than the
lost 20 minutes: I was procrastinating on *starting things* because of it. For a
side-project developer with a family and maybe eight good hours a week, the setup tax
isn't an annoyance - it's a filter that kills small ideas before they exist.

So I did what we all do: wrote a script. Then, because the script was genuinely useful,
I did the less common thing: turned it into a real tool with tests and opinions. This
post is about the three design decisions that mattered.

## "Project setup" is three different jobs

We say "setup" like it's one thing. It's three:

1. **Environment** - venv, dependencies, interpreter wiring.
2. **Plumbing** - git init, branch naming, first commit, the remote, hooks.
3. **Opinions** - layout, license, pyproject, test scaffold, what "done" looks like.

`uv init` does job 1 beautifully, and if that's all you need, use it and close this
tab. Cookiecutter does job 3 - *if* you enjoy maintaining Jinja templates in a
separate repo, which past-me apparently thought he would. (Narrator: he did not. The
template rotted in four months.)

Almost nothing does job 2, which is strange, because job 2 is the part that's pure
ritual - there are no interesting decisions in `git branch -M main`. RepoForge does
all three in one command:

```bash
python repoforge.py my-api --profile fastapi --pre-commit --create-remote --push
```

Sixty seconds later: venv, curated deps, `src/` layout with a running `/health`
endpoint, README, license, `pyproject.toml`, a passing pytest suite, ruff+black
pre-commit hooks, and a private GitHub repo with the first commit already pushed
(via the `gh` CLI when you have it, plain `remote add` when you don't).

## The constraints I refused to break

**One file, stdlib only.** A bootstrapper with its own dependency tree is a joke that
writes itself. RepoForge is a single Python file you can read in one coffee and edit
to taste. If you hate one of my opinions, it's *right there*.

**Idempotent, or it's a landmine.** The first version of this script - the private
one I used for a year - died if you ran it twice: `git remote add origin` fails when
origin exists, and `git commit` fails when there's nothing staged. Fine for me, who
remembered. Unacceptable for anyone else. The rule now: every mutation goes through
one gate that checks reality first.

```python
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
```

Re-running RepoForge on a project you've customized will never eat your README. It
tells you what it skipped and moves on. Same for git state: existing repo, existing
remote, nothing-to-commit - detected, respected, reported.

**`--dry-run` that provably touches nothing.** Because every file write and
subprocess call goes through that one `Runner` object, dry-run isn't a best-effort
flag sprinkled through the code - it's a property of the architecture. There's a test
that runs the entire pipeline in dry-run mode and asserts the target directory
*doesn't exist afterward*.

## Profiles, not templates

Here's the cookiecutter lesson: a template is a *repository* you maintain. A profile
is ten lines of *data*:

```python
"fastapi": Profile(
    description="Web API: FastAPI + Uvicorn + httpx test client, src layout.",
    packages=("fastapi", "uvicorn[standard]", "pydantic", "httpx", "pytest", "ruff"),
    src_layout=True,
),
```

Seven of them ship in v1: `minimal`, `general`, `cli` (Typer), `fastapi`, `data`,
`automation`, and the one I actually built this for - `ml-experiment`.

I do a lot of measured AI-efficiency experiments on my own hardware, and the failure
mode of hobby research isn't bad math - it's *bad bookkeeping*. "I think run 14 was
the good one" is not a methodology. So the `ml-experiment` profile scaffolds the
discipline, not just the folders: an `EXPERIMENT_LOG.md` where every entry needs a
falsifiable hypothesis and a measured result, and a `CLAIMS.md` registry where every
claim carries its evidence class - **Established / Supported / Working Hypothesis /
Falsified** - and, crucially, its falsification condition. Failed experiments stay in
the log, because a falsified claim is a result, not an embarrassment.

That file layout has survived twenty-plus iteration cycles of real work on my
machines. It's the part of this tool you genuinely can't get from a generic template,
because it's not a guess about how research should work - it's scar tissue.

## What testing your own tool teaches you

RepoForge ships with its own 23-test pytest suite, and writing it was humbling in the
specific way testing always is. The pure functions were fine. The lies were all in the
seams: the idempotency guarantees I *believed* I had implemented versus the ones the
integration test could actually demonstrate. The test that builds a real repo, edits
the README, re-runs the whole pipeline, and asserts the edit survived - that test
failed the first time I ran it, and the fix is why I trust the tool enough to sell it.

If you take one thing from this post that isn't about bootstrapping: the
one-gate-for-all-mutations pattern (`Runner` above) is what made both `--dry-run` and
the idempotency tests nearly free. Structure buys you the guarantees; discipline alone
doesn't scale past one author.

## Get it

- **RepoForge Lite** - free, MIT, one file, does the whole basic job (venv + deps +
  git + remote): **[github.com/MrWizard94-Compile/repoforge](https://github.com/MrWizard94-Compile/repoforge)**. Not crippleware; it will do that job forever.
- **RepoForge Pro** - all seven profiles, full scaffolding, pre-commit, `gh`
  integration, the test suite, and a personal license: **[wpaistudio.gumroad.com/l/repoforge](https://wpaistudio.gumroad.com/l/repoforge)**.

I'd genuinely like to know: what's in *your* project-start ritual that I haven't
automated? The profiles exist because mine kept diverging by project type - if yours
diverges differently, that's the next profile.
