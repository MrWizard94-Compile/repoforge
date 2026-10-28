"""Release-package reproducibility, safety, and integrity tests."""

import json
import zipfile

import pytest

import build_release

RELEASE_SPECS = (build_release.PRO_RELEASE, build_release.LITE_RELEASE)


@pytest.mark.parametrize("spec", RELEASE_SPECS, ids=lambda spec: spec.key)
def test_release_build_is_reproducible_and_valid(tmp_path, spec):
    first = tmp_path / f"{spec.key}-first.zip"
    second = tmp_path / f"{spec.key}-second.zip"
    first_result = build_release.build_archive(first, spec=spec)
    second_result = build_release.build_archive(second, spec=spec)
    assert first.read_bytes() == second.read_bytes()
    assert first_result["archive_sha256"] == second_result["archive_sha256"]
    assert first_result["edition"] == spec.key
    assert first_result["version"] == "1.1.0"
    assert first_result["file_count"] == len(spec.source_files) + 1


@pytest.mark.parametrize("spec", RELEASE_SPECS, ids=lambda spec: spec.key)
def test_release_manifest_matches_every_customer_file(tmp_path, spec):
    archive_path = tmp_path / f"{spec.key}.zip"
    build_release.build_archive(archive_path, spec=spec)
    with zipfile.ZipFile(archive_path) as archive:
        manifest = json.loads(archive.read(build_release.MANIFEST_NAME))
        assert manifest["product"] == spec.product
        assert manifest["edition"] == spec.key
        assert manifest["version"] == "1.1.0"
        assert [item["path"] for item in manifest["files"]] == list(spec.source_files)
        for item in manifest["files"]:
            payload = archive.read(item["path"])
            assert item["bytes"] == len(payload)
            assert item["sha256"] == build_release.sha256(payload)


@pytest.mark.parametrize("spec", RELEASE_SPECS, ids=lambda spec: spec.key)
def test_release_validator_rejects_an_extra_member(tmp_path, spec):
    archive_path = tmp_path / f"{spec.key}-tampered.zip"
    build_release.build_archive(archive_path, spec=spec)
    with zipfile.ZipFile(archive_path, "a") as archive:
        archive.writestr("unexpected.txt", b"unexpected")
    with pytest.raises(build_release.ReleaseError, match=r"metadata|members differ"):
        build_release.validate_archive(archive_path, spec=spec)


def test_release_validator_rejects_changed_metadata(tmp_path):
    canonical = tmp_path / "canonical.zip"
    tampered = tmp_path / "tampered.zip"
    build_release.build_archive(canonical)
    with (
        zipfile.ZipFile(canonical, "r") as source,
        zipfile.ZipFile(tampered, "w") as destination,
    ):
        for index, source_info in enumerate(source.infolist()):
            timestamp = (1981, 1, 1, 0, 0, 0) if index == 0 else source_info.date_time
            target_info = zipfile.ZipInfo(source_info.filename, timestamp)
            target_info.compress_type = source_info.compress_type
            target_info.create_system = source_info.create_system
            target_info.external_attr = source_info.external_attr
            destination.writestr(target_info, source.read(source_info.filename))
    with pytest.raises(build_release.ReleaseError, match="metadata differs"):
        build_release.validate_archive(tampered)


@pytest.mark.parametrize(
    "name",
    ("../escape.txt", "/absolute.txt", "C:/absolute.txt", "nested\\file.txt"),
)
def test_release_validator_rejects_unsafe_member_name(name):
    with pytest.raises(build_release.ReleaseError, match="Unsafe archive member"):
        build_release.validate_member_name(name)


def test_default_outputs_are_edition_specific():
    pro = build_release.default_output(build_release.PRO_RELEASE)
    lite = build_release.default_output(build_release.LITE_RELEASE)
    assert pro.name == "RepoForge-Pro-v1.1.0.zip"
    assert lite.name == "RepoForge-Lite-v1.1.0.zip"
