"""Approved pointer-only governance contract, with real disposable consumers."""

import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

import build_release
import repoforge

SOURCE = "https://github.com/MrWizard94-Compile/Agents-Constitution"


@pytest.fixture(autouse=True)
def isolated_governance_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(repoforge, "CONFIG_PATH", tmp_path / "defaults.json")
    monkeypatch.delenv("REPOFORGE_CONSTITUTION", raising=False)


def _no_subprocess(*_args, **_kwargs):
    pytest.fail("A rejected governance option reached subprocess execution")


def _legacy_pack(root):
    root.mkdir(parents=True)
    for name in ("AGENTS.md", "PACK.md", "VERSION", "SOP.md"):
        (root / name).write_text("legacy fixture, never authority\n", encoding="utf-8")
    return root


def _files(root):
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _local_generation(project, *options):
    repoforge.main(
        [
            "--directory",
            str(project),
            "--profile",
            "minimal",
            "--skip-venv",
            "--no-commit",
            *options,
        ]
    )


def _assert_pointer(body):
    body = " ".join(body.split())
    assert SOURCE in body
    assert "accepted `main`" in body
    assert "wpai-constitution" in body
    for artifact in ("SKILL.md", "SOURCE.json", "references/always-load.md"):
        assert artifact in body
    assert "same frozen revision" in body
    assert "full commit SHA" in body
    assert "previously verified" in body
    assert "file hashes" in body
    assert "degraded" in body
    assert "not authority" in body
    assert "does not download" in body
    assert "human authorization" in body
    assert "README" in body
    for legacy in ("Pack path", "Binding pack", "SOUL", "pwsh -File"):
        assert legacy not in body


@pytest.mark.parametrize(
    "legacy",
    (
        ("--constitution-vendor",),
        ("--constitution-vendor", "--no-constitution"),
        ("--constitution", "{pack}"),
        ("--constitution=",),
    ),
)
@pytest.mark.parametrize(
    "action",
    (
        (),
        ("--save-defaults",),
        ("--list-profiles",),
        ("--save-defaults", "--list-profiles"),
    ),
)
@pytest.mark.parametrize("dry_run", (False, True))
def test_retired_cli_options_fail_before_any_write(
    tmp_path, monkeypatch, capsys, legacy, action, dry_run
):
    pack = _legacy_pack(tmp_path / "pack")
    project = tmp_path / "existing"
    project.mkdir()
    (project / "director-notes.txt").write_bytes(b"preserve user bytes\x00\xff")
    config = repoforge.CONFIG_PATH
    config.write_bytes(b'{"owner": "original"}\r\n')
    original_config = config.read_bytes()
    original_files = _files(project)
    monkeypatch.setattr(subprocess, "run", _no_subprocess)
    args = [
        "--directory",
        str(project),
        "--owner",
        "replacement",
        "--force",
        *[str(pack) if token == "{pack}" else token for token in legacy],
        *action,
        *(["--dry-run"] if dry_run else []),
    ]
    with pytest.raises(SystemExit) as error:
        repoforge.main(args)
    assert error.value.code == 2
    output = capsys.readouterr().out
    assert "retired" in output
    assert "pointer" in output
    assert config.read_bytes() == original_config
    assert _files(project) == original_files
    assert all(
        path.read_text(encoding="utf-8").startswith("legacy fixture")
        for path in pack.iterdir()
    )


@pytest.mark.parametrize("setting", ("environment", "saved", "both"))
@pytest.mark.parametrize("list_profiles", (False, True))
def test_stale_implicit_settings_fail_closed_without_disclosing_values(
    tmp_path, monkeypatch, capsys, setting, list_profiles
):
    secret_value = "unused-private-location-do-not-disclose"
    values = {"owner": "original"}
    if setting in ("saved", "both"):
        values["constitution_path"] = secret_value
    config = repoforge.CONFIG_PATH
    config.write_text(json.dumps(values), encoding="utf-8")
    original = config.read_bytes()
    if setting in ("environment", "both"):
        monkeypatch.setenv("REPOFORGE_CONSTITUTION", secret_value)
    monkeypatch.setattr(subprocess, "run", _no_subprocess)
    target = tmp_path / "absent"
    with pytest.raises(SystemExit) as error:
        repoforge.main(
            [
                "--directory",
                str(target),
                "--save-defaults",
                "--owner",
                "new",
                *(["--list-profiles"] if list_profiles else []),
            ]
        )
    assert error.value.code == 2
    output = capsys.readouterr().out
    assert "retired" in output
    assert "--no-constitution" in output
    assert secret_value not in output
    assert config.read_bytes() == original
    assert not target.exists()


