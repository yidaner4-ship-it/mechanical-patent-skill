#!/usr/bin/env python3
"""Compare reviewed public skills and install a frozen plan without replacing runtimes.

This tool does not choose the better design, contact services, or publish changes.
Copyright 2026 Mechanical Patent Toolkit contributors
SPDX-License-Identifier: MIT
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import tempfile

from validate_plugin import PLUGIN_REL, ValidationError, excluded, public_files, _private_name

MANAGED_SKILLS = (
    "patent-disclosure-skill", "fusion-production-modeling", "mechanical-patent-drawings",
    "shensheng-patent-qa", "shensheng-patent-workbench", "patent-search",
)
METADATA = ".shensheng-github-sync.json"
REPOSITORY = "https://github.com/yidaner4-ship-it/mechanical-patent-skill"


class SyncError(RuntimeError):
    """A reviewed source/target or path invariant failed."""


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_relative(value: str) -> str:
    if not isinstance(value, str):
        raise SyncError("managed path must be text")
    path = PurePosixPath(value)
    if (not path.parts or path.parts[0] not in MANAGED_SKILLS or path.is_absolute()
            or ".." in path.parts or str(path) != value or "\\" in value or ":" in value
            or any(ord(c) < 32 for c in value) or excluded(path) or _private_name(path)
            or any(part in {".runtime", "cad-env"} for part in path.parts)):
        raise SyncError("unsafe or unmanaged skill path")
    return value


def checked_root(path: Path) -> Path:
    path = Path(path).expanduser().absolute()
    if path.is_symlink() or path.exists() and not path.is_dir():
        raise SyncError("skill root must be an ordinary directory")
    return path.resolve()


def checked_path(root: Path, relative: str) -> Path:
    path = root
    parts = PurePosixPath(relative).parts
    for i, part in enumerate(parts):
        path = path / part
        if path.is_symlink():
            raise SyncError("symbolic link in managed path")
        if path.exists() and (not path.is_file() if i == len(parts) - 1 else not path.is_dir()):
            raise SyncError("unexpected file type in managed path")
    return path


def fingerprint(path: Path) -> dict | None:
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise SyncError("expected an ordinary managed file")
    return {"sha256": digest(path.read_bytes()), "mode": 0o755 if path.stat().st_mode & 0o111 else 0o644}


def metadata_state(local: Path) -> tuple[dict, str | None]:
    path = checked_path(local, METADATA)
    if not path.exists():
        return {}, None
    try:
        raw = path.read_bytes()
        data = json.loads(raw)
        if not isinstance(data, dict) or not isinstance(data.get("manifest", {}), dict):
            raise ValueError("metadata object required")
    except (OSError, ValueError) as exc:
        raise SyncError("invalid local synchronization metadata") from exc
    return data, digest(raw)


def git_value(repo: Path, *args: str) -> str | None:
    try:
        return subprocess.check_output(["git", "-C", str(repo), *args], text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def unmanaged_candidates(local: Path, managed: set[str]) -> list[str]:
    """Report candidate additions without reading secrets or entering local runtimes."""
    result = []
    skipped = {".runtime", "cad-env", "site-packages", "vendor", "outputs", "output", "tmp", "temp",
               "backups", "backup", "logs", "cases", "dossiers", "案卷", "案件", "缓存"}
    for skill in MANAGED_SKILLS:
        root = local / skill
        if root.is_symlink():
            raise SyncError("symbolic link in local skill root")
        if not root.exists():
            continue
        if not root.is_dir():
            raise SyncError("local skill must be an ordinary directory")
        for base, directories, files in os.walk(root, followlinks=False):
            kept = []
            for name in directories:
                path = Path(base) / name
                relative = PurePosixPath(path.relative_to(local).as_posix())
                if not path.is_symlink() and name not in skipped and not excluded(relative) and not _private_name(relative):
                    kept.append(name)
            directories[:] = kept
            for name in files:
                path = Path(base) / name
                relative = path.relative_to(local).as_posix()
                if path.is_symlink() or not path.is_file() or relative in managed:
                    continue
                try:
                    safe_relative(relative)
                except SyncError:
                    continue
                result.append(relative)
    return sorted(result)


def make_plan(repo_root: Path, local_root: Path, *, scan_unmanaged: bool = False) -> dict:
    repo, local = checked_root(repo_root), checked_root(local_root)
    source = repo
    for part in (PLUGIN_REL / "skills").parts:
        source = source / part
        if source.is_symlink() or not source.is_dir():
            raise SyncError("canonical source must have ordinary directory ancestors")
    if local == source or local in source.parents or source in local.parents:
        raise SyncError("source and target overlap")
    metadata, metadata_hash = metadata_state(local)
    baseline = metadata.get("manifest", {})
    for name in baseline:
        safe_relative(name)
    source_files = {}
    for name in MANAGED_SKILLS:
        folder = source / name
        if not (folder / "SKILL.md").is_file():
            raise SyncError("missing managed source skill")
        for path in public_files(folder):
            relative = safe_relative(path.relative_to(source).as_posix())
            source_files[relative] = fingerprint(path)
    local_files, changes = {}, []
    for relative in sorted(set(source_files) | set(baseline)):
        safe_relative(relative)
        current = fingerprint(checked_path(local, relative))
        local_files[relative] = current
        target = source_files.get(relative)
        old = baseline.get(relative)
        if current != target:
            changes.append({"path": relative,
                            "action": "delete" if target is None else "add" if current is None else "replace",
                            "local_changed_since_sync": current != old,
                            "source_changed_since_sync": target != old})
    manifest_path = repo / PLUGIN_REL / "plugin.json"
    try:
        version = json.loads(manifest_path.read_text(encoding="utf-8"))["version"]
    except (OSError, ValueError, KeyError) as exc:
        raise SyncError("missing plugin version") from exc
    return {"schema_version": 1, "repository": REPOSITORY, "branch": "main",
            "repo_root": str(repo), "source_root": str(source), "local_root": str(local),
            "commit": git_value(repo, "rev-parse", "HEAD"), "plugin_version": version,
            "metadata_sha256": metadata_hash, "source_files": source_files,
            "local_files": local_files, "changes": changes, "scan_unmanaged": scan_unmanaged,
            "unmanaged_candidates": unmanaged_candidates(local, set(source_files) | set(baseline)) if scan_unmanaged else []}


def summary(plan: dict) -> dict:
    changes = plan["changes"]
    return {"managed_skills": len(MANAGED_SKILLS), "source_files": len(plan["source_files"]),
            "changes": len(changes),
            "local_changes_requiring_review": sum(c["local_changed_since_sync"] for c in changes),
            "differences": changes, "unmanaged_candidates": plan["unmanaged_candidates"]}


def atomic_write(path: Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".skill-sync-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def apply_plan(plan: dict, *, accept_local_changes: bool = False) -> dict:
    if not isinstance(plan, dict) or plan.get("schema_version") != 1:
        raise SyncError("unsupported synchronization plan")
    try:
        repo, local = checked_root(Path(plan["repo_root"])), checked_root(Path(plan["local_root"]))
        # Rebuilding the full plan prevents injected operations, paths or a stale reviewed snapshot.
        fresh = make_plan(repo, local, scan_unmanaged=plan.get("scan_unmanaged", False))
    except (KeyError, TypeError, ValueError) as exc:
        raise SyncError("invalid synchronization plan") from exc
    if fresh != plan:
        raise SyncError("source, target or metadata changed after review; regenerate the plan")
    if any(c["local_changed_since_sync"] for c in plan["changes"]) and not accept_local_changes:
        raise SyncError("local edits require semantic review and --accept-local-changes")
    old_metadata, _ = metadata_state(local)
    if (not plan["changes"] and old_metadata.get("manifest") == plan["source_files"]
            and old_metadata.get("commit") == plan["commit"]
            and old_metadata.get("plugin_version") == plan["plugin_version"]):
        return {"verified_files": len(plan["source_files"]), "changed_files": 0,
                "backup": None, "commit": plan["commit"], "plugin_version": plan["plugin_version"]}
    local.mkdir(parents=True, exist_ok=True)
    lock = checked_path(local, ".shensheng-skill-sync.lock")
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise SyncError("another synchronization is active; inspect the lock") from exc
    os.close(descriptor)
    backup = None
    originals: dict[str, tuple[bytes, int] | None] = {}
    touched: list[str] = []
    try:
        if make_plan(repo, local, scan_unmanaged=plan.get("scan_unmanaged", False)) != plan:
            raise SyncError("source or target changed while acquiring the lock")
        backup_parent = local / ".shensheng-sync-backups"
        if backup_parent.is_symlink() or backup_parent.exists() and not backup_parent.is_dir():
            raise SyncError("backup directory must be ordinary")
        backup_parent.mkdir(exist_ok=True)
        backup = Path(tempfile.mkdtemp(prefix="sync-", dir=backup_parent))
        paths = [c["path"] for c in plan["changes"]] + [METADATA]
        for relative in paths:
            path = checked_path(local, relative)
            if path.exists():
                originals[relative] = (path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
                saved = backup / relative
                saved.parent.mkdir(parents=True, exist_ok=True)
                saved.write_bytes(originals[relative][0])
                os.chmod(saved, originals[relative][1])
            else:
                originals[relative] = None
        (backup / "BACKUP.json").write_bytes(json_bytes({"paths": paths}))
        source = Path(plan["source_root"])
        for change in plan["changes"]:
            relative = safe_relative(change["path"])
            path = checked_path(local, relative)
            if fingerprint(path) != plan["local_files"][relative]:
                raise SyncError("managed target changed during installation")
            touched.append(relative)
            wanted = plan["source_files"].get(relative)
            if wanted is None:
                path.unlink(missing_ok=True)
            else:
                src = checked_path(source, relative)
                data = src.read_bytes()
                if {"sha256": digest(data), "mode": fingerprint(src)["mode"]} != wanted:
                    raise SyncError("managed source changed during installation")
                atomic_write(path, data, wanted["mode"])
        for relative, wanted in plan["source_files"].items():
            if fingerprint(checked_path(local, relative)) != wanted:
                raise SyncError("installed file verification failed")
        old_metadata, _ = metadata_state(local)
        record = dict(old_metadata)
        record.update({"repository": plan["repository"], "branch": plan["branch"],
                       "commit": plan["commit"], "plugin_version": plan["plugin_version"],
                       "destination": str(local), "completed_at": datetime.now(timezone.utc).isoformat(),
                       "manifest": plan["source_files"], "verified_files": len(plan["source_files"]),
                       "changed_files": len(plan["changes"]), "backup": str(backup),
                       "preserve_unmanaged_files": True,
                       "skills": [{"skill": name, "files": sum(p.startswith(name + "/") for p in plan["source_files"])}
                                  for name in MANAGED_SKILLS]})
        touched.append(METADATA)
        atomic_write(checked_path(local, METADATA), json_bytes(record), 0o600)
        return {"verified_files": len(plan["source_files"]), "changed_files": len(plan["changes"]),
                "backup": str(backup), "commit": plan["commit"], "plugin_version": plan["plugin_version"]}
    except Exception:
        for relative in reversed(touched):
            path = checked_path(local, relative)
            original = originals[relative]
            if original is None:
                path.unlink(missing_ok=True)
            else:
                atomic_write(path, original[0], original[1])
        if backup is not None:
            shutil.rmtree(backup)
        raise
    finally:
        lock.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    plan_parser = sub.add_parser("plan", help="read-only comparison; no installation")
    plan_parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    plan_parser.add_argument("--local-root", type=Path, default=Path.home() / ".codex/skills")
    plan_parser.add_argument("--output", type=Path, help="write a frozen review plan outside public source")
    plan_parser.add_argument("--scan-unmanaged", action="store_true",
                             help="report local candidate additions, excluding runtimes, secrets and case folders")
    apply_parser = sub.add_parser("apply", help="install only a frozen, reviewed plan")
    apply_parser.add_argument("--plan", type=Path, required=True)
    apply_parser.add_argument("--accept-local-changes", action="store_true",
                              help="confirm semantic review of local edits against the chosen source")
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            plan = make_plan(args.repo_root, args.local_root, scan_unmanaged=args.scan_unmanaged)
            if args.output:
                expanded_output = args.output.expanduser().absolute()
                if expanded_output.is_symlink():
                    raise SyncError("review plan must be an ordinary file")
                output = expanded_output.resolve()
                for root in (Path(plan["repo_root"]), Path(plan["local_root"])):
                    if output == root or root in output.parents:
                        raise SyncError("review plan must be outside repository and local skill tree")
                atomic_write(output, json_bytes(plan), 0o600)
            result = summary(plan)
        else:
            result = apply_plan(json.loads(args.plan.expanduser().read_text(encoding="utf-8")),
                                accept_local_changes=args.accept_local_changes)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (SyncError, ValidationError, OSError, ValueError) as exc:
        print(f"Synchronization stopped: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
