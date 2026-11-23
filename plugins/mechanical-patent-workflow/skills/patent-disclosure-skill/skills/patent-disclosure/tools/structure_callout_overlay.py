# -*- coding: utf-8 -*-
"""按持久化锚点给实用新型线稿叠加件号与引出线。

大模型只负责识别部件并给出归一化锚点/标签坐标；本脚本校验件号后，
以 SVG 精确绘制曲线和序号，保留已确认的真实锚点及图内/图外方式。
若视图提供 base_svg_path，把件号组注入该 SVG。缺少最终纸面尺寸时仅出待核预览。

  python tools/structure_callout_overlay.py \
    --case-dir outputs/case \
    --anchors outputs/case/structure_callout_anchors.yaml
"""
from __future__ import annotations

import argparse
import base64
import html
import json
import math
import re
import struct
import sys
from pathlib import Path
from typing import Any

from structure_callout_layout import autolayout_view

STYLE_PATH = Path(__file__).resolve().parents[4] / "mechanical-patent-drawings/references/approved-leader-style.json"

CALLOUT_START = "<!-- structure-callouts -->"
CALLOUT_END = "<!-- /structure-callouts -->"


def load_data(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore

            data = yaml.safe_load(text)
        except Exception as exc:
            raise ValueError(f"无法读取 YAML {path}: {exc}") from exc
    else:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"锚点文件根须为对象: {path}")
    return data


