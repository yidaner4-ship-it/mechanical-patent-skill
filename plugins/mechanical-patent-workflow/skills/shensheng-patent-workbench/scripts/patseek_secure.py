#!/usr/bin/env python3
"""Run the upstream PatSeek client with Keychain credentials and no implicit storage."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import hmac
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
import unicodedata

from patseek_keychain import KeychainError, get_key


PAID_COMMANDS = {"bool", "semantic", "patent"}
QUERY_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
COMMANDS = PAID_COMMANDS | {"key-info", "task", "cancel", "tasks"}
GLOBAL_FLAGS = {"--no-cache", "--no-call-log", "--force", "--help", "-h"}
COMMAND_SPECS = {
    "bool": {
        "values": {"--page", "--page-size", "--market", "--figures-dir"},
        "flags": GLOBAL_FLAGS | {"--show-figures"},
        "positionals": 0,
    },
    "patent": {
        "values": {"--market", "--figures-dir"},
        "flags": GLOBAL_FLAGS | {"--show-figures", "--no-enrichment"},
        "positionals": 0,
    },
    "semantic": {
        "values": {"--timeout"},
        "flags": GLOBAL_FLAGS,
        "positionals": 0,
    },
    "key-info": {"values": set(), "flags": GLOBAL_FLAGS, "positionals": 0},
    "task": {
        "values": set(), "flags": GLOBAL_FLAGS | {"--include-partial"}, "positionals": 1,
    },
    "cancel": {"values": set(), "flags": GLOBAL_FLAGS, "positionals": 1},
    "tasks": {"values": {"--limit"}, "flags": GLOBAL_FLAGS, "positionals": 0},
}


def default_client() -> Path:
    skills_root = Path(__file__).resolve().parents[2]
    return skills_root / "patseek-patent-search" / "scripts" / "patseek_client.py"


def trusted_default_client() -> Path:
    skills_root = Path(__file__).resolve().parents[2]
    candidate = default_client()
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(skills_root.resolve(strict=True))
    except (FileNotFoundError, ValueError) as exc:
        raise RuntimeError("PatSeek 客户端不在受信 Skills 目录内") from exc
    info = resolved.stat()
    if info.st_uid != os.getuid() or not stat.S_ISREG(info.st_mode):
        raise RuntimeError("PatSeek 客户端所有者或文件类型不可信")
    if stat.S_IMODE(info.st_mode) & 0o022:
        raise RuntimeError("PatSeek 客户端可被组或其他用户写入，拒绝加载")
    current = resolved.parent
    trusted_root = skills_root.resolve(strict=True)
    while True:
        parent_info = current.stat()
        if parent_info.st_uid != os.getuid() or stat.S_IMODE(parent_info.st_mode) & 0o022:
            raise RuntimeError(f"PatSeek 客户端目录权限不可信: {current}")
        if current == trusted_root:
            break
        current = current.parent
    return resolved


def _reject_secret_args(args: list[str]) -> None:
    for arg in args:
        option = arg.split("=", 1)[0]
        if option.startswith("--") and "--api-key".startswith(option):
            raise ValueError(
                "禁止通过 --api-key 传入 Key。请使用 scripts/workbench keychain set，或只在当前进程设置 PATSEEK_API_KEY。"
            )


def _load_client(path: Path):
    if not path.is_file():
        raise FileNotFoundError(f"未找到上游 PatSeek 客户端: {path}")
    spec = importlib.util.spec_from_file_location("shensheng_upstream_patseek_client", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载上游 PatSeek 客户端: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _apply_no_store(module) -> None:
    required = ["load_cache", "save_cache", "recent_calls", "log_call", "throttle", "main"]
    missing = [name for name in required if not hasattr(module, name)]
    if missing:
        raise RuntimeError(f"上游客户端接口发生变化，安全包装器拒绝继续: {', '.join(missing)}")
    module.CALL_LOG_DISABLED = True
    module.load_cache = lambda *args, **kwargs: None
    module.save_cache = lambda *args, **kwargs: None
    module.recent_calls = lambda *args, **kwargs: []
    module.log_call = lambda *args, **kwargs: None
    module.throttle = lambda *args, **kwargs: None
    if hasattr(module, "find_near_dup"):
        module.find_near_dup = lambda *args, **kwargs: (None, 0.0)


def _inject_private_operand(forwarded: list[str], operand: str | None) -> list[str]:
    if operand is None:
        return list(forwarded)
    supported = {"bool", "semantic", "patent"}
    for index, arg in enumerate(forwarded):
        if arg in supported:
            return [*forwarded[: index + 1], operand, *forwarded[index + 1 :]]
    raise ValueError("--query-file/--query-stdin 仅适用于 bool、semantic 或 patent 子命令")


def _validate_forwarded(forwarded: list[str]) -> tuple[str | None, int | None]:
    """Fail closed on argparse abbreviations, unknown options, and paid operands."""
    if not forwarded:
        return None, None
    command: str | None = None
    command_index: int | None = None
    for index, token in enumerate(forwarded):
        if token in COMMANDS:
            command, command_index = token, index
            break
        if token not in GLOBAL_FLAGS:
            if token.startswith("-"):
                raise ValueError(f"未知或缩写的 PatSeek 选项被拒绝: {token}")
            raise ValueError(f"未知 PatSeek 子命令: {token}")
    if command is None or command_index is None:
        if any(token in {"-h", "--help"} for token in forwarded):
            return None, None
        raise ValueError("缺少 PatSeek 子命令")

    spec = COMMAND_SPECS[command]
    values = spec["values"]
    flags = spec["flags"]
    positionals: list[str] = []
    index = command_index + 1
    while index < len(forwarded):
        token = forwarded[index]
        if token == "--":
            positionals.extend(forwarded[index + 1 :])
            break
        if token.startswith("-"):
            option, separator, _ = token.partition("=")
            if option in values:
                if separator:
                    index += 1
                    continue
                if index + 1 >= len(forwarded):
                    raise ValueError(f"{option} 缺少参数值")
                positionals.append("__OPTION_VALUE__")
                index += 2
                continue
            if option in flags and not separator:
                index += 1
                continue
            raise ValueError(f"未知或缩写的 PatSeek 选项被拒绝: {token}")
        positionals.append(token)
        index += 1

    actual_positionals = [item for item in positionals if item != "__OPTION_VALUE__"]
    if command in PAID_COMMANDS and actual_positionals:
        raise ValueError("付费子命令禁止在 argv 中传入查询/公开号；请使用 --query-file 或 --query-stdin")
    help_only = any(token in {"-h", "--help"} for token in forwarded)
    if command not in PAID_COMMANDS and not help_only:
        expected = int(spec["positionals"])
        if len(actual_positionals) != expected:
            raise ValueError(f"{command} 需要 {expected} 个位置参数")
    return command, command_index


def _option_value(forwarded: list[str], name: str, default: str) -> str:
    values: list[str] = []
    for index, token in enumerate(forwarded):
        if token == name:
            if index + 1 >= len(forwarded):
                raise ValueError(f"{name} 缺少参数值")
            values.append(forwarded[index + 1])
        elif token.startswith(name + "="):
            values.append(token.split("=", 1)[1])
    if len(values) > 1:
        raise ValueError(f"{name} 不得重复")
    return values[0] if values else default


def _normalize_operand(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    return " ".join(value.split()).casefold()


def _reservation_digest(case: dict, record: dict, operand: str) -> str:
    route_lock = case.get("route_lock")
    if not isinstance(route_lock, dict) or not route_lock.get("query_hmac_key"):
        raise ValueError("case.json 缺少 query_hmac_key")
    payload = {
        "case_id": case.get("case_id"),
        "case_type": case.get("case_type"),
        "engine": record.get("engine"),
        "paid_command": record.get("paid_command") or "",
        "market": str(record.get("market") or "").lower(),
        "page": record.get("page"),
        "page_size": record.get("page_size"),
        "enrichment_mode": record.get("enrichment_mode"),
        "purpose": str(record.get("purpose") or "").strip(),
        "jurisdiction_filter": sorted(
            str(item).upper() for item in (record.get("jurisdiction_filter") or [])
        ),
        "date_filter": record.get("date_filter") or "",
        "query": _normalize_operand(operand),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    try:
        secret = bytes.fromhex(str(route_lock["query_hmac_key"]))
    except (ValueError, TypeError) as exc:
        raise ValueError("case.json 的 query_hmac_key 非法") from exc
    return hmac.new(secret, canonical.encode("utf-8"), hashlib.sha256).hexdigest()


def _write_case(path: Path, case: dict) -> None:
    temp = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp")
    payload = json.dumps(case, ensure_ascii=False, indent=2) + "\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = -1
    try:
        fd = os.open(temp, flags, 0o600)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        parent_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            os.unlink(temp)
        except FileNotFoundError:
            pass


def _open_private_lock(path: Path) -> int:
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise ValueError(f"锁文件类型或所有者不可信: {path}")
        os.fchmod(fd, 0o600)
        return fd
    except Exception:
        os.close(fd)
        raise


def _acquire_execution_lock(case_dir: Path, query_hash: str) -> int:
    if not QUERY_HASH_RE.fullmatch(query_hash):
        raise ValueError("query_hash 必须是 64 位小写十六进制摘要")
    root = case_dir.expanduser().resolve()
    fd = _open_private_lock(root / f".patseek-exec-{query_hash}.lock")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except BlockingIOError as exc:
        os.close(fd)
        raise ValueError("同一 query_hash 的 PatSeek 调用仍在执行，拒绝并发启动") from exc


def _claim_paid_reservation(
    case_dir: Path,
    query_hash: str,
    command: str,
    forwarded: list[str],
    operand: str,
) -> str:
    root = case_dir.expanduser().resolve()
    case_path = root / "case.json"
    if not case_path.is_file():
        raise ValueError(f"未找到案件 case.json: {case_path}")
    lock_path = root / ".workbench.lock"
    fd = _open_private_lock(lock_path)
    with os.fdopen(fd, "r+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            case = json.loads(case_path.read_text(encoding="utf-8"))
            route_lock = case.get("route_lock") if isinstance(case, dict) else None
            if not isinstance(route_lock, dict):
                raise ValueError("case.json 缺少 route_lock")
            if route_lock.get("active_phase") != "search":
                raise ValueError("付费调用只允许在 search 阶段执行")
            if route_lock.get("active_search_engine") != "patseek":
                raise ValueError("route_lock 当前主引擎不是 patseek")
            records = route_lock.get("queries")
            if not isinstance(records, list):
                raise ValueError("case.json 缺少 route_lock.queries")
            record = next(
                (item for item in records if isinstance(item, dict) and item.get("query_hash") == query_hash),
                None,
            )
            if record is None:
                raise ValueError("query_hash 未经 reserve-query 预留")
            if record.get("status") != "running":
                raise ValueError(f"query_hash 不是 running 状态: {record.get('status')}")
            if record.get("engine") != "patseek":
                raise ValueError("预留记录的引擎不是 patseek")
            if record.get("paid_command") != command:
                raise ValueError("实际 PatSeek 子命令与预留 paid_command 不一致")
            if record.get("execution_started_at"):
                raise ValueError("该预留查询已经启动过付费执行；请先 complete-query，再按规则重试")

            market = _option_value(forwarded, "--market", "cn") if command in {"bool", "patent"} else None
            if market is not None and market.lower() != str(record.get("market") or "").lower():
                raise ValueError("实际 --market 与预留记录不一致")
            if command == "bool":
                try:
                    page = int(_option_value(forwarded, "--page", "1"))
                except ValueError as exc:
                    raise ValueError("--page 必须是整数") from exc
                if page != record.get("page"):
                    raise ValueError("实际 --page 与预留记录不一致")
                try:
                    page_size = int(_option_value(forwarded, "--page-size", "20"))
                except ValueError as exc:
                    raise ValueError("--page-size 必须是整数") from exc
                if not 1 <= page_size <= 50:
                    raise ValueError("--page-size 必须在 1-50")
                if page_size != record.get("page_size"):
                    raise ValueError("实际 --page-size 与预留记录不一致")
            elif record.get("page") != 1:
                raise ValueError(f"{command} 预留记录的 page 必须为 1")
            if command == "semantic" and str(record.get("market") or "").lower() != "cn":
                raise ValueError("PatSeek semantic 预留的 market 必须为 cn")
            if command == "patent":
                actual_mode = "no-enrichment" if "--no-enrichment" in forwarded else "enriched"
                if actual_mode != record.get("enrichment_mode"):
                    raise ValueError("实际 patent 增强模式与预留记录不一致")

            digest = _reservation_digest(case, record, operand)
            if not hmac.compare_digest(digest, query_hash):
                raise ValueError("实际查询与预留 query_hash 不一致")
            attempt_id = secrets.token_urlsafe(24)
            record["execution_started_at"] = datetime.now(timezone.utc).isoformat()
            record["execution_command"] = command
            record["execution_attempt_hash"] = hashlib.sha256(
                attempt_id.encode("utf-8")
            ).hexdigest()
            # The token is not a credential or query. Keeping it in the 0600 case
            # file makes an interrupted claim recoverable before completion.
            record["execution_attempt_id"] = attempt_id
            record["execution_returned_at"] = None
            record["upstream_exit_code"] = None
            _write_case(case_path, case)
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return attempt_id


def _mark_execution_returned(
    case_dir: Path,
    query_hash: str,
    attempt_id: str,
    exit_code: int | None,
) -> None:
    root = case_dir.expanduser().resolve()
    case_path = root / "case.json"
    lock_path = root / ".workbench.lock"
    fd = _open_private_lock(lock_path)
    with os.fdopen(fd, "r+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            case = json.loads(case_path.read_text(encoding="utf-8"))
            route_lock = case.get("route_lock") if isinstance(case, dict) else None
            records = route_lock.get("queries") if isinstance(route_lock, dict) else None
            if not isinstance(records, list):
                raise ValueError("case.json 缺少 route_lock.queries")
            record = next(
                (item for item in records if isinstance(item, dict) and item.get("query_hash") == query_hash),
                None,
            )
            if record is None:
                raise ValueError("执行返回时找不到 query_hash")
            supplied = hashlib.sha256(attempt_id.encode("utf-8")).hexdigest()
            if not hmac.compare_digest(supplied, str(record.get("execution_attempt_hash") or "")):
                raise ValueError("执行返回的 attempt-id 不匹配")
            stored_attempt = str(record.get("execution_attempt_id") or "")
            if stored_attempt and not hmac.compare_digest(attempt_id, stored_attempt):
                raise ValueError("执行返回的 attempt-id 与案件记录不匹配")
            record["execution_returned_at"] = datetime.now(timezone.utc).isoformat()
            record["upstream_exit_code"] = exit_code
            _write_case(case_path, case)
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _read_private_operand(query_file: Path | None, query_stdin: bool) -> str | None:
    if query_file is not None:
        query_path = query_file.expanduser()
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(query_path, flags)
        except OSError as exc:
            raise ValueError(f"无法安全打开查询文件 {query_path}: {exc}") from exc
        try:
            info = os.fstat(fd)
            mode = stat.S_IMODE(info.st_mode)
            if not stat.S_ISREG(info.st_mode):
                raise ValueError(f"查询文件不是普通文件: {query_path}")
            if info.st_uid != os.getuid():
                raise ValueError(f"查询文件不属于当前用户: {query_path}")
            if mode & 0o077:
                raise ValueError(f"查询文件权限过宽（{mode:04o}）；请先 chmod 600 {query_path}")
            if info.st_size > 1024 * 1024:
                raise ValueError("查询文件超过 1 MiB 上限")
            with os.fdopen(fd, "r", encoding="utf-8") as handle:
                fd = -1
                value = handle.read(1024 * 1024 + 1).strip()
        finally:
            if fd >= 0:
                os.close(fd)
    elif query_stdin:
        if sys.stdin.isatty():
            raise ValueError("--query-stdin 需要通过标准输入提供内容")
        value = sys.stdin.read(1024 * 1024 + 1).strip()
    else:
        return None
    if len(value.encode("utf-8")) > 1024 * 1024:
        raise ValueError("查询内容超过 1 MiB 上限")
    if not value:
        raise ValueError("查询内容为空")
    return value


def run(
    client: Path,
    forwarded: list[str],
    operand: str | None = None,
    case_dir: Path | None = None,
    query_hash: str | None = None,
) -> int:
    _reject_secret_args(forwarded)
    command, command_index = _validate_forwarded(forwarded)
    help_only = not forwarded or any(arg in {"-h", "--help"} for arg in forwarded)
    paid_call = command in PAID_COMMANDS and not help_only
    if paid_call:
        if operand is None:
            raise ValueError("付费子命令必须使用 --query-file 或 --query-stdin")
        if case_dir is None or not query_hash:
            raise ValueError("付费子命令必须同时提供 --case-dir 和 --query-hash")
        assert command is not None and command_index is not None
    key = "help-only" if help_only else get_key()
    module = _load_client(client)
    _apply_no_store(module)
    module.API_KEY = key

    safe_args = _inject_private_operand(forwarded, operand)
    if "--no-cache" not in safe_args:
        safe_args.append("--no-cache")
    if "--no-call-log" not in safe_args:
        safe_args.append("--no-call-log")

    old_argv = sys.argv[:]
    attempt_id: str | None = None
    execution_lock_fd: int | None = None
    try:
        if paid_call:
            assert case_dir is not None and query_hash is not None and operand is not None and command is not None
            execution_lock_fd = _acquire_execution_lock(case_dir, query_hash)
            attempt_id = _claim_paid_reservation(case_dir, query_hash, command, forwarded, operand)
            print(json.dumps({
                "workbench": {
                    "query_hash": query_hash,
                    "attempt_id": attempt_id,
                    "status": "executing",
                }
            }, ensure_ascii=False), file=sys.stderr)
        sys.argv = [str(client), *safe_args]
        try:
            result = module.main()
            exit_code = int(result or 0)
        except BaseException:
            if paid_call and attempt_id is not None and case_dir is not None and query_hash is not None:
                _mark_execution_returned(case_dir, query_hash, attempt_id, None)
            raise
        if paid_call and attempt_id is not None and case_dir is not None and query_hash is not None:
            _mark_execution_returned(case_dir, query_hash, attempt_id, exit_code)
        return exit_code
    finally:
        sys.argv = old_argv
        module.API_KEY = ""
        key = ""
        if execution_lock_fd is not None:
            try:
                fcntl.flock(execution_lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(execution_lock_fd)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="以 Keychain + no-store 模式运行 PatSeek；其后的参数原样传给上游客户端",
        allow_abbrev=False,
    )
    parser.add_argument("--case-dir", type=Path, help="付费调用所属案件目录；必须与 query_hash 同时使用")
    parser.add_argument("--query-hash", help="reserve-query 返回的 HMAC 摘要")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--query-file", type=Path, help="从权限为 0600 的 UTF-8 文件读取查询/公开号，避免内容进入进程参数")
    source.add_argument("--query-stdin", action="store_true", help="从标准输入读取查询/公开号，避免内容进入进程参数")
    parser.add_argument("--wrapper-help", action="store_true", help=argparse.SUPPRESS)
    known, forwarded = parser.parse_known_args()
    if known.wrapper_help:
        print("用法: patseek_secure.py [--case-dir DIR --query-hash HASH] <命令> ...")
        print("Key 默认从 macOS Keychain 获取；隐式缓存、调用日志和历史读取均被禁用。")
        print("bool/patent/semantic 强制使用受保护输入，并与 running 的 route reservation 逐项核验。")
        return 0
    try:
        operand = _read_private_operand(known.query_file, known.query_stdin)
        return run(trusted_default_client(), forwarded, operand, known.case_dir, known.query_hash)
    except (KeychainError, FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
