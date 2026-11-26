"""Observable invariants for reviewed, per-file skill synchronization."""
from __future__ import annotations

import json
import contextlib
import io
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import sync_local_skills as sync


class LocalSkillSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.local = self.root / "installed"
        self.source = self.repo / sync.PLUGIN_REL / "skills"
        self.local.mkdir()
        for name in sync.MANAGED_SKILLS:
            path = self.source / name / "SKILL.md"
            path.parent.mkdir(parents=True)
            path.write_text(f"---\nname: {name}\ndescription: Test\n---\nVersion one.\n")
        (self.source.parent / "plugin.json").write_text(json.dumps({"version": "1.0.0"}))

    def install(self):
        return sync.apply_plan(sync.make_plan(self.repo, self.local))

    def test_plan_is_read_only_and_adds_new_reference_with_mode(self):
        p = self.source / sync.MANAGED_SKILLS[0] / "scripts" / "example.py"
        p.parent.mkdir(); p.write_text("print('hello')\n"); p.chmod(0o755)
        plan = sync.make_plan(self.repo, self.local)
        self.assertEqual(list(self.local.iterdir()), [])
        sync.apply_plan(plan)
        target = self.local / p.relative_to(self.source)
        self.assertEqual(target.read_bytes(), p.read_bytes())
        self.assertTrue(target.stat().st_mode & stat.S_IXUSR)
        self.assertEqual(sync.make_plan(self.repo, self.local)["changes"], [])
        reference = self.source / sync.MANAGED_SKILLS[0] / "references" / "new.md"
        reference.parent.mkdir(); reference.write_text("New guidance\n")
        sync.apply_plan(sync.make_plan(self.repo, self.local))
        self.assertEqual((self.local / reference.relative_to(self.source)).read_text(), "New guidance\n")

    def test_noop_does_not_create_backup_or_rewrite_metadata(self):
        self.install()
        before = (self.local / sync.METADATA).read_bytes()
        backups = list((self.local / ".shensheng-sync-backups").iterdir())
        result = sync.apply_plan(sync.make_plan(self.repo, self.local))
        self.assertEqual(result["changed_files"], 0)
        self.assertIsNone(result["backup"])
        self.assertEqual((self.local / sync.METADATA).read_bytes(), before)
        self.assertEqual(list((self.local / ".shensheng-sync-backups").iterdir()), backups)

    def test_keeps_unmanaged_runtime_original_skills_and_private_files(self):
        self.install()
        paths = [self.local / sync.MANAGED_SKILLS[0] / ".venv" / "binary",
                 self.local / sync.MANAGED_SKILLS[0] / ".runtime" / "state.json",
                 self.local / sync.MANAGED_SKILLS[0] / "tools" / "cad-env" / "runtime",
                 self.local / "patent-draft-review" / "SKILL.md",
                 self.local / "patseek-patent-search" / "client" / "licensed.dat"]
        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True); path.write_text("Keep this")
        p = self.source / sync.MANAGED_SKILLS[0] / "SKILL.md"
        p.write_text(p.read_text() + "Changed\n")
        sync.apply_plan(sync.make_plan(self.repo, self.local))
        for path in paths:
            self.assertEqual(path.read_text(), "Keep this")

    def test_changed_source_after_plan_rejected_without_writes(self):
        self.install()
        path = self.source / sync.MANAGED_SKILLS[0] / "SKILL.md"
        path.write_text("Reviewed source\n")
        plan = sync.make_plan(self.repo, self.local)
        path.write_text("Unreviewed source\n")
        before = (self.local / path.relative_to(self.source)).read_bytes()
        with self.assertRaises(sync.SyncError): sync.apply_plan(plan)
        self.assertEqual((self.local / path.relative_to(self.source)).read_bytes(), before)

    def test_changed_target_after_plan_rejected_without_writes(self):
        self.install()
        plan = sync.make_plan(self.repo, self.local)
        target = self.local / sync.MANAGED_SKILLS[0] / "SKILL.md"
        target.write_text("New local edit\n")
        with self.assertRaises(sync.SyncError): sync.apply_plan(plan)
        self.assertEqual(target.read_text(), "New local edit\n")

    def test_local_edits_require_explicit_review(self):
        self.install()
        target = self.local / sync.MANAGED_SKILLS[0] / "SKILL.md"
        target.write_text("Local experiment\n")
        plan = sync.make_plan(self.repo, self.local)
        self.assertTrue(plan["changes"][0]["local_changed_since_sync"])
        with self.assertRaises(sync.SyncError): sync.apply_plan(plan)
        sync.apply_plan(plan, accept_local_changes=True)
        self.assertEqual(target.read_bytes(), (self.source / target.relative_to(self.local)).read_bytes())

    def test_deleted_managed_source_removed_but_unmanaged_file_preserved(self):
        path = self.source / sync.MANAGED_SKILLS[0] / "references" / "retired.md"
        path.parent.mkdir(); path.write_text("Retired\n")
        self.install(); path.unlink()
        extra = self.local / sync.MANAGED_SKILLS[0] / "references" / "local.md"
        extra.write_text("Local\n")
        plan = sync.make_plan(self.repo, self.local)
        self.assertEqual(plan["changes"][0]["action"], "delete")
        sync.apply_plan(plan)
        self.assertFalse((self.local / path.relative_to(self.source)).exists())
        self.assertEqual(extra.read_text(), "Local\n")

    def test_path_traversal_or_unmanaged_metadata_path_rejected(self):
        for relative in ("../outside", "documents/SKILL.md", sync.MANAGED_SKILLS[0] + "/../outside",
                         sync.MANAGED_SKILLS[0] + "/.runtime/account.json"):
            with self.subTest(relative=relative):
                (self.local / sync.METADATA).write_text(json.dumps({"manifest": {relative: {}}}))
                with self.assertRaises(sync.SyncError): sync.make_plan(self.repo, self.local)

    def test_injected_plan_operation_rejected(self):
        plan = sync.make_plan(self.repo, self.local)
        plan["changes"].append({"path": "../outside", "action": "delete"})
        with self.assertRaises(sync.SyncError): sync.apply_plan(plan)
        self.assertEqual(list(self.local.iterdir()), [])

    def test_source_symlink_rejected(self):
        (self.source / sync.MANAGED_SKILLS[0] / "link").symlink_to(self.root)
        with self.assertRaises((sync.SyncError, sync.ValidationError)):
            sync.make_plan(self.repo, self.local)

    def test_source_ancestor_symlink_rejected(self):
        plugin = self.source.parent
        relocated = self.root / "relocated-plugin"
        plugin.rename(relocated)
        plugin.symlink_to(relocated)
        with self.assertRaises(sync.SyncError): sync.make_plan(self.repo, self.local)

    def test_cli_plan_is_private_and_rejects_symlink_output(self):
        output = self.root / "reviewed.json"
        args = ["plan", "--repo-root", str(self.repo), "--local-root", str(self.local),
                "--output", str(output)]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(sync.main(args), 0)
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
        self.assertEqual(json.loads(output.read_text())["local_root"], str(self.local.resolve()))
        target = self.root / "keep.json"
        target.write_text("Keep original")
        output.unlink()
        output.symlink_to(target)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(sync.main(args), 2)
        self.assertEqual(target.read_text(), "Keep original")

    def test_target_directory_symlink_rejected(self):
        self.install()
        folder = self.local / sync.MANAGED_SKILLS[0] / "references"
        folder.symlink_to(self.root)
        reference = self.source / sync.MANAGED_SKILLS[0] / "references" / "new.md"
        reference.parent.mkdir(); reference.write_text("New\n")
        with self.assertRaises(sync.SyncError): sync.make_plan(self.repo, self.local)
        self.assertFalse((self.root / "new.md").exists())

    def test_unmanaged_scan_reports_only_candidate_paths(self):
        self.install()
        base = self.local / sync.MANAGED_SKILLS[0]
        candidates = [base / "references" / "new-local.md", base / "scripts" / "new.py"]
        ignored = [base / ".venv" / "binary", base / ".runtime" / "state.json",
                   base / "tools" / "cad-env" / "x.py", base / "accounts" / "readme.md",
                   base / "outputs" / "case.md", base / "credentials.json"]
        for path in candidates + ignored:
            path.parent.mkdir(parents=True, exist_ok=True); path.write_text("Local\n")
        plan = sync.make_plan(self.repo, self.local, scan_unmanaged=True)
        self.assertEqual(set(plan["unmanaged_candidates"]), {p.relative_to(self.local).as_posix() for p in candidates})
        sync.apply_plan(plan)
        for path in candidates + ignored:
            self.assertEqual(path.read_text(), "Local\n")

    def test_write_failure_rolls_back_files_and_metadata(self):
        self.install()
        metadata_before = (self.local / sync.METADATA).read_bytes()
        source = self.source / sync.MANAGED_SKILLS[0] / "SKILL.md"
        target = self.local / source.relative_to(self.source)
        original = target.read_bytes()
        source.write_text("Updated\n")
        plan = sync.make_plan(self.repo, self.local)
        original_write = sync.atomic_write
        def fail_metadata_once(path, data, mode):
            if path.name == sync.METADATA and not getattr(fail_metadata_once, "failed", False):
                fail_metadata_once.failed = True
                raise OSError("simulated full disk")
            return original_write(path, data, mode)
        with mock.patch.object(sync, "atomic_write", side_effect=fail_metadata_once):
            with self.assertRaises(OSError): sync.apply_plan(plan)
        self.assertEqual(target.read_bytes(), original)
        self.assertEqual((self.local / sync.METADATA).read_bytes(), metadata_before)
        self.assertFalse((self.local / ".shensheng-skill-sync.lock").exists())


if __name__ == "__main__":
    unittest.main()
