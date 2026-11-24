#!/usr/bin/env python3
"""Commit an explicitly reviewed public file set and push it once, without force.

Copyright 2026 Mechanical Patent Toolkit contributors
SPDX-License-Identifier: MIT
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit
import zipfile


class PublishError(RuntimeError):
    pass


ROOT_FILES = frozenset({
    "README.md", "MAINTAINER.md", "INSTALL.md", "LICENSE", "THIRD_PARTY_NOTICES.md",
    "install.py", ".gitignore",
})
ROOT_DIRS = frozenset({"plugins", "downloads", "tools", "tests", ".agents"})
HISTORICAL_ZIP = re.compile(r"-(?:\d+\.\d+\.\d+|\d{8})\.zip$")
OBJECT_ID = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?$")
SHA256 = re.compile(r"[0-9a-f]{64}$")


def run_git(repo: Path, *args: str, check: bool = True, binary: bool = False):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="Never",
               GIT_OPTIONAL_LOCKS="0")
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                            text=not binary, env=env, timeout=120)
    if check and result.returncode:
        # Do not copy credential URLs, hook output or personal paths to a report.
        raise PublishError(f"Git {args[0]} failed (exit {result.returncode}); inspect locally before retrying")
    return result


def repository(path: Path) -> Path:
    if any(os.environ.get(name) for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")):
        raise PublishError("Run outside custom GIT_DIR/GIT_WORK_TREE/GIT_INDEX_FILE overrides")
    root = run_git(path, "rev-parse", "--show-toplevel").stdout.strip()
    return Path(root).resolve()


def oid(value, name: str, nullable: bool = False):
    if nullable and value is None:
        return None
    if not isinstance(value, str) or not OBJECT_ID.fullmatch(value):
        raise PublishError(f"Invalid {name}")
    return value


def remote_identity(url: str) -> str:
    if not isinstance(url, str) or not url or any(c in url for c in "\r\n\0"):
        raise PublishError("Invalid remote URL")
    if re.fullmatch(r"git@github\.com:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?", url):
        return "github:" + url.split(":", 1)[1].removesuffix(".git").lower()
    parsed = urlsplit(url)
    if parsed.scheme in {"https", "ssh"}:
        if (parsed.hostname != "github.com" or parsed.query or parsed.fragment or parsed.password
                or parsed.port not in {None, 443 if parsed.scheme == "https" else 22}
                or parsed.username not in ({None} if parsed.scheme == "https" else {"git"})):
            raise PublishError("Only credential-free GitHub remote URLs are accepted")
        name = parsed.path.strip("/").removesuffix(".git")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", name):
            raise PublishError("Invalid GitHub repository name")
        return "github:" + name.lower()
    if parsed.scheme == "file" and parsed.netloc in {"", "localhost"} and not parsed.query and not parsed.fragment:
        return "local:" + str(Path(parsed.path).resolve())
    if not parsed.scheme and Path(url).is_absolute():
        return "local:" + str(Path(url).resolve())
    raise PublishError("Unsupported remote URL; use a GitHub HTTPS/SSH URL or an absolute local test remote")


def check_target(repo: Path, manifest: dict) -> None:
    name = manifest.get("remote")
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", name):
        raise PublishError("Invalid remote name")
    expected = remote_identity(manifest.get("expected_remote_url"))
    for switches in (("get-url", "--all"), ("get-url", "--push", "--all")):
        values = run_git(repo, "remote", *switches, name).stdout.splitlines()
        if len(values) != 1 or remote_identity(values[0]) != expected:
            raise PublishError("Fetch/push target differs from the explicitly selected repository")
    branch = manifest.get("branch")
    if not isinstance(branch, str) or run_git(repo, "check-ref-format", "refs/heads/" + branch, check=False).returncode:
        raise PublishError("Invalid target branch")


def remote_head(repo: Path, manifest: dict):
    result = run_git(repo, "ls-remote", "--exit-code", manifest["remote"], "refs/heads/" + manifest["branch"], check=False)
    if result.returncode == 2 and not result.stdout.strip():
        return None
    if result.returncode:
        raise PublishError("Remote read/authentication failed; configure the normal Git credential channel first")
    rows = result.stdout.splitlines()
    if len(rows) != 1:
        raise PublishError("Expected exactly one target branch")
    value, ref = rows[0].split("\t")
    if ref != "refs/heads/" + manifest["branch"]:
        raise PublishError("Unexpected remote reference")
    return oid(value, "remote commit")


def public_path(value: str) -> str:
    if not isinstance(value, str) or any(c in value for c in "\0\r\n\\"):
        raise PublishError("Invalid public path")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(p in {".", "..", ".git"} for p in path.parts) or str(path) != value:
        raise PublishError("Paths must be literal repository-relative file names")
    if value not in ROOT_FILES and path.parts[0] not in ROOT_DIRS:
        raise PublishError("Path is outside this repository's public distribution layout")
    blocked = {".env", "credentials.json", "tokens.json", "cookies.json", ".ds_store",
               "__pycache__", ".venv", "node_modules", "private", "secrets", "customer-materials"}
    if any(part.lower() in blocked for part in path.parts):
        raise PublishError("Credential, private or transient files are not publishable")
    return value


def current_entry(repo: Path, path: str) -> dict:
    target = repo / path
    if not target.exists() and not target.is_symlink():
        return {"path": path, "sha256": None, "mode": None}
    if any(p.is_symlink() for p in (target, *target.parents) if p != repo.parent):
        raise PublishError("Symbolic links are not publishable")
    if not target.is_file() or not target.resolve().is_relative_to(repo):
        raise PublishError("Selected paths must be regular repository files")
    mode = "100755" if target.stat().st_mode & 0o111 else "100644"
    return {"path": path, "sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "mode": mode}


def committed_entry(repo: Path, commit: str, path: str):
    result = run_git(repo, "--literal-pathspecs", "ls-tree", "-z", commit, "--", path, binary=True).stdout
    if not result:
        return {"path": path, "sha256": None, "mode": None}
    records = result.rstrip(b"\0").split(b"\0")
    if len(records) != 1:
        raise PublishError("Expected one committed file")
    meta, actual = records[0].split(b"\t", 1)
    mode, kind, object_id = meta.decode().split()
    if actual.decode() != path or kind != "blob" or mode not in {"100644", "100755"}:
        raise PublishError("Unsupported committed file type")
    data = run_git(repo, "cat-file", "blob", object_id, binary=True).stdout
    return {"path": path, "sha256": hashlib.sha256(data).hexdigest(), "mode": mode}


def manifest_structure(manifest: dict) -> list[dict]:
    if not isinstance(manifest, dict) or manifest.get("format") != 1:
        raise PublishError("Unsupported manifest format")
    oid(manifest.get("base_commit"), "base commit")
    oid(manifest.get("expected_remote_commit"), "expected remote commit", nullable=True)
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        raise PublishError("A nonempty explicit file manifest is required")
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256", "mode"}:
            raise PublishError("Invalid file entry")
        path = public_path(entry["path"])
        if path in seen:
            raise PublishError("Duplicate selected path")
        seen.add(path)
        if ((entry["sha256"] is None) != (entry["mode"] is None)
                or entry["sha256"] is not None and (not isinstance(entry["sha256"], str)
                    or not SHA256.fullmatch(entry["sha256"]) or entry["mode"] not in {"100644", "100755"})):
            raise PublishError("Invalid file digest/mode")
    return entries


def check_files(repo: Path, manifest: dict) -> list[dict]:
    entries = manifest_structure(manifest)
    for entry in entries:
        path = entry["path"]
        if current_entry(repo, path) != entry:
            raise PublishError(f"Reviewed bytes/mode changed: {path}")
        old = committed_entry(repo, manifest["base_commit"], path)
        if old == entry:
            raise PublishError(f"Unchanged path should not be in a publish manifest: {path}")
        if path.startswith("downloads/") and HISTORICAL_ZIP.search(path) and old["sha256"] is not None:
            raise PublishError("Previously committed versioned/date ZIPs must be preserved; publish a new version")
    return entries


def check_local_base(repo: Path, manifest: dict) -> None:
    if run_git(repo, "rev-parse", "HEAD").stdout.strip() != manifest["base_commit"]:
        raise PublishError("Local HEAD changed since preparation")
    branch = run_git(repo, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    if branch.returncode or branch.stdout.strip() != manifest["branch"]:
        raise PublishError("Check out the explicitly selected target branch before publishing")
    if run_git(repo, "diff", "--cached", "--quiet", check=False).returncode:
        raise PublishError("Existing staged changes must be resolved first; they will not be included or cleared")


def export_snapshot(repo: Path, commit: str, destination: Path) -> None:
    data = run_git(repo, "archive", "--format=zip", commit, binary=True).stdout
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for entry in archive.infolist():
            relative = PurePosixPath(entry.filename)
            if relative.is_absolute() or ".." in relative.parts:
                raise PublishError("Unsafe committed archive path")
            target = destination.joinpath(*relative.parts)
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            mode = entry.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise PublishError("Committed symlinks are not accepted in a release snapshot")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(entry))
            target.chmod(0o755 if mode & 0o111 else 0o644)


def validate_candidate(repo: Path, manifest: dict) -> None:
    with tempfile.TemporaryDirectory(prefix="skill-publish-candidate-") as temporary:
        candidate = Path(temporary)
        export_snapshot(repo, manifest["base_commit"], candidate)
        for entry in manifest["files"]:
            target = candidate / entry["path"]
            if entry["sha256"] is None:
                target.unlink()
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                data = (repo / entry["path"]).read_bytes()
                if hashlib.sha256(data).hexdigest() != entry["sha256"]:
                    raise PublishError("Selected file changed while building the candidate")
                target.write_bytes(data)
                target.chmod(0o755 if entry["mode"] == "100755" else 0o644)
        validator = candidate / "tools/validate_plugin.py"
        if not validator.is_file():
            raise PublishError("Candidate is missing the release validator")
        result = subprocess.run([sys.executable, str(validator), "--check-archives"], cwd=candidate,
                                capture_output=True, text=True, timeout=120,
                                env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        if result.returncode:
            raise PublishError("Candidate source/archive validation failed; fix the release before committing")


def preflight(repo: Path, manifest: dict) -> None:
    manifest_structure(manifest)
    check_target(repo, manifest)
    check_local_base(repo, manifest)
    check_files(repo, manifest)
    if remote_head(repo, manifest) != manifest["expected_remote_commit"]:
        raise PublishError("Remote branch changed since preparation; fetch/review and prepare again")
    if manifest["expected_remote_commit"] not in {None, manifest["base_commit"]}:
        raise PublishError("Local base must match the existing target branch")
    validate_candidate(repo, manifest)


def verify_commit(repo: Path, manifest: dict, commit: str) -> str:
    parents = run_git(repo, "show", "-s", "--format=%P", commit).stdout.strip().split()
    if parents != [manifest["base_commit"]]:
        raise PublishError("Expected exactly one new commit based on the reviewed base")
    paths = set(run_git(repo, "diff", "--name-only", "--no-renames", "-z",
                        manifest["base_commit"], commit).stdout.rstrip("\0").split("\0"))
    if paths != {entry["path"] for entry in manifest["files"]}:
        raise PublishError("Commit includes missing or additional paths; not pushing")
    for entry in manifest["files"]:
        if committed_entry(repo, commit, entry["path"]) != entry:
            raise PublishError("Committed bytes/mode differ from the reviewed manifest; not pushing")
    return run_git(repo, "rev-parse", commit + "^{tree}").stdout.strip()


def verify_remote(repo: Path, manifest: dict, commit: str) -> dict:
    manifest_structure(manifest)
    oid(commit, "published commit")
    check_target(repo, manifest)
    tree = verify_commit(repo, manifest, commit)
    if remote_head(repo, manifest) != commit:
        raise PublishError("Published commit not confirmed at the remote branch; do not repeat the push blindly")
    reference = f"refs/remotes/{manifest['remote']}/{manifest['branch']}"
    run_git(repo, "fetch", "--no-tags", manifest["remote"], f"refs/heads/{manifest['branch']}:{reference}")
    actual = run_git(repo, "rev-parse", reference).stdout.strip()
    actual_tree = run_git(repo, "rev-parse", reference + "^{tree}").stdout.strip()
    if actual != commit or actual_tree != tree:
        raise PublishError("Remote fetch did not confirm the published commit and tree")
    return {"status": "verified", "commit": commit, "tree": tree,
            "remote": manifest["remote"], "branch": manifest["branch"], "files": len(manifest["files"])}


def publish(repo: Path, manifest: dict, message: str | None, apply: bool) -> dict:
    preflight(repo, manifest)
    result = {"status": "ready", "base_commit": manifest["base_commit"],
              "branch": manifest["branch"], "files": manifest["files"], "applied": False}
    if not apply:
        return result
    if not message or not message.strip():
        raise PublishError("An explicit nonempty commit message is required with --apply")
    # Normal receive-pack authentication, before changing the user's index or HEAD.
    check_target(repo, manifest)
    run_git(repo, "push", "--dry-run", "--porcelain", manifest["remote"],
            "HEAD:refs/heads/" + manifest["branch"])
    check_target(repo, manifest)
    check_local_base(repo, manifest)
    check_files(repo, manifest)
    if remote_head(repo, manifest) != manifest["expected_remote_commit"]:
        raise PublishError("Remote changed during authentication; prepare again")
    paths = [entry["path"] for entry in manifest["files"]]
    run_git(repo, "--literal-pathspecs", "add", "--all", "--", *paths)
    staged = set(run_git(repo, "diff", "--cached", "--name-only", "--no-renames", "-z").stdout.rstrip("\0").split("\0"))
    if staged != set(paths):
        raise PublishError("Index differs from the explicit file list; not committing")
    run_git(repo, "commit", "-m", message)
    commit = run_git(repo, "rev-parse", "HEAD").stdout.strip()
    verify_commit(repo, manifest, commit)
    if run_git(repo, "diff", "--cached", "--quiet", check=False).returncode:
        raise PublishError("A hook changed the index; local commit retained for review, not pushed")
    check_files(repo, manifest)
    check_target(repo, manifest)
    if remote_head(repo, manifest) != manifest["expected_remote_commit"]:
        raise PublishError("Remote changed before push; local commit retained, not pushed")
    # One real push, no force, no retry or automatic conflict resolution.
    run_git(repo, "push", "--porcelain", manifest["remote"], "HEAD:refs/heads/" + manifest["branch"])
    return verify_remote(repo, manifest, commit)


def prepare(repo: Path, remote: str, expected_url: str, branch: str, paths: list[str]) -> dict:
    base = run_git(repo, "rev-parse", "HEAD").stdout.strip()
    manifest = {"format": 1, "base_commit": base, "remote": remote,
                "expected_remote_url": expected_url, "branch": branch,
                "expected_remote_commit": None, "files": []}
    check_target(repo, manifest)
    check_local_base(repo, manifest)
    manifest["expected_remote_commit"] = remote_head(repo, manifest)
    if manifest["expected_remote_commit"] not in {None, base}:
        raise PublishError("Fetch and reconcile the target branch before preparing a release")
    seen = set()
    for value in paths:
        path = public_path(value)
        if path in seen:
            raise PublishError("Duplicate selected path")
        seen.add(path)
        entry = current_entry(repo, path)
        old = committed_entry(repo, base, path)
        if entry["sha256"] is None and old["sha256"] is None:
            raise PublishError(f"Selected file does not exist: {path}")
        if entry != old:
            manifest["files"].append(entry)
    manifest["files"].sort(key=lambda item: item["path"])
    check_files(repo, manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest="command", required=True)
    planning = commands.add_parser("prepare", help="Freeze only explicitly selected public files; never stage/push")
    planning.add_argument("--manifest", required=True, type=Path)
    planning.add_argument("--remote", default="origin")
    planning.add_argument("--expected-remote", required=True)
    planning.add_argument("--branch", required=True)
    planning.add_argument("--paths-from", type=Path, help="UTF-8 JSON array of explicitly reviewed relative file paths")
    planning.add_argument("paths", nargs="*")
    publishing = commands.add_parser("publish", help="Default is validation only; --apply makes one commit and push")
    publishing.add_argument("--manifest", required=True, type=Path)
    publishing.add_argument("--message")
    publishing.add_argument("--apply", action="store_true")
    verification = commands.add_parser("verify", help="Repeat remote verification only, without committing or pushing")
    verification.add_argument("--manifest", required=True, type=Path)
    verification.add_argument("--commit", required=True)
    args = parser.parse_args(argv)
    try:
        repo = repository(args.repo)
        if args.manifest.resolve().is_relative_to(repo):
            raise PublishError("Keep publication manifests outside the repository, including .git")
        if args.command == "prepare":
            paths = list(args.paths)
            if args.paths_from:
                selected = json.loads(args.paths_from.read_text(encoding="utf-8"))
                if not isinstance(selected, list) or not all(isinstance(x, str) for x in selected):
                    raise PublishError("--paths-from requires a JSON array of file paths")
                paths += selected
            manifest = prepare(repo, args.remote, args.expected_remote, args.branch, paths)
            if args.manifest.exists():
                raise PublishError("Manifest already exists; review changes and choose a new manifest path")
            args.manifest.parent.mkdir(parents=True, exist_ok=True)
            args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            result = {"status": "prepared", "base_commit": manifest["base_commit"], "branch": manifest["branch"],
                      "files": manifest["files"], "applied": False}
        else:
            manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
            if not isinstance(manifest, dict):
                raise PublishError("Manifest must be a JSON object")
            result = (verify_remote(repo, manifest, args.commit) if args.command == "verify"
                      else publish(repo, manifest, args.message, args.apply))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (PublishError, ValueError, OSError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"status": "stopped", "reason": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
