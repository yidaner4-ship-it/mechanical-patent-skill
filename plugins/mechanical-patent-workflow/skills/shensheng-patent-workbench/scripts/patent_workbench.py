#!/usr/bin/env python3
"""Deterministic routing, case scaffolding, diagnostics, and evidence checks."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import date, datetime, timezone
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import sys
import unicodedata
from typing import Any

from patseek_keychain import KeychainError, key_exists

TASK_TYPES = {
    "novelty": {"label": "申请前查新", "engine": "patseek", "official": "关键日期/重点文献"},
    "oa": {"label": "OA", "engine": None, "official": "当前权项/OA/期限/审查档案"},
    "fto": {"label": "FTO", "engine": "patseek", "official": "有效权项/状态/期限/同族"},
    "public_comment": {"label": "公众意见", "engine": "patseek", "official": "当前权项/待审状态/提交窗口"},
    "invalidity": {"label": "无效", "engine": "patseek", "official": "权项版本/法律状态/在先公开"},
    "competitor": {"label": "竞品调研", "engine": "patseek", "official": "重点权利/统计抽核"},
    "download": {"label": "已知公开号下载", "engine": "patent-search", "official": "按需"},
}
BASE_JURISDICTIONS = {"CN", "US", "EP", "JP", "KR"}
# EPO member-state list checked against the EPO member-state page on 2026-08-27.
# FTO accepts the explicit EP-CC form, but CC must still be an actual EPC state;
# EP itself is never treated as the country in which the product is implemented.
EPC_STATES = {
    "AL", "AT", "BE", "BG", "CH", "CY", "CZ", "DE", "DK", "EE",
    "ES", "FI", "FR", "GB", "GR", "HR", "HU", "IE", "IS", "IT",
    "LI", "LT", "LU", "LV", "MC", "MD", "ME", "MK", "MT", "NL",
    "NO", "PL", "PT", "RO", "RS", "SE", "SI", "SK", "SM", "TR",
}
PHASES = ["intake", "search", "retrieval", "official_verify", "analysis", "reporting", "complete"]
SEARCH_ENGINES = {"patseek", "patent-search"}
SEARCH_STATUSES = {"planned", "success", "partial", "failed", "timeout", "blocked", "uncertain"}
EVIDENCE_MODES = {
    "text_explicit", "figure_explicit", "text_figure_combined",
    "implicit_with_reason", "model_inference_only",
}
COVERAGE_VALUES = {"covered", "partial", "missing", "uncertain"}
CASE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
EP_TARGET_RE = re.compile(r"^EP-([A-Z]{2})$")
QUERY_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def skill_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def normalize_scope(task_type: str, jurisdictions: list[str]) -> tuple[list[str], list[str]]:
    raw = []
    for item in jurisdictions:
        value = item.strip().upper()
        if value and value not in raw:
            raw.append(value)
    if not raw:
        raw = ["CN"]

    if task_type != "fto":
        invalid = sorted(set(raw) - BASE_JURISDICTIONS)
        if invalid:
            raise ValueError(f"暂不支持的法域: {', '.join(invalid)}")
        return raw, raw

    rights_countries: list[str] = []
    search_authorities: list[str] = []
    bare_ep = False
    for item in raw:
        if item == "EP":
            bare_ep = True
            continue
        match = EP_TARGET_RE.fullmatch(item)
        if match:
            country = match.group(1)
            if country not in EPC_STATES:
                raise ValueError(f"EP-{country} 不是当前支持的 EPC 实施国代码")
            if country not in rights_countries:
                rights_countries.append(country)
            if country not in search_authorities:
                search_authorities.append(country)
            if "EP" not in search_authorities:
                search_authorities.append("EP")
            continue
        if item in EPC_STATES:
            if item not in rights_countries:
                rights_countries.append(item)
            if item not in search_authorities:
                search_authorities.append(item)
            if "EP" not in search_authorities:
                search_authorities.append("EP")
            continue
        if item in {"CN", "US", "JP", "KR"}:
            if item not in rights_countries:
                rights_countries.append(item)
            if item not in search_authorities:
                search_authorities.append(item)
            continue
        raise ValueError(
            f"FTO 暂不支持的权利国家: {item}；欧洲实施国请写 DE、FR 等国家代码，或 EP-DE 形式。"
        )
    if bare_ep:
        raise ValueError("FTO 不能只写 EP；请给出实际实施国，例如 DE、FR 或 EP-DE。")
    if not rights_countries:
        raise ValueError("FTO 至少需要一个实际权利国家。")
    return rights_countries, search_authorities


def route_for(task_type: str, rights_countries: list[str], search_authorities: list[str]) -> dict[str, Any]:
    task = TASK_TYPES[task_type]
    markets: list[str] = []
    if "CN" in search_authorities:
        markets.append("cn")
    if any(item != "CN" for item in search_authorities):
        markets.append("world")
    route = {
        "task_type": task_type,
        "task_label": task["label"],
        "active_search_engine": task["engine"],
        "search_markets": markets,
        "rights_countries": rights_countries,
        "search_authorities": search_authorities,
        "retrieval_engine": "patent-search" if task_type != "download" else "patent-search-only",
        "official_verification": task["official"],
        "fallback_approved": False,
    }
    if task_type == "oa":
        route["analysis_mode"] = "case-first"
        route["supplemental_search_engine"] = "patseek"
    return route


def evidence_skeleton(case: dict[str, Any]) -> dict[str, Any]:
    immutable_case = {
        key: case[key]
        for key in (
            "case_id", "case_type", "subtype", "title", "decision_question",
            "confidentiality", "rights_jurisdictions", "search_authorities",
            "search_markets", "critical_date", "data_cutoff", "depth", "deliverables",
        )
    }
    return {
        "schema_version": "1.0",
        "case": immutable_case,
        "case_file": "../case.json",
        "targets": [],
        "features": [],
        "search_runs": [],
        "documents": [],
        "evidence_units": [],
        "feature_maps": [],
        "legal_status_checks": [],
        "oa_objections": [],
        "limitations": [],
        "audit_events": [],
    }


def _safe_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = -1
    try:
        fd = os.open(temp, flags, 0o600)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = -1
            handle.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        parent_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            os.unlink(temp)
        except FileNotFoundError:
            pass


def init_case(args: argparse.Namespace) -> int:
    if not CASE_ID_RE.fullmatch(args.case_id):
        raise ValueError("case-id 只能含字母、数字、点、下划线和连字符，最长 64 字符。")
    rights_countries, search_authorities = normalize_scope(args.task_type, args.jurisdictions)
    case_root = args.output_dir.expanduser().resolve() / args.case_id
    if case_root.exists():
        raise FileExistsError(f"案件目录已存在，拒绝覆盖: {case_root}")
    for name in ["inputs", "evidence", "originals", "figures", "working", "working/templates", "deliverables", "logs"]:
        path = case_root / name
        path.mkdir(parents=True, exist_ok=True)
        os.chmod(path, 0o700)
    os.chmod(case_root, 0o700)

    route = route_for(args.task_type, rights_countries, search_authorities)
    now = datetime.now(timezone.utc).isoformat()
    case = {
        "case_id": args.case_id,
        "case_type": args.task_type,
        "subtype": args.subtype or None,
        "title": args.title,
        "decision_question": args.decision_question or "",
        "confidentiality": "external-search-approved-no-store",
        "rights_jurisdictions": rights_countries,
        "search_authorities": search_authorities,
        "search_markets": route["search_markets"],
        "critical_date": args.critical_date or None,
        "data_cutoff": args.data_cutoff or date.today().isoformat(),
        "depth": "full" if args.task_type not in {"download", "competitor"} else "task-appropriate",
        "deliverables": ["xlsx", "docx", "pdf"],
        "brand": "申晟知产 / SHENSHENG",
        "created_at": now,
        "status": "intake",
        "route_lock": {
            "active_phase": "intake",
            "active_search_engine": route["active_search_engine"],
            "fallback_approved": False,
            "approved_fallback_engine": None,
            "round_engines": {},
            "queries": [],
            "completed_query_hashes": [],
            "query_hmac_key": secrets.token_hex(32),
        },
    }
    _safe_write_json(case_root / "case.json", case)
    _safe_write_json(case_root / "evidence" / "evidence.json", evidence_skeleton(case))
    _safe_write_json(case_root / "route.json", route)

    templates = skill_dir() / "assets" / "templates"
    if templates.is_dir():
        for source in templates.iterdir():
            if source.is_file() and source.suffix.lower() in {".xlsx", ".docx", ".pdf"}:
                target = case_root / "working" / "templates" / source.name
                shutil.copy2(source, target)
                os.chmod(target, 0o600)
    print(json.dumps({"ok": True, "case_dir": str(case_root), "route": route}, ensure_ascii=False, indent=2))
    return 0


def _rows(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = data.get(key)
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _index_ids(rows: list[dict[str, Any]], key: str, label: str, errors: list[str]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for position, row in enumerate(rows, start=1):
        value = row.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{label} 第 {position} 项缺少 {key}")
            continue
        if value in result:
            errors.append(f"{label} 的 {key} 重复: {value}")
            continue
        result[value] = row
    return result


def _filled(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return True


def _country_code(value: Any) -> str:
    return str(value or "").strip().upper()


def _document_supports_right(document: dict[str, Any] | None, right_country: str) -> bool:
    """Return whether this exact document can evidence a right in the country.

    A national document can only support its own jurisdiction.  An EP family
    member may support an EPC state, but the legal-status row must separately
    identify the national right instance and its official register evidence.
    """
    if not isinstance(document, dict):
        return False
    jurisdiction = _country_code(document.get("jurisdiction"))
    country = _country_code(right_country)
    return jurisdiction == country or (jurisdiction == "EP" and country in EPC_STATES)


def _claim_key(value: Any) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    return " ".join(normalized.split()).casefold()


def _active_claim_keys(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {_claim_key(item) for item in value if _filled(item)}


def _read_protected_text(path: Path, *, max_bytes: int = 1024 * 1024) -> str:
    query_path = path.expanduser()
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(query_path, flags)
    except OSError as exc:
        raise ValueError(f"无法安全打开查询文件 {query_path}: {exc}") from exc
    try:
        info = os.fstat(fd)
        mode = stat.S_IMODE(info.st_mode)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError(f"查询文件不是普通文件: {query_path}")
        if info.st_uid != os.getuid():
            raise ValueError(f"查询文件不属于当前用户: {query_path}")
        if mode & 0o077:
            raise ValueError(f"查询文件权限过宽（{mode:04o}）；请先 chmod 600 {query_path}")
        if info.st_size > max_bytes:
            raise ValueError(f"查询文件超过 {max_bytes} 字节上限")
        with os.fdopen(fd, "r", encoding="utf-8") as handle:
            fd = -1
            return handle.read(max_bytes + 1)
    finally:
        if fd >= 0:
            os.close(fd)


def _load_case_state(evidence_path: Path, data: dict[str, Any], errors: list[str]) -> dict[str, Any] | None:
    ref = data.get("case_file")
    if not isinstance(ref, str) or not ref.strip():
        return None
    candidate = (evidence_path.parent / ref).resolve()
    try:
        candidate.relative_to(evidence_path.parent.parent.resolve())
    except ValueError:
        errors.append("case_file 越出案件目录")
        return None
    if not candidate.is_file():
        errors.append(f"case_file 不存在: {candidate}")
        return None
    try:
        value = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"无法读取权威 case.json: {exc}")
        return None
    if not isinstance(value, dict):
        errors.append("权威 case.json 必须是对象")
        return None
    return value


def validate_evidence(path: Path, stage: str = "final") -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("证据文件根节点必须是对象")
    errors: list[str] = []
    required_lists = [
        "targets", "features", "search_runs", "documents", "evidence_units",
        "feature_maps", "legal_status_checks", "oa_objections", "limitations", "audit_events",
    ]
    if data.get("schema_version") != "1.0":
        errors.append("schema_version 必须为 1.0")
    case = data.get("case")
    if not isinstance(case, dict):
        errors.append("缺少 case 对象")
        case = {}
    for key in required_lists:
        if not isinstance(data.get(key), list):
            errors.append(f"{key} 必须是数组")
        elif any(not isinstance(row, dict) for row in data[key]):
            errors.append(f"{key} 的每一项都必须是对象")

    targets = _rows(data, "targets")
    features = _rows(data, "features")
    search_runs = _rows(data, "search_runs")
    documents = _rows(data, "documents")
    evidence_units = _rows(data, "evidence_units")
    feature_maps = _rows(data, "feature_maps")
    legal_checks = _rows(data, "legal_status_checks")
    oa_objections = _rows(data, "oa_objections")
    limitations = _rows(data, "limitations")
    audit_events = _rows(data, "audit_events")

    target_by_id = _index_ids(targets, "target_id", "targets", errors)
    feature_by_id = _index_ids(features, "feature_id", "features", errors)
    run_by_id = _index_ids(search_runs, "run_id", "search_runs", errors)
    doc_by_id = _index_ids(documents, "doc_id", "documents", errors)
    evidence_by_id = _index_ids(evidence_units, "evidence_id", "evidence_units", errors)
    map_by_id = _index_ids(feature_maps, "map_id", "feature_maps", errors)
    status_by_id = _index_ids(legal_checks, "status_id", "legal_status_checks", errors)
    right_instance_by_id = _index_ids(
        legal_checks, "right_instance_id", "legal_status_checks", errors
    ) if legal_checks else {}
    objection_by_id = _index_ids(oa_objections, "objection_id", "oa_objections", errors)
    _index_ids(limitations, "limitation_id", "limitations", errors)
    _index_ids(audit_events, "event_id", "audit_events", errors)
    del run_by_id, map_by_id, status_by_id, objection_by_id

    for row in features:
        feature_id = row.get("feature_id", "?")
        if row.get("target_id") not in target_by_id:
            errors.append(f"特征 {feature_id} 引用了不存在的 target_id")
        parent = row.get("parent_feature_id")
        if parent and parent not in feature_by_id:
            errors.append(f"特征 {feature_id} 引用了不存在的 parent_feature_id={parent}")

    for row in search_runs:
        run_id = row.get("run_id", "?")
        status = row.get("status")
        if status not in SEARCH_STATUSES:
            errors.append(f"检索 {run_id} 的 status 非法: {status}")
        count = row.get("result_count")
        if status in {"failed", "timeout", "blocked", "uncertain"} and count is not None:
            errors.append(f"检索 {run_id} 失败/超时/阻断/不确定时 result_count 必须为 null")
        if status in {"success", "partial"} and (not isinstance(count, int) or count < 0):
            errors.append(f"检索 {run_id} 成功/部分成功时 result_count 必须是非负整数")
        if status != "planned" and not _filled(row.get("query_hash")):
            errors.append(f"检索 {run_id} 已执行但缺少 query_hash")
        credits = row.get("credits_charged")
        if credits is not None and (not isinstance(credits, (int, float)) or credits < 0):
            errors.append(f"检索 {run_id} 的 credits_charged 非法")

    for row in evidence_units:
        evidence_id = row.get("evidence_id", "?")
        feature_id = row.get("feature_id")
        doc_id = row.get("doc_id")
        if feature_id not in feature_by_id:
            errors.append(f"证据 {evidence_id} 引用了不存在的 feature_id")
        if doc_id not in doc_by_id:
            errors.append(f"证据 {evidence_id} 引用了不存在的 doc_id")
        mode = row.get("evidence_mode")
        if mode not in EVIDENCE_MODES:
            errors.append(f"证据 {evidence_id} 的 evidence_mode 非法: {mode}")
        disclosure = row.get("disclosure")
        if disclosure not in {"explicit", "inferred", "missing"}:
            errors.append(f"证据 {evidence_id} 的 disclosure 非法: {disclosure}")
        if mode == "model_inference_only" and disclosure == "explicit":
            errors.append(f"证据 {evidence_id} 把模型推断标成明确披露")
        if stage == "final" and disclosure != "missing":
            if not _filled(row.get("locator")):
                errors.append(f"证据 {evidence_id} 缺少权项/段落/附图定位")
            if not _filled(row.get("excerpt_or_paraphrase")):
                errors.append(f"证据 {evidence_id} 缺少短摘录或可复核释义")

    for row in feature_maps:
        map_id = row.get("map_id", "?")
        target_id = row.get("target_id")
        doc_id = row.get("doc_id")
        feature_id = row.get("feature_id")
        if target_id not in target_by_id:
            errors.append(f"映射 {map_id} 引用了不存在的 target_id={target_id}")
        if doc_id not in doc_by_id:
            errors.append(f"映射 {map_id} 引用了不存在的 doc_id={doc_id}")
        if feature_id not in feature_by_id:
            errors.append(f"映射 {map_id} 引用了不存在的 feature_id={feature_id}")
        elif target_id in target_by_id and feature_by_id[feature_id].get("target_id") != target_id:
            errors.append(f"映射 {map_id} 的 target_id 与特征所属 target 不一致")
        coverage = row.get("coverage")
        if coverage not in COVERAGE_VALUES:
            errors.append(f"映射 {map_id} 的 coverage 非法: {coverage}")
        linked = row.get("evidence_ids") or []
        if not isinstance(linked, list):
            errors.append(f"映射 {map_id} 的 evidence_ids 必须是数组")
            linked = []
        if coverage in {"covered", "partial"} and not linked:
            errors.append(f"映射 {map_id} 标为 {coverage} 但没有证据")
        if coverage == "missing" and not _filled(row.get("missing_reason")):
            errors.append(f"映射 {map_id} 标为 missing 但没有 missing_reason")
        for evidence_id in linked:
            evidence = evidence_by_id.get(evidence_id)
            if evidence is None:
                errors.append(f"映射 {map_id} 引用了不存在的 evidence_id={evidence_id}")
                continue
            if evidence.get("doc_id") != doc_id or evidence.get("feature_id") != feature_id:
                errors.append(f"映射 {map_id} 的证据 {evidence_id} 与 doc_id/feature_id 不一致")

    for row in legal_checks:
        status_id = row.get("status_id", "?")
        document = doc_by_id.get(row.get("doc_id"))
        if document is None:
            errors.append(f"状态核验 {status_id} 引用了不存在的 doc_id")
        country = _country_code(row.get("right_country"))
        if country == "EP":
            errors.append(f"状态核验 {status_id} 不能把 EP 当作实际权利国家")
        if country and document is not None and not _document_supports_right(document, country):
            errors.append(
                f"状态核验 {status_id} 的文献法域={_country_code(document.get('jurisdiction'))} "
                f"不能证明 {country} 权利实例"
            )

    case_type = case.get("case_type")
    if case_type not in TASK_TYPES:
        errors.append(f"case.case_type 非法: {case_type}")

    case_state = _load_case_state(path, data, errors)
    if case_state is not None:
        for key in ("case_id", "case_type", "rights_jurisdictions", "data_cutoff"):
            if case.get(key) != case_state.get(key):
                errors.append(f"evidence.case.{key} 与权威 case.json 不一致")

    if stage == "final":
        if not targets:
            errors.append("final 阶段至少需要一个 target")
        feature_required = {"novelty", "fto", "public_comment", "invalidity"}
        search_required = {"novelty", "fto", "public_comment", "invalidity", "competitor"}
        if case_type in feature_required and not features:
            errors.append(f"{case_type} final 阶段至少需要一个必要技术特征")
        if case_type in search_required:
            if not search_runs:
                errors.append(f"{case_type} final 阶段至少需要一条检索记录")
            elif not any(row.get("status") in {"success", "partial"} for row in search_runs):
                errors.append(f"{case_type} final 阶段至少需要一条 success/partial 检索记录")
        if any((row.get("result_count") or 0) > 0 for row in search_runs) and not documents:
            errors.append("检索有正命中但 documents 为空")

        if case_state is not None and search_runs:
            lock = case_state.get("route_lock") if isinstance(case_state.get("route_lock"), dict) else {}
            query_records = lock.get("queries") if isinstance(lock.get("queries"), list) else []
            query_by_hash = {
                row.get("query_hash"): row
                for row in query_records
                if isinstance(row, dict) and row.get("query_hash")
            }
            for row in search_runs:
                if row.get("status") == "planned":
                    errors.append(f"final 阶段检索 {row.get('run_id', '?')} 仍为 planned")
                    continue
                locked = query_by_hash.get(row.get("query_hash"))
                if not locked:
                    errors.append(f"检索 {row.get('run_id', '?')} 未经 route_lock 预留/完成")
                    continue
                run_id = row.get("run_id", "?")
                for field in (
                    "status", "engine", "paid_command", "market", "round_id",
                    "result_count", "credits_charged",
                ):
                    if locked.get(field) != row.get(field):
                        errors.append(f"检索 {run_id} 的 {field} 与 route_lock 不一致")
            run_hashes = {
                row.get("query_hash")
                for row in search_runs
                if _filled(row.get("query_hash"))
            }
            for locked in query_records:
                if not isinstance(locked, dict):
                    errors.append("route_lock.queries 含非对象记录")
                    continue
                query_hash = locked.get("query_hash")
                if locked.get("status") in {"planned", "running"}:
                    errors.append(f"final 阶段 route_lock 查询 {query_hash or '?'} 尚未完成")
                if query_hash not in run_hashes:
                    errors.append(f"route_lock 查询 {query_hash or '?'} 未写入 search_runs")

        if case_type == "fto":
            if not documents or not evidence_units or not feature_maps:
                errors.append("FTO final 阶段必须有候选文献、逐特征证据和特征映射")
            rights = [_country_code(item) for item in case.get("rights_jurisdictions", [])]
            if not rights:
                errors.append("FTO 缺少实际权利国家")
            if "EP" in rights:
                errors.append("FTO rights_jurisdictions 不能只写 EP，必须落实到实施国")
            necessary_features = [row for row in features if row.get("necessary") is True]
            if not necessary_features:
                errors.append("FTO final 阶段至少需要一个 necessary=true 的产品特征")
            checked_countries: set[str] = set()
            for row in legal_checks:
                status_id = row.get("status_id", "?")
                country = _country_code(row.get("right_country"))
                document = doc_by_id.get(row.get("doc_id"))
                for field in (
                    "right_instance_id", "national_right_identifier", "office",
                    "official_register_url", "checked_at", "application_or_patent_status",
                    "operative_claim_version", "active_claims",
                ):
                    if not _filled(row.get(field)):
                        errors.append(f"FTO 状态核验 {status_id} 缺少 {field}")
                if country not in rights:
                    errors.append(f"FTO 状态核验 {status_id} 的 right_country={country or '?'} 不在案件实施国")
                if not isinstance(row.get("active_claims"), list):
                    errors.append(f"FTO 状态核验 {status_id} 的 active_claims 必须是逐项列出的数组")
                if document is not None and _document_supports_right(document, country):
                    checked_countries.add(country)
                    if _country_code(document.get("jurisdiction")) == "EP" and not _filled(
                        row.get("national_right_identifier")
                    ):
                        errors.append(f"FTO 状态核验 {status_id} 的 EP 文献缺少目标国权利标识")
            for country in rights:
                if country not in checked_countries:
                    errors.append(f"FTO 缺少与 {country} 法域相容的官方法律状态/有效权项核验")

            for row in feature_maps:
                map_id = row.get("map_id", "?")
                right_instance_id = row.get("right_instance_id")
                country = _country_code(row.get("right_country"))
                operative_claim = row.get("operative_claim")
                if not _filled(right_instance_id):
                    errors.append(f"FTO 映射 {map_id} 缺少 right_instance_id")
                if country not in rights:
                    errors.append(f"FTO 映射 {map_id} 的 right_country={country or '?'} 不在案件实施国")
                if not _filled(operative_claim):
                    errors.append(f"FTO 映射 {map_id} 缺少 operative_claim")
                instance = right_instance_by_id.get(right_instance_id)
                if instance is None:
                    errors.append(f"FTO 映射 {map_id} 引用了不存在的 right_instance_id={right_instance_id}")
                else:
                    if instance.get("doc_id") != row.get("doc_id"):
                        errors.append(f"FTO 映射 {map_id} 的 doc_id 与权利实例不一致")
                    if _country_code(instance.get("right_country")) != country:
                        errors.append(f"FTO 映射 {map_id} 的 right_country 与权利实例不一致")
                    if _claim_key(operative_claim) not in _active_claim_keys(instance.get("active_claims")):
                        errors.append(f"FTO 映射 {map_id} 的 operative_claim 不在该国当前有效权项中")
                if row.get("coverage") not in {"covered", "partial"}:
                    continue
                linked = [evidence_by_id.get(item) for item in (row.get("evidence_ids") or [])]
                linked = [item for item in linked if item]
                for evidence in linked:
                    if _claim_key(evidence.get("claim_no")) != _claim_key(operative_claim):
                        errors.append(
                            f"FTO 映射 {map_id} 的证据 {evidence.get('evidence_id', '?')} "
                            "未绑定同一 operative_claim"
                        )
                if linked and all(item.get("evidence_mode") == "model_inference_only" for item in linked):
                    errors.append(f"FTO 映射 {map_id} 仅由模型推断支持，不能升级风险")

            mapped_instance_features = {
                (str(row.get("right_instance_id") or ""), str(row.get("feature_id") or ""))
                for row in feature_maps
                if _filled(row.get("right_instance_id")) and _filled(row.get("feature_id"))
            }
            for instance_id, instance in right_instance_by_id.items():
                country = _country_code(instance.get("right_country"))
                if country not in rights:
                    continue
                for feature in necessary_features:
                    feature_id = str(feature.get("feature_id") or "")
                    if (instance_id, feature_id) not in mapped_instance_features:
                        errors.append(
                            f"FTO 权利实例 {instance_id}（{country}）缺少必要特征 {feature_id} 的映射；"
                            "即使未覆盖也必须写 coverage=missing 及理由"
                        )

        if case_type == "oa":
            if not oa_objections:
                errors.append("OA final 阶段至少需要一个审查意见点")
            for row in oa_objections:
                objection_id = row.get("objection_id", "?")
                for field in ("office", "oa_date", "deadline", "legal_basis", "affected_claims", "examiner_locator", "recommended_action"):
                    if not _filled(row.get(field)):
                        errors.append(f"OA 意见 {objection_id} 缺少 {field}")
                if _filled(row.get("proposed_amendment")):
                    if not _filled(row.get("support_locator")):
                        errors.append(f"OA 修改 {objection_id} 缺少原申请 support_locator")
                    if not _filled(row.get("added_matter_check")):
                        errors.append(f"OA 修改 {objection_id} 缺少 added_matter_check")

        if case_type in {"public_comment", "invalidity"}:
            if not documents or not evidence_units:
                errors.append(f"{case_type} final 阶段必须有候选文献和证据定位")
            for row in documents:
                if not _filled(row.get("publication_date")):
                    errors.append(f"文献 {row.get('doc_id', '?')} 缺少公开日")
            for row in evidence_units:
                if row.get("date_eligible") is not True:
                    errors.append(f"证据 {row.get('evidence_id', '?')} 未确认关键日前适格")
            if case_type == "public_comment" and not legal_checks:
                errors.append("公众意见 final 阶段缺少待审状态/程序窗口官方核验")

        if case_type == "competitor":
            categories = {str(row.get("category") or "").strip().lower() for row in limitations}
            for required in {"family_deduplication", "applicant_normalization", "truncation", "denominator"}:
                if required not in categories:
                    errors.append(f"竞品统计缺少口径披露 limitation.category={required}")

        if case_type == "download":
            if not documents:
                errors.append("下载任务 final 阶段至少需要一个 documents 记录")
            for row in documents:
                if not (_filled(row.get("pdf_path")) or _filled(row.get("docx_path"))):
                    errors.append(f"下载文献 {row.get('doc_id', '?')} 没有 PDF/Word 路径")

        if case_type == "novelty":
            necessary = {row.get("feature_id") for row in features if row.get("necessary") is True}
            for row in feature_maps:
                if row.get("single_document_complete") is not True:
                    continue
                doc_id = row.get("doc_id")
                covered = {
                    item.get("feature_id")
                    for item in feature_maps
                    if item.get("doc_id") == doc_id and item.get("coverage") == "covered"
                }
                if necessary and not necessary.issubset(covered):
                    errors.append(f"文献 {doc_id} 标为单篇完整披露，但未覆盖全部必要特征")

    result = {"ok": not errors, "stage": stage, "error_count": len(errors), "errors": errors}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


def _case_paths(case_dir: Path) -> tuple[Path, Path]:
    root = case_dir.expanduser().resolve()
    case_path = root / "case.json"
    if not case_path.is_file():
        raise FileNotFoundError(f"未找到案件 case.json: {case_path}")
    return root, case_path


@contextmanager
def _locked_case(case_dir: Path):
    root, case_path = _case_paths(case_dir)
    lock_path = root / ".workbench.lock"
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(lock_path, flags, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise ValueError("案件锁文件类型或所有者不可信")
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "r+") as handle:
            fd = -1
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            case = json.loads(case_path.read_text(encoding="utf-8"))
            if not isinstance(case, dict):
                raise ValueError("case.json 根节点必须是对象")
            yield case, case_path
            _safe_write_json(case_path, case)
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except Exception:
        if fd >= 0:
            os.close(fd)
        raise


def _execution_lock_path(case_root: Path, query_hash: str) -> Path:
    if not QUERY_HASH_RE.fullmatch(query_hash):
        raise ValueError("query_hash 必须是 64 位小写十六进制摘要")
    return case_root / f".patseek-exec-{query_hash}.lock"


def _execution_in_progress(case_root: Path, query_hash: str) -> bool:
    """Probe the per-query lock without waiting; the wrapper holds it for the API call."""
    path = _execution_lock_path(case_root, query_hash)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise ValueError("PatSeek 执行锁文件类型或所有者不可信")
        os.fchmod(fd, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


def _audit(case: dict[str, Any], action: str, details: dict[str, Any]) -> None:
    events = case.setdefault("route_audit", [])
    events.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "details": details,
    })


def transition_phase(args: argparse.Namespace) -> int:
    with _locked_case(args.case_dir) as (case, _):
        lock = case.get("route_lock")
        if not isinstance(lock, dict):
            raise ValueError("case.json 缺少 route_lock")
        current = lock.get("active_phase", "intake")
        if current not in PHASES or args.phase not in PHASES:
            raise ValueError("非法案件阶段")
        if PHASES.index(args.phase) < PHASES.index(current):
            raise ValueError(f"拒绝从 {current} 回退到 {args.phase}")
        engine = args.engine
        if args.phase == "search":
            if engine is None:
                engine = lock.get("active_search_engine")
            if engine not in SEARCH_ENGINES:
                raise ValueError("进入 search 阶段必须指定 patseek 或 patent-search")
            current_engine = lock.get("active_search_engine")
            if current_engine and engine != current_engine:
                approved = lock.get("fallback_approved") and lock.get("approved_fallback_engine") == engine
                if not approved:
                    raise ValueError(f"引擎从 {current_engine} 切换到 {engine} 前必须明确 approve-fallback")
            lock["active_search_engine"] = engine
        elif args.phase != "intake":
            lock["active_search_engine"] = None
        lock["active_phase"] = args.phase
        case["status"] = args.phase
        _audit(case, "transition_phase", {"from": current, "to": args.phase, "engine": engine})
    print(json.dumps({"ok": True, "phase": args.phase, "engine": engine}, ensure_ascii=False, indent=2))
    return 0


def approve_fallback(args: argparse.Namespace) -> int:
    if args.engine not in SEARCH_ENGINES:
        raise ValueError("fallback engine 必须是 patseek 或 patent-search")
    if not args.reason.strip():
        raise ValueError("必须记录用户批准回退的原因")
    with _locked_case(args.case_dir) as (case, _):
        lock = case.get("route_lock")
        if not isinstance(lock, dict):
            raise ValueError("case.json 缺少 route_lock")
        if lock.get("active_search_engine") == args.engine:
            raise ValueError("回退引擎与当前引擎相同")
        lock["fallback_approved"] = True
        lock["approved_fallback_engine"] = args.engine
        _audit(case, "approve_fallback", {"engine": args.engine, "reason": args.reason})
    print(json.dumps({"ok": True, "approved_fallback_engine": args.engine}, ensure_ascii=False, indent=2))
    return 0


def _read_query(args: argparse.Namespace) -> str:
    if args.query_file:
        query = _read_protected_text(args.query_file)
    else:
        if sys.stdin.isatty():
            raise ValueError("请通过标准输入传入检索式，或使用 --query-file；不要把未公开技术写进 argv。")
        query = sys.stdin.read(1024 * 1024 + 1)
    if len(query.encode("utf-8")) > 1024 * 1024:
        raise ValueError("检索式超过 1 MiB 上限")
    query = unicodedata.normalize("NFKC", query)
    query = " ".join(query.split()).casefold()
    if not query:
        raise ValueError("检索式为空")
    return query


def _paid_execution_spec(args: argparse.Namespace) -> tuple[int | None, str | None]:
    """Normalize result-depth options that must be bound to a paid reservation."""
    if args.engine != "patseek":
        if args.page_size is not None or args.no_enrichment:
            raise ValueError("--page-size/--no-enrichment 只适用于 PatSeek 预留")
        return None, None
    if args.paid_command == "bool":
        page_size = 20 if args.page_size is None else args.page_size
        if not 1 <= page_size <= 50:
            raise ValueError("PatSeek bool 的 page-size 必须在 1-50")
        if args.no_enrichment:
            raise ValueError("--no-enrichment 只适用于 PatSeek patent")
        return page_size, None
    if args.page_size is not None:
        raise ValueError("--page-size 只适用于 PatSeek bool")
    if args.paid_command == "patent":
        return None, "no-enrichment" if args.no_enrichment else "enriched"
    if args.no_enrichment:
        raise ValueError("--no-enrichment 只适用于 PatSeek patent")
    return None, None


def _query_hash(
    case: dict[str, Any],
    args: argparse.Namespace,
    query: str,
    page_size: int | None,
    enrichment_mode: str | None,
) -> str:
    lock = case.get("route_lock")
    if not isinstance(lock, dict) or not _filled(lock.get("query_hmac_key")):
        raise ValueError("case.json 缺少 query_hmac_key；请重新初始化或迁移案件")
    payload = {
        "case_id": case.get("case_id"),
        "case_type": case.get("case_type"),
        "engine": args.engine,
        "paid_command": args.paid_command or "",
        "market": args.market.lower(),
        "page": args.page,
        "page_size": page_size,
        "enrichment_mode": enrichment_mode,
        "purpose": args.purpose.strip(),
        "jurisdiction_filter": sorted(item.upper() for item in (args.jurisdiction_filter or [])),
        "date_filter": args.date_filter or "",
        "query": query,
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hmac.new(
        bytes.fromhex(lock["query_hmac_key"]),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def reserve_query(args: argparse.Namespace) -> int:
    if args.page < 1:
        raise ValueError("page 必须从 1 开始")
    if args.engine == "patseek":
        if args.paid_command not in {"bool", "semantic", "patent"}:
            raise ValueError("PatSeek 预留必须指定 --paid-command bool|semantic|patent")
        if args.paid_command == "semantic" and (args.market != "cn" or args.page != 1):
            raise ValueError("PatSeek semantic 固定使用 --market cn 且 page=1")
        if args.paid_command == "patent" and args.page != 1:
            raise ValueError("PatSeek patent 详情调用的 page 必须为 1")
    elif args.paid_command is not None:
        raise ValueError("--paid-command 只适用于 patseek 引擎")
    if args.retry_uncertain and not _filled(args.reconciliation_note):
        raise ValueError("--retry-uncertain 必须同时记录 --reconciliation-note")
    page_size, enrichment_mode = _paid_execution_spec(args)
    query = _read_query(args)
    with _locked_case(args.case_dir) as (case, case_path):
        lock = case.get("route_lock")
        if not isinstance(lock, dict):
            raise ValueError("case.json 缺少 route_lock")
        if lock.get("active_phase") != "search":
            raise ValueError("只有 search 阶段可以预留查询；请先 transition-phase search")
        active = lock.get("active_search_engine")
        if args.engine != active:
            raise ValueError(f"route_lock 当前主引擎为 {active}，拒绝使用 {args.engine}")
        rounds = lock.setdefault("round_engines", {})
        round_engine = rounds.get(args.round_id)
        if round_engine and round_engine != args.engine:
            raise ValueError(f"search_round={args.round_id} 已锁定 {round_engine}，不能改用 {args.engine}")
        rounds[args.round_id] = args.engine
        digest = _query_hash(case, args, query, page_size, enrichment_mode)
        records = lock.setdefault("queries", [])
        prior = next((row for row in records if row.get("query_hash") == digest), None)
        if prior:
            prior_status = prior.get("status")
            started = _filled(prior.get("execution_started_at"))
            ordinary_retry = (
                prior_status in {"failed", "blocked"} and args.retry_failed and not started
            )
            reconciled_retry = (
                prior_status in {"failed", "blocked", "timeout", "uncertain"}
                and args.retry_uncertain
                and started
            )
            if not (ordinary_retry or reconciled_retry):
                raise ValueError(
                    f"重复查询已被阻止: {digest} status={prior_status}；"
                    "从未启动的失败/阻断可用 --retry-failed；任何已启动调用都须先核对服务端，"
                    "再用 --retry-uncertain --reconciliation-note。"
                )
            if prior.get("upstream_exit_code") == 0:
                raise ValueError("上游已成功返回，禁止重复付费调用；请复用结果或核对已有任务")
            if started and _execution_in_progress(case_path.parent, digest):
                raise ValueError("原 PatSeek 调用仍在执行，拒绝并发重试；请等待返回后再核对")
            prior.update({
                "status": "planned",
                "round_id": args.round_id,
                "reserved_at": datetime.now(timezone.utc).isoformat(),
                "completed_at": None,
                "result_count": None,
                "credits_charged": None,
                "error": None,
                "attempt": int(prior.get("attempt") or 1) + 1,
                "paid_command": args.paid_command,
                "page_size": page_size,
                "enrichment_mode": enrichment_mode,
                "execution_started_at": None,
                "execution_command": None,
                "execution_attempt_hash": None,
                "execution_attempt_id": None,
                "execution_returned_at": None,
                "upstream_exit_code": None,
                "reconcile_required": False,
                "reconciliation_note": args.reconciliation_note or None,
            })
            record = prior
        else:
            record = {
                "query_hash": digest,
                "round_id": args.round_id,
                "engine": args.engine,
                "paid_command": args.paid_command,
                "market": args.market.lower(),
                "page": args.page,
                "page_size": page_size,
                "enrichment_mode": enrichment_mode,
                "purpose": args.purpose,
                "jurisdiction_filter": [item.upper() for item in (args.jurisdiction_filter or [])],
                "date_filter": args.date_filter or None,
                "status": "planned",
                "reserved_at": datetime.now(timezone.utc).isoformat(),
                "completed_at": None,
                "result_count": None,
                "credits_charged": None,
                "error": None,
                "attempt": 1,
                "execution_started_at": None,
                "execution_command": None,
                "execution_attempt_hash": None,
                "execution_attempt_id": None,
                "execution_returned_at": None,
                "upstream_exit_code": None,
                "reconcile_required": False,
                "reconciliation_note": None,
            }
            records.append(record)
        # Do not persist the raw query. The caller must begin the paid call only
        # after this reservation succeeds.
        record["status"] = "running"
        _audit(case, "reserve_query", {
            "query_hash": digest,
            "round_id": args.round_id,
            "engine": args.engine,
            "paid_command": args.paid_command,
            "page_size": page_size,
            "enrichment_mode": enrichment_mode,
            "reconciled_retry": bool(args.retry_uncertain),
        })
    print(json.dumps({
        "ok": True,
        "query_hash": digest,
        "status": "running",
        "paid_command": args.paid_command,
    }, ensure_ascii=False, indent=2))
    return 0


def complete_query(args: argparse.Namespace) -> int:
    if args.status not in {"success", "partial", "failed", "timeout", "blocked", "uncertain"}:
        raise ValueError("complete-query status 非法")
    if args.status in {"success", "partial"} and (args.result_count is None or args.result_count < 0):
        raise ValueError("success/partial 必须给出非负 --result-count")
    if args.status in {"failed", "timeout", "blocked", "uncertain"} and args.result_count is not None:
        raise ValueError("failed/timeout/blocked/uncertain 不得给 result_count；失败不是 0 命中")
    if args.credits is not None and args.credits < 0:
        raise ValueError("credits 不能为负数")
    with _locked_case(args.case_dir) as (case, _):
        lock = case.get("route_lock")
        records = lock.get("queries") if isinstance(lock, dict) else None
        if not isinstance(records, list):
            raise ValueError("case.json 缺少 route_lock.queries")
        record = next((row for row in records if row.get("query_hash") == args.query_hash), None)
        if record is None:
            raise ValueError("query_hash 未预留，拒绝补写结果")
        if record.get("status") != "running":
            raise ValueError(f"查询已经完成: status={record.get('status')}")
        if record.get("engine") == "patseek":
            started = _filled(record.get("execution_started_at"))
            if args.status == "blocked" and not started:
                if args.attempt_id:
                    raise ValueError("尚未执行的 blocked 记录不得提供 attempt-id")
            else:
                if not started or not _filled(record.get("execution_attempt_hash")):
                    raise ValueError("PatSeek 尚未由安全包装器启动，拒绝补写执行结果")
                if not _filled(args.attempt_id):
                    raise ValueError("PatSeek 完成记录必须提供包装器输出的 --attempt-id")
                supplied_hash = hashlib.sha256(args.attempt_id.encode("utf-8")).hexdigest()
                if not hmac.compare_digest(supplied_hash, str(record.get("execution_attempt_hash"))):
                    raise ValueError("attempt-id 与本次执行不一致")
                stored_attempt = str(record.get("execution_attempt_id") or "")
                if stored_attempt and not hmac.compare_digest(args.attempt_id, stored_attempt):
                    raise ValueError("attempt-id 与案件中保存的本次执行标识不一致")
                if record.get("execution_command") != record.get("paid_command"):
                    raise ValueError("实际执行命令与预留 paid_command 不一致")
                if args.status not in {"timeout", "uncertain"} and not _filled(
                    record.get("execution_returned_at")
                ):
                    raise ValueError("PatSeek 包装器尚未返回；只能标记 timeout/uncertain 并进入核对")
                exit_code = record.get("upstream_exit_code")
                if args.status in {"success", "partial"} and exit_code != 0:
                    raise ValueError("上游退出码非 0，不能标记 success/partial")
                if _filled(record.get("execution_returned_at")) and exit_code is None and args.status not in {
                    "timeout", "uncertain"
                }:
                    raise ValueError("包装器异常退出且结果未知，只能标记 timeout/uncertain 并先核对服务端")
                if exit_code == 0 and args.status not in {
                    "success", "partial", "uncertain"
                }:
                    raise ValueError("上游已成功返回，只能标记 success/partial/uncertain，不能伪装为失败后重试")
        record.update({
            "status": args.status,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "result_count": args.result_count,
            "credits_charged": args.credits,
            "error": args.error or None,
            "reconcile_required": args.status in {"timeout", "uncertain"},
        })
        if args.status in {"success", "partial"}:
            completed = lock.setdefault("completed_query_hashes", [])
            if args.query_hash not in completed:
                completed.append(args.query_hash)
        _audit(case, "complete_query", {
            "query_hash": args.query_hash,
            "status": args.status,
            "result_count": args.result_count,
            "credits": args.credits,
        })
    print(json.dumps({"ok": True, "query_hash": args.query_hash, "status": args.status}, ensure_ascii=False, indent=2))
    return 0


def _runtime_tool(name: str) -> Path | None:
    found = shutil.which(name)
    if found:
        return Path(found)
    try:
        dependencies = Path(sys.executable).resolve().parents[2]
    except IndexError:
        return None
    candidate = dependencies / "bin" / "override" / name
    return candidate if candidate.is_file() else None


def _patseek_wrapper_compatible() -> bool:
    try:
        from patseek_secure import _apply_no_store, _load_client, trusted_default_client
        module = _load_client(trusted_default_client())
        _apply_no_store(module)
        return True
    except Exception:
        return False


def doctor(case_path: Path | None = None) -> int:
    root = skill_dir()
    skills_root = root.parent
    import importlib.util
    try:
        has_key = bool(os.environ.get("PATSEEK_API_KEY")) or key_exists()
    except KeychainError:
        has_key = bool(os.environ.get("PATSEEK_API_KEY"))
    required = {
        "python_3_11_plus": sys.version_info >= (3, 11),
        "patseek_skill": (skills_root / "patseek-patent-search" / "SKILL.md").is_file(),
        "patent_search_skill": (skills_root / "patent-search" / "SKILL.md").is_file(),
        "patseek_secure_wrapper_compatible": _patseek_wrapper_compatible(),
        "public_search_dependencies": all(
            importlib.util.find_spec(name) is not None for name in ("requests", "yaml", "bs4")
        ),
        "logo": (root / "assets" / "shensheng-logo.png").is_file(),
        "xlsx_template": (root / "assets" / "templates" / "申晟知产_专利检索候选表模板.xlsx").is_file(),
        "docx_template": (root / "assets" / "templates" / "申晟知产_专利检索分析报告模板.docx").is_file(),
        "pdf_template": (root / "assets" / "templates" / "申晟知产_专利检索分析报告模板.pdf").is_file(),
    }
    capabilities = {
        "patseek_key": has_key,
        "google_proxy": bool(os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")),
        "playwright": False,
        "libreoffice": bool(_runtime_tool("soffice") or _runtime_tool("libreoffice")),
        "pdftoppm": bool(_runtime_tool("pdftoppm")),
    }
    try:
        capabilities["playwright"] = importlib.util.find_spec("playwright") is not None
    except Exception:
        pass
    install_ok = all(required.values())
    report_pipeline_ready = (
        required["xlsx_template"] and required["docx_template"] and required["pdf_template"]
        and capabilities["libreoffice"] and capabilities["pdftoppm"]
    )
    case_ready: bool | None = None
    blockers: list[str] = []
    if case_path is not None:
        case_data = json.loads(case_path.expanduser().read_text(encoding="utf-8"))
        task_type = case_data.get("case_type")
        requires_patseek = task_type not in {"download", "oa"}
        case_ready = install_ok and report_pipeline_ready
        if requires_patseek and not has_key:
            case_ready = False
            blockers.append("PatSeek Key 未设置")
        if task_type == "oa" and case_data.get("route_lock", {}).get("active_search_engine") == "patseek" and not has_key:
            case_ready = False
            blockers.append("OA 已进入 PatSeek 补检，但 Key 未设置")
        if not report_pipeline_ready:
            blockers.append("Word/PDF 渲染链未就绪")
    result = {
        "ok": install_ok and report_pipeline_ready and (case_ready is not False),
        "install_ok": install_ok,
        "report_pipeline_ready": report_pipeline_ready,
        "case_ready": case_ready,
        "required": required,
        "capabilities": capabilities,
        "blockers": blockers,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="申晟专利工作台案件与证据工具", allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    doctor_parser = sub.add_parser("doctor", help="检查安装、案件就绪度和报告渲染链")
    doctor_parser.add_argument("--case", type=Path, help="可选的案件 case.json")

    route_parser = sub.add_parser("route", help="输出确定性任务路由")
    route_parser.add_argument("task_type", choices=sorted(TASK_TYPES))
    route_parser.add_argument("--jurisdictions", nargs="+", default=["CN"])

    init_parser = sub.add_parser("init-case", help="建立安全案件目录和证据骨架")
    init_parser.add_argument("--case-id", required=True)
    init_parser.add_argument("--task-type", choices=sorted(TASK_TYPES), required=True)
    init_parser.add_argument("--subtype")
    init_parser.add_argument("--title", required=True)
    init_parser.add_argument("--decision-question")
    init_parser.add_argument("--jurisdictions", nargs="+", default=["CN"])
    init_parser.add_argument("--critical-date")
    init_parser.add_argument("--data-cutoff")
    init_parser.add_argument("--output-dir", type=Path, default=Path.cwd() / "cases")

    validate_parser = sub.add_parser("validate-evidence", help="校验证据引用和任务硬门")
    validate_parser.add_argument("path", type=Path)
    validate_parser.add_argument("--stage", choices=["draft", "final"], default="final")

    transition_parser = sub.add_parser("transition-phase", help="原子推进案件阶段")
    transition_parser.add_argument("--case-dir", type=Path, required=True)
    transition_parser.add_argument("phase", choices=PHASES)
    transition_parser.add_argument("--engine", choices=sorted(SEARCH_ENGINES))

    fallback_parser = sub.add_parser("approve-fallback", help="记录用户明确批准的检索引擎回退")
    fallback_parser.add_argument("--case-dir", type=Path, required=True)
    fallback_parser.add_argument("--engine", choices=sorted(SEARCH_ENGINES), required=True)
    fallback_parser.add_argument("--reason", required=True)

    reserve_parser = sub.add_parser("reserve-query", help="付费调用前原子预留查询并阻止重复")
    reserve_parser.add_argument("--case-dir", type=Path, required=True)
    reserve_parser.add_argument("--round-id", required=True)
    reserve_parser.add_argument("--engine", choices=sorted(SEARCH_ENGINES), required=True)
    reserve_parser.add_argument("--paid-command", choices=["bool", "semantic", "patent"])
    reserve_parser.add_argument("--market", choices=["cn", "world"], required=True)
    reserve_parser.add_argument("--page", type=int, default=1)
    reserve_parser.add_argument("--page-size", type=int)
    reserve_parser.add_argument("--no-enrichment", action="store_true")
    reserve_parser.add_argument("--purpose", required=True)
    reserve_parser.add_argument("--jurisdiction-filter", nargs="*")
    reserve_parser.add_argument("--date-filter")
    reserve_parser.add_argument("--query-file", type=Path)
    retry_group = reserve_parser.add_mutually_exclusive_group()
    retry_group.add_argument("--retry-failed", action="store_true")
    retry_group.add_argument("--retry-uncertain", action="store_true")
    reserve_parser.add_argument("--reconciliation-note")

    complete_parser = sub.add_parser("complete-query", help="原子记录查询结果、积分和失败状态")
    complete_parser.add_argument("--case-dir", type=Path, required=True)
    complete_parser.add_argument("--query-hash", required=True)
    complete_parser.add_argument("--attempt-id")
    complete_parser.add_argument(
        "--status",
        choices=["success", "partial", "failed", "timeout", "blocked", "uncertain"],
        required=True,
    )
    complete_parser.add_argument("--result-count", type=int)
    complete_parser.add_argument("--credits", type=float)
    complete_parser.add_argument("--error")

    args = parser.parse_args()
    try:
        if args.command == "doctor":
            return doctor(args.case)
        if args.command == "route":
            rights_countries, search_authorities = normalize_scope(args.task_type, args.jurisdictions)
            print(json.dumps(route_for(args.task_type, rights_countries, search_authorities), ensure_ascii=False, indent=2))
            return 0
        if args.command == "init-case":
            return init_case(args)
        if args.command == "validate-evidence":
            return validate_evidence(args.path, args.stage)
        if args.command == "transition-phase":
            return transition_phase(args)
        if args.command == "approve-fallback":
            return approve_fallback(args)
        if args.command == "reserve-query":
            return reserve_query(args)
        return complete_query(args)
    except (ValueError, FileExistsError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
