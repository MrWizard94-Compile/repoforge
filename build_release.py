#!/usr/bin/env python3
"""Build and verify deterministic RepoForge Pro and Lite customer archives."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
MANIFEST_NAME = "MANIFEST.json"
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
ZIP_FILE_MODE = 0o100644 << 16
VERSION_PATTERN = re.compile(
    rb'^__version__\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"', re.MULTILINE
)


@dataclass(frozen=True)
class ReleaseSpec:
    """Immutable allowlist and naming contract for one customer edition."""

    key: str
    product: str
    filename_stem: str
    version_source: str
    source_files: tuple[str, ...]


PRO_RELEASE = ReleaseSpec(
    key="pro",
    product="RepoForge Pro",
    filename_stem="RepoForge-Pro",
    version_source="repoforge.py",
    source_files=(
        "repoforge.py",
        "repoforge_lite.py",
        "build_release.py",
        "pyproject.toml",
        "requirements-dev.txt",
        "README.md",
        "README-LITE.md",
        "LICENSE.txt",
        "LICENSE-LITE.txt",
        "CHANGELOG.md",
        "tests/test_repoforge.py",
        "tests/test_constitution.py",
        "tests/test_repoforge_lite.py",
        "tests/test_release.py",
    ),
)
LITE_RELEASE = ReleaseSpec(
    key="lite",
    product="RepoForge Lite",
    filename_stem="RepoForge-Lite",
    version_source="repoforge_lite.py",
    source_files=(
        "repoforge_lite.py",
        "README-LITE.md",
        "LICENSE-LITE.txt",
    ),
)
RELEASE_SPECS = {spec.key: spec for spec in (PRO_RELEASE, LITE_RELEASE)}

# Backward-compatible public name for Pro release consumers.
SOURCE_FILES = PRO_RELEASE.source_files


class ReleaseError(RuntimeError):
    """Raised when source or archive integrity does not match its release contract."""


def sha256(data: bytes) -> str:
    """Return a lowercase SHA-256 digest."""
    return hashlib.sha256(data).hexdigest()


def source_payloads(
    source_root: Path, spec: ReleaseSpec = PRO_RELEASE
) -> tuple[str, dict[str, bytes]]:
    """Read one edition's allowlisted files and derive its semantic version."""
    try:
        source_root = source_root.resolve(strict=True)
    except OSError as error:
        raise ReleaseError(
            f"Release source root is unavailable: {source_root}"
        ) from error

    payloads: dict[str, bytes] = {}
    for relative in spec.source_files:
        try:
            path = (source_root / relative).resolve(strict=True)
        except OSError as error:
            raise ReleaseError(f"Release source is unavailable: {relative}") from error
        try:
            path.relative_to(source_root)
        except ValueError as error:
            raise ReleaseError(
                f"Release source escaped project root: {relative}"
            ) from error
        if not path.is_file():
            raise ReleaseError(f"Release source is not a file: {relative}")
        payloads[relative] = path.read_bytes()

    match = VERSION_PATTERN.search(payloads[spec.version_source])
    if match is None:
        raise ReleaseError(f"{spec.version_source} has no strict semantic __version__")
    return match.group(1).decode("ascii"), payloads


