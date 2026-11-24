#!/usr/bin/env python3
"""Build deterministic plugin and offline ZIPs from the single canonical skill tree.

Copyright 2026 Mechanical Patent Toolkit contributors
SPDX-License-Identifier: MIT
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import tempfile
import zipfile

from validate_plugin import (PLUGIN_NAME, PLUGIN_REL, ValidationError, public_files,
                             compatibility_payloads, read_json, sha256,
                             validate_repository, version_tuple)

FIXED_ZIP_TIME = (2020, 1, 1, 0, 0, 0)
MANIFEST_NAME = "RELEASE_MANIFEST.json"


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _archive_name(value: str) -> str:
    path = PurePosixPath(value)
    if (not value or path.is_absolute() or ".." in path.parts or "\\" in value
            or ":" in value or str(path) != value or value.startswith("/")
            or any(ord(character) < 32 for character in value)):
        raise ValidationError(f"unsafe archive name: {value}")
    return value


def _mode(path: Path) -> int:
    # Preserve command launchers while stripping ownership, write and special bits.
    return 0o755 if path.stat().st_mode & 0o111 else 0o644


def write_archive(destination: Path, entries: dict[str, tuple[bytes, int]]) -> None:
    """No mtimes, host paths, owners or platform-specific permission bits enter ZIPs."""
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(entries):
            _archive_name(name)
            payload, mode = entries[name]
            info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | mode) << 16
            archive.writestr(info, payload, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def build_release(repo_root: Path, version: str, *, versioned: bool = True) -> dict:
    """Validate first; stage all output; update only release files and two manifests.

    This function never installs skills, connects accounts, publishes a release,
    removes dated downloads, or permits a downgrade. Rebuilding a version is legal.
    """
    requested = version_tuple(version)
    repo = Path(repo_root)
    report = validate_repository(repo)
    repo = repo.resolve()
    plugin = repo / PLUGIN_REL
    downloads = repo / "downloads"
    if downloads.is_symlink() or downloads.exists() and not downloads.is_dir():
        raise ValidationError("downloads must be an ordinary directory")
    prior = downloads / MANIFEST_NAME
    versions = [version_tuple(report["version"])]
    if prior.exists():
        if prior.is_symlink():
            raise ValidationError("release manifest must not be a symbolic link")
        versions.append(version_tuple(read_json(prior).get("version")))
    if requested < max(versions):
        raise ValidationError("refusing release version downgrade; use a preserved versioned ZIP for rollback")
    legacy = report.get("compatibility_plugins", [])
    previous_legacy = {}
    if prior.exists():
        previous_legacy = {entry["name"]: entry["version"] for entry in
                           read_json(prior).get("validation", {}).get("compatibility_plugins", [])}
    for entry in legacy:
        if entry["name"] in previous_legacy and version_tuple(entry["version"]) < version_tuple(previous_legacy[entry["name"]]):
            raise ValidationError(f"refusing compatibility plugin downgrade: {entry['name']}")
    manifests = [plugin / "plugin.json", plugin / ".codex-plugin/plugin.json"]
    manifest_bytes = {}
    for path in manifests:
        data = read_json(path)
        data["version"] = version
        manifest_bytes[path] = _json_bytes(data)
    entries = {}
    for path in public_files(plugin):
        name = _archive_name(path.relative_to(plugin).as_posix())
        entries[name] = (manifest_bytes.get(path, path.read_bytes()), _mode(path))
    offline = {name: value for name, value in entries.items() if name.startswith("skills/")}
    for name in ("install.py", "README.md", "INSTALL.md", "LICENSE", "THIRD_PARTY_NOTICES.md"):
        path = repo / name
        offline[name] = (path.read_bytes(), _mode(path))
    plugin_latest = "mechanical-patent-workflow-latest.zip"
    offline_latest = "mechanical-patent-toolkit-latest.zip"
    versioned_name = f"mechanical-patent-workflow-{version}.zip"
    # A temp directory inside repo ensures final replacements remain on one filesystem.
    with tempfile.TemporaryDirectory(prefix=".release-stage-", dir=repo) as temporary:
        staged = Path(temporary)
        write_archive(staged / plugin_latest, entries)
        write_archive(staged / offline_latest, offline)
        names = [plugin_latest, offline_latest]
        if versioned:
            (staged / versioned_name).write_bytes((staged / plugin_latest).read_bytes())
            names.append(versioned_name)
        compatibility_archives = {}
        payloads = compatibility_payloads(repo)
        for entry in legacy:
            name = entry["name"]
            archive_name = entry["archive"]
            compatibility_archives[name] = archive_name
            packed = {relative: (path.read_bytes(), _mode(path)) for relative, path in payloads[name].items()}
            write_archive(staged / archive_name, packed)
            names.append(archive_name)
        # Existing dated and versioned ZIPs remain listed and untouched.
        existing = {}
        if downloads.exists():
            for path in downloads.glob("*.zip"):
                if path.is_symlink() or not path.is_file():
                    raise ValidationError("archive destinations must be ordinary files")
                if path.name not in names:
                    existing[path.name] = path
        all_archives = {**existing, **{name: staged / name for name in names}}
        report["version"] = version
        record = {
            "schema_version": 1, "plugin": PLUGIN_NAME, "version": version,
            "canonical_skills": report["canonical_skills"],
            "current_archives": {"plugin": plugin_latest, "offline": offline_latest,
                                 "versioned_plugin": versioned_name if versioned else None},
            "current_compatibility_archives": compatibility_archives,
            "archives": [{"name": name, "sha256": sha256(path), "bytes": path.stat().st_size}
                         for name, path in sorted(all_archives.items())],
            "plugin_files": [{"path": name, "sha256": hashlib.sha256(data).hexdigest(),
                              "mode": f"{mode:04o}", "bytes": len(data)}
                             for name, (data, mode) in sorted(entries.items())],
            "validation": report,
        }
        (staged / MANIFEST_NAME).write_bytes(_json_bytes(record))
        sums = {name: sha256(path) for name, path in all_archives.items()}
        sums[MANIFEST_NAME] = sha256(staged / MANIFEST_NAME)
        (staged / "SHA256SUMS").write_text("".join(f"{digest}  {name}\n" for name, digest in sorted(sums.items())),
                                           encoding="utf-8")
        output_names = names + [MANIFEST_NAME, "SHA256SUMS"]
        for name in output_names:
            target = downloads / name
            if target.is_symlink() or target.exists() and not target.is_file():
                raise ValidationError("release destinations must be ordinary files")
        downloads.mkdir(exist_ok=True)
        previous = {path: path.read_bytes() if path.exists() else None
                    for path in list(manifest_bytes) + [downloads / name for name in output_names]}
        try:
            for path, payload in manifest_bytes.items():
                path.write_bytes(payload)
            for name in output_names:
                target = downloads / name
                if target.is_symlink():
                    raise ValidationError("release destination changed into a symbolic link")
                os.replace(staged / name, target)
        except Exception:
            for path, payload in previous.items():
                if payload is None:
                    path.unlink(missing_ok=True)
                elif not path.is_symlink():
                    path.write_bytes(payload)
            raise
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="X.Y.Z; equal versions may be rebuilt, lower versions are rejected")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--no-versioned", action="store_true", help="omit the optional versioned plugin ZIP")
    args = parser.parse_args(argv)
    try:
        record = build_release(args.repo_root, args.version, versioned=not args.no_versioned)
    except (ValidationError, OSError, zipfile.BadZipFile) as exc:
        print(f"Build failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"version": record["version"], "current_archives": record["current_archives"],
                      "root_skills": len(record["validation"]["root_skills"]),
                      "skill_entrypoints": record["validation"]["skill_entrypoints"]},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
