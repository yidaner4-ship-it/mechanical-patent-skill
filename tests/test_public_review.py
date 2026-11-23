"""Offline tests of the original public report and vendor adapter interfaces.

MIT License. Copyright (c) 2026 Mechanical Patent Toolkit contributors.
No installed third-party client or external service is read or invoked.
"""

import contextlib
from html.parser import HTMLParser
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT / "plugins" / "mechanical-patent-workflow"
SKILL_BASE = PLUGIN_ROOT if PLUGIN_ROOT.is_dir() else ROOT
RENDERER = SKILL_BASE / "skills/patent-draft-review/scripts/render_review.py"
ADAPTER = SKILL_BASE / "skills/patseek-patent-search/scripts/patseek_client.py"


def load_script(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ParsedReport(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.complete = []
        self.in_complete = False

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag == "pre" and dict(attrs).get("id") == "complete-input":
            self.in_complete = True

    def handle_endtag(self, tag):
        if tag == "pre":
            self.in_complete = False

    def handle_data(self, data):
        if self.in_complete:
            self.complete.append(data)


class ReviewReportTests(unittest.TestCase):
    def setUp(self):
        self.renderer = load_script(RENDERER, "public_review_test")

    def test_all_input_is_text_and_unknown_fields_are_preserved(self):
        payload = '</pre><script>alert("x")</script><img src=x onerror="oops">&'
        data = {
            "title": payload,
            "issues": [{"id": payload, "evidence": payload,
                        "future_extension": {"nested": [payload, None, 3, True]}}],
            "unknown_root": {"key": payload},
        }
        document = self.renderer.render_report(data)
        parsed = ParsedReport()
        parsed.feed(document)
        self.assertNotIn("script", parsed.tags)
        self.assertNotIn("img", parsed.tags)
        self.assertEqual(json.loads("".join(parsed.complete)), data)
        self.assertIn("报告生成不等于", document)

    def test_cli_and_aliases_generate_readable_html(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "review.json"
            output = root / "review.html"
            source.write_text(json.dumps({"issues": [], "extra": "保留"}), encoding="utf-8")
            for input_option, output_option in (("--input", "--output"), ("--json", "--out")):
                result = subprocess.run(
                    [sys.executable, str(RENDERER), input_option, str(source), output_option, str(output)],
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("保留", output.read_text(encoding="utf-8"))

    def test_cli_rejects_invalid_or_overwriting_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "review.json"
            for data in ("not json", "42", '{"x": NaN}'):
                source.write_text(data, encoding="utf-8")
                with contextlib.redirect_stderr(io.StringIO()):
                    status = self.renderer.main(["-i", str(source), "-o", str(source.with_suffix(".html"))])
                self.assertNotEqual(status, 0)
            source.write_text("{}", encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertNotEqual(self.renderer.main(["-i", str(source), "-o", str(source)]), 0)
            self.assertEqual(source.read_text(encoding="utf-8"), "{}")

    def test_stdin_stdout_and_nonarray_issues_preserve_source(self):
        data = {"issues": {"unexpected": "value"}, "status": "未核"}
        target = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps(data))), contextlib.redirect_stdout(target):
            self.assertEqual(self.renderer.main(["-i", "-", "-o", "-"]), 0)
        parsed = ParsedReport()
        parsed.feed(target.getvalue())
        self.assertEqual(json.loads("".join(parsed.complete)), data)


STUB = '''
import sys
API_KEY = "vendor-default"
CALL_LOG_DISABLED = False
def load_cache(*args, **kwargs): raise AssertionError("original cache read")
def save_cache(*args, **kwargs): raise AssertionError("original cache write")
def recent_calls(*args, **kwargs): raise AssertionError("original history read")
def log_call(*args, **kwargs): raise AssertionError("original log write")
def throttle(*args, **kwargs): raise AssertionError("original throttle")
def find_near_dup(*args, **kwargs): raise AssertionError("original duplicate read")
def main():
    assert API_KEY == "temporary-unit-test-key"
    assert sys.modules[__name__].API_KEY == API_KEY
    assert CALL_LOG_DISABLED is True
    assert load_cache("query") is None
    assert save_cache("query", {}) is None
    assert recent_calls() == []
    assert log_call("query") is None
    assert throttle() is None
    assert find_near_dup("query") == (None, 0.0)
    assert sys.argv[1:] == ["semantic", "private-query", "--no-cache", "--no-call-log"]
    sys.stdout.write(API_KEY[:7])
    sys.stdout.flush()
    sys.stdout.write(API_KEY[7:] + "\\n")
    print(API_KEY, file=sys.stderr)
    return 7
'''


class PatseekAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "patseek-patent-search"
        (self.root / "scripts").mkdir(parents=True)
        (self.root / "vendor").mkdir()
        self.path = self.root / "scripts/patseek_client.py"
        shutil.copyfile(ADAPTER, self.path)
        self.client = self.root / "vendor/client.py"
        self.client.write_text(textwrap.dedent(STUB), encoding="utf-8")
        self.adapter = load_script(self.path, "public_patseek_adapter_test")
        self.environment = mock.patch.dict(os.environ, {"PATSEEK_CLIENT_PATH": str(self.client)})
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.temporary.cleanup()

    def authorize_like_wrapper(self):
        self.adapter.API_KEY = "temporary-unit-test-key"
        self.adapter.CALL_LOG_DISABLED = True
        self.adapter.load_cache = lambda *args, **kwargs: None
        self.adapter.save_cache = lambda *args, **kwargs: None
        self.adapter.recent_calls = lambda *args, **kwargs: []
        self.adapter.log_call = lambda *args, **kwargs: None
        self.adapter.throttle = lambda *args, **kwargs: None

    def call_main(self):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            result = self.adapter.main()
        return result, output.getvalue(), errors.getvalue()

    def test_import_is_inert_and_direct_execution_refuses(self):
        self.client.write_text('raise AssertionError("must not import")', encoding="utf-8")
        # setUp imported the adapter without executing the configured vendor.
        result = subprocess.run([sys.executable, str(self.path), "semantic", "private-query"],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("private-query", result.stdout + result.stderr)
        self.assertEqual(self.call_main()[0], 2)

    def test_key_no_store_and_arguments_pass_in_process_with_cleanup(self):
        self.authorize_like_wrapper()
        captured = []
        original_load = self.adapter._load_vendor

        def capture(path):
            module = original_load(path)
            captured.append(module)
            return module

        argv = [str(self.path), "semantic", "private-query", "--no-cache", "--no-call-log"]
        with mock.patch.object(self.adapter, "_load_vendor", capture), mock.patch.object(sys, "argv", argv), \
                mock.patch("subprocess.Popen", side_effect=AssertionError("no subprocess allowed")), \
                mock.patch("os.system", side_effect=AssertionError("no shell allowed")):
            result, output, errors = self.call_main()
            self.assertEqual(sys.argv, argv)
        self.assertEqual(result, 7)
        self.assertNotIn("temporary-unit-test-key", output + errors)
        self.assertIn("[REDACTED]", output)
        self.assertIn("[REDACTED]", errors)
        self.assertEqual(captured[0].API_KEY, "")
        self.assertEqual(self.adapter.API_KEY, "")
        self.assertNotIn("_public_patseek_vendor", sys.modules)

    def test_missing_no_store_injection_is_rejected(self):
        self.adapter.API_KEY = "temporary-unit-test-key"
        self.adapter.CALL_LOG_DISABLED = True
        with mock.patch.object(self.adapter, "_load_vendor", side_effect=AssertionError("must not load")):
            self.assertEqual(self.call_main()[0], 2)
        self.assertEqual(self.adapter.API_KEY, "")

    def test_missing_outside_self_and_writable_paths_are_rejected(self):
        outside = Path(self.temporary.name) / "outside.py"
        outside.write_text(STUB, encoding="utf-8")
        for bad in ("", "relative.py", str(outside), str(self.path), str(self.client.with_name("missing.py"))):
            self.authorize_like_wrapper()
            with mock.patch.dict(os.environ, {"PATSEEK_CLIENT_PATH": bad}):
                self.assertEqual(self.call_main()[0], 2, bad)
        self.client.chmod(0o666)
        self.authorize_like_wrapper()
        self.assertEqual(self.call_main()[0], 2)

    def test_untrusted_owner_directory_and_symlink_are_rejected(self):
        self.authorize_like_wrapper()
        with mock.patch.object(self.adapter.os, "getuid", return_value=os.getuid() + 1):
            self.assertEqual(self.call_main()[0], 2)
        vendor = self.root / "vendor"
        vendor.chmod(0o777)
        self.authorize_like_wrapper()
        self.assertEqual(self.call_main()[0], 2)
        vendor.chmod(0o755)
        outside = Path(self.temporary.name) / "outside.py"
        outside.write_text(STUB, encoding="utf-8")
        link = vendor / "link.py"
        link.symlink_to(outside)
        self.authorize_like_wrapper()
        with mock.patch.dict(os.environ, {"PATSEEK_CLIENT_PATH": str(link)}):
            self.assertEqual(self.call_main()[0], 2)

    def test_incompatible_hooks_and_vendor_exception_do_not_claim_success(self):
        for code in ('def main(): return 0', STUB.replace('return 7', 'raise RuntimeError(API_KEY)')):
            self.client.write_text(code, encoding="utf-8")
            self.authorize_like_wrapper()
            argv = [str(self.path), "semantic", "private-query", "--no-cache", "--no-call-log"]
            with mock.patch.object(sys, "argv", argv):
                result, output, errors = self.call_main()
            self.assertEqual(result, 2)
            self.assertNotIn("temporary-unit-test-key", output + errors)
            self.assertEqual(self.adapter.API_KEY, "")


if __name__ == "__main__":
    unittest.main()
