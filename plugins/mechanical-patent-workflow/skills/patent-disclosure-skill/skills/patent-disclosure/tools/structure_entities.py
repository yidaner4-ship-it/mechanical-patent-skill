"""Shared index for physical parts and separately registered markable features."""
from __future__ import annotations
from typing import Any


def entity_index(schema: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for group in ("parts", "features"):
        for item in schema.get(group) or []:
            if not isinstance(item, dict):
                continue
            reference = item.get("id") or item.get("reference_number")
            pid = str(reference or item.get("id") or "").strip()
            if pid:
                out[pid] = str(item.get("name") or "").strip()
    return out


def entity_errors(schema: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    part_ids = {str(p.get("id") or "").strip() for p in schema.get("parts") or [] if isinstance(p, dict)}
    seen: set[str] = set()
    for group in ("parts", "features"):
        for item in schema.get(group) or []:
            if not isinstance(item, dict):
                errors.append(f"{group} item must be an object")
                continue
            pid = str(item.get("id") or item.get("reference_number") or "").strip()
            if item.get("id") and item.get("reference_number") and str(item["id"]) != str(item["reference_number"]):
                errors.append(f"conflicting id/reference_number: {pid}")
            if not pid or pid in seen:
                errors.append(f"missing or duplicate reference number: {pid}")
            seen.add(pid)
            if group == "features":
                parent = str(item.get("parent_part_id") or "").strip()
                if parent not in part_ids:
                    errors.append(f"feature {pid} parent_part_id not in parts: {parent}")
                if not item.get("source"):
                    errors.append(f"feature {pid} missing verified source")
                if item.get("kind") in {"section_symbol", "arrow", "cutting_line"}:
                    errors.append(f"feature {pid} is a drawing annotation, not a structural feature")
    return errors
