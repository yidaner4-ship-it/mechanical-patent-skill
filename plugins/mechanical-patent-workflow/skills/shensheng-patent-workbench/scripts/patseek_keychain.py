#!/usr/bin/env python3
"""Store and retrieve a PatSeek API key from macOS Keychain without echoing it."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

SERVICE = "com.shensheng.codex.patseek"
ACCOUNT = "patseek-api"
SECURITY = "/usr/bin/security"


class KeychainError(RuntimeError):
    pass


def _security_path() -> str:
    path = SECURITY if os.path.exists(SECURITY) else (shutil.which("security") or "")
    if not path:
        raise KeychainError("未找到 macOS security 命令；请只在当前进程设置 PATSEEK_API_KEY。")
    return path


def get_key() -> str:
    env_key = os.environ.get("PATSEEK_API_KEY", "").strip()
    if env_key:
        return env_key
    proc = subprocess.run(
        [_security_path(), "find-generic-password", "-w", "-a", ACCOUNT, "-s", SERVICE],
        text=True,
        capture_output=True,
        check=False,
    )
    key = proc.stdout.strip()
    if proc.returncode != 0 or not key:
        raise KeychainError("未在 macOS Keychain 找到 PatSeek Key。请先运行本脚本的 set 命令。")
    return key


def key_exists() -> bool:
    proc = subprocess.run(
        [_security_path(), "find-generic-password", "-a", ACCOUNT, "-s", SERVICE],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return proc.returncode == 0


def set_key(prompt_each_time: bool = False) -> int:
    cmd = [_security_path(), "add-generic-password", "-U", "-a", ACCOUNT, "-s", SERVICE]
    if prompt_each_time:
        cmd.extend(["-T", ""])
    cmd.append("-w")
    print("请在 macOS Keychain 提示中粘贴 PatSeek API Key；输入不会显示。", file=sys.stderr)
    proc = subprocess.run(cmd, check=False)
    if proc.returncode:
        print("Key 未保存。请确认在 Mac 终端中运行并允许钥匙串访问。", file=sys.stderr)
        return proc.returncode
    print("PatSeek API Key 已保存到 macOS Keychain；Key 内容未显示。")
    return 0


def delete_key() -> int:
    proc = subprocess.run(
        [_security_path(), "delete-generic-password", "-a", ACCOUNT, "-s", SERVICE],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if proc.returncode:
        print("未找到可删除的 PatSeek Key。")
        return 1
    print("PatSeek API Key 已从 macOS Keychain 删除。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="管理申晟专利工作台的 PatSeek Keychain 凭据")
    sub = parser.add_subparsers(dest="command", required=True)
    set_parser = sub.add_parser("set", help="由 macOS Keychain 隐式读取并保存 Key")
    set_parser.add_argument(
        "--prompt-each-time",
        action="store_true",
        help="以后每次读取 Key 时由 macOS 单独确认（更严格但会打断自动化）",
    )
    sub.add_parser("check", help="只检查 Key 是否存在，不显示内容")
    sub.add_parser("delete", help="删除 Keychain 中的 PatSeek Key")
    args = parser.parse_args()
    try:
        if args.command == "set":
            return set_key(args.prompt_each_time)
        if args.command == "check":
            if key_exists() or bool(os.environ.get("PATSEEK_API_KEY")):
                print("PatSeek API Key 已设置（内容未显示）。")
                return 0
            print("PatSeek API Key 尚未设置。")
            return 1
        return delete_key()
    except KeychainError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