def test_generated_pointer_names_one_verified_authority():
    _assert_pointer(repoforge.agents_pointer_content())


@pytest.mark.parametrize("profile", sorted(repoforge.PROFILES))
def test_every_profile_emits_pointer_without_local_law(tmp_path, profile):
    project = tmp_path / profile
    repoforge.main(
        [
            "--directory",
            str(project),
            "--profile",
            profile,
            "--skip-venv",
            "--no-commit",
        ]
    )
    _assert_pointer((project / "AGENTS.md").read_text(encoding="utf-8"))
    assert not (project / "law").exists()
    readme = (project / "README.md").read_text(encoding="utf-8")
    assert SOURCE in readme
    assert "wpai-constitution" in readme
    assert "Load that pack" not in readme
    assert "pwsh -File" not in readme


def test_default_pointer_never_discovers_neighboring_pack(tmp_path, monkeypatch):
    software = tmp_path / "Software"
    tool = software / "RepoForge"
    tool.mkdir(parents=True)
    monkeypatch.setattr(repoforge, "__file__", str(tool / "repoforge.py"))
    project = tool / "consumer"

    # A probe of any ancestor/sibling location fails, even if no known pack
    # name exists there. This checks the discovery boundary, not one spelling.
    for method in ("is_dir", "is_file"):
        original = getattr(Path, method)

        def confined_probe(path, *, _original=original):
            assert path.is_relative_to(project), f"Out-of-target probe: {path}"
            return _original(path)

        monkeypatch.setattr(Path, method, confined_probe)

    _local_generation(project)
    body = (project / "AGENTS.md").read_text(encoding="utf-8")
    _assert_pointer(body)
    assert "QuillForge" not in body


@pytest.mark.parametrize("force", (False, True))
def test_existing_vendor_tree_is_rejected_and_never_deleted(
    tmp_path, monkeypatch, capsys, force
):
    project = tmp_path / "existing"
    pack = _legacy_pack(project / "law" / "AGENTS-Constitution")
    (project / "AGENTS.md").write_text("old project guidance\n", encoding="utf-8")
    (pack / "user-addition.txt").write_bytes(b"do not delete\xff")
    before = _files(project)
    monkeypatch.setattr(subprocess, "run", _no_subprocess)
    with pytest.raises(SystemExit) as error:
        _local_generation(project, *(["--force"] if force else []))
    assert error.value.code == 2
    assert "retired vendored" in capsys.readouterr().out
    assert _files(project) == before


def test_opt_out_ignores_stale_settings_without_rewriting_them(tmp_path, monkeypatch):
    config = repoforge.CONFIG_PATH
    config.write_text('{"constitution_path": "unused-old-path"}', encoding="utf-8")
    original = config.read_bytes()
    monkeypatch.setenv("REPOFORGE_CONSTITUTION", "unused-other-path")
    project = tmp_path / "consumer"
    _local_generation(project, "--no-constitution")
    assert not (project / "AGENTS.md").exists()
    assert not (project / "law").exists()
    assert config.read_bytes() == original


def test_explicit_opt_out_save_retires_only_legacy_config_key(tmp_path, monkeypatch):
    config = repoforge.CONFIG_PATH
    config.write_text(
        '{"owner": "alice", "author": "Director", "constitution_path": "old"}',
        encoding="utf-8",
    )
    monkeypatch.setenv("REPOFORGE_CONSTITUTION", "unused")
    repoforge.main(["--no-constitution", "--save-defaults", "--list-profiles"])
    saved = json.loads(config.read_text(encoding="utf-8"))
    assert saved == {
        "owner": "alice",
        "author": "Director",
        "license": "mit",
        "profile": "general",
    }


def test_dry_run_plans_pointer_without_writes_or_commands(
    tmp_path, monkeypatch, capsys
):
    target = tmp_path / "absent"
    monkeypatch.setattr(subprocess, "run", _no_subprocess)
    _local_generation(target, "--dry-run", "--save-defaults")
    output = capsys.readouterr().out
    assert "WPAI Constitution" in output
    assert "pointer" in output
    assert not target.exists()
    assert not repoforge.CONFIG_PATH.exists()


