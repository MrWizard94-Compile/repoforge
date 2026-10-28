# RepoForge Changelog

All product changes are recorded here. Customer archives are built from the
allow-listed source with `python build_release.py` and include a SHA-256 manifest.

## Unreleased — approved WPAI Constitution migration (2026-10-18)

- Replaced the local pack integration proposed for 1.1.0 with a canonical
  WPAI Constitution pointer, enabled by default with explicit opt-out.
- Retired local-path flags and editable vendoring before all writes, including
  saved-default/profile-list actions; removed ancestor/sibling pack discovery.
- Reject stale implicit path settings while enabled. Explicit opt-out preserves
  them unless saving defaults, which retires only the old configuration key.
- Preserve user guidance without claiming it was migrated. Refuse enabled
  generation over a known old vendor tree, even with force; never delete it.
- Added real disposable project, index, dry-run and fresh packaged-CLI checks.
  Customer archives include the complete new regression suite, not copied law.
- These local changes do not publish a product release or refresh every agent.

## 1.1.0 — 2026-09-09

- Originally proposed local pointer and vendored-pack modes (retired by the
  approved pointer-only migration above, not the current product contract).
- Added installable packaging for every profile, runnable entry behavior, and
  behavior-focused generated tests, including CLI and FastAPI paths.
- Split runtime and development inputs, installed generated projects in editable
  mode, and added resolved `requirements.lock` creation and reuse.
- Confined all scaffold writes and virtual-environment names to the selected
  project directory and added preflight validation for invalid option, target,
  Git identity, GitHub authentication, and remote combinations.
- Scoped Git staging and commits to generated paths. Existing staged, modified,
  and untracked user files remain outside RepoForge commits; `--no-commit`
  leaves generated files unstaged.
- Made saved-default writes atomic, corrected `--save-defaults --list-profiles`,
  and extended dry-run's zero-mutation guarantee to saved configuration.
- Updated the pinned hook contract for the supported Python 3.10+ runtime and
  ensured `.pre-commit-config.yaml` is part of the generated initial commit.
- Updated the FastAPI test stack to HTTPX2 and constrained AnyIO below 4.15 until
  Starlette removes its deprecated `anyio.abc.BlockingPortal` reference, keeping
  generated tests warning-free on the current dependency graph.
- Added deterministic, self-verifying Pro and Lite customer archives with strict
  path, metadata, payload, and manifest validation. Pro ships the builder and its
  release-integrity tests; Lite ships a minimal executable bundle.
- Expanded the behavior suite across rerun safety, dependency setup, path and
  staging confinement, Constitution integration, and release integrity.
- Rebuilt Lite as a safe Python 3.10+ foundation with isolated installation,
  separated dependency inputs, resolved lock reuse, installable metadata,
  runnable behavior, scoped Git commits, force/no-commit controls, and dry-run.
- Added repository-owned, pinned pytest, Ruff, and strict mypy gates.

## 1.0.0 — 2026-07-08

- Initial RepoForge Pro release with seven project profiles, safe file
  preservation, dry-run support, Git initialization, and optional GitHub setup.
