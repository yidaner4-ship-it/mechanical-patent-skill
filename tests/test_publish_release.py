"""Exercise batch publication against isolated local bare repositories only.

Copyright 2026 Mechanical Patent Toolkit contributors
SPDX-License-Identifier: MIT
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "tools/publish_release.py"


class BatchPublishTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="batch-publish-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.remote = self.base / "remote.git"
        self.repo = self.base / "source"
        self.repo.mkdir()
        self.git(self.base, "init", "--bare", str(self.remote))
        self.git(self.repo, "init", "-b", "main")
        self.git(self.repo, "config", "user.name", "Public Fixture")
        self.git(self.repo, "config", "user.email", "fixture@example.invalid")
        self.git(self.repo, "config", "commit.gpgsign", "false")
        (self.repo / "README.md").write_text("Initial public fixture.\n")
        tools = self.repo / "tools"
        tools.mkdir()
        # This intentionally small validator proves the frozen candidate is used.
        (tools / "validate_plugin.py").write_text(
            "from pathlib import Path\nimport sys\n"
            "assert '--check-archives' in sys.argv\n"
            "raise SystemExit(1 if 'INVALID' in Path('README.md').read_text() else 0)\n")
        (self.repo / "downloads").mkdir()
        (self.repo / "downloads/tool-1.0.0.zip").write_bytes(b"historical fixture")
        self.git(self.repo, "add", ".")
        self.git(self.repo, "commit", "-m", "Initial fixture")
        self.git(self.repo, "remote", "add", "origin", str(self.remote))
        self.git(self.repo, "push", "origin", "main")
        self.initial = self.git(self.repo, "rev-parse", "HEAD").stdout.strip()
        self.manifest = self.base / "manifest.json"

    def git(self, cwd, *args, check=True):
        result = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True,
                                env=dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_CONFIG_NOSYSTEM="1"))
        if check and result.returncode:
            self.fail(f"git {args[0]} failed: {result.stderr}")
        return result

    def cli(self, *args, ok=True):
        result = subprocess.run([sys.executable, str(SCRIPT), "--repo", str(self.repo), *map(str, args)],
                                capture_output=True, text=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        self.assertEqual(result.returncode, 1, result.stdout)
        return json.loads(result.stderr)

    def prepare(self, *paths, branch="main"):
        return self.cli("prepare", "--manifest", self.manifest, "--expected-remote", self.remote,
                        "--branch", branch, "--", *paths)

    def apply(self, ok=True):
        return self.cli("publish", "--manifest", self.manifest, "--message", "Update public release", "--apply", ok=ok)

    def remote_commit(self, branch="main"):
        result = self.git(self.remote, "rev-parse", "--verify", "refs/heads/" + branch, check=False)
        return result.stdout.strip() if result.returncode == 0 else None

    def change(self, text="Updated public fixture.\n"):
        (self.repo / "README.md").write_text(text)

    def test_prepare_and_default_plan_do_not_change_git_index_refs_or_worktree(self):
        self.change()
        (self.repo / "private-note.txt").write_text("Unrelated local note, not selected.\n")
        status = self.git(self.repo, "-c", "core.untrackedCache=false", "status", "--porcelain").stdout
        index = (self.repo / ".git/index").read_bytes()
        self.prepare("README.md")
        self.assertEqual(self.cli("publish", "--manifest", self.manifest)["status"], "ready")
        self.assertEqual(self.git(self.repo, "rev-parse", "HEAD").stdout.strip(), self.initial)
        self.assertEqual(self.remote_commit(), self.initial)
        self.assertEqual((self.repo / ".git/index").read_bytes(), index)
        self.assertEqual(self.git(self.repo, "status", "--porcelain").stdout, status)
        self.assertFalse((self.repo / ".git/FETCH_HEAD").exists())

    def test_one_commit_push_verifies_remote_and_preserves_unrelated_changes(self):
        self.change()
        command = self.repo / "tools/public-command"
        command.write_text("#!/bin/sh\nprintf 'public fixture\\n'\n")
        command.chmod(0o755)
        note = self.repo / "private-note.txt"
        note.write_text("Keep me local.\n")
        self.prepare("README.md", "tools/public-command")
        result = self.apply()
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["files"], 2)
        self.assertEqual(result["commit"], self.remote_commit())
        self.assertEqual(self.git(self.repo, "rev-list", "--count", self.initial + "..HEAD").stdout.strip(), "1")
        paths = self.git(self.remote, "diff", "--name-only", self.initial, result["commit"]).stdout.splitlines()
        self.assertEqual(set(paths), {"README.md", "tools/public-command"})
        self.assertEqual(self.git(self.remote, "ls-tree", result["commit"], "tools/public-command").stdout.split()[0], "100755")
        self.assertEqual(note.read_text(), "Keep me local.\n")
        self.assertIn("?? private-note.txt", self.git(self.repo, "status", "--porcelain").stdout)
        self.assertEqual(self.cli("verify", "--manifest", self.manifest, "--commit", result["commit"])["tree"], result["tree"])

    def test_new_target_branch_must_be_explicit_and_absent(self):
        self.git(self.repo, "switch", "-c", "codex/new-release")
        self.change()
        self.prepare("README.md", branch="codex/new-release")
        self.assertIsNone(json.loads(self.manifest.read_text())["expected_remote_commit"])
        result = self.apply()
        self.assertEqual(self.remote_commit("codex/new-release"), result["commit"])
        self.assertEqual(self.remote_commit(), self.initial)

    def test_existing_staged_changes_are_not_cleared_or_included(self):
        self.change()
        (self.repo / "tools/unrelated.py").write_text("print('unrelated')\n")
        self.git(self.repo, "add", "tools/unrelated.py")
        index = (self.repo / ".git/index").read_bytes()
        self.cli("prepare", "--manifest", self.manifest, "--expected-remote", self.remote,
                 "--branch", "main", "README.md", ok=False)
        self.assertEqual((self.repo / ".git/index").read_bytes(), index)
        self.assertEqual(self.remote_commit(), self.initial)

    def test_changed_reviewed_bytes_are_stopped_before_staging(self):
        self.change()
        self.prepare("README.md")
        self.change("Changed after review.\n")
        self.assertIn("Reviewed bytes", self.apply(ok=False)["reason"])
        self.assertEqual(self.git(self.repo, "diff", "--cached", "--name-only").stdout, "")
        self.assertEqual(self.remote_commit(), self.initial)

    def test_wrong_push_url_is_rejected_without_modifying_index(self):
        self.change()
        self.prepare("README.md")
        self.git(self.repo, "remote", "set-url", "--push", "origin", str(self.base / "wrong.git"))
        self.assertIn("target differs", self.apply(ok=False)["reason"])
        self.assertEqual(self.git(self.repo, "diff", "--cached", "--name-only").stdout, "")

    def test_commit_hook_cannot_redirect_the_real_push(self):
        self.change()
        self.prepare("README.md")
        wrong = self.base / "wrong.git"
        self.git(self.base, "init", "--bare", str(wrong))
        hook = self.repo / ".git/hooks/pre-commit"
        hook.write_text(f"#!/bin/sh\ngit remote set-url --push origin '{wrong}'\n")
        hook.chmod(0o755)
        self.assertIn("target differs", self.apply(ok=False)["reason"])
        self.assertEqual(self.remote_commit(), self.initial)
        self.assertNotEqual(self.git(self.repo, "rev-parse", "HEAD").stdout.strip(), self.initial)
        self.assertNotEqual(self.git(wrong, "rev-parse", "--verify", "refs/heads/main", check=False).returncode, 0)

    def test_manifest_is_not_written_into_repository_or_git_internal_files(self):
        self.change()
        for path in (self.repo / "release.json", self.repo / ".git/publish.json"):
            with self.subTest(path=path):
                result = self.cli("prepare", "--manifest", path, "--expected-remote", self.remote,
                                  "--branch", "main", "README.md", ok=False)
                self.assertIn("outside", result["reason"])
                self.assertFalse(path.exists())

    def test_remote_advance_stops_before_committing(self):
        self.change()
        self.prepare("README.md")
        other = self.other_clone()
        (other / "README.md").write_text("Concurrent public change.\n")
        self.git(other, "commit", "-am", "Concurrent fixture")
        self.git(other, "push", "origin", "main")
        expected = self.remote_commit()
        self.assertIn("Remote branch changed", self.apply(ok=False)["reason"])
        self.assertEqual(self.git(self.repo, "rev-parse", "HEAD").stdout.strip(), self.initial)
        self.assertEqual(self.remote_commit(), expected)

    def other_clone(self):
        other = self.base / "other"
        self.git(self.base, "clone", "--branch", "main", str(self.remote), str(other))
        self.git(other, "config", "user.name", "Other Fixture")
        self.git(other, "config", "user.email", "other@example.invalid")
        self.git(other, "config", "commit.gpgsign", "false")
        return other

    def test_candidate_validation_failure_cannot_publish(self):
        self.change("INVALID fixture for a source/archive mismatch.\n")
        self.prepare("README.md")
        self.assertIn("validation failed", self.apply(ok=False)["reason"])
        self.assertEqual(self.remote_commit(), self.initial)
        self.assertEqual(self.git(self.repo, "rev-parse", "HEAD").stdout.strip(), self.initial)

    def test_historical_zip_modification_or_deletion_is_rejected(self):
        history = self.repo / "downloads/tool-1.0.0.zip"
        history.write_bytes(b"replaced history")
        result = self.cli("prepare", "--manifest", self.manifest, "--expected-remote", self.remote,
                          "--branch", "main", "downloads/tool-1.0.0.zip", ok=False)
        self.assertIn("preserved", result["reason"])
        history.unlink()
        result = self.cli("prepare", "--manifest", self.manifest, "--expected-remote", self.remote,
                          "--branch", "main", "downloads/tool-1.0.0.zip", ok=False)
        self.assertIn("preserved", result["reason"])

    def test_path_traversal_symlink_and_private_layout_are_rejected(self):
        for path in ("../README.md", str(self.repo / "README.md"), "private-note.txt", "tools/.env", "tools/.DS_Store"):
            with self.subTest(path=path):
                self.cli("prepare", "--manifest", self.manifest, "--expected-remote", self.remote,
                         "--branch", "main", path, ok=False)
        (self.repo / "tools/linked").symlink_to(self.base)
        (self.base / "secret.txt").write_text("private fixture")
        self.cli("prepare", "--manifest", self.manifest, "--expected-remote", self.remote,
                 "--branch", "main", "tools/linked/secret.txt", ok=False)

    def test_literal_filename_does_not_expand_to_other_files(self):
        literal = self.repo / "tools/*literal.txt"
        literal.write_text("Public literal fixture.\n")
        (self.repo / "tools/anotherliteral.txt").write_text("Unselected fixture.\n")
        self.prepare("tools/*literal.txt")
        result = self.apply()
        self.assertEqual(self.git(self.remote, "diff", "--name-only", self.initial, result["commit"]).stdout.strip(), "tools/*literal.txt")

    def test_prepare_paths_file_omits_unchanged_selected_paths(self):
        self.change()
        selection = self.base / "paths.json"
        selection.write_text(json.dumps(["README.md", "tools/validate_plugin.py"]))
        result = self.cli("prepare", "--manifest", self.manifest, "--expected-remote", self.remote,
                          "--branch", "main", "--paths-from", selection)
        self.assertEqual([x["path"] for x in result["files"]], ["README.md"])

    def test_commit_hook_cannot_add_an_unreviewed_file_to_the_remote(self):
        self.change()
        self.prepare("README.md")
        hook = self.repo / ".git/hooks/pre-commit"
        hook.write_text("#!/bin/sh\nprintf 'unreviewed\\n' > tools/extra.txt\ngit add tools/extra.txt\n")
        hook.chmod(0o755)
        self.assertIn("additional paths", self.apply(ok=False)["reason"])
        self.assertEqual(self.remote_commit(), self.initial)
        self.assertNotEqual(self.git(self.repo, "rev-parse", "HEAD").stdout.strip(), self.initial)

    def test_non_fast_forward_race_does_not_force_or_retry(self):
        self.change()
        self.prepare("README.md")
        other = self.other_clone()
        hook = self.repo / ".git/hooks/pre-push"
        # The auth dry-run uses the reviewed base; only the real new commit triggers the race.
        hook.write_text("#!/bin/sh\n"
            + f"if [ \"$(git rev-parse HEAD)\" != '{self.initial}' ]; then\n"
            + f"  git -C '{other}' -c user.name='Other Fixture' -c user.email='other@example.invalid' commit --allow-empty -m race >/dev/null 2>&1\n"
            + f"  git -C '{other}' push origin main >/dev/null 2>&1\nfi\n")
        hook.chmod(0o755)
        result = self.apply(ok=False)
        self.assertIn("Git push failed", result["reason"])
        local = self.git(self.repo, "rev-parse", "HEAD").stdout.strip()
        remote = self.remote_commit()
        self.assertNotEqual(local, self.initial)
        self.assertNotEqual(remote, self.initial)
        self.assertNotEqual(local, remote)
        self.assertEqual(self.git(self.repo, "rev-list", "--count", self.initial + "..HEAD").stdout.strip(), "1")


if __name__ == "__main__":
    unittest.main()
