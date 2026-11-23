#!/usr/bin/env python3
"""Install the unpacked toolkit's skills using only the Python standard library.

Copyright 2026 Mechanical Patent Toolkit contributors
SPDX-License-Identifier: MIT
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from typing import Iterable


SKILL_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


class InstallError(RuntimeError):
    """A validation or installation failure that leaves original skills intact."""


def default_destination() -> Path:
    configured = os.environ.get("CODEX_HOME")
    return (Path(configured).expanduser() if configured else Path.home() / ".codex") / "skills"


def default_source(package_root: Path | None = None) -> Path:
    """Use the canonical plugin in a checkout, or flat skills in an offline ZIP."""
    root = package_root if package_root is not None else Path(__file__).resolve().parent
    canonical = root / "plugins" / "mechanical-patent-workflow" / "skills"
    return canonical if canonical.exists() else root / "skills"


def _overlaps(first: Path, second: Path) -> bool:
    return first == second or first in second.parents or second in first.parents


def _validate_tree(folder: Path) -> None:
    if folder.is_symlink() or not folder.is_dir():
        raise InstallError(f"技能源必须是普通目录：{folder.name}")
    if not (folder / "SKILL.md").is_file() or (folder / "SKILL.md").is_symlink():
        raise InstallError(f"缺少普通 SKILL.md 文件：{folder.name}")
    for base, directories, files in os.walk(folder, followlinks=False):
        for name in directories + files:
            path = Path(base) / name
            if path.is_symlink():
                raise InstallError(f"公开包中不允许符号链接：{path.relative_to(folder)}")
            if not path.is_file() and not path.is_dir():
                raise InstallError(f"公开包中不允许特殊文件：{path.relative_to(folder)}")


def _safe_file_copy(source: str, destination: str) -> str:
    path = Path(source)
    if path.is_symlink() or not path.is_file():
        raise InstallError(f"复制时源文件发生变化：{path.name}")
    return shutil.copy2(source, destination)


def discover_skills(source_root: Path) -> dict[str, Path]:
    if source_root.is_symlink() or not source_root.is_dir():
        raise InstallError("未找到整包 skills 目录；请先解压全流程技能包，再运行其中的 install.py。")
    result: dict[str, Path] = {}
    for path in sorted(source_root.iterdir()):
        if path.name.startswith("."):
            continue
        if path.is_symlink():
            raise InstallError(f"技能根目录不允许符号链接：{path.name}")
        if not path.is_dir() or not (path / "SKILL.md").exists():
            continue
        if not SKILL_NAME.fullmatch(path.name):
            raise InstallError(f"不合法的技能目录名：{path.name}")
        _validate_tree(path)
        result[path.name] = path
    if not result:
        raise InstallError("skills 目录中没有可安装的技能。")
    return result


def install_skills(source_root: Path, destination: Path, *, only: Iterable[str] | None = None,
                   dry_run: bool = False) -> dict[str, object]:
    """Validate and stage first; back up replacements and roll back failed commits.

    The source and destination must not overlap. Existing symlink targets are
    rejected, while OS-level parent aliases are resolved before overlap checks.
    No package manager, account connection, or global instruction file is used.
    """
    source_root = Path(source_root).expanduser()
    destination = Path(destination).expanduser()
    if source_root.is_symlink() or destination.is_symlink():
        raise InstallError("源目录和安装目录不能是符号链接。")
    available = discover_skills(source_root)
    source = source_root.resolve()
    dest = destination.resolve()
    if _overlaps(source, dest):
        raise InstallError("源技能目录与安装目录不能相同、互为父子或互相重叠。")
    requested = list(dict.fromkeys(only)) if only is not None else list(available)
    if not requested:
        raise InstallError("至少选择一个技能。")
    for name in requested:
        if not SKILL_NAME.fullmatch(name) or name not in available:
            raise InstallError(f"未知或不安全的技能选择：{name}")
    if dest.exists() and not dest.is_dir():
        raise InstallError("安装位置已存在且不是目录。")
    actions = []
    for name in requested:
        target = dest / name
        if target.is_symlink() or (target.exists() and not target.is_dir()):
            raise InstallError(f"现有技能目标不是普通目录，已停止：{name}")
        actions.append({"skill": name, "action": "update" if target.exists() else "install"})
    plan: dict[str, object] = {"destination": str(dest), "dry_run": dry_run, "actions": actions,
                              "backup": None}
    if dry_run:
        return plan

    dest.mkdir(parents=True, exist_ok=True)
    lock = dest / ".mechanical-patent-toolkit-install.lock"
    try:
        lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise InstallError("检测到安装锁。确认没有安装进程后，才可手动移除该锁并重试。") from exc
    os.close(lock_fd)
    staged: Path | None = None
    backup: Path | None = None
    moved: list[str] = []
    installed: list[str] = []
    try:
        staged = Path(tempfile.mkdtemp(prefix=".toolkit-stage-", dir=dest))
        for name in requested:
            _validate_tree(available[name])
            shutil.copytree(available[name], staged / name, copy_function=_safe_file_copy)
            _validate_tree(staged / name)

        if any(item["action"] == "update" for item in actions):
            backup_parent = dest.parent / f"{dest.name}-backups"
            if backup_parent.is_symlink() or (backup_parent.exists() and not backup_parent.is_dir()):
                raise InstallError("备份位置不是普通目录，已停止而未替换原技能。")
            backup_parent.mkdir(exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup = Path(tempfile.mkdtemp(prefix=f"mechanical-patent-toolkit-{stamp}-", dir=backup_parent))
            (backup / "BACKUP.json").write_text(json.dumps({"skills": [item["skill"] for item in actions
                                                                      if item["action"] == "update"]},
                                                           ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for name in requested:
            target = dest / name
            if target.is_symlink() or (target.exists() and not target.is_dir()):
                raise InstallError(f"安装期间目标发生变化，已停止：{name}")
            if target.exists():
                if backup is None:
                    raise InstallError(f"安装期间出现未计划替换的技能，已停止：{name}")
                os.replace(target, backup / name)
                moved.append(name)
            os.replace(staged / name, target)
            installed.append(name)
        plan["backup"] = str(backup) if backup else None
        return plan
    except Exception:
        for name in reversed(installed):
            target = dest / name
            if target.exists():
                shutil.rmtree(target)
        for name in reversed(moved):
            assert backup is not None
            os.replace(backup / name, dest / name)
        if backup is not None and backup.exists():
            shutil.rmtree(backup)
        raise
    finally:
        if staged is not None and staged.exists():
            shutil.rmtree(staged)
        lock.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="安装已解压全流程技能包中的技能；已有同名技能先备份。")
    parser.add_argument("--dest", type=Path, default=None, help="技能安装目录；默认 $CODEX_HOME/skills 或用户 .codex/skills")
    parser.add_argument("--only", nargs="+", metavar="SKILL", help="仅安装指定根技能；保留其完整嵌套内容")
    parser.add_argument("--dry-run", action="store_true", help="只验证并列计划，不创建或修改任何目录")
    args = parser.parse_args(argv)
    try:
        plan = install_skills(default_source(), args.dest or default_destination(),
                              only=args.only, dry_run=args.dry_run)
    except (InstallError, OSError) as exc:
        print(f"安装未完成：{exc}", file=sys.stderr)
        return 2
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    print("仅生成安装计划，未写入文件。" if args.dry_run else "技能文件安装完成；应用、Python依赖及检索账号请按 INSTALL.md 配置。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
