# RepoForge project entry

The accepted `main` of
[WPAI Constitution](https://github.com/MrWizard94-Compile/Agents-Constitution)
is the only editable source of constitutional law. Use `wpai-constitution`:
freeze and verify one accepted full commit, then read its SKILL, SOURCE manifest,
always-load set and applicable law from that same revision. Generated mirrors
are distributions, not authority. Follow only the frozen skill's permitted,
verified offline fallback; disclose degraded sync, never substitute a local pack.

## Product facts and preservation

Read [README](README.md), [packaging](build_release.py),
[stack and QA pins](pyproject.toml), [development inputs](requirements-dev.txt)
and [adoption record](docs/GOVERNANCE-ADOPTION.md). RepoForge Pro and Lite are
stdlib-only Python >=3.10 bootstrappers for Windows, macOS and Linux. Pro adds
profiles, saved defaults, optional hooks, remote creation and explicit push.

Preserve the unpublished 1.1.0 work, customer/licensing assets, historic release
archives, separate Git history, existing index and user modifications. The
primary tree is not interchangeable with the published remote baseline.
Do not publish a source checkout or customer release as a side effect of
governance adoption. Commercial listings, uploads and distribution remain
director-controlled. Do not reset, rebase, force-push or auto-merge the unrelated
`baseline/local-source-20260728` history.

## Approved integration contract

Pro emits a canonical pointer by default, not editable law. `--no-constitution`
is an explicit opt-out. Retired local-path/vendor requests fail before writes,
including config-only actions. Do not restore old-pack auto-discovery or delete
old vendor trees on a force rerun. Preserving an existing AGENTS file does not
prove migration. The installed skill owns accepted-source and offline verification;
RepoForge pointer generation does not download law, install a skill or run agents.

## Verification and operations

Use an isolated QA environment with the pinned development inputs:

```powershell
python -m ruff format --check repoforge.py repoforge_lite.py build_release.py tests governance_tests
python -m ruff check repoforge.py repoforge_lite.py build_release.py tests governance_tests
python -m mypy
python -X utf8 -W error -m pytest tests -q
python -B -W error -m unittest discover -s governance_tests -v
```

Tests use disposable project roots, local Git and explicit fixture settings;
inspect side effects before adding or running new integration flows. Never
point tests at real customer repositories, user configuration or production state.
Normal product execution can create environments, install packages/hooks, save
configuration, commit, create remotes and push when explicitly requested by the
operator. Examples do not grant authority to perform these actions on real data.
Dry-run must leave configuration and project bytes untouched and execute no
mutating subprocess. Do not weaken those guarantees to obtain green tests.

Build verification archives at separate explicit disposable/audit paths; do not
overwrite a historic customer ZIP. Source QA, generated behavior, package
integrity, installed-agent loading and actual release/publication are separate
acceptance boundaries. No source check proves every client refreshed.
