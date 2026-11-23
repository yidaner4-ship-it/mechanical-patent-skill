"""Offline fixtures for explicit vendor trust and cache replacement safety."""
import contextlib
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / "scripts/patseek_client.py"


def load_adapter(path=SOURCE):
    spec = importlib.util.spec_from_file_location("patseek_adapter_fixture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(hasattr(os, "getuid"), "POSIX ownership checks required")
class VendorPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.vendor = self.root / "user-data/vendor/patseek"
        self.vendor.mkdir(parents=True, mode=0o700)
        self.client = self.vendor / "client.py"
        self.client.write_text("# user-owned offline fixture\n", encoding="utf-8")
        self.client.chmod(0o600)
        self.env = patch.dict(os.environ, {
            "PATSEEK_VENDOR_ROOT": str(self.vendor),
            "PATSEEK_CLIENT_PATH": str(self.client),
        }, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.adapter = load_adapter()

    def test_explicit_external_vendor_is_accepted(self):
        self.assertEqual(self.adapter._trusted_vendor(), self.client.resolve())

    def test_external_path_without_explicit_root_is_rejected(self):
        os.environ.pop("PATSEEK_VENDOR_ROOT")
        with self.assertRaises(self.adapter.AdapterError):
            self.adapter._trusted_vendor()

    def test_legacy_local_vendor_still_requires_its_own_trusted_path(self):
        skill = self.root / "manual-skill"
        (skill / "scripts").mkdir(parents=True)
        (skill / "vendor").mkdir()
        shutil.copy2(SOURCE, skill / "scripts/patseek_client.py")
        client = skill / "vendor/client.py"
        client.write_text("# fixture", encoding="utf-8")
        os.environ.pop("PATSEEK_VENDOR_ROOT")
        os.environ["PATSEEK_CLIENT_PATH"] = str(client)
        self.assertEqual(load_adapter(skill / "scripts/patseek_client.py")._trusted_vendor(), client.resolve())

    def test_relative_root_parent_traversal_and_outside_file_are_rejected(self):
        cases = [
            {"PATSEEK_VENDOR_ROOT": "relative"},
            {"PATSEEK_CLIENT_PATH": "relative.py"},
            {"PATSEEK_CLIENT_PATH": str(self.vendor / "../patseek/client.py")},
            {"PATSEEK_CLIENT_PATH": str(self.root / "outside.py")},
            {"PATSEEK_VENDOR_ROOT": str(self.client)},
        ]
        for change in cases:
            with self.subTest(change=change), patch.dict(os.environ, change):
                with self.assertRaises(self.adapter.AdapterError):
                    self.adapter._trusted_vendor()

    def test_file_directory_and_root_symlinks_are_rejected(self):
        alias = self.vendor / "alias.py"
        alias.symlink_to(self.client)
        nested = self.vendor / "real"
        nested.mkdir()
        nested_client = nested / "client.py"
        nested_client.write_text("# fixture", encoding="utf-8")
        directory_alias = self.vendor / "alias"
        directory_alias.symlink_to(nested, target_is_directory=True)
        root_alias = self.root / "vendor-alias"
        root_alias.symlink_to(self.vendor, target_is_directory=True)
        cases = [
            {"PATSEEK_CLIENT_PATH": str(alias)},
            {"PATSEEK_CLIENT_PATH": str(directory_alias / "client.py")},
            {"PATSEEK_VENDOR_ROOT": str(root_alias), "PATSEEK_CLIENT_PATH": str(root_alias / "client.py")},
        ]
        for change in cases:
            with self.subTest(change=change), patch.dict(os.environ, change):
                with self.assertRaises(self.adapter.AdapterError):
                    self.adapter._trusted_vendor()

    def test_group_or_world_writable_root_and_file_are_rejected(self):
        for path in (self.vendor, self.client):
            original = path.stat().st_mode & 0o777
            for mode in (original | 0o020, original | 0o002):
                try:
                    path.chmod(mode)
                    with self.subTest(path=path.name, mode=mode):
                        with self.assertRaises(self.adapter.AdapterError):
                            self.adapter._trusted_vendor()
                finally:
                    path.chmod(original)

    def test_wrong_owner_is_rejected(self):
        with patch.object(self.adapter.os, "getuid", return_value=os.getuid() + 1):
            with self.assertRaises(self.adapter.AdapterError):
                self.adapter._trusted_vendor()

    def test_missing_wrapper_does_not_import_vendor(self):
        self.client.write_text("raise AssertionError('must not import without wrapper')", encoding="utf-8")
        with contextlib.redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(self.adapter.main(), 2)
        self.assertIn("安全上下文", errors.getvalue())

    def test_update_preserves_vendor_and_wrapper_requirements(self):
        self.client.write_text('''import sys
API_KEY = ""
def load_cache(*a, **k): raise AssertionError("unsafe hook")
def save_cache(*a, **k): raise AssertionError("unsafe hook")
def recent_calls(*a, **k): raise AssertionError("unsafe hook")
def log_call(*a, **k): raise AssertionError("unsafe hook")
def throttle(*a, **k): raise AssertionError("unsafe hook")
def main():
    assert API_KEY and CALL_LOG_DISABLED and API_KEY not in sys.argv
    assert load_cache() is None and save_cache() is None
    assert recent_calls() == [] and log_call() is None and throttle() is None
    print(API_KEY[:5], end="")
    print(API_KEY[5:])
    return 0
''', encoding="utf-8")
        expected = hashlib.sha256(self.client.read_bytes()).digest()
        cache = self.root / "replaceable-plugin-cache"
        original_argv = sys.argv[:]
        for version in ("1.0.0", "1.0.1"):
            if cache.exists():
                shutil.rmtree(cache)
            (cache / "scripts").mkdir(parents=True)
            shutil.copy2(SOURCE, cache / "scripts/patseek_client.py")
            adapter = load_adapter(cache / "scripts/patseek_client.py")
            adapter.API_KEY = "ephemeral-offline-fixture-key"
            adapter.CALL_LOG_DISABLED = True
            for name in adapter._HOOK_NAMES:
                setattr(adapter, name, (lambda *a, **k: []) if name == "recent_calls" else (lambda *a, **k: None))
            with self.subTest(version=version), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(adapter.main(), 0)
            self.assertIn("[REDACTED]", output.getvalue())
            self.assertNotIn("ephemeral-offline-fixture-key", output.getvalue())
            self.assertEqual(adapter.API_KEY, "")
            self.assertEqual(sys.argv, original_argv)
            self.assertEqual(hashlib.sha256(self.client.read_bytes()).digest(), expected)
            self.assertNotIn(adapter._VENDOR_MODULE_NAME, sys.modules)


if __name__ == "__main__":
    unittest.main()
