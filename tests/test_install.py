"""Isolated installer behavior tests; no real home directory is modified."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("toolkit_install", Path(__file__).resolve().parents[1] / "install.py")
installer = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(installer)


class InstallTests(unittest.TestCase):
    def test_checkout_uses_canonical_plugin_and_offline_zip_uses_flat_skills(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            flat = root / "skills"
            flat.mkdir()
            self.assertEqual(installer.default_source(root), flat)
            canonical = root / "plugins" / "mechanical-patent-workflow" / "skills"
            canonical.mkdir(parents=True)
            self.assertEqual(installer.default_source(root), canonical)

    def fixture(self, base: Path) -> Path:
        source = base / "bundle" / "skills"
        for name in ("mechanical-patent-drawings", "patent-disclosure-skill"):
            root = source / name
            root.mkdir(parents=True)
            (root / "SKILL.md").write_text(f"---\nname: {name}\ndescription: test fixture\n---\n", encoding="utf-8")
        nested = source / "patent-disclosure-skill" / "skills" / "patent-application"
        nested.mkdir(parents=True)
        (nested / "SKILL.md").write_text("nested skill", encoding="utf-8")
        return source

    def test_new_install_keeps_nested_package_and_unrelated_skill(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = self.fixture(base)
            dest = base / "target" / "skills"
            (dest / "unrelated").mkdir(parents=True)
            (dest / "unrelated" / "keep.txt").write_text("keep")
            result = installer.install_skills(source, dest)
            self.assertIsNone(result["backup"])
            self.assertTrue((dest / "patent-disclosure-skill" / "skills" / "patent-application" / "SKILL.md").is_file())
            self.assertEqual((dest / "unrelated" / "keep.txt").read_text(), "keep")

    def test_update_backs_up_original_before_replacement(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = self.fixture(base)
            dest = base / "target" / "skills"
            old = dest / "mechanical-patent-drawings"
            old.mkdir(parents=True)
            (old / "old.txt").write_text("original")
            result = installer.install_skills(source, dest, only=[old.name])
            backup = Path(result["backup"])
            self.assertEqual((backup / old.name / "old.txt").read_text(), "original")
            self.assertTrue((old / "SKILL.md").exists())
            self.assertFalse((dest / "patent-disclosure-skill").exists())

    def test_dry_run_creates_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = self.fixture(base)
            dest = base / "not-created" / "skills"
            before = sorted(str(p.relative_to(base)) for p in base.rglob("*"))
            result = installer.install_skills(source, dest, dry_run=True)
            after = sorted(str(p.relative_to(base)) for p in base.rglob("*"))
            self.assertTrue(result["dry_run"])
            self.assertEqual(before, after)

    def test_bad_selection_and_source_destination_overlap(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = self.fixture(base)
            for name in ("../outside", "unknown-skill", "/absolute"):
                with self.subTest(name=name), self.assertRaises(installer.InstallError):
                    installer.install_skills(source, base / "target", only=[name])
            for dest in (source, source / "inside", source.parent):
                with self.subTest(dest=dest), self.assertRaises(installer.InstallError):
                    installer.install_skills(source, dest)

    def test_source_and_existing_target_symlinks_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = self.fixture(base)
            outside = base / "outside"
            outside.mkdir()
            dest = base / "target"
            dest.mkdir()
            try:
                (dest / "mechanical-patent-drawings").symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest("symbolic links unavailable on this platform")
            with self.assertRaises(installer.InstallError):
                installer.install_skills(source, dest)
            (dest / "mechanical-patent-drawings").unlink()
            (source / "mechanical-patent-drawings" / "external").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(installer.InstallError):
                installer.install_skills(source, dest)

    def test_failed_commit_restores_every_replaced_skill(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = self.fixture(base)
            dest = base / "target" / "skills"
            for name in installer.discover_skills(source):
                (dest / name).mkdir(parents=True)
                (dest / name / "old.txt").write_text(name)
            real_replace = installer.os.replace

            def fail_second_install(src, dst):
                if Path(src).parent.name.startswith(".toolkit-stage-") and Path(src).name == "patent-disclosure-skill":
                    raise OSError("simulated commit failure")
                return real_replace(src, dst)

            with patch.object(installer.os, "replace", side_effect=fail_second_install):
                with self.assertRaises(OSError):
                    installer.install_skills(source, dest)
            for name in installer.discover_skills(source):
                self.assertEqual((dest / name / "old.txt").read_text(), name)
                self.assertFalse((dest / name / "SKILL.md").exists())
            self.assertFalse((dest / ".mechanical-patent-toolkit-install.lock").exists())
            self.assertFalse(list(dest.glob(".toolkit-stage-*")))

    def test_existing_backup_symlink_stops_without_replacing_skill(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = self.fixture(base)
            dest = base / "skills"
            old = dest / "mechanical-patent-drawings"
            old.mkdir(parents=True)
            (old / "old.txt").write_text("original")
            outside = base / "outside"
            outside.mkdir()
            try:
                (base / "skills-backups").symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest("symbolic links unavailable on this platform")
            with self.assertRaises(installer.InstallError):
                installer.install_skills(source, dest, only=[old.name])
            self.assertEqual((old / "old.txt").read_text(), "original")
            self.assertEqual(list(outside.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