def manifest_payload(
    version: str,
    payloads: Mapping[str, bytes],
    spec: ReleaseSpec = PRO_RELEASE,
) -> bytes:
    """Create the canonical in-archive integrity manifest."""
    document = {
        "schema_version": 1,
        "product": spec.product,
        "edition": spec.key,
        "version": version,
        "files": [
            {
                "path": relative,
                "bytes": len(payloads[relative]),
                "sha256": sha256(payloads[relative]),
            }
            for relative in spec.source_files
        ],
    }
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_member(archive: zipfile.ZipFile, name: str, payload: bytes) -> None:
    """Write one portable member with stable metadata."""
    info = zipfile.ZipInfo(name, ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = ZIP_FILE_MODE
    archive.writestr(info, payload)


def validate_member_name(name: str) -> None:
    """Reject absolute, parent-relative, or platform-specific member names."""
    if (
        not name
        or "\\" in name
        or name.startswith("/")
        or re.match(r"^[A-Za-z]:", name)
        or any(part in ("", ".", "..") for part in name.split("/"))
    ):
        raise ReleaseError(f"Unsafe archive member: {name!r}")


def validate_member_metadata(info: zipfile.ZipInfo) -> None:
    """Require the deterministic regular-file metadata written by this builder."""
    if (
        info.is_dir()
        or info.date_time != ZIP_TIMESTAMP
        or info.create_system != 3
        or info.external_attr != ZIP_FILE_MODE
        or info.compress_type != zipfile.ZIP_DEFLATED
    ):
        raise ReleaseError(f"Archive metadata differs from contract: {info.filename}")


def validate_archive(
    archive_path: Path,
    source_root: Path = PROJECT_ROOT,
    spec: ReleaseSpec = PRO_RELEASE,
) -> dict[str, object]:
    """Prove that an archive exactly matches its allowlisted source and metadata."""
    version, payloads = source_payloads(source_root, spec)
    expected_names = [*spec.source_files, MANIFEST_NAME]
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            for info in infos:
                validate_member_name(info.filename)
                validate_member_metadata(info)
            if names != expected_names or len(names) != len(set(names)):
                raise ReleaseError(
                    "Archive members differ from contract: "
                    f"expected {expected_names}, got {names}"
                )
            corrupt_member = archive.testzip()
            if corrupt_member is not None:
                raise ReleaseError(f"Archive CRC validation failed: {corrupt_member}")
            for relative, expected in payloads.items():
                if archive.read(relative) != expected:
                    raise ReleaseError(
                        f"Archive payload differs from source: {relative}"
                    )
            manifest_bytes = archive.read(MANIFEST_NAME)
        archive_bytes = archive_path.read_bytes()
    except ReleaseError:
        raise
    except (FileNotFoundError, zipfile.BadZipFile, OSError) as error:
        raise ReleaseError(f"Unable to read release archive: {error}") from error

    expected_manifest = manifest_payload(version, payloads, spec)
    if manifest_bytes != expected_manifest:
        raise ReleaseError("Archive manifest differs from canonical source manifest")
    return {
        "archive": str(archive_path.resolve()),
        "archive_sha256": sha256(archive_bytes),
        "edition": spec.key,
        "file_count": len(expected_names),
        "version": version,
    }


def build_archive(
    output: Path,
    source_root: Path = PROJECT_ROOT,
    spec: ReleaseSpec = PRO_RELEASE,
) -> dict[str, object]:
    """Build atomically, validate fully, and return release evidence."""
    version, payloads = source_payloads(source_root, spec)
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    try:
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as archive:
            for relative in spec.source_files:
                write_member(archive, relative, payloads[relative])
            write_member(
                archive,
                MANIFEST_NAME,
                manifest_payload(version, payloads, spec),
            )
        # Windows requires a writable descriptor for a successful fsync call.
        with temporary.open("r+b") as archive_file:
            os.fsync(archive_file.fileno())
        validate_archive(temporary, source_root, spec)
        temporary.replace(output)
    except ReleaseError:
        raise
    except OSError as error:
        raise ReleaseError(f"Unable to build release archive: {error}") from error
    finally:
        if temporary.exists():
            temporary.unlink()
    return validate_archive(output, source_root, spec)


def default_output(spec: ReleaseSpec, source_root: Path = PROJECT_ROOT) -> Path:
    """Return the versioned default archive path for an edition."""
    version, _ = source_payloads(source_root, spec)
    return source_root / f"{spec.filename_stem}-v{version}.zip"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse release-builder arguments without touching the source tree."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--edition",
        choices=tuple(RELEASE_SPECS),
        default="pro",
        help="Customer edition to build or check (default: pro)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Customer ZIP path (default: versioned archive in the project root)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate the existing output without modifying it",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Build or verify an edition and print machine-readable evidence."""
    try:
        args = parse_args(argv)
        spec = RELEASE_SPECS[args.edition]
        output = args.output or default_output(spec)
        result = (
            validate_archive(output, spec=spec)
            if args.check
            else build_archive(output, spec=spec)
        )
    except (OSError, ReleaseError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
