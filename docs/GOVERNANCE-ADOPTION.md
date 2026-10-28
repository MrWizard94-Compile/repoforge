# RepoForge canonical Constitution migration — 2026-10-18

The director selected pointer-only integration and explicitly retired editable
law vendoring. Accepted `main` of
[WPAI Constitution](https://github.com/MrWizard94-Compile/Agents-Constitution)
alone owns law. The source/tool pin for adoption is v6.16.4,
`0010a8353b00754fad31a30ed24327d3b6d05425`; an already frozen invocation does
not change law retroactively. Root AGENTS and generated entries are pointers.

## Behavior and migration

- Pro writes a canonical pointer by default. It does not download law, install
  skills, invoke agents or prove fresh accepted-source verification. The agent
  uses the installed skill's frozen-source and permitted verified offline rules.
- `--constitution PATH` and `--constitution-vendor` return exit 2 before writes,
  including force, dry-run, opt-out and combined save-defaults/profile-list flows.
- Enabled governance rejects non-empty retired environment/saved path settings
  without reading their target or printing the private values. Explicit opt-out
  ignores them; an explicit opt-out save removes the retired config key while
  preserving normal defaults. No automatic configuration rewrite.
- No nearby/ancestor pack discovery and no copy/delete vendoring implementation.
  Known old vendor trees block enabled generation even with force; they require
  separate, preservation-aware migration. Opt-out does not certify their cleanup.
- Existing AGENTS files retain normal preservation/explicit-force behavior.
  A preserved file is reported as unverified and not migrated, never silently
  described as the canonical pointer.

The seven old pack-mode tests are intentionally replaced with the approved
pointer/retirement contract; their old behavior is no longer supported. All
98 unrelated baseline test cases remain unchanged. The separate new 55-case
suite covers rejected options before mutations, stale configuration, all seven
profiles, neighboring-pack nonselection, vendor-tree preservation, opt-out,
dry-run, existing guidance, real user staging and packaged fresh-process execution.
Its negative control against unchanged product code fails 53 cases, passes two;
the original 105-case baseline and its format/lint/type gates passed beforehand.
The no-discovery case rejects any directory/file probe outside the generation
target, not merely one known folder spelling. Old verifier text is checked
through forbidden invocation/authority behavior rather than literal name-only
assertions; the broad adoption scanner must not mistake those negative tests
for a live loader. No scanner exemption or excluded test directory is added.

## Product preservation and source QA

Private recovery holds exact raw originals plus initial path/index/HEAD/branch
hashes. Existing unpublished 1.1.0 work, unrelated source, customer artifacts,
licensing assets, historic ZIPs and separate remote history are not reset or
published by adoption. The old pre-pack loader contains product context retained
in the new entry, but its Python >=3.9 statement is superseded by the current
declared >=3.10 stack. Its exact bytes remain recoverable before retirement.

The source CI declares Windows/Linux/macOS product cohorts at Python3.10/3.14,
immutable actions and the accepted canonical source pin. A separate Python3.12
canonical-tool job runs the accepted 96-test suite. A workflow file alone does
not establish successful remote CI: report terminal exact-head evidence if it
is actually published and run. Source fixtures avoid real remotes, pip installs
into customer projects, provider actions and user config.

Pro's archive allowlist includes the new regression suite; Lite's behavior is
unchanged apart from the accurate Pro feature description. New audit packages
are validated and run separately; historical customer archives are not silently
overwritten. This is not a storefront update, a new public release or proof
that every installed agent loaded the new pointer.
