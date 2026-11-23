#!/usr/bin/env python3
"""Render a DOCX with locally installed LibreOffice and Poppler. MIT licensed."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def find_program(explicit: str | None, kind: str) -> str:
    """Prefer an explicit executable, then PATH, then common installation paths."""
    names = {"libreoffice": ("libreoffice", "soffice"), "pdftoppm": ("pdftoppm",)}[kind]
    if explicit:
        candidate = shutil.which(explicit)
        if candidate:
            return candidate
        path = Path(explicit).expanduser()
        if path.is_file() and (os.name == "nt" or os.access(path, os.X_OK)):
            return str(path.resolve())
        raise ValueError(f"The explicit {kind} executable is unavailable.")
    for name in names:
        candidate = shutil.which(name)
        if candidate:
            return candidate
    candidates: list[Path] = []
    if kind == "libreoffice":
        candidates += [Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")]
        for key in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            if os.environ.get(key):
                candidates.append(Path(os.environ[key]) / "LibreOffice/program/soffice.exe")
    else:
        candidates += [Path("/opt/homebrew/bin/pdftoppm"), Path("/usr/local/bin/pdftoppm")]
    for path in candidates:
        if path.is_file() and (os.name == "nt" or os.access(path, os.X_OK)):
            return str(path)
    raise ValueError(f"Install {kind} separately, add it to PATH, or provide --{kind}.")


def render_docx(source: Path, output_dir: Path, *, libreoffice: str | None = None,
                pdftoppm: str | None = None, dpi: int = 150,
                timeout: int = 180) -> dict:
    source = source.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    if not source.is_file() or source.suffix.lower() != ".docx":
        raise ValueError("Input must be an existing .docx file.")
    if output_dir.exists() and (not output_dir.is_dir() or any(output_dir.iterdir())):
        raise ValueError("Output directory must be absent or empty; existing results are never overwritten.")
    if not 36 <= dpi <= 600 or timeout <= 0:
        raise ValueError("DPI must be 36–600 and timeout must be positive.")
    office = find_program(libreoffice, "libreoffice")
    poppler = find_program(pdftoppm, "pdftoppm")
    # Stage all work in a separate directory. A fresh office profile avoids
    # touching the user's open LibreOffice session or changing its settings.
    with tempfile.TemporaryDirectory(prefix="docx-render-") as temp:
        work = Path(temp)
        staged_source = work / "document.docx"
        shutil.copyfile(source, staged_source)
        staged_out = work / "out"
        staged_out.mkdir()
        subprocess.run([
            office, f"-env:UserInstallation={(work / 'profile').as_uri()}",
            "--headless", "--nologo", "--nodefault", "--nofirststartwizard",
            "--norestore", "--convert-to", "pdf", "--outdir", str(staged_out),
            str(staged_source),
        ], check=True, capture_output=True, timeout=timeout)
        pdf = staged_out / "document.pdf"
        if not pdf.is_file() or pdf.stat().st_size == 0:
            raise ValueError("LibreOffice did not produce a PDF; inspect the document and local font setup.")
        subprocess.run([poppler, "-png", "-r", str(dpi), str(pdf), str(staged_out / "page")],
                       check=True, capture_output=True, timeout=timeout)
        pages = sorted(staged_out.glob("page-*.png"))
        if not pages:
            raise ValueError("Poppler did not produce page images.")
        output_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(pdf, output_dir / "document.pdf")
        for page in pages:
            shutil.copyfile(page, output_dir / page.name)
        result = {"pdf": "document.pdf", "pages": [p.name for p in pages],
                  "dpi": dpi, "visual_review": "pending", "privacy_review": "pending"}
        (output_dir / "render.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--libreoffice", help="Explicit soffice/libreoffice executable")
    parser.add_argument("--pdftoppm", help="Explicit Poppler pdftoppm executable")
    parser.add_argument("--dpi", type=int, default=150)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    try:
        result = render_docx(args.source, args.output_dir, libreoffice=args.libreoffice,
                             pdftoppm=args.pdftoppm, dpi=args.dpi, timeout=args.timeout)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        # Avoid printing subprocess stdout/stderr, which can contain private paths.
        detail = str(exc) if isinstance(exc, ValueError) else "Check input, executable paths, and local fonts."
        parser.exit(1, f"Render failed ({type(exc).__name__}): {detail}\n")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
