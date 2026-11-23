#!/usr/bin/env python
"""件号 / 图号登记：图 ↔ 权要 ↔ 说明书双向核对。

用法：
  python tools/check_numeral_register.py --register 件号登记表.yaml \\
    --schema structure_schema.yaml --figure-plan figure_plan.yaml \\
    --claims 权利要求书.md --spec 说明书.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from stdio_utf8 import ensure_utf8_stdio

MARK = re.compile(r"[（(](\d+)[）)]")
NEAR_MARK = re.compile(r"([\u4e00-\u9fffA-Za-z0-9]{1,80})\s*[（(](\d+)[）)]")
# A registered suffix must have a plausible grammatical boundary.  Otherwise
# "外壳体" must not silently become "壳体" merely because it shares a suffix.
NAME_BOUNDARY = re.compile(
    r"(?:包括|具有|设有|设置|所述|上述|前述|该|各|的|于|与|和|及|或|为|由|"
    r"若干|多个|至少一个|至少两个|一个|两个|三个|各个|\d+个)$"
)


@dataclass
class Finding:
    level: str
    code: str
    message: str


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


def _as_int_list(raw: Any) -> list[int]:
    out: list[int] = []
    for item in raw or []:
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            continue
    return out


def _part_id(raw: Any) -> str:
    return str(raw).strip() if raw is not None else ""


def _entities(mapping: dict[str, Any]) -> list[dict[str, Any]]:
    """Physical parts and independently marked features share one number space."""
    entities: list[dict[str, Any]] = []
    for key in ("parts", "features"):
        for item in mapping.get(key) or []:
            if not isinstance(item, dict):
                continue
            value = dict(item)
            if key == "features" and not _part_id(value.get("id")):
                value["id"] = value.get("reference_number")
            entities.append(value)
    return entities


def _number_conflicts(mapping: dict[str, Any], *, where: str) -> list[Finding]:
    findings: list[Finding] = []
    for item in mapping.get("features") or []:
        if not isinstance(item, dict):
            continue
        pid = _part_id(item.get("id"))
        reference = _part_id(item.get("reference_number"))
        if pid and reference and pid != reference:
            findings.append(
                Finding(
                    "ERROR", "FEATURE_NUMBER_CONFLICT",
                    f"{where}子特征 id「{pid}」与 reference_number「{reference}」不一致。",
                )
            )
    return findings


def _split_claims(text: str) -> dict[int, str]:
    start = re.compile(r"(?m)^\s*(\d+)\s*[.、．]\s*")
    matches = list(start.finditer(text))
    claims: dict[int, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        claims[int(match.group(1))] = text[match.end() : end]
    return claims


def _mentions_part(text: str, part_id: str, name: str) -> bool:
    if MARK.search(text) and part_id in MARK.findall(text):
        return True
    if name and name in text:
        return True
    return False


def _occurrence_findings(text: str, parts: list[dict[str, Any]], *, where: str) -> list[Finding]:
    """Check registered names/aliases; uncertain wording remains a manual hint.

    Chinese has no whitespace word boundaries.  The entire run before a mark
    ("包括支撑座", "所述支撑座") is not itself a component name.  Resolve its
    longest registered suffix instead of treating sentence prefixes as names.
    """
    findings: list[Finding] = []
    register_ids = {_part_id(item.get("id")) for item in parts if _part_id(item.get("id"))}
    register_names: dict[str, str] = {}
    name_owners: dict[str, set[str]] = {}
    for item in parts:
        pid = _part_id(item.get("id"))
        if not pid:
            continue
        name = str(item.get("name") or "").strip()
        register_names[pid] = name
        aliases = item.get("aliases") or []
        if isinstance(aliases, str):
            aliases = [aliases]
        for value in [name] + list(aliases):
            value = str(value).strip()
            if value:
                name_owners.setdefault(value, set()).add(pid)

    by_name: dict[str, set[str]] = {}
    for match in NEAR_MARK.finditer(text or ""):
        raw_name, pid = match.group(1), match.group(2)
        if pid not in register_ids:
            findings.append(
                Finding("ERROR", "MARK_UNREGISTERED", f"{where}出现未登记件号（{pid}），附近用语：{raw_name}。")
            )
        matches = [
            name for name in name_owners
            if raw_name.endswith(name)
            and (
                raw_name == name
                or NAME_BOUNDARY.search(raw_name[:-len(name)])
            )
        ]
        if not matches:
            # A new abbreviation, a collective name or an unregistered term
            # cannot reliably prove cross-numbering from a regex alone.
            findings.append(
                Finding(
                    "WARNING", "OCCURRENCE_NAME",
                    f"{where}件号（{pid}）附近用语「{raw_name}」未匹配登记名称或别名，请逐处核实。",
                )
            )
            continue
        longest = max(len(name) for name in matches)
        names = [name for name in matches if len(name) == longest]
        owners = set().union(*(name_owners[name] for name in names))
        # Different physical features can legitimately share a short name.
        # Such names need their parent/context checked, not a guessed identity.
        if len(owners) > 1 and pid in owners:
            findings.append(
                Finding(
                    "WARNING", "OCCURRENCE_AMBIGUOUS",
                    f"{where}「{' / '.join(names)}（{pid}）」对应多个登记对象，请沿所属母件及上下文核实。",
                )
            )
        if pid in register_ids and pid not in owners:
            findings.append(
                Finding(
                    "ERROR", "CROSS_NAME",
                    f"{where}「{' / '.join(names)}」使用件号（{pid}），登记对应件号为{'、'.join(sorted(owners))}；（{pid}）登记名为「{register_names[pid]}」。",
                )
            )
        if len(owners) == 1:
            # Only an unambiguous registered identity supports a definite
            # same-name/different-number error.  Aliases share its canonical name.
            owner = next(iter(owners))
            canonical = register_names[owner]
            by_name.setdefault(canonical, set()).add(pid)
    for name, ids in sorted(by_name.items()):
        if len(ids) > 1:
            findings.append(
                Finding("ERROR", "NAME_SPLIT", f"{where}「{name}」用了多个件号：{'、'.join(f'（{i}）' for i in sorted(ids))}。")
            )
    return findings


def check_register(
    register: dict[str, Any],
    *,
    schema: Optional[dict[str, Any]] = None,
    figure_plan: Optional[dict[str, Any]] = None,
    claims_text: Optional[str] = None,
    spec_text: Optional[str] = None,
) -> list[Finding]:
    findings: list[Finding] = []
    parts = _entities(register)
    findings.extend(_number_conflicts(register, where="登记表"))
    figures = [item for item in (register.get("figures") or []) if isinstance(item, dict)]
    ids = [_part_id(item.get("id")) for item in parts]
    if ids and len(ids) != len(set(ids)):
        findings.append(Finding("ERROR", "DUP_ID", "件号登记表 parts.id 有重复。"))

    for item in parts:
        if not _part_id(item.get("id")):
            findings.append(Finding("ERROR", "EMPTY_ID", "存在空的 parts.id。"))
        if not str(item.get("name") or "").strip():
            findings.append(
                Finding("ERROR", "EMPTY_NAME", f"件号 {item.get('id')} 缺少 name。")
            )

    if schema is not None:
        findings.extend(_number_conflicts(schema, where="structure_schema"))
        schema_ids = [_part_id(item.get("id")) for item in _entities(schema)]
        if len(schema_ids) != len(set(schema_ids)):
            findings.append(
                Finding("ERROR", "SCHEMA_DUP_ID", "structure_schema 部件与子特征共用的标号空间存在重复。")
            )
        schema_parts = {
            _part_id(item.get("id")): str(item.get("name") or "").strip()
            for item in _entities(schema)
            if _part_id(item.get("id"))
        }
        physical_ids = {
            _part_id(item.get("id"))
            for item in schema.get("parts") or []
            if isinstance(item, dict)
        }
        for item in schema.get("features") or []:
            if isinstance(item, dict) and _part_id(item.get("parent_part_id")) not in physical_ids:
                findings.append(
                    Finding(
                        "ERROR", "FEATURE_PARENT_UNKNOWN",
                        f"子特征 {item.get('id') or item.get('reference_number')} 的母件 {item.get('parent_part_id')} 不在 structure_schema.parts。",
                    )
                )
        register_ids = {i for i in ids if i}
        for pid, pname in schema_parts.items():
            if pid not in register_ids:
                findings.append(
                    Finding("ERROR", "SCHEMA_MISSING", f"structure_schema 件号 {pid}（{pname}）未入登记表。")
                )
        for item in parts:
            pid = _part_id(item.get("id"))
            if pid and pid not in schema_parts:
                findings.append(
                    Finding("ERROR", "REGISTER_EXTRA", f"登记表件号 {pid} 不在 structure_schema。")
                )
            name = str(item.get("name") or "").strip()
            if pid in schema_parts and name and schema_parts[pid] and name != schema_parts[pid]:
                findings.append(
                    Finding(
                        "WARNING",
                        "NAME_MISMATCH",
                        f"件号 {pid} 登记名「{name}」与 schema「{schema_parts[pid]}」不一致。",
                    )
                )

    plan_figs: set[int] = set()
    cover_map: dict[int, set[str]] = {}
    if figure_plan is not None:
        for item in figure_plan.get("figures") or []:
            if not isinstance(item, dict) or item.get("use_in_disclosure") is not True:
                continue
            try:
                fig = int(item.get("fig"))
            except (TypeError, ValueError):
                continue
            plan_figs.add(fig)
            covers = {str(x).strip() for x in (item.get("covers") or []) if str(x).strip()}
            cover_map[fig] = covers

        registered_figs: set[int] = set()
        for item in figures:
            try:
                registered_figs.add(int(item.get("fig")))
            except (TypeError, ValueError):
                continue
        for item in parts:
            registered_figs.update(_as_int_list(item.get("figures")))

        for fig in sorted(plan_figs):
            if fig not in registered_figs:
                findings.append(
                    Finding("ERROR", "FIG_UNREGISTERED", f"入文图 {fig} 未写入登记表 figures 或 parts.figures。")
                )
        for fig in sorted(registered_figs):
            if plan_figs and fig not in plan_figs:
                findings.append(
                    Finding("ERROR", "FIG_UNKNOWN", f"登记表图 {fig} 不是 figure_plan 的入文 fig。")
                )
        for item in parts:
            pid = _part_id(item.get("id"))
            for fig in _as_int_list(item.get("figures")):
                covers = cover_map.get(fig)
                if covers is not None and covers and pid not in covers:
                    findings.append(
                        Finding(
                            "WARNING",
                            "COVERS_MISMATCH",
                            f"件号 {pid} 登记出现于图 {fig}，但 figure_plan.covers 未列该件。",
                        )
                    )

    if claims_text is not None and parts:
        claim_map = _split_claims(claims_text)
        for item in parts:
            pid = _part_id(item.get("id"))
            name = str(item.get("name") or "").strip()
            listed = set(_as_int_list(item.get("claims")))
            appeared: set[int] = set()
            for num, body in claim_map.items():
                if _mentions_part(body, pid, name):
                    appeared.add(num)
            for num in sorted(listed - appeared):
                findings.append(
                    Finding(
                        "ERROR",
                        "CLAIM_MARK_MISSING",
                        f"件号 {pid} 登记出现于权项 {num}，但该权项未见「（{pid}）」或名称「{name}」。",
                    )
                )
            for num in sorted(appeared - listed):
                findings.append(
                    Finding(
                        "WARNING",
                        "CLAIM_UNLISTED",
                        f"权项 {num} 出现了件号 {pid}，登记表 claims 未列入。",
                    )
                )

    if spec_text is not None and parts:
        for item in parts:
            pid = _part_id(item.get("id"))
            name = str(item.get("name") or "").strip()
            hit = _mentions_part(spec_text, pid, name)
            flagged = item.get("specification")
            if flagged is True and not hit:
                findings.append(
                    Finding(
                        "ERROR",
                        "SPEC_MARK_MISSING",
                        f"件号 {pid} 标明已入说明书，但未见「（{pid}）」或名称「{name}」。",
                    )
                )
            if flagged is False and hit:
                findings.append(
                    Finding(
                        "WARNING",
                        "SPEC_UNFLAGGED",
                        f"说明书出现了件号 {pid}，登记表 specification 未标 true。",
                    )
                )
            if flagged is None and not hit:
                findings.append(
                    Finding(
                        "WARNING",
                        "SPEC_UNCHECKED",
                        f"件号 {pid} 未填 specification，且说明书未见该件。",
                    )
                )

        findings.extend(_occurrence_findings(spec_text, parts, where="说明书"))

    if claims_text is not None and parts:
        findings.extend(_occurrence_findings(claims_text, parts, where="权要"))

    if not parts and not figures:
        findings.append(Finding("ERROR", "EMPTY_REGISTER", "登记表 parts 与 figures 都为空。"))

    return findings


def main() -> int:
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--register", required=True, type=Path)
    parser.add_argument("--schema", type=Path, default=None)
    parser.add_argument("--figure-plan", type=Path, default=None)
    parser.add_argument("--claims", type=Path, default=None)
    parser.add_argument("--spec", type=Path, default=None)
    args = parser.parse_args()

    try:
        register = _load_mapping(args.register.expanduser().resolve())
        schema = _load_mapping(args.schema) if args.schema else None
        plan = _load_mapping(args.figure_plan) if args.figure_plan else None
        claims = args.claims.read_text(encoding="utf-8") if args.claims else None
        spec = args.spec.read_text(encoding="utf-8") if args.spec else None
    except FileNotFoundError as exc:
        print("APPLICATION_NUMERALS: ok=0 errors=1 warnings=0")
        print(f"文件不存在：{exc.filename}", file=sys.stderr)
        return 1
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("APPLICATION_NUMERALS: ok=0 errors=1 warnings=0")
        print(f"无法读取：{exc}", file=sys.stderr)
        return 1

    findings = check_register(
        register, schema=schema, figure_plan=plan, claims_text=claims, spec_text=spec
    )
    errors = sum(item.level == "ERROR" for item in findings)
    warnings = sum(item.level == "WARNING" for item in findings)
    ok = errors == 0
    print(f"APPLICATION_NUMERALS: ok={1 if ok else 0} errors={errors} warnings={warnings}")
    if not findings:
        print("PASS: 图↔权要↔说明书未见结构性缺口。机器通过不等于可提交。")
    else:
        for item in findings:
            print(f"{item.level}\t{item.code}\t{item.message}")
        print(f"汇总: {errors} 个错误, {warnings} 个警告。机器通过不等于可提交。")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
