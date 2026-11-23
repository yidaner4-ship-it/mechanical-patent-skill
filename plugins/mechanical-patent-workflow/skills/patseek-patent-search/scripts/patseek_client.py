#!/usr/bin/env python3
"""Original in-process bridge for a separately licensed PatSeek client.

No vendor code or network action occurs when this module is imported.
MIT License. Copyright (c) 2026 Mechanical Patent Toolkit contributors.
"""

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import stat
import sys


API_KEY = ""
CALL_LOG_DISABLED = False


def load_cache(*args, **kwargs):
    return None


def save_cache(*args, **kwargs):
    return None


def recent_calls(*args, **kwargs):
    return []


def log_call(*args, **kwargs):
    return None


def throttle(*args, **kwargs):
    return None


_HOOK_NAMES = ("load_cache", "save_cache", "recent_calls", "log_call", "throttle")
_ORIGINAL_HOOKS = {name: globals()[name] for name in _HOOK_NAMES}
_VENDOR_MODULE_NAME = "_public_patseek_vendor"
_MISSING = object()


class AdapterError(RuntimeError):
    """A fixed, non-sensitive compatibility or configuration error."""


class _RedactedStream(io.TextIOBase):
    """Redact a secret even when a client splits it across write() calls."""

    def __init__(self, stream, secret):
        self._stream = stream
        self._secret = secret
        self._pending = ""

    @property
    def encoding(self):
        return getattr(self._stream, "encoding", "utf-8")

    def writable(self):
        return True

    def isatty(self):
        return self._stream.isatty()

    def write(self, text):
        if not isinstance(text, str):
            raise TypeError("text stream requires str")
        combined = (self._pending + text).replace(self._secret, "[REDACTED]")
        keep = 0
        for count in range(min(len(self._secret) - 1, len(combined)), 0, -1):
            if combined.endswith(self._secret[:count]):
                keep = count
                break
        self._pending = combined[-keep:] if keep else ""
        emitted = combined[:-keep] if keep else combined
        self._stream.write(emitted)
        return len(text)

    def flush(self):
        # Keep a possible secret prefix until the next write or final completion.
        self._stream.flush()

    def finish(self):
        self._stream.write(self._pending)
        self._pending = ""
        self._stream.flush()


def _require_wrapper():
    if not isinstance(API_KEY, str) or not API_KEY or not CALL_LOG_DISABLED:
        raise AdapterError("缺少工作台安全上下文；请通过 shensheng-patent-workbench 调用")
    if any(not callable(globals()[name]) or globals()[name] is _ORIGINAL_HOOKS[name]
           for name in _HOOK_NAMES):
        raise AdapterError("no-store hooks 未由安全包装器注入，拒绝执行")


def _trusted_vendor():
    value = os.environ.get("PATSEEK_CLIENT_PATH", "")
    if not value:
        raise AdapterError("未设置 PATSEEK_CLIENT_PATH；原客户端不随包提供")
    candidate = Path(value).expanduser()
    if not candidate.is_absolute() or ".." in candidate.parts:
        raise AdapterError("PATSEEK_CLIENT_PATH 必须为 vendor 内 .py 文件的绝对路径")
    skill_root = Path(__file__).resolve().parents[1]
    configured_root = os.environ.get("PATSEEK_VENDOR_ROOT", "").strip()
    if configured_root:
        vendor = Path(configured_root).expanduser()
        if not vendor.is_absolute() or ".." in vendor.parts:
            raise AdapterError("PATSEEK_VENDOR_ROOT 必须为持久 vendor 目录的绝对路径")
        trust_anchor = vendor
    else:
        # Compatibility for manual installs. Cached plugin installs should opt in
        # to a persistent root; this legacy directory is replaced on update.
        vendor = skill_root / "vendor"
        trust_anchor = skill_root
    try:
        if vendor.is_symlink() or not vendor.is_dir():
            raise AdapterError("受信 vendor 根不存在、不是目录或为符号链接")
        # Resolve only for containment. Keep the original candidate for lstat
        # below, including symlinks whose targets happen to remain in the root.
        resolved = candidate.resolve(strict=True)
        if resolved == Path(__file__).resolve():
            raise AdapterError("PATSEEK_CLIENT_PATH 不能指向适配器自身")
        resolved.relative_to(vendor.resolve(strict=True))
        if resolved.suffix != ".py":
            raise AdapterError("外部客户端必须为 .py 文件")
        if not hasattr(os, "getuid"):
            raise AdapterError("当前平台不能执行所需的所有者校验")
        current = candidate
        while True:
            info = current.lstat()
            expected_type = stat.S_ISREG if current == candidate else stat.S_ISDIR
            if not expected_type(info.st_mode) or info.st_uid != os.getuid():
                raise AdapterError("外部客户端或目录含符号链接，或类型、所有者不可信")
            if stat.S_IMODE(info.st_mode) & 0o022:
                raise AdapterError("外部客户端或目录可被组或其他用户写入，拒绝加载")
            # An OS alias above the trust root (macOS /var -> /private/var)
            # must not reject a valid tree. Every component within it is still
            # checked with lstat before comparing its directory identity.
            if current.samefile(trust_anchor):
                break
            parent = current.parent
            if parent == current:
                raise AdapterError("外部客户端路径不在受信根内")
            current = parent
        return resolved
    except (OSError, ValueError) as exc:
        raise AdapterError("外部客户端路径无效或不在已配置的受信 vendor 目录内") from exc


