#!/usr/bin/env python
"""中国发明/实用新型权利要求结构检查（编号、引用、过渡语、宣传措辞）。

用法：
  python tools/audit_claims.py 权利要求书.md
  python tools/audit_claims.py 权利要求书.md --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from stdio_utf8 import ensure_utf8_stdio
from lexicon import promo_pattern

CLAIM_START = re.compile(r"(?m)^\s*(\d+)\s*[.、．]\s*")
REFERENCE = re.compile(
    r"权利要求\s*(\d+(?:\s*(?:[-—~～至]|或|、|及|和|,)\s*\d+)*)"
)
TERM_INTRO = re.compile(r"(?:所述|该)([\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z0-9_-]{1,20})")
PLACEHOLDER = re.compile(r"\[(?:TO CONFIRM|待确认)[^\]]*\]", re.IGNORECASE)
INDEPENDENT_OPEN = re.compile(
    r"^一种[^，,；;。:\n]{1,80}(?:[，,；;])?(?:其特征在于|包括|包含|具有)"
)
PROMO = promo_pattern()
TERM_TAIL = re.compile(
    r"(?:与|和|及|或|通过|相对|沿|分别|均|仅|还|至少|大于|小于|等于|"
    r"设有|设于|设置(?:在|于|为|有)|固定(?:在|于|连接|设置)|连接(?:于|到|在|有)|"
    r"安装(?:在|于|有)|包括|具有|位于|用于|能够|可以|"
    r"可(?=相对|沿|在|滑动|转动|移动|拆卸|伸缩|往复)|布置(?:在|于|有)|"
    r"形成|为|是|呈|在|由|的|不|上设有|下设有|内设有|外设有|"
    r"连接$|固定$|安装$|设置$|布置$)"
)
TERM_LEFT_BOUNDARY = re.compile(
    r"(?:包括|包含|具有|设有|设置|所述|上述|前述|该|各|的|于|与|和|及|或|为|由|"
    r"若干|多个|至少一个|至少两个|一个|两个|三个|各个|\d+个|一种|计算|采集|"
    r"获取|生成|输出|确定|接收|提供|形成|配备|采用|使用|安装|连接|固定)$"
)


@dataclass
class Finding:
    level: str
    claim: Optional[int]
    code: str
    message: str


def split_claims(text: str) -> list[tuple[int, str]]:
    matches = list(CLAIM_START.finditer(text))
    claims: list[tuple[int, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        claims.append((int(match.group(1)), text[match.end() : end].strip()))
    return claims


def references(body: str) -> list[int]:
    result: list[int] = []
    for match in REFERENCE.finditer(body):
        # Parse the complete expression before considering alternatives; a
        # single-number alternative must not swallow "1或3" before 3 is read.
        for item in re.split(r"或|、|及|和|,", match.group(1)):
            bounds = re.split(r"\s*[-—~～至]\s*", item.strip())
            start = int(bounds[0])
            finish = int(bounds[-1])
            if finish < start:
                # Keep both numbers so malformed/reversed ranges are not
                # silently erased from the structural checks.
                result.extend((start, finish))
            else:
                result.extend(range(start, finish + 1))
    return sorted(set(result))


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", text)


def is_further_independent(compact: str) -> bool:
    """Recognize an explicit subject and structural opening, including products."""
    if compact.startswith("根据权利要求") or "根据权利要求" in compact[:20]:
        return False
    if re.match(r"一种(?:进一步|优选|上述|前述|根据|如上|所述|该)", compact):
        return False
    return bool(INDEPENDENT_OPEN.match(compact))


def _registered_aliases(register: Optional[dict[str, Any]]) -> dict[str, set[str]]:
    groups: list[set[str]] = []
    for key in ("parts", "features"):
        for item in (register or {}).get(key) or []:
            if not isinstance(item, dict):
                continue
            aliases = item.get("aliases") or []
            if isinstance(aliases, str):
                aliases = [aliases]
            names = {str(name).strip() for name in [item.get("name") or ""] + list(aliases) if str(name).strip()}
            if names:
                groups.append(names)
    result: dict[str, set[str]] = {}
    for name in set().union(*groups) if groups else set():
        owners = [group for group in groups if name in group]
        # A shared short name cannot merge two physical entities' aliases.
        result[name] = owners[0] if len(owners) == 1 else {name}
    return result


def _right_boundary(text: str) -> bool:
    return not text or not re.match(r"[\u4e00-\u9fffA-Za-z0-9_-]", text) or bool(TERM_TAIL.match(text))


def _antecedent_terms(tail: str, names: dict[str, set[str]]) -> list[str]:
    """Prefer a registered full term; never shorten to arbitrary shared stems."""
    for name in sorted(names, key=len, reverse=True):
        if tail.startswith(name) and _right_boundary(tail[len(name):]):
            return [name]
    # Without a register, use an explicit marker/punctuation or a recognizable
    # relation as the end of the noun phrase.  Ambiguity remains a warning.
    raw = re.split(r"[\s，,；;。.!！?？：:（()）]", tail, maxsplit=1)[0]
    candidates = [
        raw[:end] for end in range(len(raw), 1, -1)
        if _right_boundary(raw[end:])
        and not re.fullmatch(r"第[一二三四五六七八九十百零\d]+", raw[:end])
    ]
    return candidates


def _term_in_basis(basis: str, term: str) -> bool:
    for match in re.finditer(re.escape(term), basis):
        before = basis[:match.start()]
        left_ok = not before or not re.match(r"[\u4e00-\u9fffA-Za-z0-9_-]", before[-1]) or bool(TERM_LEFT_BOUNDARY.search(before))
        if left_ok and _right_boundary(basis[match.end():]):
            return True
    return False


def _reference_header_end(body: str) -> int:
    if not re.match(r"\s*(?:(?:根据|如)\s*)?权利要求\s*\d", body):
        return 0
    # The dependent-claim title is a reference to the protected subject, not
    # an introduced component.  This works for any product name, without a
    # fixed list such as 装置/设备/系统/方法.  Later clauses are still checked.
    ends = [match.start() for match in re.finditer(r"[，,；;。\n]|其特征在于", body)]
    return min(ends) if ends else len(body)


def audit(text: str, *, register: Optional[dict[str, Any]] = None) -> list[Finding]:
    claims = split_claims(text)
    findings: list[Finding] = []
    if not claims:
        return [Finding("ERROR", None, "NO_CLAIMS", "未识别到以“1.”形式起始的权利要求。")]

    numbers = [number for number, _ in claims]
    expected = list(range(1, len(claims) + 1))
    if numbers != expected:
        findings.append(
            Finding("ERROR", None, "NUMBER_SEQUENCE", f"编号应连续为{expected}，实际为{numbers}。")
        )

    claim_map: dict[int, str] = {}
    names = _registered_aliases(register)
    # Each entry is one actual alternative dependency path.  Combining all
    # earlier claims (or all alternatives) can manufacture antecedent basis.
    inherited_paths: dict[int, list[tuple[tuple[int, ...], str]]] = {}
    for number, body in claims:
        compact = normalize(body)
        claim_map[number] = compact
        refs = references(body)

        if not body:
            findings.append(Finding("ERROR", number, "EMPTY", "权利要求正文为空。"))
            continue
        if PLACEHOLDER.search(body):
            findings.append(
                Finding("ERROR", number, "PLACEHOLDER", "正式权利要求中仍含待确认标记。")
            )
        if number == 1 and refs:
            findings.append(
                Finding("ERROR", number, "INDEPENDENT_REFERENCE", "权利要求1不应引用其他权利要求。")
            )
        if number > 1 and not refs and not is_further_independent(compact):
            findings.append(
                Finding("WARNING", number, "NO_REFERENCE", "未检测到从属引用；确认其是否为独立权利要求。")
            )
        for ref in refs:
            if ref >= number:
                findings.append(
                    Finding("ERROR", number, "FORWARD_REFERENCE", f"引用了非在先权利要求{ref}。")
                )
            if ref not in claim_map:
                findings.append(
                    Finding("ERROR", number, "MISSING_REFERENCE", f"引用的权利要求{ref}不存在。")
                )

        paths: list[tuple[tuple[int, ...], str]] = []
        for ref in refs:
            if ref >= number or ref not in inherited_paths:
                continue
            for ancestors, basis in inherited_paths[ref]:
                paths.append(((ref,) + ancestors, basis + "\n" + claim_map[ref]))
        inherited_paths[number] = paths or [((), "")]

        if "其特征在于" not in compact:
            findings.append(
                Finding("WARNING", number, "TRANSITION", "未检测到“其特征在于”过渡语。")
            )
        if len(compact) < 25:
            findings.append(
                Finding("WARNING", number, "TOO_SHORT", "权利要求较短，确认是否完整限定技术方案。")
            )
        if PROMO.search(compact):
            findings.append(
                Finding("WARNING", number, "RESULT_LANGUAGE", "含结果或宣传性措辞，确认是否改为技术限定。")
            )

        skip_terms = {"方法", "装置", "设备", "系统", "步骤", "程序", "权利要求"}
        header_end = _reference_header_end(body)
        for match in re.finditer(
            r"所述(?:的)?(?!权利要求)([\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z0-9_-]{0,60})",
            body,
        ):
            if match.start() < header_end:
                continue
            captured_terms = [term for term in _antecedent_terms(match.group(1), names) if term not in skip_terms]
            if not captured_terms:
                continue
            captured = captured_terms[-1]
            before = normalize(body[: match.start()])
            candidates = set().union(*(names.get(term, {term}) for term in captured_terms))
            failed_paths = [
                path
                for path, basis in inherited_paths[number]
                if not any(_term_in_basis(basis, term) or _term_in_basis(before, term) for term in candidates)
            ]
            if failed_paths:
                detail = "；".join("→".join(map(str, path)) or "无引用" for path in failed_paths)
                findings.append(
                    Finding(
                        "WARNING",
                        number,
                        "SAID_ANTECEDENT",
                        f"「所述{captured}」在本项及实际引用路径（{detail}）中未见清晰的首次出现，请人工核实。",
                    )
                )
        for term in sorted(set(TERM_INTRO.findall(body))):
            if term in skip_terms:
                continue
            if compact.find(term) <= 4 and any(
                term not in basis for _path, basis in inherited_paths[number]
            ):
                findings.append(
                    Finding(
                        "WARNING",
                        number,
                        "ANTECEDENT_BASIS",
                        f"术语“{term}”可能缺少清晰的前置基础。",
                    )
                )

    return findings


def summarize(findings: list[Finding]) -> tuple[int, int]:
    errors = sum(item.level == "ERROR" for item in findings)
    warnings = sum(item.level == "WARNING" for item in findings)
    return errors, warnings


def main() -> int:
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("claims", type=Path, help="UTF-8 权利要求书")
    parser.add_argument("--register", type=Path, help="可选件号登记表 JSON/YAML，优先使用已核定部件名和别名")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    path = args.claims.expanduser().resolve()
    if not path.is_file():
        print("APPLICATION_CLAIMS: ok=0 errors=1 warnings=0")
        print(f"文件不存在：{path}", file=sys.stderr)
        return 1

    text = path.read_text(encoding="utf-8")
    register = None
    if args.register:
        from check_numeral_register import _load_mapping
        try:
            register = _load_mapping(args.register.expanduser().resolve())
        except (OSError, ValueError) as exc:
            print("APPLICATION_CLAIMS: ok=0 errors=1 warnings=0")
            print(f"登记表无法读取：{exc}", file=sys.stderr)
            return 1
    findings = audit(text, register=register)
    errors, warnings = summarize(findings)
    ok = errors == 0
    print(f"APPLICATION_CLAIMS: ok={1 if ok else 0} errors={errors} warnings={warnings}")
    if args.json:
        print(json.dumps([asdict(item) for item in findings], ensure_ascii=False, indent=2))
    elif not findings:
        print("PASS: 未发现结构性问题。机器通过不等于可提交。")
    else:
        for item in findings:
            location = f"权利要求{item.claim}" if item.claim else "整体"
            print(f"{item.level}\t{location}\t{item.code}\t{item.message}")
        print(f"汇总: {errors} 个错误, {warnings} 个警告。机器通过不等于可提交。")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
