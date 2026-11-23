#!/usr/bin/env python3
"""Validate the public plugin source without installing software or contacting services.

Copyright 2026 Mechanical Patent Toolkit contributors
SPDX-License-Identifier: MIT
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import zipfile
from urllib.parse import unquote, urlsplit

PLUGIN_NAME = "mechanical-patent-workflow"
PLUGIN_REL = Path("plugins") / PLUGIN_NAME
ROOT_SKILLS = frozenset({
    "fusion-production-modeling", "mechanical-patent-drawings", "patent-disclosure-skill",
    "patent-draft-review", "patent-search", "patseek-patent-search", "shensheng-patent-qa",
    "shensheng-patent-workbench", "documents", "pdf", "spreadsheets",
})
NESTED_SKILLS = frozenset({
    "patent-application", "patent-chart", "patent-disclosure", "patent-docket",
    "patent-exam-policy", "patent-map", "patent-oa", "patent-reader", "patent-search",
})
TRANSIENT_DIRS = frozenset({
    ".git", ".venv", "venv", "env", "node_modules", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".cache", "client", "clients",
})
TEXT_SUFFIXES = frozenset({
    ".md", ".txt", ".json", ".yaml", ".yml", ".py", ".toml", ".ini", ".cfg",
    ".sh", ".html", ".css", ".js", ".ts", ".xml", ".tex", ".go",
})
VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
MARKDOWN_LINK = re.compile(r"!?\[[^\]\n]*\]\(<?([^\s)>]+)>?(?:\s+[^)]*)?\)")
CODE_PATH = re.compile(r"`((?:(?:\.\./)*|\./)?(?:references|scripts|tools|assets|agents|prompts|skills)/[^`\n]+)`")


class ValidationError(RuntimeError):
    """A public source or archive invariant failed."""


def version_tuple(value: str) -> tuple[int, int, int]:
    if not isinstance(value, str) or not VERSION.fullmatch(value):
        raise ValidationError("version must be X.Y.Z, using nonnegative integers without leading zeroes")
    return tuple(map(int, value.split(".")))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValidationError(f"invalid or missing JSON: {path.name}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"JSON object required: {path.name}")
    return value


def excluded(relative: PurePosixPath) -> bool:
    return (any(part in TRANSIENT_DIRS for part in relative.parts)
            or relative.name in {".DS_Store", "Thumbs.db"}
            or relative.suffix in {".pyc", ".pyo"})


def _private_name(relative: PurePosixPath) -> bool:
    name = relative.name.lower()
    return (name == ".env" or name.startswith(".env.") and name not in {".env.example", ".env.template"}
            or name in {"credentials.json", "credentials.yaml", "credentials.yml", "token.json",
                        "tokens.json", "cookies.json", "cookies.txt", "auth.json", ".netrc",
                        "id_rsa", "id_ed25519", "login.keychain-db", "api_key.txt", "apikey.txt"}
            or name.endswith((".pem", ".p12", ".pfx", ".keychain", ".keychain-db"))
            or any(part.lower() in {"private", "secrets", "accounts", "customer-materials"}
                   for part in relative.parts))


def public_files(root: Path) -> list[Path]:
    """Return safe distributable files, rejecting links even inside excluded trees.

    Cache/virtualenv/client folders are omitted. Bundled JavaScript vendor assets
    and their licenses remain; PatSeek's vendor may contain documentation only.
    """
    if root.is_symlink() or not root.is_dir():
        raise ValidationError("source must be an ordinary directory")
    result = []
    for base, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            path = Path(base) / name
            relative = PurePosixPath(path.relative_to(root).as_posix())
            if path.is_symlink():
                raise ValidationError(f"symbolic links are forbidden: {relative}")
            mode = path.lstat().st_mode
            if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise ValidationError(f"special files are forbidden: {relative}")
            if _private_name(relative):
                raise ValidationError(f"private/credential material is forbidden: {relative}")
            if stat.S_ISREG(mode) and not excluded(relative):
                if any(ord(character) < 32 for character in relative.as_posix()):
                    raise ValidationError("control characters are forbidden in distributable filenames")
                if ("patseek-patent-search" in relative.parts and "vendor" in relative.parts
                        and relative.name not in {"README.md", "README.txt", ".gitignore"}):
                    raise ValidationError(f"PatSeek client is not redistributable: {relative}")
                result.append(path)
    return sorted(result, key=lambda path: path.relative_to(root).as_posix())


def _check_text(path: Path, root: Path) -> None:
    if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"workbench", ".gitignore"}:
        return
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeError as exc:
        raise ValidationError(f"expected UTF-8 text: {path.relative_to(root)}") from exc
    # Placeholder paths are portable examples; actual user account paths are not.
    for match in re.finditer(r"(?:/Users/|/home/)([^/\s\"'`<>]+)|[A-Za-z]:\\Users\\([^\\\s\"'`<>]+)", text):
        account = match.group(1) or match.group(2)
        if account.lower() not in {"user", "username", "example", "test", "your-user", "yourname", "name"}:
            raise ValidationError(f"local account path in {path.relative_to(root)}")
    if re.search(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", text):
        raise ValidationError(f"private key in {path.relative_to(root)}")
    if re.search(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|sk-[A-Za-z0-9]{32,})\b", text):
        raise ValidationError(f"possible live credential in {path.relative_to(root)}")


def _frontmatter(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    if len(parts) != 3 or parts[0].strip():
        raise ValidationError(f"missing YAML frontmatter: {path.parent.name}")
    fields = dict(re.findall(r"^([a-zA-Z][\w-]*):[ \t]*(.*)$", parts[1], re.MULTILINE))
    name = fields.get("name", "").strip().strip("\"'")
    if name != path.parent.name or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
        raise ValidationError(f"skill folder/name mismatch: {path.parent.name}")
    if not fields.get("description", "").strip():
        raise ValidationError(f"missing skill description: {path.parent.name}")


def _template(target: str) -> bool:
    return any(part in target for part in ("{", "}", "<", ">", "*", "...", "$", "[", "]"))


def _resolve_reference(path: Path, target: str, plugin: Path) -> Path | None:
    """Resolve skill-relative references, including paths in supporting documents."""
    target = unquote(target.split("#", 1)[0].split("?", 1)[0])
    if not target or _template(target) or urlsplit(target).scheme or target.startswith(("/", "~")):
        return None
    candidates = [path.parent / target]
    # References often quote the entrypoint's command from a nested document.
    for parent in path.parents:
        if parent == plugin.parent:
            break
        if (parent / "SKILL.md").is_file():
            candidates.append(parent / target)
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved == plugin or plugin in resolved.parents:
            if resolved.exists():
                if excluded(PurePosixPath(resolved.relative_to(plugin).as_posix())):
                    raise ValidationError(f"reference points into an omitted runtime/cache: {target}")
                return resolved
    raise ValidationError(f"missing local reference: {path.relative_to(plugin)} -> {target}")


def validate_repository(repo_root: Path) -> dict:
    """Validate the canonical tree and return portable, non-personal inventory data."""
    repo = Path(repo_root)
    if repo.is_symlink() or not repo.is_dir():
        raise ValidationError("repository must be an ordinary directory")
    repo = repo.resolve()
    if (repo / "skills").exists() or (repo / "skills").is_symlink():
        raise ValidationError("root skills/ would create a second source; use plugins/mechanical-patent-workflow/skills only")
    plugin = repo / PLUGIN_REL
    if any(path.is_symlink() for path in (repo / "plugins", plugin, plugin / "skills")):
        raise ValidationError("canonical source parents must not be symbolic links")
    files = public_files(plugin)
    for relative in ("plugin.json", ".codex-plugin/plugin.json", "README.md", "LICENSE", "THIRD_PARTY_NOTICES.md"):
        if not (plugin / relative).is_file():
            raise ValidationError(f"missing plugin resource: {relative}")
    for relative in ("README.md", "INSTALL.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "install.py"):
        if not (repo / relative).is_file() or (repo / relative).is_symlink():
            raise ValidationError(f"missing ordinary repository file: {relative}")
    main = read_json(plugin / "plugin.json")
    compat = read_json(plugin / ".codex-plugin/plugin.json")
    version_tuple(main.get("version"))
    if main.get("name") != PLUGIN_NAME or compat.get("name") != PLUGIN_NAME:
        raise ValidationError("plugin names must match the canonical folder")
    if main["version"] != compat.get("version"):
        raise ValidationError("portable and Codex compatibility manifest versions differ")
    if compat.get("skills") != "./skills/":
        raise ValidationError("Codex compatibility manifest must use ./skills/")
    source = plugin / "skills"
    roots = {p.name for p in source.iterdir() if p.is_dir() and not p.name.startswith(".")}
    if roots != ROOT_SKILLS:
        raise ValidationError(f"expected exactly 11 root skills; missing={sorted(ROOT_SKILLS-roots)}, extra={sorted(roots-ROOT_SKILLS)}")
    skill_paths = sorted(p for p in files if p.name == "SKILL.md")
    expected = {source / name / "SKILL.md" for name in ROOT_SKILLS}
    expected |= {source / "patent-disclosure-skill/skills" / name / "SKILL.md" for name in NESTED_SKILLS}
    if set(skill_paths) != expected:
        raise ValidationError("expected 20 SKILL.md entrypoints, including the nine nested patent skills")
    for path in skill_paths:
        _frontmatter(path)
    marketplace = read_json(repo / ".agents/plugins/marketplace.json")
    entries = [entry for entry in marketplace.get("plugins", [])
               if isinstance(entry, dict) and entry.get("name") == PLUGIN_NAME]
    if len(entries) != 1:
        raise ValidationError("marketplace must have exactly one mechanical-patent-workflow entry")
    origin = entries[0].get("source")
    if isinstance(origin, dict):
        origin = origin.get("path")
    if origin not in {"./plugins/mechanical-patent-workflow", "plugins/mechanical-patent-workflow"}:
        raise ValidationError("marketplace entry must point to ./plugins/mechanical-patent-workflow")
    checked_links = 0
    for path in files:
        _check_text(path, plugin)
        if path.name == "SKILL.md":
            text = path.read_text(encoding="utf-8")
            for target in MARKDOWN_LINK.findall(text) + CODE_PATH.findall(text):
                # Shell commands and example argument values are not resource links.
                if any(character.isspace() for character in target):
                    continue
                if _resolve_reference(path, target, plugin) is not None:
                    checked_links += 1
    reference = source / "mechanical-patent-drawings/references/approved-leader-style.json"
    style = read_json(reference)
    sample_name = style.get("approved_pdf")
    if not isinstance(sample_name, str) or PurePosixPath(sample_name).name != sample_name:
        raise ValidationError("approved PDF must be a same-directory filename")
    sample = reference.parent / sample_name
    if not sample.is_file() or sha256(sample) != style.get("approved_pdf_sha256"):
        raise ValidationError("approved leader sample PDF differs from its declared SHA256")
    preferred = style.get("preferred_exemplar", {})
    preview = preferred.get("preview_png")
    if preview and (not isinstance(preview, str) or PurePosixPath(preview).name != preview
                    or not (reference.parent / preview).is_file()):
        raise ValidationError("approved leader preview must be a same-directory PNG")
    # Requirements describe dependencies; none of these environments is bundled.
    requirements = [p.relative_to(plugin).as_posix() for p in files
                    if p.name.startswith("requirements") and p.suffix == ".txt"]
    return {
        "plugin": PLUGIN_NAME, "version": main["version"],
        "canonical_skills": (PLUGIN_REL / "skills").as_posix(),
        "root_skills": sorted(roots), "skill_entrypoints": len(skill_paths),
        "file_count": len(files), "checked_local_references": checked_links,
        "approved_style": {"json": reference.relative_to(plugin).as_posix(),
                           "json_sha256": sha256(reference),
                           "pdf": sample.relative_to(plugin).as_posix(), "pdf_sha256": sha256(sample)},
        "dependency_declarations": requirements,
        "external_dependencies": ["Autodesk Fusion or another CAD application", "Word or LibreOffice",
                                  "Poppler", "Python packages declared in requirements files",
                                  "configured MCP connections", "user-supplied licensed PatSeek client and account"],
        "runtime_bundled": False,
    }


def validate_archives(repo_root: Path) -> dict:
    """Check preserved archive hashes and verify the latest ZIPs follow the source."""
    report = validate_repository(repo_root)
    repo = Path(repo_root).resolve()
    downloads = repo / "downloads"
    if downloads.is_symlink() or not downloads.is_dir():
        raise ValidationError("downloads must be an ordinary directory")
    record = read_json(downloads / "RELEASE_MANIFEST.json")
    if record.get("version") != report["version"] or record.get("plugin") != PLUGIN_NAME:
        raise ValidationError("release manifest does not describe the current plugin version")
    sums = {}
    try:
        lines = (downloads / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValidationError("missing SHA256SUMS") from exc
    for line in lines:
        parts = line.split("  ", 1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            raise ValidationError("invalid SHA256SUMS entry")
        digest, name = parts
        if PurePosixPath(name).name != name or "\\" in name or name in sums:
            raise ValidationError("unsafe or duplicate SHA256SUMS filename")
        path = downloads / name
        if path.is_symlink() or not path.is_file() or sha256(path) != digest:
            raise ValidationError(f"checksum mismatch or missing file: {name}")
        sums[name] = digest
    actual_names = {path.name for path in downloads.glob("*.zip")} | {"RELEASE_MANIFEST.json"}
    if set(sums) != actual_names:
        raise ValidationError("SHA256SUMS must cover all ZIPs and RELEASE_MANIFEST.json exactly once")
    archive_entries = record.get("archives", [])
    declared = {entry.get("name"): entry for entry in archive_entries if isinstance(entry, dict)}
    if len(declared) != len(archive_entries) or set(declared) != actual_names - {"RELEASE_MANIFEST.json"}:
        raise ValidationError("release archive inventory differs from downloads")
    for name, entry in declared.items():
        path = downloads / name
        if entry.get("sha256") != sums[name] or entry.get("bytes") != path.stat().st_size:
            raise ValidationError(f"release archive inventory mismatch: {name}")
    expected = {path.relative_to(repo / PLUGIN_REL).as_posix(): path
                for path in public_files(repo / PLUGIN_REL)}
    offline = {name: path for name, path in expected.items() if name.startswith("skills/")}
    offline.update({name: repo / name for name in ("install.py", "README.md", "INSTALL.md", "LICENSE", "THIRD_PARTY_NOTICES.md")})
    latest = record.get("current_archives", {})
    for kind, files in (("plugin", expected), ("offline", offline)):
        name = latest.get(kind)
        if not isinstance(name, str) or name not in declared:
            raise ValidationError(f"missing current {kind} archive")
        try:
            with zipfile.ZipFile(downloads / name) as archive:
                if set(archive.namelist()) != set(files) or len(archive.namelist()) != len(files):
                    raise ValidationError(f"current {kind} ZIP file inventory differs from source")
                for relative, path in files.items():
                    if archive.read(relative) != path.read_bytes():
                        raise ValidationError(f"ZIP does not follow current source: {relative}")
                    mode = stat.S_IMODE(archive.getinfo(relative).external_attr >> 16)
                    wanted = 0o755 if path.stat().st_mode & 0o111 else 0o644
                    if mode != wanted:
                        raise ValidationError(f"ZIP executable mode differs from source: {relative}")
        except (OSError, zipfile.BadZipFile, KeyError) as exc:
            raise ValidationError(f"invalid {kind} ZIP") from exc
    file_entries = record.get("plugin_files", [])
    declared_files = {entry.get("path"): entry for entry in file_entries if isinstance(entry, dict)}
    if len(declared_files) != len(file_entries) or set(declared_files) != set(expected):
        raise ValidationError("release plugin file inventory differs from source")
    for name, path in expected.items():
        if declared_files[name].get("sha256") != sha256(path):
            raise ValidationError(f"release plugin file hash differs from source: {name}")
    return {"archives": len(declared), "current_payloads_match_source": True}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--check-archives", action="store_true", help="verify ZIP checksums and agreement with current canonical source")
    args = parser.parse_args(argv)
    try:
        result = validate_repository(args.repo_root)
        if args.check_archives:
            result["release"] = validate_archives(args.repo_root)
    except (ValidationError, OSError) as exc:
        print(f"Validation failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