def resolve_path(case_dir: Path, raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    return (case_dir / path).resolve()


def image_size(path: Path) -> tuple[int, int]:
    """不用 Pillow 读取 PNG/JPEG 尺寸。"""
    data = path.read_bytes()
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return struct.unpack(">II", data[16:24])
    if data.startswith(b"\xff\xd8"):
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            i += 2
            if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
                continue
            if i + 2 > len(data):
                break
            seg_len = int.from_bytes(data[i : i + 2], "big")
            if marker in {
                0xC0,
                0xC1,
                0xC2,
                0xC3,
                0xC5,
                0xC6,
                0xC7,
                0xC9,
                0xCA,
                0xCB,
                0xCD,
                0xCE,
                0xCF,
            }:
                height = int.from_bytes(data[i + 3 : i + 5], "big")
                width = int.from_bytes(data[i + 5 : i + 7], "big")
                return width, height
            i += max(seg_len, 2)
    raise ValueError(f"仅支持 PNG/JPEG 尺寸读取: {path}")


def _parts_index(structure: dict[str, Any]) -> dict[str, str]:
    from structure_entities import entity_index
    return entity_index(structure)


def _point(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        return float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None


def validate_manifest(
    manifest: dict[str, Any],
    case_dir: Path,
    *,
    structure: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    if int(manifest.get("version") or 0) != 1:
        errors.append("structure_callout_anchors.version 须为 1")
    if (manifest.get("coordinate_system") or "normalized") != "normalized":
        errors.append("coordinate_system 须为 normalized")
    views = manifest.get("views") or []
    if not isinstance(views, list) or not views:
        errors.append("views 为空")
        return errors

    from structure_entities import entity_errors
    errors.extend(entity_errors(structure or {}))
    parts = _parts_index(structure or {})
    for vi, view in enumerate(views):
        if not isinstance(view, dict):
            errors.append(f"views[{vi}] 非法")
            continue
        if "paper_width_mm" in view:
            try:
                paper_width = float(view["paper_width_mm"])
                if not math.isfinite(paper_width) or paper_width <= 0:
                    errors.append(f"views[{vi}] paper_width_mm 须为正数")
            except (TypeError, ValueError):
                errors.append(f"views[{vi}] paper_width_mm 须为正数")
        image_raw = str(view.get("image_path") or "").strip()
        base_svg_raw = str(view.get("base_svg_path") or "").strip()
        output_raw = str(view.get("output_svg_path") or "").strip()
        if base_svg_raw:
            if not resolve_path(case_dir, base_svg_raw).is_file():
                errors.append(f"views[{vi}] base_svg_path 不存在: {base_svg_raw}")
        elif not image_raw:
            errors.append(f"views[{vi}] 缺少 image_path 或 base_svg_path")
        elif not resolve_path(case_dir, image_raw).is_file():
            errors.append(f"views[{vi}] 原图不存在: {image_raw}")
        if not output_raw:
            errors.append(f"views[{vi}] 缺少 output_svg_path")

        callouts = view.get("callouts") or []
        if not isinstance(callouts, list) or not callouts:
            errors.append(f"views[{vi}].callouts 为空")
            continue
        seen: set[str] = set()
        labels: list[tuple[float, float]] = []
        for ci, item in enumerate(callouts):
            if not isinstance(item, dict):
                errors.append(f"views[{vi}].callouts[{ci}] 非法")
                continue
            pid = str(item.get("id") or "").strip()
            name = str(item.get("name") or "").strip()
            if not pid:
                errors.append(f"views[{vi}].callouts[{ci}] 缺少 id")
            seen.add(pid)
            if parts:
                if pid not in parts:
                    errors.append(f"views[{vi}] 件号 {pid} 不在 structure_schema.parts/features")
                elif name and parts[pid] and name != parts[pid]:
                    errors.append(f"views[{vi}] 件号 {pid} 名称与 StructureSchema 不一致")

            if "arrow_axis" in item:
                axis = _point(item["arrow_axis"])
                if axis is None or not all(math.isfinite(x) for x in axis) or math.hypot(*axis) <= 1e-9:
                    errors.append(f"views[{vi}] 件号 {pid} arrow_axis 须为非零有限二维向量")
            if item.get("target_kind", "edge") not in {"part", "edge", "face", "hole", "slot", "gap", "flow_path"}:
                errors.append(f"views[{vi}] 件号 {pid} target_kind 非法")
            if item.get("label_placement", "external") not in {"external", "internal"}:
                errors.append(f"views[{vi}] 件号 {pid} label_placement 非法")
            for key in ("anchor", "label"):
                point = _point(item.get(key))
                if point is None:
                    errors.append(f"views[{vi}] 件号 {pid or '?'} 的 {key} 须为 [x, y]")
                    continue
                lo, hi = (-0.08, 1.08) if key == "label" else (0.0, 1.0)
                if not all(lo <= n <= hi for n in point):
                    errors.append(f"views[{vi}] 件号 {pid or '?'} 的 {key} 超出 {lo}..{hi}")
                if key == "label":
                    labels.append(point)
            confidence = item.get("confidence", 1.0)
            try:
                if float(confidence) < 0.60:
                    errors.append(f"views[{vi}] 件号 {pid or '?'} 锚点置信度低于 0.60")
            except (TypeError, ValueError):
                errors.append(f"views[{vi}] 件号 {pid or '?'} confidence 非数字")

        # 归一化距离过小意味着序号会互相覆盖。
        for i, first in enumerate(labels):
            for second in labels[i + 1 :]:
                if math.dist(first, second) < 0.035:
                    errors.append(f"views[{vi}] 存在距离过近的 label 坐标")
                    break
    return errors


def _mime(path: Path) -> str:
    return "image/png" if path.suffix.lower() == ".png" else "image/jpeg"


_SVG_OPEN_RE = re.compile(r"<svg\b[^>]*>", re.IGNORECASE | re.DOTALL)


def _svg_attr(tag: str, name: str) -> str | None:
    match = re.search(rf'\b{name}="([^"]+)"', tag, re.IGNORECASE)
    return match.group(1) if match else None


def _svg_length(raw: str | None) -> float:
    if not raw:
        return 0.0
    text = re.sub(r"[a-z%]+$", "", raw.strip(), flags=re.IGNORECASE)
    try:
        return float(text)
    except ValueError:
        return 0.0


def canvas_padding(width: int, height: int, view: dict[str, Any]) -> int:
    """Leave visible margins; an explicit paper width refers to this padded final canvas."""
    if view.get("paper_width_mm"):
        return max(2, int(round(max(width, height) * 0.08)))
    return int(round(max(64, min(width, height) * 0.08)))


def drawing_metrics(view: dict[str, Any], width: int, height: int) -> dict[str, Any]:
    """Convert the single approved physical style into current SVG user units."""
    approved = json.loads(STYLE_PATH.read_text(encoding="utf-8"))
    paper_width = float(view.get("paper_width_mm") or 0)
    if paper_width < 0:
        raise ValueError("paper_width_mm must be positive")
    pad = canvas_padding(width, height, view)
    units_per_pt = (width + 2 * pad) / (paper_width * 72 / 25.4) if paper_width else 96 / 72
    return {
        "font_size": float(approved["marker_font_size_pt"]) * units_per_pt,
        "font_family": str(approved["marker_font"]),
        "line_width": float(approved["leader_stroke_width_pt"]) * units_per_pt,
        "arrow_length": float(approved["primary_arrow_length_pt"]) * units_per_pt,
        "arrow_width": float(approved["primary_arrow_base_width_pt"]) * units_per_pt,
        "units_per_pt": units_per_pt,
        "nominal_arc_mm": float(approved["preferred_exemplar"]["s_body_arc_length_mm"]),
        "control_points": approved["preferred_exemplar"]["normalized_chord_frame_control_points"],
        "paper_width_mm": paper_width,
        "drafting_status": "requires_visual_review" if paper_width else "preview_missing_paper_size",
    }


def _physical_svg_size(text: str, view: dict[str, Any], width: int, height: int) -> str:
    paper_width = float(view.get("paper_width_mm") or 0)
    match = _SVG_OPEN_RE.search(text)
    if not match:
        return text
    tag = match.group(0)
    status = "requires_visual_review" if paper_width else "preview_missing_paper_size"
    tag = tag[:-1] + f' data-drafting-status="{status}">'
    if paper_width:
        pad = canvas_padding(width, height, view)
        paper_height = paper_width * (height + 2 * pad) / (width + 2 * pad)
        tag = re.sub(r'\bwidth="[^\"]+"', f'width="{paper_width:.6f}mm"', tag, count=1)
        tag = re.sub(r'\bheight="[^\"]+"', f'height="{paper_height:.6f}mm"', tag, count=1)
    return text[:match.start()] + tag + text[match.end():]


def pad_svg_canvas(svg_text: str, pad: int) -> str:
    if pad <= 0:
        return svg_text
    match = _SVG_OPEN_RE.search(svg_text)
    if not match:
        return svg_text
    tag = match.group(0)
    width = _svg_length(_svg_attr(tag, "width"))
    height = _svg_length(_svg_attr(tag, "height"))
    vb_raw = _svg_attr(tag, "viewBox")
    vb: tuple[float, float, float, float] | None = None
    if vb_raw:
        parts = re.split(r"[\s,]+", vb_raw.strip())
        if len(parts) == 4:
            try:
                vb = (float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3]))
            except ValueError:
                vb = None
    if width <= 0 or height <= 0:
        if vb is None:
            return svg_text
        width, height = vb[2], vb[3]
    if vb is None:
        vb = (0.0, 0.0, width, height)
    new_w = width + 2 * pad
    new_h = height + 2 * pad
    new_vb = (
        f"{vb[0] - pad:.2f} {vb[1] - pad:.2f} {vb[2] + 2 * pad:.2f} {vb[3] + 2 * pad:.2f}"
    )
    new_tag = tag
    if _svg_attr(tag, "width"):
        new_tag = re.sub(r'\bwidth="[^"]+"', f'width="{new_w:.0f}"', new_tag, count=1, flags=re.I)
    else:
        new_tag = new_tag[:-1] + f' width="{new_w:.0f}">'
    if _svg_attr(new_tag, "height"):
        new_tag = re.sub(r'\bheight="[^"]+"', f'height="{new_h:.0f}"', new_tag, count=1, flags=re.I)
    else:
        new_tag = new_tag[:-1] + f' height="{new_h:.0f}">'
    if vb_raw:
        new_tag = re.sub(r'\bviewBox="[^"]+"', f'viewBox="{new_vb}"', new_tag, count=1, flags=re.I)
    else:
        new_tag = new_tag[:-1] + f' viewBox="{new_vb}">'
    if "overflow=" not in new_tag.lower():
        new_tag = new_tag[:-1] + ' overflow="visible">'
    return svg_text[: match.start()] + new_tag + svg_text[match.end() :]


def svg_canvas_size(path: Path) -> tuple[float, float]:
    text = path.read_text(encoding="utf-8")
    match = _SVG_OPEN_RE.search(text)
    if match:
        vb = _svg_attr(match.group(0), "viewBox")
        if vb:
            values = re.split(r"[\s,]+", vb.strip())
            if len(values) == 4:
                width, height = float(values[2]), float(values[3])
                if width > 0 and height > 0:
                    return width, height
        width = _svg_length(_svg_attr(match.group(0), "width"))
        height = _svg_length(_svg_attr(match.group(0), "height"))
        if width > 0 and height > 0:
            return width, height
    raise ValueError(f"无法读取 SVG 画布尺寸: {path}")


def _source_origin(svg_text: str) -> tuple[float, float]:
    match = _SVG_OPEN_RE.search(svg_text)
    vb = _svg_attr(match.group(0), "viewBox") if match else None
    if vb:
        values = re.split(r"[\s,]+", vb.strip())
        if len(values) == 4:
            return float(values[0]), float(values[1])
    return 0.0, 0.0


def strip_callouts(svg_text: str) -> str:
    start = svg_text.find(CALLOUT_START)
    end = svg_text.find(CALLOUT_END)
    if start != -1 and end != -1 and end > start:
        return svg_text[:start] + svg_text[end + len(CALLOUT_END) :]
    return svg_text


def inject_callouts(svg_text: str, markup: str) -> str:
    stripped = strip_callouts(svg_text).rstrip()
    close = stripped.rfind("</svg>")
    if close == -1:
        raise ValueError("base SVG 缺少 </svg>")
    block = f"{CALLOUT_START}\n{markup}\n{CALLOUT_END}\n"
    return stripped[:close] + block + stripped[close:]


def leader_geometry(item: dict[str, Any], view: dict[str, Any], width: float, height: float) -> dict[str, Any]:
    metrics = drawing_metrics(view, width, height)
    anchor_n, label_n = _point(item["anchor"]), _point(item["label"])
    assert anchor_n is not None and label_n is not None
    anchor = (anchor_n[0] * width, anchor_n[1] * height)
    label = (label_n[0] * width, label_n[1] * height)
    dx, dy = label[0] - anchor[0], label[1] - anchor[1]
    length = max(math.hypot(dx, dy), 0.001)
    ux, uy = dx / length, dy / length
    pid = str(item["id"])
    clearance = max(metrics["font_size"] * 0.56 * max(1, len(pid) * 0.6), metrics["units_per_pt"] * 2)
    end = (label[0] - ux * clearance, label[1] - uy * clearance)
    primary = item.get("marker_type") == "primary_arrow" or item.get("primary") is True
    start = anchor
    arrow: list[tuple[float,float]] = []
    axis = _point(item.get("arrow_axis"))
    warnings: list[str] = []
    first_cp = metrics["control_points"][1]
    if primary:
        # Default axis follows the exemplar's actual initial tangent, not its chord.
        # When the user supplies a geometry-based axis, preserve it and the true tip.
        if axis is None:
            phi = math.atan2(first_cp[1], first_cp[0])
            axis = (ux * math.cos(phi) - uy * math.sin(phi), ux * math.sin(phi) + uy * math.cos(phi))
            for _ in range(24):
                base = (anchor[0] + axis[0] * metrics["arrow_length"], anchor[1] + axis[1] * metrics["arrow_length"])
                bx, by = end[0] - base[0], end[1] - base[1]
                bl = max(math.hypot(bx, by), 0.001)
                axis = ((bx * math.cos(phi) - by * math.sin(phi))/bl, (bx * math.sin(phi) + by * math.cos(phi))/bl)
        axis_length = math.hypot(*axis)
        if axis_length <= 1e-9:
            raise ValueError(f"mark {pid} arrow_axis cannot be zero")
        axis = (axis[0]/axis_length, axis[1]/axis_length)
        if axis[0]*dx + axis[1]*dy <= 0:
            warnings.append("supplied_arrow_axis_away_from_label: reposition label, preserve target")
        start = (anchor[0] + axis[0] * metrics["arrow_length"], anchor[1] + axis[1] * metrics["arrow_length"])
        normal = (-axis[1],axis[0])
        arrow = [anchor, (start[0] + normal[0]*metrics["arrow_width"]/2,start[1] + normal[1]*metrics["arrow_width"]/2), (start[0] - normal[0]*metrics["arrow_width"]/2,start[1] - normal[1]*metrics["arrow_width"]/2)]
    vx, vy = end[0] - start[0], end[1] - start[1]
    def cp(point: list[float]) -> tuple[float,float]:
        return start[0] + point[0]*vx - point[1]*vy, start[1] + point[0]*vy + point[1]*vx
    c1, c2 = cp(first_cp), cp(metrics["control_points"][2])
    if primary and axis is not None:
        handle = math.hypot(vx,vy) * math.hypot(*first_cp)
        c1 = (start[0] + axis[0]*handle,start[1] + axis[1]*handle)
    if length <= clearance + (metrics["arrow_length"] if primary else 0):
        warnings.append("label_too_close_to_target: reposition label, preserve target")
    points = [start]
    for k in range(1,81):
        t=k/80; u=1-t
        points.append((u*u*u*start[0]+3*u*u*t*c1[0]+3*u*t*t*c2[0]+t*t*t*end[0],u*u*u*start[1]+3*u*u*t*c1[1]+3*u*t*t*c2[1]+t*t*t*end[1]))
    arc = sum(math.dist(left,right) for left,right in zip(points,points[1:]))
    arc_mm = arc/(metrics["units_per_pt"]*72/25.4) if metrics["paper_width_mm"] else None
    ratio = arc_mm/metrics["nominal_arc_mm"] if arc_mm is not None else None
    reason = str(item.get("length_exception_reason") or "").strip()
    if ratio is not None and (ratio < 0.65 or ratio > 1.5) and not reason:
        warnings.append("length_departs_from_nominal: review at final size and record any necessary exception; advisory, not a pass/fail threshold")
    return {"start":start,"c1":c1,"c2":c2,"end":end,"anchor":anchor,"label":label,"arrow":arrow,"metrics":metrics,"s_arc_length_mm":arc_mm,"nominal_s_arc_length_mm":metrics["nominal_arc_mm"],"length_ratio":ratio,"length_exception_reason":reason,"warnings":warnings}


def leader_records(view: dict[str, Any], width: float, height: float) -> list[dict[str, Any]]:
    records=[]
    for occurrence,item in enumerate(view.get("callouts") or [],1):
        geometry=leader_geometry(item,view,width,height)
        records.append({"occurrence":occurrence,"id":str(item["id"]),**{k:geometry[k] for k in ("s_arc_length_mm","nominal_s_arc_length_mm","length_ratio","length_exception_reason","warnings")},"review_status":"requires_visual_review" if view.get("paper_width_mm") else "preview_missing_paper_size"})
    return records


def callouts_markup(view: dict[str, Any], width: int, height: int) -> str:
    metrics = drawing_metrics(view, width, height)
    svg = [f'<g id="structure-callouts" fill="none" stroke="#111" stroke-width="{metrics["line_width"]:.6f}" stroke-linecap="round" stroke-linejoin="round">']
    for item in view.get("callouts") or []:
        pid = str(item["id"])
        g = leader_geometry(item,view,width,height)
        start,c1,c2,end,label=(g[k] for k in ("start","c1","c2","end","label"))
        arrow = '<polygon fill="#111" stroke="none" points="' + ' '.join(f'{x:.6f},{y:.6f}' for x,y in g['arrow']) + '"/>' if g['arrow'] else ''
        d = f'M {start[0]:.6f},{start[1]:.6f} C {c1[0]:.6f},{c1[1]:.6f} {c2[0]:.6f},{c2[1]:.6f} {end[0]:.6f},{end[1]:.6f}'
        title = html.escape(f"{pid} {item.get('name') or ''}".strip())
        svg.append(f'<g data-part-id="{html.escape(pid)}" data-target-kind="{html.escape(str(item.get("target_kind") or "edge"))}"><title>{title}</title>{arrow}<path d="{d}"/></g>')
        svg.append(f'<text x="{label[0]:.6f}" y="{label[1]:.6f}" font-family="{html.escape(metrics["font_family"])}" font-size="{metrics["font_size"]:.6f}" font-weight="normal" text-anchor="middle" dominant-baseline="central" stroke="none" fill="#111">{html.escape(pid)}</text>')
    svg.append("</g>")
    return "\n".join(svg)


def render_view(view: dict[str, Any], case_dir: Path, *, autolayout: bool = False) -> Path:
    output_path = resolve_path(case_dir, str(view["output_svg_path"]))
    base_raw = str(view.get("base_svg_path") or "").strip()
    if base_raw:
        base_path = resolve_path(case_dir, base_raw)
        width, height = svg_canvas_size(base_path)
        if autolayout:
            view = autolayout_view(view, case_dir, (width, height))
        markup = callouts_markup(view, width, height)
        source_text = base_path.read_text(encoding="utf-8")
        origin_x, origin_y = _source_origin(source_text)
        if origin_x or origin_y:
            markup = f'<g transform="translate({origin_x:.6f} {origin_y:.6f})">{markup}</g>'
        text = inject_callouts(source_text, markup)
        text = pad_svg_canvas(text, canvas_padding(width, height, view))
        text = _physical_svg_size(text, view, width, height)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
        return output_path

    image_path = resolve_path(case_dir, str(view["image_path"]))
    width, height = image_size(image_path)
    if autolayout:
        view = autolayout_view(view, case_dir, (width, height))
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    markup = callouts_markup(view, width, height)
    pad = canvas_padding(width, height, view)
    svg = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
            f'overflow="visible">'
        ),
        f'<image width="{width}" height="{height}" href="data:{_mime(image_path)};base64,{encoded}"/>',
        CALLOUT_START,
        markup,
        CALLOUT_END,
        "</svg>",
    ]
    text = pad_svg_canvas("\n".join(svg) + "\n", pad)
    text = _physical_svg_size(text, view, width, height)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    return output_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="按持久化锚点给结构线稿叠件号（SVG）")
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--anchors", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--no-autolayout",
        action="store_true",
        help="兼容旧旗标；默认已保留 YAML 锚点，不自动吸附墨线",
    )
    args = parser.parse_args(argv)

    case_dir = args.case_dir.resolve()
    anchors_path = args.anchors.resolve()
    manifest = load_data(anchors_path)
    structure_path = case_dir / str(manifest.get("structure_ref") or "structure_schema.yaml")
    structure = load_data(structure_path) if structure_path.is_file() else None
    errors = validate_manifest(manifest, case_dir, structure=structure)
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    outputs: list[str] = []
    if not args.check:
        outputs = [
            str(render_view(view, case_dir, autolayout=False))
            for view in manifest.get("views") or []
        ]
    statuses = []
    for view in manifest.get("views") or []:
        raw = str(view.get("base_svg_path") or "")
        width,height = svg_canvas_size(resolve_path(case_dir,raw)) if raw else image_size(resolve_path(case_dir,str(view["image_path"])))
        statuses.append({"view":view.get("view_name", ""),"drafting_status":"requires_visual_review" if view.get("paper_width_mm") else "preview_missing_paper_size", "leaders":leader_records(view,width,height)})
    print(json.dumps({"ok": True, "anchors": str(anchors_path), "outputs": outputs, "view_status": statuses, "warning": "File generation is not geometry or visual approval; verify final paper size, each target, short S length and neighbor clearance."}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
