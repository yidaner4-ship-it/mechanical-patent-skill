"""Behavioral regression tests using isolated sources, never the publishing tree.

Copyright 2026 Mechanical Patent Toolkit contributors
SPDX-License-Identifier: MIT
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
from build_release import FIXED_ZIP_TIME, _archive_name, build_release  # noqa: E402
from validate_plugin import (CLAIM_POLICY_REL, COMPAT_PLUGINS, QA_SCANNER_REL,
                             NESTED_SKILLS, PLUGIN_REL, ROOT_SKILLS, ValidationError,
                             MARKDOWN_LINK, _resolve_reference,
                             sha256, validate_archives, validate_repository, version_tuple)  # noqa: E402


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class PluginReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="plugin-release-test-")
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "source"
        self.plugin = self.repo / PLUGIN_REL
        self.skills = self.plugin / "skills"
        for name in ROOT_SKILLS:
            self.skill(self.skills / name)
        for name in NESTED_SKILLS:
            self.skill(self.skills / "patent-disclosure-skill/skills" / name)
        write_json(self.plugin / "plugin.json", {"name": "mechanical-patent-workflow", "version": "1.0.0"})
        write_json(self.plugin / ".codex-plugin/plugin.json",
                   {"name": "mechanical-patent-workflow", "version": "1.0.0", "skills": "./skills/"})
        write_json(self.repo / ".agents/plugins/marketplace.json", {"plugins": [{
            "name": "mechanical-patent-workflow", "source": {"source": "local", "path": "./plugins/mechanical-patent-workflow"}}]})
        for root in (self.repo, self.plugin):
            for name in ("README.md", "INSTALL.md", "LICENSE", "THIRD_PARTY_NOTICES.md"):
                (root / name).write_text("Public test fixture. External applications and accounts are configured separately.\n", encoding="utf-8")
        shutil.copy2(REPO / "install.py", self.repo / "install.py")
        refs = self.skills / "mechanical-patent-drawings/references"
        refs.mkdir()
        (refs / "sample.pdf").write_bytes(b"%PDF-1.4\npublic generic style fixture\n%%EOF\n")
        write_json(refs / "approved-leader-style.json", {"approved_pdf": "sample.pdf", "approved_pdf_sha256": sha256(refs / "sample.pdf")})
        self.command = self.skills / "shensheng-patent-workbench/scripts/workbench"
        self.command.parent.mkdir()
        self.command.write_text("#!/usr/bin/env python3\nprint('fixture')\n", encoding="utf-8")
        self.command.chmod(0o755)

    def skill(self, folder: Path) -> None:
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text(f"---\nname: {folder.name}\ndescription: A test fixture skill.\n---\n\nUse the input supplied by the user.\n", encoding="utf-8")

    def compatibility_fixture(self) -> tuple[Path, Path]:
        policy = self.plugin / CLAIM_POLICY_REL
        policy.parent.mkdir(parents=True, exist_ok=True)
        policy.write_text("# Shared claim scope policy\n\nA self-contained public test policy.\n", encoding="utf-8")
        scanner = self.plugin / QA_SCANNER_REL
        scanner.parent.mkdir(parents=True, exist_ok=True)
        scanner.write_text("print('standard-library fixture scanner')\n", encoding="utf-8")
        canonical_qa = self.skills / "shensheng-patent-qa/SKILL.md"
        canonical_qa.write_text(canonical_qa.read_text().replace("---\n\n", 'metadata:\n  version: "1.2.4"\n---\n\n'))
        market = self.repo / ".agents/plugins/marketplace.json"
        registrations = json.loads(market.read_text())
        for name, skills in COMPAT_PLUGINS.items():
            root = self.repo / "plugins" / name
            version = "0.2.1" if name == "mechanical-patent-drafting" else "1.2.4"
            write_json(root / "plugin.json", {"name": name, "version": version})
            registrations["plugins"].append({"name": name, "source": {"source": "local", "path": f"./plugins/{name}"}})
            for skill in skills:
                self.skill(root / "skills" / skill)
                entry = root / "skills" / skill / "SKILL.md"
                entry_version = version if skill == "mechanical-patent-drafting" else "1.2.4"
                target = ("references/claim-scope-and-names.md" if skill == "shensheng-patent-qa"
                          else "../shensheng-patent-qa/references/claim-scope-and-names.md")
                entry.write_text(entry.read_text().replace("---\n\n", f'metadata:\n  version: "{entry_version}"\n---\n\n')
                                 + f"\n[Shared policy]({target})\n")
            mirror = root / "skills/shensheng-patent-qa/references/claim-scope-and-names.md"
            mirror.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(policy, mirror)
            copy = root / QA_SCANNER_REL
            copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(scanner, copy)
        write_json(market, registrations)
        return policy, scanner

    def test_real_archives_layout_permissions_and_offline_dry_run(self) -> None:
        report = build_release(self.repo, "1.0.0")
        self.assertEqual(report["validation"]["skill_entrypoints"], 20)
        downloads = self.repo / "downloads"
        with zipfile.ZipFile(downloads / "mechanical-patent-workflow-latest.zip") as archive:
            self.assertIn("plugin.json", archive.namelist())
            self.assertIn(".codex-plugin/plugin.json", archive.namelist())
            self.assertIn("skills/mechanical-patent-drawings/SKILL.md", archive.namelist())
            self.assertNotIn("install.py", archive.namelist())
            self.assertTrue(all(info.date_time == FIXED_ZIP_TIME for info in archive.infolist()))
            executable = archive.getinfo("skills/shensheng-patent-workbench/scripts/workbench")
            self.assertEqual(stat.S_IMODE(executable.external_attr >> 16), 0o755)
            ordinary = archive.getinfo("plugin.json")
            self.assertEqual(stat.S_IMODE(ordinary.external_attr >> 16), 0o644)
        extracted = Path(self.temp.name) / "offline"
        with zipfile.ZipFile(downloads / "mechanical-patent-toolkit-latest.zip") as archive:
            archive.extractall(extracted)
        destination = Path(self.temp.name) / "never-created"
        result = subprocess.run([sys.executable, str(extracted / "install.py"), "--dry-run", "--dest", str(destination)],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(destination.exists())
        self.assertEqual(len(json.JSONDecoder().raw_decode(result.stdout)[0]["actions"]), 11)
        for line in (downloads / "SHA256SUMS").read_text().splitlines():
            digest, name = line.split("  ", 1)
            self.assertEqual(digest, sha256(downloads / name))
        self.assertTrue(validate_archives(self.repo)["current_payloads_match_source"])

    def test_rebuild_is_deterministic_and_follows_canonical_edits(self) -> None:
        build_release(self.repo, "1.0.0")
        archive = self.repo / "downloads/mechanical-patent-workflow-latest.zip"
        original = archive.read_bytes()
        self.command.touch()
        build_release(self.repo, "1.0.0")
        self.assertEqual(archive.read_bytes(), original)
        self.command.write_text("#!/usr/bin/env python3\nprint('updated canonical command')\n", encoding="utf-8")
        build_release(self.repo, "1.0.0")
        self.assertNotEqual(archive.read_bytes(), original)
        for name in ("mechanical-patent-workflow-latest.zip", "mechanical-patent-toolkit-latest.zip"):
            with zipfile.ZipFile(self.repo / "downloads" / name) as packed:
                self.assertEqual(packed.read("skills/shensheng-patent-workbench/scripts/workbench"), self.command.read_bytes())

    def test_bump_preserves_old_archives_and_rejects_downgrade(self) -> None:
        downloads = self.repo / "downloads"
        downloads.mkdir()
        dated = downloads / "mechanical-patent-toolkit-20261120.zip"
        dated.write_bytes(b"preserved historical archive")
        build_release(self.repo, "1.0.0")
        old = (downloads / "mechanical-patent-workflow-1.0.0.zip").read_bytes()
        build_release(self.repo, "1.1.0")
        self.assertEqual((downloads / "mechanical-patent-workflow-1.0.0.zip").read_bytes(), old)
        self.assertEqual(dated.read_bytes(), b"preserved historical archive")
        for path in (self.plugin / "plugin.json", self.plugin / ".codex-plugin/plugin.json"):
            self.assertEqual(json.loads(path.read_text())["version"], "1.1.0")
        with self.assertRaisesRegex(ValidationError, "downgrade"):
            build_release(self.repo, "1.0.9")
        self.assertEqual(json.loads((self.plugin / "plugin.json").read_text())["version"], "1.1.0")

    def test_runtime_and_cache_excluded_but_licensed_vendor_retained(self) -> None:
        for relative in (".venv/python.bin", "node_modules/dependency/index.js", "client/client.py", "__pycache__/cached.pyc"):
            path = self.skills / "documents" / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"runtime bytes do not distribute")
        vendor = self.skills / "patent-disclosure-skill/skills/patent-map/web/vendor"
        vendor.mkdir(parents=True)
        (vendor / "three.module.min.js").write_text("/* redistributable fixture */", encoding="utf-8")
        (vendor / "THREE_LICENSE").write_text("MIT fixture", encoding="utf-8")
        build_release(self.repo, "1.0.0", versioned=False)
        with zipfile.ZipFile(self.repo / "downloads/mechanical-patent-workflow-latest.zip") as archive:
            self.assertTrue(any(name.endswith("/vendor/THREE_LICENSE") for name in archive.namelist()))
            self.assertFalse(any(".venv/" in name or "node_modules/" in name or "__pycache__/" in name or "/client/" in name for name in archive.namelist()))
        self.assertFalse((self.repo / "downloads/mechanical-patent-workflow-1.0.0.zip").exists())

    def test_rejects_symlinks_credentials_and_patseek_client(self) -> None:
        bad = self.skills / "documents/linked.txt"
        bad.symlink_to(self.command)
        with self.assertRaisesRegex(ValidationError, "symbolic"):
            build_release(self.repo, "1.0.0")
        bad.unlink()
        bad = self.skills / "documents/.env"
        bad.write_text("SECRET=not-a-real-credential", encoding="utf-8")
        with self.assertRaisesRegex(ValidationError, "credential"):
            build_release(self.repo, "1.0.0")
        bad.unlink()
        bad = self.skills / "patseek-patent-search/vendor/third_party_client.py"
        bad.parent.mkdir()
        bad.write_text("pass\n", encoding="utf-8")
        with self.assertRaisesRegex(ValidationError, "PatSeek client"):
            build_release(self.repo, "1.0.0")

    def test_crossrefs_templates_and_style_digest(self) -> None:
        entry = self.skills / "documents/SKILL.md"
        entry.write_text(entry.read_text() + "\n[QA](../shensheng-patent-qa/SKILL.md)\n`assets/{project}/sample.json`\n", encoding="utf-8")
        self.assertGreater(validate_repository(self.repo)["checked_local_references"], 0)
        entry.write_text(entry.read_text() + "\n[Missing](references/missing.md)\n", encoding="utf-8")
        with self.assertRaisesRegex(ValidationError, "missing local reference"):
            validate_repository(self.repo)
        entry.write_text(entry.read_text().replace("[Missing](references/missing.md)", ""), encoding="utf-8")
        sample = self.skills / "mechanical-patent-drawings/references/sample.pdf"
        sample.write_bytes(b"changed after approval")
        with self.assertRaisesRegex(ValidationError, "SHA256"):
            validate_repository(self.repo)

    def test_duplicate_source_marketplace_and_manifest_mismatch(self) -> None:
        (self.repo / "skills").mkdir()
        with self.assertRaisesRegex(ValidationError, "second source"):
            validate_repository(self.repo)
        (self.repo / "skills").rmdir()
        market = self.repo / ".agents/plugins/marketplace.json"
        data = json.loads(market.read_text())
        data["plugins"].append(data["plugins"][0])
        write_json(market, data)
        with self.assertRaisesRegex(ValidationError, "exactly one"):
            validate_repository(self.repo)
        data["plugins"].pop()
        write_json(market, data)
        write_json(self.plugin / ".codex-plugin/plugin.json", {"name": "mechanical-patent-workflow", "version": "1.0.1", "skills": "./skills/"})
        with self.assertRaisesRegex(ValidationError, "versions differ"):
            validate_repository(self.repo)

    def test_archive_name_and_version_validation(self) -> None:
        for name in ("../escape", "/absolute", "skills/../../escape", "skills\\escape", "C:/escape", "skills/./file"):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                _archive_name(name)
        self.assertEqual(_archive_name("skills/documents/SKILL.md"), "skills/documents/SKILL.md")
        for version in ("1.0", "v1.0.0", "01.0.0", "1.0.0-beta", "1.-1.0"):
            with self.subTest(version=version), self.assertRaises(ValidationError):
                version_tuple(version)

    def test_unsafe_download_destination_does_not_write_release(self) -> None:
        target = Path(self.temp.name) / "elsewhere"
        target.mkdir()
        (self.repo / "downloads").symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(ValidationError, "downloads"):
            build_release(self.repo, "1.1.0")
        self.assertEqual(json.loads((self.plugin / "plugin.json").read_text())["version"], "1.0.0")
        self.assertEqual(list(target.iterdir()), [])

    def test_symlinked_checksum_target_does_not_bump_version(self) -> None:
        target = Path(self.temp.name) / "do-not-change"
        target.write_bytes(b"keep")
        downloads = self.repo / "downloads"
        downloads.mkdir()
        (downloads / "SHA256SUMS").symlink_to(target)
        with self.assertRaisesRegex(ValidationError, "ordinary files"):
            build_release(self.repo, "1.1.0")
        self.assertEqual(target.read_bytes(), b"keep")
        self.assertEqual(json.loads((self.plugin / "plugin.json").read_text())["version"], "1.0.0")

    def test_archive_verification_detects_stale_source_and_tampering(self) -> None:
        build_release(self.repo, "1.0.0")
        self.command.write_text("# canonical source changed after release\n", encoding="utf-8")
        with self.assertRaisesRegex(ValidationError, "current source"):
            validate_archives(self.repo)
        build_release(self.repo, "1.0.0")
        archive = self.repo / "downloads/mechanical-patent-workflow-latest.zip"
        archive.write_bytes(archive.read_bytes() + b"tampered")
        with self.assertRaisesRegex(ValidationError, "checksum"):
            validate_archives(self.repo)

    def test_compatibility_archives_are_independent_and_follow_the_same_policy(self) -> None:
        policy, scanner = self.compatibility_fixture()
        record = build_release(self.repo, "1.0.0")
        self.assertEqual(len(record["current_compatibility_archives"]), 2)
        self.assertEqual(len(record["archives"]), 5)
        for name, packed_name in record["current_compatibility_archives"].items():
            with zipfile.ZipFile(self.repo / "downloads" / packed_name) as archive:
                self.assertEqual(archive.read("skills/shensheng-patent-qa/references/claim-scope-and-names.md"), policy.read_bytes())
                self.assertEqual(archive.read(QA_SCANNER_REL.as_posix()), scanner.read_bytes())
                self.assertIn("LICENSE", archive.namelist())
                self.assertIn("THIRD_PARTY_NOTICES.md", archive.namelist())
                extracted = Path(self.temp.name) / name
                archive.extractall(extracted)
            for entry in (extracted / "skills").glob("*/SKILL.md"):
                for target in MARKDOWN_LINK.findall(entry.read_text()):
                    self.assertIsNotNone(_resolve_reference(entry, target, extracted))
        self.assertTrue(validate_archives(self.repo)["current_payloads_match_source"])

    def test_compatibility_policy_drift_and_broken_local_route_block_build(self) -> None:
        policy, _ = self.compatibility_fixture()
        root = self.repo / "plugins/shensheng-patent-qa"
        mirror = root / "skills/shensheng-patent-qa/references/claim-scope-and-names.md"
        mirror.write_text("edited only in the compatibility copy\n", encoding="utf-8")
        with self.assertRaisesRegex(ValidationError, "policy mirror differs"):
            build_release(self.repo, "1.0.0")
        self.assertFalse((self.repo / "downloads").exists())
        shutil.copyfile(policy, mirror)
        entry = root / "skills/shensheng-patent-qa/SKILL.md"
        entry.write_text(entry.read_text() + "\n[Missing](references/not-distributed.md)\n", encoding="utf-8")
        with self.assertRaisesRegex(ValidationError, "missing local reference"):
            validate_repository(self.repo)

    def test_compatibility_scanner_and_version_drift_are_rejected(self) -> None:
        _, scanner = self.compatibility_fixture()
        root = self.repo / "plugins/shensheng-patent-qa"
        copied = root / QA_SCANNER_REL
        copied.write_text("print('stale scanner')\n", encoding="utf-8")
        with self.assertRaisesRegex(ValidationError, "scanner differs"):
            validate_repository(self.repo)
        shutil.copyfile(scanner, copied)
        write_json(root / "plugin.json", {"name": "shensheng-patent-qa", "version": "1.2.5"})
        with self.assertRaisesRegex(ValidationError, "plugin and skill versions differ"):
            validate_repository(self.repo)

    def test_compatibility_stale_payload_and_changed_installation_identity_are_rejected(self) -> None:
        self.compatibility_fixture()
        build_release(self.repo, "1.0.0")
        entry = self.repo / "plugins/shensheng-patent-qa/skills/shensheng-patent-qa/SKILL.md"
        entry.write_text(entry.read_text() + "\nA reviewed compatibility-only explanation.\n", encoding="utf-8")
        with self.assertRaisesRegex(ValidationError, "compatibility ZIP does not follow current source"):
            validate_archives(self.repo)
        root = self.repo / "plugins/shensheng-patent-qa"
        write_json(root / "plugin.json", {"name": "new-identity", "version": "1.2.4"})
        with self.assertRaisesRegex(ValidationError, "installation identity changed"):
            validate_repository(self.repo)

    def test_compatibility_bump_preserves_prior_archives_and_rejects_downgrade(self) -> None:
        self.compatibility_fixture()
        build_release(self.repo, "1.0.0")
        old = self.repo / "downloads/mechanical-patent-drafting-0.2.1.zip"
        before = old.read_bytes()
        root = self.repo / "plugins/mechanical-patent-drafting"
        entry = root / "skills/mechanical-patent-drafting/SKILL.md"
        original = entry.read_text()
        entry.write_text(original.replace('version: "0.2.1"', 'version: "0.2.2"'))
        write_json(root / "plugin.json", {"name": "mechanical-patent-drafting", "version": "0.2.2"})
        build_release(self.repo, "1.0.1")
        self.assertEqual(old.read_bytes(), before)
        self.assertTrue((self.repo / "downloads/mechanical-patent-drafting-0.2.2.zip").exists())
        entry.write_text(original)
        write_json(root / "plugin.json", {"name": "mechanical-patent-drafting", "version": "0.2.1"})
        with self.assertRaisesRegex(ValidationError, "compatibility plugin downgrade"):
            build_release(self.repo, "1.0.1")

    def test_compatibility_policy_cannot_depend_on_another_installation(self) -> None:
        policy, _ = self.compatibility_fixture()
        policy.write_text(policy.read_text() + "\n[Unshipped](../../../../other-plugin/SKILL.md)\n")
        for name in COMPAT_PLUGINS:
            shutil.copyfile(policy, self.repo / f"plugins/{name}/skills/shensheng-patent-qa/references/claim-scope-and-names.md")
        with self.assertRaisesRegex(ValidationError, "missing local reference"):
            validate_repository(self.repo)

    def test_registered_compatibility_identity_requires_its_installable_source(self) -> None:
        self.compatibility_fixture()
        shutil.rmtree(self.repo / "plugins/shensheng-patent-qa")
        with self.assertRaisesRegex(ValidationError, "registered compatibility plugin is missing"):
            validate_repository(self.repo)


if __name__ == "__main__":
    unittest.main()
