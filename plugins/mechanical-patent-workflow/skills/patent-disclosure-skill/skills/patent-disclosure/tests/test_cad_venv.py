# -*- coding: utf-8 -*-
"""cad-env probe, pip indexes, SVG HTTP port, requirements ASCII."""
from __future__ import annotations

import socket
import importlib.util
import shutil
import subprocess
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SHARED_PKG = Path(__file__).resolve().parents[1]
SHARED = SHARED_PKG / "tools"
ROOT = SHARED_PKG.parent.parent if SHARED_PKG.parent.name == "skills" else SHARED_PKG.parent
sys.path.insert(0, str(SHARED))

import bootstrap_cad_venv as boot
import cad_venv
import run_step_to_views as runner
import svg_screenshot as shot
from step_to_views import build_figure_plan_seed


class CadVenvTests(unittest.TestCase):
    def test_venv_name_and_range(self) -> None:
        self.assertEqual(cad_venv.VENV_NAME, "cad-env")
        self.assertTrue(str(cad_venv.VENV_DIR).endswith("cad-env") or cad_venv.VENV_DIR.name == "cad-env")
        self.assertTrue(cad_venv.version_supported((3, 10, 0)))
        self.assertTrue(cad_venv.version_supported((3, 11, 9)))
        self.assertTrue(cad_venv.version_supported((3, 12, 1)))
        self.assertFalse(cad_venv.version_supported((3, 9, 18)))
        self.assertFalse(cad_venv.version_supported((3, 13, 0)))

    def test_isolated_env_drops_pythonpath(self) -> None:
        with patch.dict("os.environ", {"PYTHONPATH": "C:\\leak", "PIP_INDEX_URL": "http://x"}, clear=False):
            env = cad_venv.isolated_env()
        self.assertNotIn("PYTHONPATH", env)
        self.assertNotIn("PIP_INDEX_URL", env)
        self.assertEqual(env.get("PYTHONNOUSERSITE"), "1")

    def test_status_missing_venv(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            st = cad_venv.status(Path(td) / "cad-env")
        self.assertFalse(st["ok"])
        self.assertEqual(st["reason"], "missing_venv")
        self.assertFalse(st["skip_install"])

    def test_persistent_default_and_explicit_venv_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as td, patch.dict("os.environ", {}, clear=True):
            root = Path(td)
            with patch.object(Path, "home", return_value=root):
                self.assertEqual(cad_venv.cad_venv_dir(), root / ".local/share/mechanical-patent-workflow/cad-env")
            with patch.dict("os.environ", {"XDG_DATA_HOME": str(root / "xdg")}):
                self.assertEqual(cad_venv.cad_venv_dir(), root / "xdg/mechanical-patent-workflow/cad-env")
            with patch.dict("os.environ", {"PATENT_TOOLKIT_DATA_HOME": str(root / "data")}):
                self.assertEqual(cad_venv.cad_venv_dir(), root / "data/cad-env")
                with patch.dict("os.environ", {"PATENT_SKILL_CAD_VENV": str(root / "existing")}):
                    self.assertEqual(cad_venv.cad_venv_dir(), root / "existing")
                    self.assertEqual(cad_venv.meta_path(), root / "existing/cad_venv_meta.json")

    def test_windows_appdata_and_relative_xdg_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as td, patch.dict("os.environ", {}, clear=True):
            root = Path(td)
            with patch.object(cad_venv.sys, "platform", "win32"), patch.dict("os.environ", {"APPDATA": str(root)}):
                self.assertEqual(cad_venv.data_home(), root / "mechanical-patent-workflow")
            with patch.object(Path, "home", return_value=root), patch.dict("os.environ", {"XDG_DATA_HOME": "relative"}):
                self.assertEqual(cad_venv.data_home(), root / ".local/share/mechanical-patent-workflow")

    def test_explicit_relative_paths_are_rejected(self) -> None:
        for name in ("PATENT_TOOLKIT_DATA_HOME", "PATENT_SKILL_CAD_VENV"):
            with self.subTest(name=name), patch.dict("os.environ", {name: "relative"}, clear=True):
                with self.assertRaisesRegex(ValueError, name):
                    cad_venv.cad_venv_dir()

    def test_ready_external_environment_is_not_installed_again(self) -> None:
        with tempfile.TemporaryDirectory() as td, patch.dict("os.environ", {"PATENT_SKILL_CAD_VENV": td}):
            py = cad_venv.venv_python()
            py.parent.mkdir(parents=True)
            py.write_text("fixture", encoding="utf-8")
            with patch.object(cad_venv, "python_version", return_value=(3, 12, 1)), \
                    patch.object(cad_venv, "_cadquery_ok", return_value=(True, "fixture")), \
                    patch.object(boot, "_pip_install", side_effect=AssertionError("must not install")):
                self.assertTrue(boot.bootstrap()["skip_install"])

    def test_existing_unsupported_or_unprobeable_environment_is_preserved(self) -> None:
        for version in ((3, 13, 1), None):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as td, \
                    patch.dict("os.environ", {"PATENT_SKILL_CAD_VENV": td}):
                root = Path(td)
                py = cad_venv.venv_python()
                py.parent.mkdir()
                py.write_bytes(b"existing interpreter fixture")
                marker = root / "user-file.fixture"
                marker.write_bytes(b"must survive")
                with patch.object(cad_venv, "python_version", return_value=version), \
                        patch.object(boot, "_run") as run:
                    with self.assertRaisesRegex(RuntimeError, "left unchanged"):
                        boot._create_venv("unused-host-python")
                    run.assert_not_called()
                self.assertEqual(marker.read_bytes(), b"must survive")
                self.assertEqual(py.read_bytes(), b"existing interpreter fixture")

    def test_existing_directory_without_python_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as td, patch.dict("os.environ", {"PATENT_SKILL_CAD_VENV": td}):
            marker = Path(td) / "user-file.fixture"
            marker.write_bytes(b"must survive")
            with patch.object(boot, "_run") as run:
                with self.assertRaisesRegex(RuntimeError, "new, nonexistent path"):
                    boot._create_venv("unused-host-python")
                run.assert_not_called()
            self.assertEqual(list(Path(td).iterdir()), [marker])
            self.assertEqual(marker.read_bytes(), b"must survive")

    def test_existing_supported_environment_is_reused_without_recreation(self) -> None:
        with tempfile.TemporaryDirectory() as td, patch.dict("os.environ", {"PATENT_SKILL_CAD_VENV": td}):
            py = cad_venv.venv_python()
            py.parent.mkdir()
            py.write_bytes(b"supported interpreter fixture")
            marker = Path(td) / "user-file.fixture"
            marker.write_bytes(b"must survive")
            with patch.object(cad_venv, "python_version", return_value=(3, 12, 1)), \
                    patch.object(boot, "_run") as run:
                self.assertEqual(boot._create_venv("unused-host-python"), py)
                run.assert_not_called()
            self.assertEqual(marker.read_bytes(), b"must survive")
            self.assertEqual(py.read_bytes(), b"supported interpreter fixture")

    def test_new_environment_creation_and_failed_partial_files(self) -> None:
        for result in (0, 1):
            with self.subTest(returncode=result), tempfile.TemporaryDirectory() as td:
                root = Path(td) / "new-cad-env"
                with patch.dict("os.environ", {"PATENT_SKILL_CAD_VENV": str(root)}):
                    py = cad_venv.venv_python()

                    def create_fixture(cmd, **kwargs):
                        self.assertEqual(cmd[-1], str(root))
                        py.parent.mkdir(parents=True)
                        py.write_bytes(b"new interpreter fixture")
                        return subprocess.CompletedProcess(cmd, result, "", "fixture failure" if result else "")

                    with patch.object(boot, "_run", side_effect=create_fixture) as run:
                        if result:
                            with self.assertRaisesRegex(RuntimeError, "partial files were retained"):
                                boot._create_venv("fixture-host-python")
                        else:
                            self.assertEqual(boot._create_venv("fixture-host-python"), py)
                        run.assert_called_once()
                    self.assertEqual(py.read_bytes(), b"new interpreter fixture")

    def test_replacing_plugin_does_not_replace_environment_or_metadata(self) -> None:
        def load(path: Path):
            spec = importlib.util.spec_from_file_location("cad_venv_update_fixture", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module

        with tempfile.TemporaryDirectory() as td, patch.dict("os.environ", {}, clear=True):
            root = Path(td)
            plugin = root / "plugin-cache"
            data = root / "user-data"
            with patch.dict("os.environ", {"PATENT_TOOLKIT_DATA_HOME": str(data)}):
                plugin.mkdir()
                shutil.copy2(SHARED / "cad_venv.py", plugin / "cad_venv.py")
                before = load(plugin / "cad_venv.py")
                before.write_meta({"fixture": "preserve-on-update"})
                marker = before.cad_venv_dir() / "installed-dependency.fixture"
                marker.write_bytes(b"persistent dependency")
                shutil.rmtree(plugin)
                plugin.mkdir()
                shutil.copy2(SHARED / "cad_venv.py", plugin / "cad_venv.py")
                after = load(plugin / "cad_venv.py")
                self.assertEqual(before.cad_venv_dir(), after.cad_venv_dir())
                self.assertEqual(after.read_meta(), {"fixture": "preserve-on-update"})
                self.assertEqual(marker.read_bytes(), b"persistent dependency")
                self.assertFalse((plugin / "cad-env").exists())


class BootstrapIndexTests(unittest.TestCase):
    def test_china_mirrors_then_pypi(self) -> None:
        urls = boot._index_list(pypi_only=False, extra=[])
        self.assertEqual(urls[-1], "https://pypi.org/simple")
        self.assertTrue(any("tsinghua" in u or "tuna" in u for u in urls))
        self.assertTrue(any("aliyun" in u for u in urls))

    def test_pypi_only(self) -> None:
        self.assertEqual(boot._index_list(pypi_only=True, extra=[]), ["https://pypi.org/simple"])


class CadRunnerGateTests(unittest.TestCase):
    def test_disabled_runner_never_checks_or_creates_environment(self) -> None:
        with tempfile.TemporaryDirectory() as td, patch.dict("os.environ", {}, clear=True):
            model = Path(td) / "fixture.step"
            model.write_text("offline fixture", encoding="utf-8")
            output = Path(td) / "output"
            with patch.object(runner, "ensure_cad_env") as ensure, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(runner.main([]), 3)
                self.assertEqual(runner.main(["-i", str(model), "-o", str(output)]), 3)
                ensure.assert_not_called()
            self.assertFalse(output.exists())

    def test_missing_or_invalid_input_output_never_creates_environment(self) -> None:
        with tempfile.TemporaryDirectory() as td, patch.dict("os.environ", {}, clear=True):
            root = Path(td)
            model = root / "fixture.step"
            model.write_text("offline fixture", encoding="utf-8")
            other = root / "fixture.txt"
            other.write_text("offline fixture", encoding="utf-8")
            output = root / "output"
            cases = [
                ["--enable-step-parse"],
                ["--enable-step-parse", "-i", str(model)],
                ["--enable-step-parse", "-i", str(root / "missing.step"), "-o", str(output)],
                ["--enable-step-parse", "-i", str(root), "-o", str(output)],
                ["--enable-step-parse", "-i", str(other), "-o", str(output)],
                ["--enable-step-parse", "-i", str(model), "-o", str(other)],
            ]
            with patch.object(runner, "ensure_cad_env") as ensure, contextlib.redirect_stderr(io.StringIO()):
                for args in cases:
                    with self.subTest(args=args):
                        self.assertEqual(runner.main(args), 2)
                ensure.assert_not_called()
            self.assertFalse(output.exists())

    def test_dependency_probe_is_read_only_without_enable(self) -> None:
        with patch.object(runner, "status", return_value={"ok": False}), \
                patch.object(runner, "ensure_cad_env") as ensure, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(runner.main(["--check-deps"]), 2)
            ensure.assert_not_called()

    def test_explicit_flag_or_existing_environment_opt_in_allows_valid_request(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            model = Path(td) / "fixture.step"
            model.write_text("offline fixture", encoding="utf-8")
            base = ["-i", str(model), "-o", str(Path(td) / "output"), "--no-screenshot"]
            for flag, env in ((["--enable-step-parse"], {}), ([], {"PATENT_SKILL_STEP_PARSE": "1"})):
                with self.subTest(flag=flag), patch.dict("os.environ", env, clear=True), \
                        patch.object(runner, "ensure_cad_env", return_value={"ok": True}) as ensure, \
                        patch.object(runner, "_run", return_value=0) as run:
                    self.assertEqual(runner.main(flag + base), 0)
                    ensure.assert_called_once_with(bootstrap=True)
                    run.assert_called_once()


class CadNoMatplotlibTests(unittest.TestCase):
    def test_cad_scripts_do_not_import_matplotlib(self) -> None:
        names = (
            "step_to_views.py",
            "svg_screenshot.py",
            "run_step_to_views.py",
            "cad_venv.py",
            "bootstrap_cad_venv.py",
            "requirements-step.txt",
        )
        for name in names:
            text = (SHARED / name).read_text(encoding="utf-8")
            self.assertNotIn("import matplotlib", text, name)
            self.assertNotIn("matplotlib_tessellate", text, name)


class RequirementsAsciiTests(unittest.TestCase):
    def test_step_and_root_are_ascii(self) -> None:
        for path in (SHARED / "requirements-step.txt", ROOT / "requirements.txt"):
            raw = path.read_bytes()
            raw.decode("ascii")


class SvgScreenshotTests(unittest.TestCase):
    def test_wrap_strips_xml_decl(self) -> None:
        html = shot.wrap_svg_html('<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"></svg>')
        self.assertIn("<svg", html)
        self.assertNotIn("<?xml", html)
        self.assertIn('id="stage"', html)

    def test_wrap_allows_braces_in_svg(self) -> None:
        html = shot.wrap_svg_html('<svg><style>.x{fill:red}</style></svg>')
        self.assertIn("{fill:red}", html)

    def test_pick_free_port_skips_busy(self) -> None:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind(("127.0.0.1", 0))
        busy = int(srv.getsockname()[1])
        try:
            got = shot.pick_free_port("127.0.0.1", preferred=busy)
            self.assertNotEqual(got, busy)
            self.assertGreater(got, 0)
        finally:
            srv.close()

    def test_jobs_from_dir_skips_existing_png(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.svg").write_text("<svg/>", encoding="utf-8")
            (root / "a.png").write_bytes(b"x")
            (root / "b.svg").write_text("<svg/>", encoding="utf-8")
            jobs = shot.jobs_from_dir(root)
            stems = [s.stem for s, _ in jobs]
            self.assertEqual(stems, ["b"])


class FigurePlanSeedPathTests(unittest.TestCase):
    def test_falls_back_to_svg(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "figure_plan.seed.yaml"
            plan = build_figure_plan_seed(
                view_records=[
                    {
                        "name": "iso",
                        "role": "assembly",
                        "png": "",
                        "svg": str(Path(td) / "iso.svg"),
                    }
                ],
                out_path=out,
                theme_summary="t",
            )
            self.assertTrue(plan["figures"][0]["path"].endswith("iso.svg"))


if __name__ == "__main__":
    unittest.main()
