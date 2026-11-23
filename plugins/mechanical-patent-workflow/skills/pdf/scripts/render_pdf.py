#!/usr/bin/env python3
"""Render a PDF with a separately installed Poppler pdftoppm. MIT licensed."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def find_pdftoppm(explicit: str | None = None) -> str:
    candidate = shutil.which(explicit or "pdftoppm")
    if candidate:
        return candidate
    candidates = [Path(explicit).expanduser()] if explicit else [Path("/opt/homebrew/bin/pdftoppm"), Path("/usr/local/bin/pdftoppm")]
    for path in candidates:
        if path.is_file() and (os.name == "nt" or os.access(path, os.X_OK)):
            return str(path.resolve())
    raise ValueError("Install Poppler separately and add pdftoppm to PATH or provide --pdftoppm.")


def render_pdf(source: Path, output_dir: Path, *, pdftoppm: str | None = None,
               dpi: int = 150, timeout: int = 180) -> dict:
    source = source.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    if not source.is_file() or source.suffix.lower() != ".pdf":
        raise ValueError("Input must be an existing PDF.")
    if output_dir.exists() and (not output_dir.is_dir() or any(output_dir.iterdir())):
        raise ValueError("Output directory must be absent or empty.")
    if not 36 <= dpi <= 600 or timeout <= 0:
        raise ValueError("DPI must be 36–600 and timeout must be positive.")
    executable = find_pdftoppm(pdftoppm)
    with tempfile.TemporaryDirectory(prefix="pdf-render-") as temp:
        work = Path(temp)
        # A neutral staging name avoids exporting the source basename in logs.
        staged = work / "document.pdf"
        shutil.copyfile(source, staged)
        subprocess.run([executable, "-png", "-r", str(dpi), str(staged), str(work / "page")],
                       check=True, capture_output=True, timeout=timeout)
        pages = sorted(work.glob("page-*.png"))
        if not pages:
            raise ValueError("Poppler did not produce page images.")
        output_dir.mkdir(parents=True, exist_ok=True)
        for page in pages:
            shutil.copyfile(page, output_dir / page.name)
        result = {"pages": [p.name for p in pages], "dpi": dpi, "visual_review": "pending"}
        (output_dir / "render.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--pdftoppm")
    parser.add_argument("--dpi", type=int, default=150)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    try:
        print(json.dumps(render_pdf(args.source, args.output_dir, pdftoppm=args.pdftoppm,
                                    dpi=args.dpi, timeout=args.timeout), ensure_ascii=False))
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        detail = str(exc) if isinstance(exc, ValueError) else "Check input and local Poppler installation."
        parser.exit(1, f"PDF render failed ({type(exc).__name__}): {detail}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
