#!/usr/bin/env python
"""检查申请底稿所需交底材料是否齐全。缺则 exit 2，勿空写申请。

用法：
  python tools/material_gate.py --case-dir outputs/{案件}
  python tools/material_gate.py --case-dir outputs/{案件} --type utility_model
  python tools/material_gate.py --case-dir outputs/{案件} --disclosure 某案_20260101120000.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from stdio_utf8 import ensure_utf8_stdio

DISCLOSURE_TS = re.compile(r".+_\d{14}\.(md|docx)$", re.I)
PATENT_TYPE_LINE = re.compile(
    r"(?:\*\*)?专利类型(?:\*\*)?\s*[：:]\s*(?:\*\*)?"
    r"(utility_model|invention|design|实用新型|外观设计|发明|实用|外观)", re.I
)
SUBJECT_KINDS = ("mechanical_product", "method", "software_system", "mixed", "unknown")
EXCLUDE_NAME = re.compile(
    r"readme|skill|修订对话|申请底稿|权利要求|说明书|移交|"
    r"figure_plan|structure_schema|appearance_schema|formula_plan|iteration",
    re.I,
)
TYPE_ALIASES = {
    "发明": "invention",
    "invention": "invention",
    "实用新型": "utility_model",
    "utility_model": "utility_model",
    "实用": "utility_model",
    "外观设计": "design",
    "外观": "design",
    "design": "design",
}
SCHEMA_NAMES = {
    "structure": ("structure_schema.yaml", "structure_schema.json"),
    "appearance": ("appearance_schema.yaml", "appearance_schema.json"),
    "figure_plan": ("figure_plan.yaml", "figure_plan.json"),
}


def _load_mapping(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        try:
            import yaml
        except ImportError as exc:
            raise SystemExit("需要 PyYAML：pip install -r requirements.txt") from exc
        data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} 根须为 mapping")
    return data


def _first_file(case: Path, names: tuple[str, ...]) -> Path | None:
    for name in names:
        cand = case / name
        if cand.is_file():
            return cand
    return None


def _read_disclosure_text(path: Path) -> str:
    """Read the actual disclosure text, including a type split across Word runs."""
    if path.suffix.lower() == ".docx":
        with zipfile.ZipFile(path) as package:
            root = ET.fromstring(package.read("word/document.xml"))
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        return "\n".join("".join(p.itertext()) for p in root.findall(".//w:p", ns))
    if path.suffix.lower() == ".md":
        return path.read_text(encoding="utf-8")
    return ""


def _looks_like_disclosure(path: Path) -> bool:
    try:
        head = "\n".join(_read_disclosure_text(path).splitlines()[:120])
    except (OSError, UnicodeError, KeyError, zipfile.BadZipFile, ET.ParseError):
        return False
    return "技术交底书" in head or PATENT_TYPE_LINE.search(head) is not None


def find_disclosure(case: Path, explicit: Path | None) -> Path | None:
    if explicit is not None:
        return explicit if explicit.is_file() else None
    if not case.is_dir():
        return None
    scored: list[tuple[int, float, Path]] = []
    for path in case.iterdir():
        if not path.is_file() or EXCLUDE_NAME.search(path.name):
            continue
        if path.suffix.lower() not in {".md", ".docx"}:
            continue
        ts = 2 if DISCLOSURE_TS.match(path.name) else 0
        looks = 1 if _looks_like_disclosure(path) else 0
        if ts or looks:
            scored.append((ts + looks, path.stat().st_mtime, path))
    if not scored:
        return None
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return scored[0][2]


def detect_type_from_disclosure(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        text = _read_disclosure_text(path)
    except (OSError, UnicodeError, KeyError, zipfile.BadZipFile, ET.ParseError):
        return None
    match = PATENT_TYPE_LINE.search(text)
    if not match:
        return None
    return TYPE_ALIASES.get(match.group(1).strip().lower())


def resolve_asset(case: Path, rel: str) -> Path | None:
    raw = (rel or "").strip()
    if not raw:
        return None
    path = Path(raw)
    if path.is_file():
        return path
    cand = case / raw
    return cand if cand.is_file() else None


def in_disclosure_figures(plan: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in plan.get("figures") or []:
        if isinstance(item, dict) and item.get("use_in_disclosure") is True:
            rows.append(item)
    return rows


def check_case(
    case: Path,
    *,
    disclosure: Path | None = None,
    type_hint: str | None = None,
    subject_kind: str | None = None,
) -> dict[str, Any]:
    missing: list[str] = []
    warnings: list[str] = []
    files: dict[str, str] = {}
    found = find_disclosure(case, disclosure)
    if found is None:
        missing.append("disclosure")
    else:
        files["disclosure"] = str(found)
        try:
            if not _read_disclosure_text(found).strip():
                missing.append("disclosure_unreadable")
        except (OSError, UnicodeError, KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
            missing.append("disclosure_unreadable")
            files["disclosure_error"] = str(exc)

    structure = _first_file(case, SCHEMA_NAMES["structure"])
    appearance = _first_file(case, SCHEMA_NAMES["appearance"])
    figure_plan = _first_file(case, SCHEMA_NAMES["figure_plan"])
    if structure is not None:
        files["structure_schema"] = str(structure)
    if appearance is not None:
        files["appearance_schema"] = str(appearance)
    if figure_plan is not None:
        files["figure_plan"] = str(figure_plan)

    lineart_ok = 0
    photo_ok = 0
    plan: dict[str, Any] = {}
    if figure_plan is not None:
        try:
            plan = _load_mapping(figure_plan)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            missing.append("figure_plan_unreadable")
            plan = {}
            files["figure_plan_error"] = str(exc)

    declared_type = detect_type_from_disclosure(found)
    patent_type = type_hint or declared_type
    if patent_type is not None and patent_type not in {"invention", "utility_model", "design"}:
        raise ValueError(f"未知专利类型：{patent_type}")
    if type_hint and declared_type and type_hint != declared_type:
        warnings.append("type_hint_overrides_disclosure")
    if patent_type is None:
        # Structure is a technical form shared by inventions and utility models.
        # Its presence must never change the chosen filing type.
        patent_type = "invention" if found is not None else ""
        if found is not None:
            warnings.append("patent_type_default_invention")
    selected_subject = subject_kind or str(plan.get("subject_kind") or "")
    if not selected_subject:
        selected_subject = "mechanical_product" if structure is not None or patent_type == "utility_model" else "unknown"
    if selected_subject not in SUBJECT_KINDS:
        raise ValueError(f"未知保护对象：{selected_subject}")
    if patent_type == "utility_model" and selected_subject not in {"mechanical_product", "unknown"}:
        missing.append("subject_type_conflict")

    needs_structure = patent_type == "utility_model" or (
        patent_type == "invention" and selected_subject in {"mechanical_product", "mixed"}
    )
    if needs_structure:
        if structure is None:
            missing.append("structure_schema")
        if figure_plan is None:
            missing.append("figure_plan")
        elif "figure_plan_unreadable" not in missing:
            for item in in_disclosure_figures(plan):
                if str(item.get("kind") or "") != "lineart":
                    continue
                if resolve_asset(case, str(item.get("path") or "")) is None:
                    continue
                lineart_ok += 1
            if lineart_ok < 1:
                missing.append("lineart")
    elif patent_type == "design":
        if appearance is None:
            missing.append("appearance_schema")
        if figure_plan is None:
            missing.append("figure_plan")
        elif "figure_plan_unreadable" not in missing:
            for item in in_disclosure_figures(plan):
                kind = str(item.get("kind") or "")
                if resolve_asset(case, str(item.get("path") or "")) is None:
                    continue
                if kind == "lineart":
                    lineart_ok += 1
                elif kind in {"photo_clean", "photo_scene"}:
                    photo_ok += 1
            if lineart_ok < 1:
                missing.append("lineart")
            if photo_ok < 1:
                missing.append("photo")
    elif patent_type == "invention":
        pass
    elif patent_type == "" and "disclosure" in missing:
        pass
    elif not patent_type:
        missing.append("patent_type")

    ok = not missing
    return {
        "ok": ok,
        "type": patent_type or "",
        "subject_kind": selected_subject,
        "missing": missing,
        "warnings": warnings,
        "files": files,
        "lineart": lineart_ok,
        "photo": photo_ok,
    }


def _kv(result: dict[str, Any]) -> str:
    parts = [
        f"ok={1 if result['ok'] else 0}",
        f"type={result['type'] or '-'}",
        f"subject_kind={result['subject_kind']}",
        f"missing={','.join(result['missing']) or '-'}",
        f"lineart={result['lineart']}",
        f"photo={result['photo']}",
        f"warnings={len(result['warnings'])}",
    ]
    files = result.get("files") or {}
    for key in ("disclosure", "structure_schema", "appearance_schema", "figure_plan"):
        if key in files:
            parts.append(f"{key}={files[key]}")
    return " ".join(parts)


def main() -> int:
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-dir", required=True, type=Path, help="交底产出目录")
    parser.add_argument("--disclosure", type=Path, default=None, help="指定交底 md/docx")
    parser.add_argument(
        "--type",
        dest="type_hint",
        choices=("invention", "utility_model", "design"),
        default=None,
    )
    parser.add_argument("--subject-kind", choices=SUBJECT_KINDS, default=None,
                        help="已核定的技术形态，独立于发明/实用新型申请类型")
    args = parser.parse_args()
    case = args.case_dir.expanduser().resolve()
    if not case.is_dir():
        print(f"APPLICATION_GATE: ok=0 type=- missing=case_dir hint=run_disclosure")
        print(f"目录不存在：{case}", file=sys.stderr)
        return 2
    disclosure = args.disclosure.expanduser().resolve() if args.disclosure else None
    if args.disclosure is not None and (disclosure is None or not disclosure.is_file()):
        print("APPLICATION_GATE: ok=0 type=- missing=disclosure hint=run_disclosure")
        print(f"交底文件不存在：{args.disclosure}", file=sys.stderr)
        return 2

    result = check_case(case, disclosure=disclosure, type_hint=args.type_hint, subject_kind=args.subject_kind)
    print(f"APPLICATION_GATE: {_kv(result)}")
    for warning in result["warnings"]:
        print(f"WARNING\t{warning}\t以本案核定类型为准；辅助结构文件不决定申请类型。")
    if result["ok"]:
        print(f"本分支材料门禁通过，类型={result['type']}。继续成文；技术支持、检索、图面与定稿状态仍按共用收尾核验。")
        return 0

    print("本分支材料尚有缺口。先核对已有Word、模型和原图，可内部整理的补齐后重检；完成其余有依据部分，并明确未完成范围，不宣称整套定稿。")
    labels = {
        "disclosure": "可读的同案交底书（Word或Markdown，可用--disclosure指定）",
        "disclosure_unreadable": "交底正文无法读取或为空，请使用可读的同案Word/Markdown",
        "structure_schema": "structure_schema.yaml（机械结构产品）",
        "appearance_schema": "appearance_schema.yaml（外观）",
        "figure_plan": "figure_plan.yaml",
        "lineart": "figure_plan 中入文且路径可读的线稿",
        "photo": "figure_plan 中入文且路径可读的实拍",
        "figure_plan_unreadable": "figure_plan 无法解析",
        "ambiguous_type": "同时有结构/外观 schema，请加 --type",
        "patent_type": "无法判断专利类型",
        "subject_type_conflict": "实用新型与所选保护对象不一致，请核对类型及对象",
        "case_dir": "交底目录",
    }
    for key in result["missing"]:
        print(f"- 缺失：{labels.get(key, key)}")
    print("hint=review_materials → 核定材料和保护对象；必要时衔接交底入口，不要求用户重做已有资料。")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
