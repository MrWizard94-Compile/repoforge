"""RepoForge Pro test suite.

Unit tests cover the pure logic; the integration test builds a real project in a
temp directory (git required, dependency install skipped for speed).

Run:  pytest tests/ -v
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import repoforge

# --------------------------------------------------------------------------- #
# build_remote_url                                                            #
# --------------------------------------------------------------------------- #


def test_full_url_passthrough():
    url = "https://github.com/someone/thing.git"
    assert repoforge.build_remote_url("ignored", url, "owner") == url


def test_bare_slug_uses_owner():
    assert (
        repoforge.build_remote_url("demo", None, "alice")
        == "https://github.com/alice/demo.git"
    )


def test_owner_slash_slug_ignores_default_owner():
    assert (
        repoforge.build_remote_url("bob/demo", None, "alice")
        == "https://github.com/bob/demo.git"
    )


def test_ssh_url_passthrough():
    url = "git@github.com:alice/demo.git"
    assert repoforge.build_remote_url(url, None, None) == url


def test_no_name_means_no_remote():
    assert repoforge.build_remote_url(None, None, "alice") is None


def test_bare_slug_without_owner_raises():
    with pytest.raises(ValueError):
        repoforge.build_remote_url("demo", None, None)


@pytest.mark.parametrize("repo_name", [" ", "owner/repo/extra", "owner/bad repo"])
def test_invalid_repository_slug_raises(repo_name):
    with pytest.raises(ValueError):
        repoforge.build_remote_url(repo_name, None, "alice")


def test_blank_explicit_repo_url_raises():
    with pytest.raises(ValueError, match="cannot be blank"):
        repoforge.build_remote_url(None, "  ", None)


@pytest.mark.parametrize(
    "remote,expected",
    [
        ("https://github.com/alice/demo.git", "alice/demo"),
        ("https://github.com/alice/demo", "alice/demo"),
        ("git@github.com:alice/demo.git", "alice/demo"),
        ("ssh://git@github.com/alice/demo.git", "alice/demo"),
        ("https://gitlab.com/alice/demo.git", None),
        ("https://github.com/alice/demo/extra", None),
    ],
)
def test_github_slug_from_remote(remote, expected):
    assert repoforge.github_slug_from_remote(remote) == expected


# --------------------------------------------------------------------------- #
# package_name_from                                                           #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("my-cool-tool", "my_cool_tool"),
        ("My Tool!", "my_tool"),
        ("3d-render", "app_3d_render"),
        ("---", "app"),
        ("already_fine", "already_fine"),
        ("class", "app_class"),
        ("CON", "app_con"),
    ],
)
def test_package_name_sanitization(raw, expected):
    assert repoforge.package_name_from(raw) == expected


# --------------------------------------------------------------------------- #
# Profile registry integrity                                                  #
# --------------------------------------------------------------------------- #


def test_every_profile_has_pytest():
    """Every profile must ship a test runner — the sample test has to pass."""
    for name, profile in repoforge.PROFILES.items():
        assert any(p.startswith("pytest") for p in profile.packages), name


def test_profile_dependency_groups_keep_test_tools_out_of_runtime():
    for name, profile in repoforge.PROFILES.items():
        assert "pytest" not in profile.runtime_packages, name
        assert "pytest" in profile.development_packages, name
    fastapi = repoforge.PROFILES["fastapi"]
    assert "httpx2" in fastapi.development_packages
    assert "httpx" not in fastapi.packages
    assert "anyio>=4.14.2,<4.15" in fastapi.runtime_packages


def test_profile_extras_are_known():
    known = {"EXPERIMENT_LOG.md", "CLAIMS.md"}
    for profile in repoforge.PROFILES.values():
        assert set(profile.extras) <= known
        assert set(profile.ignored_dirs) <= set(profile.dirs)


def test_ml_experiment_profile_scaffolds_registries():
    profile = repoforge.PROFILES["ml-experiment"]
    assert "EXPERIMENT_LOG.md" in profile.extras
    assert "CLAIMS.md" in profile.extras
    assert "results" in profile.dirs and "plots" in profile.dirs


# --------------------------------------------------------------------------- #
# Content generators                                                          #
# --------------------------------------------------------------------------- #


def test_readme_mentions_profile_and_project():
    profile = repoforge.PROFILES["cli"]
    text = repoforge.readme_content("my-tool", "cli", profile, "my_tool")
    assert "# my-tool" in text
    assert "`cli` profile" in text
    assert "python -m my_tool --help" in text


def test_cli_sample_test_exercises_status_command():
    text = repoforge.sample_test_content("my_pkg", profile_name="cli")
    assert "from my_pkg.__main__ import app" in text
    assert 'runner.invoke(app, ["status"])' in text


def test_non_src_sample_test_exercises_generated_entry_point():
    text = repoforge.sample_test_content("my_pkg", profile_name="minimal")
    assert "import main" in text
    assert 'main.project_status()["status"] == "ready"' in text


def test_pyproject_declares_installable_src_layout_and_runtime_dependencies():
    profile = repoforge.PROFILES["cli"]
    text = repoforge.pyproject_content("my-tool", "my_tool", "cli", profile)
    assert 'requires-python = ">=3.10"' in text
    assert 'dependencies = ["typer", "rich"]' in text
    assert 'package-dir = {"" = "src"}' in text
    assert 'my_tool = "my_tool.__main__:app"' in text


@pytest.mark.parametrize("profile_name", sorted(repoforge.PROFILES))
def test_generated_python_sources_compile(profile_name):
    profile = repoforge.PROFILES[profile_name]
    package = "demo_package"
    compile(
        repoforge.sample_test_content(package, profile_name),
        "tests/test_smoke.py",
        "exec",
    )
    if profile.src_layout:
        entry_name = "main.py" if profile_name == "fastapi" else "__main__.py"
        compile(
            repoforge.entry_module_content(profile_name, package),
            entry_name,
            "exec",
        )
    else:
        compile(
            repoforge.main_module_content('demo "quoted"', profile_name),
            "main.py",
            "exec",
        )


def test_defaults_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(repoforge, "CONFIG_PATH", tmp_path / "config.json")
    repoforge.save_defaults({"owner": "alice", "profile": "cli"})
    assert repoforge.load_defaults() == {"owner": "alice", "profile": "cli"}


def test_defaults_dry_run_does_not_write(tmp_path, monkeypatch):
    config = tmp_path / "config.json"
    monkeypatch.setattr(repoforge, "CONFIG_PATH", config)
    repoforge.save_defaults({"owner": "alice"}, dry_run=True)
    assert not config.exists()


def test_save_defaults_and_list_profiles_performs_both_actions(
    tmp_path, monkeypatch, capsys
):
    config = tmp_path / "config.json"
    monkeypatch.setattr(repoforge, "CONFIG_PATH", config)
    repoforge.main(
        [
            "--owner",
            "alice",
            "--profile",
            "cli",
            "--save-defaults",
            "--list-profiles",
        ]
    )
    assert repoforge.load_defaults()["owner"] == "alice"
    assert "Available profiles:" in capsys.readouterr().out


def test_dry_run_save_defaults_and_list_profiles_writes_nothing(tmp_path, monkeypatch):
    config = tmp_path / "config.json"
    monkeypatch.setattr(repoforge, "CONFIG_PATH", config)
    repoforge.main(
        [
            "--owner",
            "alice",
            "--save-defaults",
            "--list-profiles",
            "--dry-run",
        ]
    )
    assert not config.exists()


def test_corrupt_defaults_return_empty(tmp_path, monkeypatch):
    config = tmp_path / "config.json"
    config.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(repoforge, "CONFIG_PATH", config)
    assert repoforge.load_defaults() == {}


def test_defaults_ignore_unknown_and_non_string_values(tmp_path, monkeypatch):
    config = tmp_path / "config.json"
    config.write_text(
        '{"owner": "alice", "profile": 7, "unknown": "value"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(repoforge, "CONFIG_PATH", config)
    assert repoforge.load_defaults() == {"owner": "alice"}


def test_oversized_defaults_are_ignored(tmp_path, monkeypatch):
    config = tmp_path / "config.json"
    config.write_text(" " * (repoforge.MAX_CONFIG_BYTES + 1), encoding="utf-8")
    monkeypatch.setattr(repoforge, "CONFIG_PATH", config)
    assert repoforge.load_defaults() == {}


# --------------------------------------------------------------------------- #
# Runner behaviour                                                            #
# --------------------------------------------------------------------------- #


def test_runner_write_respects_existing_files(tmp_path):
    target = tmp_path / "file.txt"
    target.write_text("original", encoding="utf-8")
    runner = repoforge.Runner()
    assert runner.write(target, "new", "write") is False
    assert target.read_text(encoding="utf-8") == "original"
    assert str(target) in runner.skipped


def test_runner_force_overwrites(tmp_path):
    target = tmp_path / "file.txt"
    target.write_text("original", encoding="utf-8")
    runner = repoforge.Runner(force=True)
    assert runner.write(target, "new", "write") is True
    assert target.read_text(encoding="utf-8") == "new"
    assert runner.stage_paths == [target]


def test_dry_run_touches_nothing(tmp_path):
    runner = repoforge.Runner(dry_run=True, root=tmp_path)
    runner.write(tmp_path / "file.txt", "content", "write")
    runner.mkdir(tmp_path / "dir", "mkdir")
    assert list(tmp_path.iterdir()) == []
    assert runner.stage_paths == [tmp_path / "file.txt"]


def test_runner_capture_dry_run_does_not_execute(tmp_path):
    runner = repoforge.Runner(dry_run=True, root=tmp_path)
    assert runner.capture(["missing-command"], "capture", tmp_path) is None


def test_runner_rejects_write_outside_project_root(tmp_path):
    project = tmp_path / "project"
    runner = repoforge.Runner(root=project)
    with pytest.raises(ValueError, match="outside the project directory"):
        runner.write(tmp_path / "outside.txt", "content", "write")
    assert not (tmp_path / "outside.txt").exists()


def test_generated_git_pathspecs_are_relative_and_unique(tmp_path):
    project = tmp_path / "project"
    runner = repoforge.Runner(root=project)
    runner.track_for_git(project / "README.md")
    runner.track_for_git(project / "README.md")
    runner.track_for_git(project / "src")
    assert repoforge.generated_git_pathspecs(runner, project) == ["README.md", "src"]


def test_environment_dry_run_plans_editable_install_and_lock(tmp_path, capsys):
    runner = repoforge.Runner(dry_run=True, root=tmp_path)
    repoforge.setup_environment(runner, tmp_path, ".venv", skip_install=False)
    output = capsys.readouterr().out
    assert "requirements-dev.txt" in output
    assert "--editable ." in output
    assert "freeze --local --exclude-editable" in output
    assert tmp_path / "requirements.lock" in runner.stage_paths
    assert list(tmp_path.iterdir()) == []


# --------------------------------------------------------------------------- #
# Integration — real end-to-end run (no dependency install, no remote).       #
# --------------------------------------------------------------------------- #

git_available = shutil.which("git") is not None


def _provide_git_identity(monkeypatch):
    monkeypatch.setenv("GIT_AUTHOR_NAME", "RepoForge Tests")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "repoforge-tests@example.invalid")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "RepoForge Tests")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "repoforge-tests@example.invalid")


@pytest.mark.skipif(not git_available, reason="git not on PATH")
def test_end_to_end_minimal_project(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(repoforge, "CONFIG_PATH", tmp_path / "unused-config.json")
    _provide_git_identity(monkeypatch)
    project_dir = tmp_path / "demo"

    repoforge.main(
        [
            "--directory",
            str(project_dir),
            "--profile",
            "ml-experiment",
            "--skip-install",
            "--license",
            "mit",
            "--author",
            "Test Author",
            "--no-constitution",
        ]
    )

    # Scaffold
    for expected in [
        ".gitignore",
        "requirements.txt",
        "requirements-dev.txt",
        "README.md",
        "pyproject.toml",
        "LICENSE",
        "main.py",
        "EXPERIMENT_LOG.md",
        "CLAIMS.md",
        "tests/test_smoke.py",
    ]:
        assert (project_dir / expected).exists(), expected
    for directory in ["experiments", "results", "plots", "references", ".venv"]:
        assert (project_dir / directory).is_dir(), directory
    assert (project_dir / "experiments" / ".gitkeep").is_file()
    assert (project_dir / "references" / ".gitkeep").is_file()
    assert (project_dir / "results" / ".gitignore").read_text(
        encoding="utf-8"
    ) == "*\n!.gitignore\n"

    # Git state
    assert (project_dir / ".git").is_dir()
    log = subprocess.run(
        ["git", "log", "--oneline"],
        cwd=str(project_dir),
        check=False,
        text=True,
        capture_output=True,
    )
    identity_ready = repoforge.git_identity_ready(project_dir)
    if identity_ready:
        assert "Initial commit (RepoForge)" in log.stdout

    # Idempotency: second run must not fail or clobber
    (project_dir / "README.md").write_text("customized", encoding="utf-8")
    (project_dir / "director-notes.txt").write_text("private", encoding="utf-8")
    repoforge.main(
        [
            "--directory",
            str(project_dir),
            "--profile",
            "ml-experiment",
            "--skip-install",
            "--no-constitution",
        ]
    )
    assert (project_dir / "README.md").read_text(encoding="utf-8") == "customized"
    status = subprocess.run(
        ["git", "status", "--porcelain=v1"],
        cwd=str(project_dir),
        text=True,
        capture_output=True,
        check=True,
    ).stdout.splitlines()
    assert " M README.md" in status
    assert "?? director-notes.txt" in status

    out = capsys.readouterr().out
    assert "[SUCCESS]" in out


@pytest.mark.skipif(not git_available, reason="git not on PATH")
def test_existing_staged_user_file_is_not_in_repoforge_commit(tmp_path, monkeypatch):
    _provide_git_identity(monkeypatch)
    project_dir = tmp_path / "existing"
    project_dir.mkdir()
    subprocess.run(["git", "init"], cwd=project_dir, check=True, capture_output=True)
    user_file = project_dir / "director-notes.txt"
    user_file.write_text("private", encoding="utf-8")
    subprocess.run(
        ["git", "add", "director-notes.txt"],
        cwd=project_dir,
        check=True,
        capture_output=True,
    )

    repoforge.main(
        [
            "--directory",
            str(project_dir),
            "--profile",
            "minimal",
            "--skip-venv",
            "--no-constitution",
        ]
    )

    committed = subprocess.run(
        ["git", "show", "--pretty=", "--name-only", "HEAD"],
        cwd=project_dir,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.splitlines()
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=project_dir,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.splitlines()
    assert "director-notes.txt" not in committed
    assert staged == ["director-notes.txt"]
    assert "README.md" in committed


@pytest.mark.skipif(not git_available, reason="git not on PATH")
def test_no_commit_leaves_generated_files_unstaged(tmp_path, monkeypatch):
    monkeypatch.setattr(repoforge, "CONFIG_PATH", tmp_path / "unused-config.json")
    project_dir = tmp_path / "no-commit"
    repoforge.main(
        [
            "--directory",
            str(project_dir),
            "--profile",
            "minimal",
            "--skip-venv",
            "--no-commit",
            "--no-constitution",
        ]
    )
    status = subprocess.run(
        ["git", "status", "--porcelain=v1"],
        cwd=project_dir,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.splitlines()
    assert status
    assert all(line.startswith("?? ") for line in status)
    head = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=project_dir,
        check=False,
        text=True,
        capture_output=True,
    )
    assert head.returncode != 0


@pytest.mark.skipif(not git_available, reason="git not on PATH")
def test_pre_commit_configuration_is_in_initial_commit(tmp_path, monkeypatch):
    monkeypatch.setattr(repoforge, "CONFIG_PATH", tmp_path / "unused-config.json")
    _provide_git_identity(monkeypatch)
    project_dir = tmp_path / "hooks"
    python = repoforge.venv_python(project_dir / ".venv")
    python.parent.mkdir(parents=True)
    python.write_text("test-only executable marker", encoding="utf-8")

    def fake_setup(runner, target, _venv_name):
        runner.write(
            target / ".pre-commit-config.yaml",
            repoforge.PRE_COMMIT_CONFIG,
            "Writing .pre-commit-config.yaml",
        )

    monkeypatch.setattr(repoforge, "setup_pre_commit", fake_setup)
    monkeypatch.setattr(repoforge, "activate_pre_commit", lambda *_args: None)
    repoforge.main(
        [
            "--directory",
            str(project_dir),
            "--profile",
            "minimal",
            "--skip-venv",
            "--pre-commit",
            "--no-constitution",
        ]
    )

    committed = subprocess.run(
        ["git", "show", "--pretty=", "--name-only", "HEAD"],
        cwd=project_dir,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.splitlines()
    assert ".pre-commit-config.yaml" in committed
    assert repoforge.PRE_COMMIT_REQUIREMENT in (
        project_dir / "requirements-dev.txt"
    ).read_text(encoding="utf-8")


def test_preflight_rejects_push_without_commit(tmp_path):
    with pytest.raises(ValueError, match="requires the default initial commit"):
        repoforge.validate_run_preflight(
            tmp_path / "project",
            "https://github.com/alice/demo.git",
            dry_run=True,
            commit=False,
            create_remote=False,
            push=True,
        )


def test_preflight_rejects_non_github_create_remote(tmp_path):
    with pytest.raises(ValueError, match="supports GitHub"):
        repoforge.validate_run_preflight(
            tmp_path / "project",
            "https://gitlab.com/alice/demo.git",
            dry_run=True,
            commit=True,
            create_remote=True,
            push=False,
        )


@pytest.mark.parametrize("venv_name", ["../escape", "nested/venv", "CON", "bad name"])
def test_preflight_rejects_unsafe_venv_names(tmp_path, venv_name):
    with pytest.raises(ValueError, match="safe directory name"):
        repoforge.validate_run_preflight(
            tmp_path / "project",
            None,
            dry_run=True,
            commit=False,
            create_remote=False,
            push=False,
            venv_name=venv_name,
        )


def test_preflight_rejects_file_as_target(tmp_path):
    target = tmp_path / "project"
    target.write_text("not a directory", encoding="utf-8")
    with pytest.raises(ValueError, match="not a directory"):
        repoforge.validate_run_preflight(
            target,
            None,
            dry_run=True,
            commit=False,
            create_remote=False,
            push=False,
        )


def test_preflight_requires_existing_venv_when_skipping_for_hooks(tmp_path):
    with pytest.raises(ValueError, match="existing virtual environment"):
        repoforge.validate_run_preflight(
            tmp_path / "project",
            None,
            dry_run=True,
            commit=False,
            create_remote=False,
            push=False,
            pre_commit=True,
            skip_venv=True,
        )


def test_preflight_rejects_retired_vendor_tree(tmp_path):
    target = tmp_path / "project"
    (target / "law" / "AGENTS-Constitution").mkdir(parents=True)
    with pytest.raises(ValueError, match="retired vendored"):
        repoforge.validate_run_preflight(
            target,
            None,
            dry_run=True,
            commit=False,
            create_remote=False,
            push=False,
        )


@pytest.mark.skipif(not git_available, reason="git not on PATH")
def test_dry_run_end_to_end_creates_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(repoforge, "CONFIG_PATH", tmp_path / "unused-config.json")
    project_dir = tmp_path / "ghost"
    repoforge.main(
        [
            "--directory",
            str(project_dir),
            "--profile",
            "minimal",
            "--dry-run",
            "--no-constitution",
        ]
    )
    assert not project_dir.exists()


# --------------------------------------------------------------------------- #
# WPAI Constitution pointer integration — approved retirement of pack modes.  #
# --------------------------------------------------------------------------- #


def test_pointer_records_manifest_and_frozen_source_contract():
    text = repoforge.agents_pointer_content()
    assert "SOURCE.json" in text
    assert "full commit SHA" in text
    assert "file hashes" in text
    assert "wpai-constitution" in text


def test_explicit_local_pack_selection_is_retired(tmp_path):
    with pytest.raises(ValueError, match="--constitution PATH is retired"):
        repoforge.validate_constitution_options(
            str(tmp_path), vendor=False, enabled=True, saved_path=None
        )


def test_old_implicit_pack_selection_is_retired(tmp_path, monkeypatch):
    monkeypatch.setenv("REPOFORGE_CONSTITUTION", str(tmp_path))
    with pytest.raises(ValueError, match="settings are retired"):
        repoforge.validate_constitution_options(
            None, vendor=False, enabled=True, saved_path=None
        )


def test_agents_pointer_content_links_canonical_source():
    text = repoforge.agents_pointer_content()
    assert repoforge.CONSTITUTION_SOURCE in text
    assert "SKILL.md" in text
    assert "references/always-load.md" in text
    assert "same frozen" in text


@pytest.mark.skipif(not git_available, reason="git not on PATH")
def test_end_to_end_constitution_pointer(tmp_path, monkeypatch):
    monkeypatch.setattr(repoforge, "CONFIG_PATH", tmp_path / "unused-config.json")
    monkeypatch.delenv("REPOFORGE_CONSTITUTION", raising=False)
    _provide_git_identity(monkeypatch)
    project_dir = tmp_path / "app"
    repoforge.main(
        [
            "--directory",
            str(project_dir),
            "--profile",
            "minimal",
            "--skip-install",
        ]
    )
    agents = project_dir / "AGENTS.md"
    assert agents.is_file()
    body = agents.read_text(encoding="utf-8")
    assert "WPAI Constitution" in body
    assert repoforge.CONSTITUTION_SOURCE in body
    assert "SOURCE.json" in body
    assert repoforge.venv_python(project_dir / ".venv").is_file()
    committed = subprocess.run(
        ["git", "show", "HEAD:AGENTS.md"],
        cwd=project_dir,
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    assert committed == body


def test_end_to_end_constitution_vendor_is_retired(tmp_path, monkeypatch):
    monkeypatch.setattr(repoforge, "CONFIG_PATH", tmp_path / "unused-config.json")
    project_dir = tmp_path / "app"
    with pytest.raises(SystemExit) as error:
        repoforge.main(
            [
                "--directory",
                str(project_dir),
                "--profile",
                "minimal",
                "--skip-install",
                "--constitution-vendor",
            ]
        )
    assert error.value.code == 2
    assert not project_dir.exists()