def _load_vendor(path):
    spec = importlib.util.spec_from_file_location(_VENDOR_MODULE_NAME, path)
    if spec is None or spec.loader is None:
        raise AdapterError("无法加载外部客户端")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_VENDOR_MODULE_NAME] = module
    try:
        spec.loader.exec_module(module)
        names = (*_HOOK_NAMES, "main")
        if any(not callable(getattr(module, name, None)) for name in names):
            raise AdapterError("外部客户端接口不兼容：需要约定的六个可调用 hooks")
    except BaseException:
        module.API_KEY = ""
        if sys.modules.get(_VENDOR_MODULE_NAME) is module:
            del sys.modules[_VENDOR_MODULE_NAME]
        raise
    return module


def main():
    """Called by the workbench after its authorization and no-store injection."""
    global API_KEY
    module = None
    old_argv = sys.argv[:]
    old_path = sys.path[:]
    previous_module = sys.modules.get(_VENDOR_MODULE_NAME, _MISSING)
    output = None
    errors = None
    key = ""
    try:
        _require_wrapper()
        path = _trusted_vendor()
        key = API_KEY
        output = _RedactedStream(sys.stdout, key)
        errors = _RedactedStream(sys.stderr, key)
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            # The legal local client may have sibling dependencies. The path is
            # restricted and checked above; this does not make vendor code a sandbox.
            sys.path.insert(0, str(path.parent))
            module = _load_vendor(path)
            module.API_KEY = key
            module.CALL_LOG_DISABLED = True
            for name in _HOOK_NAMES:
                setattr(module, name, globals()[name])
            if hasattr(module, "find_near_dup"):
                module.find_near_dup = lambda *args, **kwargs: (None, 0.0)
            sys.argv = [str(path), *old_argv[1:]]
            try:
                result = module.main()
            except SystemExit as exc:
                result = exc.code
            if result is None:
                return 0
            if isinstance(result, int):
                return result
            raise AdapterError("外部客户端未返回兼容的退出状态，不能确认成功")
    except AdapterError as exc:
        print("PatSeek 适配失败：" + str(exc), file=sys.stderr)
        return 2
    except Exception:
        # Do not echo vendor exceptions, which may contain a Key or query.
        print("PatSeek 外部客户端执行失败；未确认检索成功，请核实任务与费用状态后处理", file=sys.stderr)
        return 2
    finally:
        if module is not None:
            module.API_KEY = ""
        API_KEY = ""
        key = ""
        if previous_module is _MISSING:
            sys.modules.pop(_VENDOR_MODULE_NAME, None)
        else:
            sys.modules[_VENDOR_MODULE_NAME] = previous_module
        sys.argv = old_argv
        sys.path[:] = old_path
        if output is not None:
            output.finish()
        if errors is not None:
            errors.finish()


def _direct_cli():
    if sys.argv[1:] in (["--help"], ["-h"]):
        print("本文件是独立 PatSeek 适配器，不含原客户端。请配置 PATSEEK_CLIENT_PATH，")
        print("并通过 shensheng-patent-workbench 安全包装器查询；不得在 argv 中传 Key 或原始查询。")
        return 0
    print("拒绝直接调用：请通过 shensheng-patent-workbench 安全包装器执行", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_direct_cli())
