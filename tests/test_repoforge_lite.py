"""RepoForge Lite unit and real-Git behavior tests."""

import shutil
import subprocess

import pytest

import repoforge_lite


@pytest.mark.parametrize(
    "name,owner,expected",
    [
        (None, None, None),
        ("demo", "alice", "https://github.com/alice/demo.git"),
        ("alice/demo", None, "https://github.com/alice/demo.git"),
        (
            "git@github.com:alice/demo.git",
            None,
            "git@github.com:alice/demo.git",
        ),
    ],
)
def test_remote_url_resolution(name, owner, expected):
    assert repoforge_lite.remote_url_from(name, owner) == expected


@pytest.mark.parametrize("name", [" ", "owner/repo/extra", "owner/bad repo"])
def test_remote_url_rejects_invalid_names(name):
    with pytest.raises(ValueError):
        repoforge_lite.remote_url_from(name, "alice")


def test_bare_remote_requires_owner():
    with pytest.raises(ValueError, match="requires --owner"):
        repoforge_lite.remote_url_from("demo", None)


@pytest.mark.parametrize(
    "project,expected",
    [
        ("My Project", "my_project"),
        ("3d-tool", "app_3d_tool"),
        ("class", "app_class"),
        ("CON", "app_con"),
    ],
)
def test_package_name_is_portable(project, expected):
    assert repoforge_lite.package_name_from(project) == expected


def test_runner_confines_writes_and_dry_run(tmp_path):
    target = tmp_path / "project"
    target.mkdir()
    runner = repoforge_lite.Runner(root=target, dry_run=True)
    runner.write(target / "README.md", "content", "Writing README")
    assert not (target / "README.md").exists()
    assert runner.stage_paths == [target / "README.md"]
    with pytest.raises(ValueError, match="outside the project directory"):
        runner.write(tmp_path / "outside.txt", "content", "Writing outside")


def test_generated_python_is_complete_and_compiles():
    main_source = repoforge_lite.main_module_content('quoted "project"')
    compile(main_source, "main.py", "exec")
    compile(repoforge_lite.SMOKE_TEST, "tests/test_smoke.py", "exec")
    assert "project_status" in main_source
    assert "TODO" not in main_source
    assert "placeholder" not in main_source.casefold()


def test_scaffold_writes_installable_foundation(tmp_path):
    runner = repoforge_lite.Runner(root=tmp_path)
    repoforge_lite.scaffold(runner, tmp_path, "demo")
    expected = {
        ".gitignore",
        "requirements.txt",
        "requirements-dev.txt",
        "README.md",
        "main.py",
        "pyproject.toml",
        "tests/test_smoke.py",
    }
    assert expected == {
        path.relative_to(tmp_path).as_posix()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert 'requires-python = ">=3.10"' in (tmp_path / "pyproject.toml").read_text(
        encoding="utf-8"
    )


def test_environment_dry_run_plans_lock_without_writes(tmp_path, capsys):
    runner = repoforge_lite.Runner(root=tmp_path, dry_run=True)
    repoforge_lite.setup_environment(
        runner, tmp_path, skip_venv=False, skip_install=False
    )
    output = capsys.readouterr().out
    assert "requirements-dev.txt" in output
    assert "--editable ." in output
    assert "freeze --local --exclude-editable" in output
    assert not list(tmp_path.iterdir())


def test_main_dry_run_creates_nothing(tmp_path):
    target = tmp_path / "ghost"
    repoforge_lite.main(["--directory", str(target), "--dry-run", "--no-commit"])
    assert not target.exists()


def test_bare_repository_defaults_to_a_named_project_directory(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    repoforge_lite.main(["demo", "--owner", "alice", "--dry-run", "--no-commit"])
    output = capsys.readouterr().out
    assert f"Directory: {(tmp_path / 'demo').resolve()}" in output
    assert not (tmp_path / "demo").exists()


def test_preflight_rejects_file_target(tmp_path):
    target = tmp_path / "target"
    target.write_text("file", encoding="utf-8")
    with pytest.raises(ValueError, match="not a directory"):
        repoforge_lite.validate_preflight(target, dry_run=True, commit=False)


git_available = shutil.which("git") is not None


def _provide_git_identity(monkeypatch):
    monkeypatch.setenv("GIT_AUTHOR_NAME", "RepoForge Lite Tests")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "repoforge-lite@example.invalid")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "RepoForge Lite Tests")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "repoforge-lite@example.invalid")


@pytest.mark.skipif(not git_available, reason="git not on PATH")
def test_existing_staged_user_file_is_excluded_from_lite_commit(tmp_path, monkeypatch):
    _provide_git_identity(monkeypatch)
    target = tmp_path / "existing"
    target.mkdir()
    subprocess.run(["git", "init"], cwd=target, check=True, capture_output=True)
    user_file = target / "director-notes.txt"
    user_file.write_text("private", encoding="utf-8")
    subprocess.run(
        ["git", "add", "director-notes.txt"],
        cwd=target,
        check=True,
        capture_output=True,
    )

    repoforge_lite.main(["--directory", str(target), "--skip-venv"])

    committed = subprocess.run(
        ["git", "show", "--pretty=", "--name-only", "HEAD"],
        cwd=target,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.splitlines()
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=target,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.splitlines()
    assert "director-notes.txt" not in committed
    assert staged == ["director-notes.txt"]
    assert "README.md" in committed

    (target / "README.md").write_text("customized", encoding="utf-8")
    (target / "private-untracked.txt").write_text("private", encoding="utf-8")
    repoforge_lite.main(["--directory", str(target), "--skip-venv"])
    assert (target / "README.md").read_text(encoding="utf-8") == "customized"
    status = subprocess.run(
        ["git", "status", "--porcelain=v1"],
        cwd=target,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.splitlines()
    assert " M README.md" in status
    assert "?? private-untracked.txt" in status


@pytest.mark.skipif(not git_available, reason="git not on PATH")
def test_lite_no_commit_leaves_everything_unstaged(tmp_path, monkeypatch):
    for key in (
        "GIT_AUTHOR_NAME",
        "GIT_AUTHOR_EMAIL",
        "GIT_COMMITTER_NAME",
        "GIT_COMMITTER_EMAIL",
    ):
        monkeypatch.delenv(key, raising=False)
    target = tmp_path / "no-commit"
    repoforge_lite.main(["--directory", str(target), "--skip-venv", "--no-commit"])
    status = subprocess.run(
        ["git", "status", "--porcelain=v1"],
        cwd=target,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.splitlines()
    assert status
    assert all(line.startswith("?? ") for line in status)
