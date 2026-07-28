"""RepoForge Pro test suite.

Unit tests cover the pure logic; the integration test builds a real project in a
temp directory (git required, dependency install skipped for speed).

Run:  pytest tests/ -v
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import repoforge  # noqa: E402


# --------------------------------------------------------------------------- #
# build_remote_url                                                            #
# --------------------------------------------------------------------------- #

def test_full_url_passthrough():
    url = "https://github.com/someone/thing.git"
    assert repoforge.build_remote_url("ignored", url, "owner") == url


def test_bare_slug_uses_owner():
    assert repoforge.build_remote_url("demo", None, "alice") \
        == "https://github.com/alice/demo.git"


def test_owner_slash_slug_ignores_default_owner():
    assert repoforge.build_remote_url("bob/demo", None, "alice") \
        == "https://github.com/bob/demo.git"


def test_ssh_url_passthrough():
    url = "git@github.com:alice/demo.git"
    assert repoforge.build_remote_url(url, None, None) == url


def test_no_name_means_no_remote():
    assert repoforge.build_remote_url(None, None, "alice") is None


def test_bare_slug_without_owner_raises():
    with pytest.raises(ValueError):
        repoforge.build_remote_url("demo", None, None)


# --------------------------------------------------------------------------- #
# package_name_from                                                           #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("raw,expected", [
    ("my-cool-tool", "my_cool_tool"),
    ("My Tool!", "my_tool"),
    ("3d-render", "app_3d_render"),
    ("---", "app"),
    ("already_fine", "already_fine"),
])
def test_package_name_sanitization(raw, expected):
    assert repoforge.package_name_from(raw) == expected


# --------------------------------------------------------------------------- #
# Profile registry integrity                                                  #
# --------------------------------------------------------------------------- #

def test_every_profile_has_pytest():
    """Every profile must ship a test runner — the sample test has to pass."""
    for name, profile in repoforge.PROFILES.items():
        assert any(p.startswith("pytest") for p in profile.packages), name


def test_profile_extras_are_known():
    known = {"EXPERIMENT_LOG.md", "CLAIMS.md"}
    for profile in repoforge.PROFILES.values():
        assert set(profile.extras) <= known


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


def test_sample_test_imports_package_in_src_layout():
    text = repoforge.sample_test_content("my_pkg", src_layout=True)
    assert "import my_pkg" in text


def test_defaults_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(repoforge, "CONFIG_PATH", tmp_path / "config.json")
    repoforge.save_defaults({"owner": "alice", "profile": "cli"})
    assert repoforge.load_defaults() == {"owner": "alice", "profile": "cli"}


def test_corrupt_defaults_return_empty(tmp_path, monkeypatch):
    config = tmp_path / "config.json"
    config.write_text("{not json", encoding="utf-8")
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


def test_dry_run_touches_nothing(tmp_path):
    runner = repoforge.Runner(dry_run=True)
    runner.write(tmp_path / "file.txt", "content", "write")
    runner.mkdir(tmp_path / "dir", "mkdir")
    assert list(tmp_path.iterdir()) == []


# --------------------------------------------------------------------------- #
# Integration — real end-to-end run (no dependency install, no remote).       #
# --------------------------------------------------------------------------- #

git_available = shutil.which("git") is not None


@pytest.mark.skipif(not git_available, reason="git not on PATH")
def test_end_to_end_minimal_project(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(repoforge, "CONFIG_PATH", tmp_path / "unused-config.json")
    project_dir = tmp_path / "demo"

    repoforge.main([
        "--directory", str(project_dir),
        "--profile", "ml-experiment",
        "--skip-install",
        "--license", "mit",
        "--author", "Test Author",
        "--no-constitution",
    ])

    # Scaffold
    for expected in [".gitignore", "requirements.txt", "README.md",
                     "pyproject.toml", "LICENSE", "EXPERIMENT_LOG.md", "CLAIMS.md",
                     "tests/test_smoke.py"]:
        assert (project_dir / expected).exists(), expected
    for directory in ["experiments", "results", "plots", "references", ".venv"]:
        assert (project_dir / directory).is_dir(), directory

    # Git state
    assert (project_dir / ".git").is_dir()
    log = subprocess.run(["git", "log", "--oneline"], cwd=str(project_dir),
                         text=True, capture_output=True)
    identity_ready = repoforge.git_identity_ready(project_dir)
    if identity_ready:
        assert "Initial commit (RepoForge)" in log.stdout

    # Idempotency: second run must not fail or clobber
    (project_dir / "README.md").write_text("customized", encoding="utf-8")
    repoforge.main([
        "--directory", str(project_dir),
        "--profile", "ml-experiment",
        "--skip-install",
        "--no-constitution",
    ])
    assert (project_dir / "README.md").read_text(encoding="utf-8") == "customized"

    out = capsys.readouterr().out
    assert "[SUCCESS]" in out


@pytest.mark.skipif(not git_available, reason="git not on PATH")
def test_dry_run_end_to_end_creates_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(repoforge, "CONFIG_PATH", tmp_path / "unused-config.json")
    project_dir = tmp_path / "ghost"
    repoforge.main([
        "--directory", str(project_dir),
        "--profile", "minimal",
        "--dry-run",
        "--no-constitution",
    ])
    assert not project_dir.exists()


# --------------------------------------------------------------------------- #
# AGENTS Constitution integration                                             #
# --------------------------------------------------------------------------- #

def _fake_constitution_pack(root: Path) -> Path:
    """Minimal valid pack markers (enough for is_constitution_pack)."""
    root.mkdir(parents=True, exist_ok=True)
    for name in repoforge.CONSTITUTION_MARKERS:
        (root / name).write_text(f"# {name}\n", encoding="utf-8")
    return root


def test_is_constitution_pack_requires_markers(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    assert not repoforge.is_constitution_pack(pack)
    _fake_constitution_pack(pack)
    assert repoforge.is_constitution_pack(pack)


def test_discover_constitution_explicit(tmp_path, monkeypatch):
    monkeypatch.setattr(repoforge, "CONFIG_PATH", tmp_path / "cfg.json")
    pack = _fake_constitution_pack(tmp_path / "AGENTS Constitution")
    found = repoforge.discover_constitution_pack(str(pack), start=tmp_path)
    assert found == pack.resolve()


def test_discover_constitution_auto_sibling(tmp_path, monkeypatch):
    monkeypatch.setattr(repoforge, "CONFIG_PATH", tmp_path / "cfg.json")
    monkeypatch.delenv("REPOFORGE_CONSTITUTION", raising=False)
    software = tmp_path / "Software"
    tool = software / "RepoForge"
    tool.mkdir(parents=True)
    pack = _fake_constitution_pack(software / "QuillForge" / "AGENTS Constitution")
    found = repoforge.discover_constitution_pack(None, start=tool)
    assert found == pack.resolve()


def test_agents_pointer_content_links_pack():
    text = repoforge.agents_pointer_content("demo", "../law/AGENTS-Constitution")
    assert "# AGENTS — Project Entry Point (demo)" in text
    assert "../law/AGENTS-Constitution/AGENTS.md" in text
    assert "Always load" in text


@pytest.mark.skipif(not git_available, reason="git not on PATH")
def test_end_to_end_constitution_pointer(tmp_path, monkeypatch):
    monkeypatch.setattr(repoforge, "CONFIG_PATH", tmp_path / "unused-config.json")
    pack = _fake_constitution_pack(tmp_path / "AGENTS Constitution")
    project_dir = tmp_path / "app"
    repoforge.main([
        "--directory", str(project_dir),
        "--profile", "minimal",
        "--skip-install",
        "--constitution", str(pack),
    ])
    agents = project_dir / "AGENTS.md"
    assert agents.is_file()
    body = agents.read_text(encoding="utf-8")
    assert "AGENTS Constitution" in body
    assert "SOP.md" in body


@pytest.mark.skipif(not git_available, reason="git not on PATH")
def test_end_to_end_constitution_vendor(tmp_path, monkeypatch):
    monkeypatch.setattr(repoforge, "CONFIG_PATH", tmp_path / "unused-config.json")
    pack = _fake_constitution_pack(tmp_path / "pack-src")
    (pack / "standards").mkdir()
    (pack / "standards" / "ENGINEERING.md").write_text("# eng\n", encoding="utf-8")
    project_dir = tmp_path / "app"
    repoforge.main([
        "--directory", str(project_dir),
        "--profile", "minimal",
        "--skip-install",
        "--constitution", str(pack),
        "--constitution-vendor",
    ])
    vendored = project_dir / "law" / "AGENTS-Constitution"
    assert (vendored / "AGENTS.md").is_file()
    assert (vendored / "standards" / "ENGINEERING.md").is_file()
    pointer = (project_dir / "AGENTS.md").read_text(encoding="utf-8")
    assert "law/AGENTS-Constitution" in pointer