def test_existing_guidance_is_preserved_without_claiming_migration(tmp_path, capsys):
    project = tmp_path / "existing"
    project.mkdir()
    existing = b"director-owned guidance\r\n"
    (project / "AGENTS.md").write_bytes(existing)
    _local_generation(project)
    assert (project / "AGENTS.md").read_bytes() == existing
    output = capsys.readouterr().out
    assert "pointer was not installed" in output
    assert "not verified" in output
    _local_generation(project, "--force")
    _assert_pointer((project / "AGENTS.md").read_text(encoding="utf-8"))


def test_pointer_is_scoped_in_git_and_preserves_user_index(tmp_path, monkeypatch):
    for key, value in (
        ("GIT_AUTHOR_NAME", "RepoForge Fixture"),
        ("GIT_COMMITTER_NAME", "RepoForge Fixture"),
        ("GIT_AUTHOR_EMAIL", "fixture@example.invalid"),
        ("GIT_COMMITTER_EMAIL", "fixture@example.invalid"),
    ):
        monkeypatch.setenv(key, value)
    project = tmp_path / "existing"
    project.mkdir()
    subprocess.run(["git", "init"], cwd=project, check=True, capture_output=True)
    (project / "private.txt").write_bytes(b"director work\xff")
    subprocess.run(["git", "add", "private.txt"], cwd=project, check=True)
    repoforge.main(
        [
            "--directory",
            str(project),
            "--profile",
            "minimal",
            "--skip-venv",
        ]
    )
    tracked = subprocess.run(
        ["git", "show", "--pretty=", "--name-only", "HEAD"],
        cwd=project,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=project,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert "AGENTS.md" in tracked
    assert "private.txt" not in tracked
    assert staged == ["private.txt"]
    assert (project / "private.txt").read_bytes() == b"director work\xff"


def test_packaged_cli_generates_canonical_pointer_in_fresh_process(tmp_path):
    archive_path = tmp_path / "pro.zip"
    build_release.build_archive(archive_path)
    bundle = tmp_path / "bundle"
    with zipfile.ZipFile(archive_path) as archive:
        assert "tests/test_constitution.py" in archive.namelist()
        assert not any(name.startswith("law/") for name in archive.namelist())
        archive.extractall(bundle)
    isolated_home = tmp_path / "fixture-home"
    isolated_home.mkdir()
    environment = dict(os.environ)
    environment.update(HOME=str(isolated_home), USERPROFILE=str(isolated_home))
    environment.pop("REPOFORGE_CONSTITUTION", None)
    target = tmp_path / "packaged-consumer"
    command = [sys.executable, "-B", "-W", "error", str(bundle / "repoforge.py")]
    result = subprocess.run(
        [
            *command,
            "--directory",
            str(target),
            "--profile",
            "minimal",
            "--skip-venv",
            "--no-commit",
        ],
        cwd=bundle,
        env=environment,
        text=True,
        capture_output=True,
        check=True,
    )
    assert result.stderr == ""
    assert "[SUCCESS]" in result.stdout
    _assert_pointer((target / "AGENTS.md").read_text(encoding="utf-8"))
    assert not (target / "law").exists()
    assert not (isolated_home / ".repoforge.json").exists()
    entry = subprocess.run(
        [sys.executable, "-B", "-W", "error", "main.py"],
        cwd=target,
        env=environment,
        text=True,
        capture_output=True,
        check=True,
    )
    assert "packaged-consumer [minimal] is ready" in entry.stdout
    assert entry.stderr == ""
    smoke = subprocess.run(
        [sys.executable, "-B", "-W", "error", "-m", "pytest", "tests", "-q"],
        cwd=target,
        env=environment,
        text=True,
        capture_output=True,
        check=True,
    )
    assert "1 passed" in smoke.stdout
    assert smoke.stderr == ""
    rejected = subprocess.run(
        [
            *command,
            "--directory",
            str(tmp_path / "rejected"),
            "--constitution-vendor",
            "--save-defaults",
            "--list-profiles",
        ],
        cwd=bundle,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert rejected.returncode == 2
    assert "retired" in rejected.stdout
    assert not (tmp_path / "rejected").exists()
    assert not (isolated_home / ".repoforge.json").exists()
