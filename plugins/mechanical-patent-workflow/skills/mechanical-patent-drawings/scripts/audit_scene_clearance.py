#!/usr/bin/env python3
"""Flag drawing-layout conflicts in a normalized millimetre scene (stdlib only).

Usage: python3 audit_scene_clearance.py scene.json --clearance-mm 0.7 --out audit.json

Input schema_version=1, units="mm", pages=[{figure, paths, labels}]. Each path
has id, kind (polyline/cubic/polygon), points, width_mm, role, optional owner.
Each label has id, text, box=[xmin,ymin,xmax,ymax], bounds_source
(measured/estimated/provided), optional target and exceptions. Paths use page
coordinates; the caller must first apply every view/scale/translation.

This is a preflight, not a CAD visibility, target-ownership, or visual approval.
Bounds and exceptions remain explicit in the report. No exception suppresses a
finding. A genuine leader contact can therefore appear as a review candidate.
Each path pair keeps multiple separated conflict locations as well as the worst
clearance. Limited output explicitly sets truncated=true. A valid endpoint
contact never exempts other contacts, including parts with the same owner.

Copyright 2026 Mechanical Patent Toolkit contributors
SPDX-License-Identifier: MIT
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

EPS = 1e-9
ROLES = {"structure", "leader", "arrow", "hatch", "assembly", "break", "other"}


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("coordinates, widths and clearances must be finite numbers")
    return float(value)


def point(value):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("a point must have two coordinates")
    return tuple(number(v) for v in value)


def box(points):
    return (min(p[0] for p in points), min(p[1] for p in points),
            max(p[0] for p in points), max(p[1] for p in points))


def boxes_near(a, b, pad=0):
    return not (a[2] + pad < b[0] or b[2] + pad < a[0] or
                a[3] + pad < b[1] or b[3] + pad < a[1])


def nearest_point(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    den = dx * dx + dy * dy
    t = max(0., min(1., ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / den)) if den else 0.
    return (a[0] + t * dx, a[1] + t * dy)


def segment_distance(a, b, c, d):
    ux, uy = b[0] - a[0], b[1] - a[1]
    vx, vy = d[0] - c[0], d[1] - c[1]
    det = ux * vy - uy * vx
    if abs(det) > EPS:
        wx, wy = c[0] - a[0], c[1] - a[1]
        t, s = (wx * vy - wy * vx) / det, (wx * uy - wy * ux) / det
        if -EPS <= t <= 1 + EPS and -EPS <= s <= 1 + EPS:
            p = (a[0] + t * ux, a[1] + t * uy)
            return 0., p, p
    candidates = [(math.dist(p, q), p, q) for p in (a, b) for q in [nearest_point(p, c, d)]]
    candidates += [(math.dist(p, q), q, p) for p in (c, d) for q in [nearest_point(p, a, b)]]
    return min(candidates, key=lambda row: row[0])


def rectangle_segments(rect):
    x0, y0, x1, y1 = rect
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return list(zip(pts, pts[1:] + pts[:1]))


def rect_segment_distance(rect, a, b):
    if any(rect[0] <= p[0] <= rect[2] and rect[1] <= p[1] <= rect[3] for p in (a, b)):
        return 0.
    return min(segment_distance(a, b, c, d)[0] for c, d in rectangle_segments(rect))


def in_polygon(p, polygon):
    result = False
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        if (a[1] > p[1]) != (b[1] > p[1]):
            x = a[0] + (p[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if x > p[0]:
                result = not result
    return result


def cubic_points(points, tolerance, depth=0):
    a, b, c, d = points
    flat = max(math.dist(b, nearest_point(b, a, d)), math.dist(c, nearest_point(c, a, d)))
    if flat <= tolerance or depth == 20:
        return [a, d]
    mid = lambda x, y: ((x[0] + y[0]) / 2, (x[1] + y[1]) / 2)
    ab, bc, cd = mid(a, b), mid(b, c), mid(c, d)
    abc, bcd = mid(ab, bc), mid(bc, cd)
    centre = mid(abc, bcd)
    return (cubic_points([a, ab, abc, centre], tolerance, depth + 1)[:-1] +
            cubic_points([centre, bcd, cd, d], tolerance, depth + 1))


def normalize_path(raw, tolerance):
    identity = raw.get("id")
    if not isinstance(identity, str) or not identity:
        raise ValueError("each path needs a nonempty id")
    kind, role = raw.get("kind"), raw.get("role")
    if kind not in {"polyline", "cubic", "polygon"} or role not in ROLES:
        raise ValueError(f"{identity}: unsupported kind or missing role")
    pts = [point(p) for p in raw.get("points", [])]
    if len(pts) < (3 if kind == "polygon" else 2) or kind == "cubic" and len(pts) != 4:
        raise ValueError(f"{identity}: invalid point count")
    width = number(raw.get("width_mm"))
    if width < 0:
        raise ValueError(f"{identity}: negative width")
    if kind == "cubic":
        pts = cubic_points(pts, tolerance)
    segments = list(zip(pts, pts[1:]))
    if kind == "polygon":
        segments.append((pts[-1], pts[0]))
    return {**raw, "points": pts, "segments": segments, "box": box(pts), "width_mm": width}


def audit_scene(scene, clearance_mm, curve_tolerance_mm=.01, max_conflict_locations=128):
    clearance = number(clearance_mm)
    tolerance = number(curve_tolerance_mm)
    if clearance < 0 or tolerance <= 0:
        raise ValueError("clearance must be nonnegative and curve tolerance positive")
    if isinstance(max_conflict_locations, bool) or not isinstance(max_conflict_locations, int) or max_conflict_locations < 1:
        raise ValueError("max_conflict_locations must be a positive integer")
    if scene.get("schema_version") != 1 or scene.get("units") != "mm":
        raise ValueError("expected schema_version 1 in millimetres")
    pages = scene.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ValueError("pages must be a nonempty list")
    report = {"schema_version": 1, "tool_scope": "layout_preflight_only",
              "clearance_mm": clearance, "curve_tolerance_mm": tolerance,
              "max_conflict_locations": max_conflict_locations,
              "overall_status": "manual_and_geometry_review_required", "pages": []}
    for page in pages:
        paths = [normalize_path(p, tolerance) for p in page.get("paths", [])]
        if len({p["id"] for p in paths}) != len(paths):
            raise ValueError("duplicate path ids in a page")
        labels = page.get("labels", [])
        if len({l["id"] for l in labels}) != len(labels):
            raise ValueError("duplicate label ids in a page")
        result = {"figure": page.get("figure"), "findings": [], "unmeasured": [],
                  "exceptions": list(page.get("exceptions", [])),
                  "target_ownership": "not_checked_by_this_tool",
                  "self_and_mutual_occlusion": "not_checked_by_this_tool",
                  "curve_self_intersection": "not_checked_by_this_tool",
                  "section_material_region_ownership": "not_checked_by_this_tool"}
        if not paths:
            result["unmeasured"].append({"reason": "missing_vector_geometry"})
        if not labels:
            result["unmeasured"].append({"reason": "missing_label_inventory"})
        valid_labels = []
        for label in labels:
            if not isinstance(label.get("id"), str) or not isinstance(label.get("text"), str):
                raise ValueError("labels need string ids and text")
            if label.get("exceptions"):
                result["exceptions"].append({"label": label["id"], "declared": label["exceptions"]})
            if not isinstance(label.get("box"), list) or len(label["box"]) != 4:
                result["unmeasured"].append({"label": label["id"], "reason": "missing_complete_text_bounds"})
                continue
            rect = tuple(number(v) for v in label["box"])
            if rect[0] >= rect[2] or rect[1] >= rect[3]:
                raise ValueError("text boxes must have positive width and height")
            source = label.get("bounds_source", "provided")
            if source != "measured":
                result["unmeasured"].append({"label": label["id"], "reason": "text_bounds_not_measured", "bounds_source": source})
            valid_labels.append((label, rect))
            for path in paths:
                if not boxes_near(rect, path["box"], clearance + path["width_mm"] / 2 + tolerance):
                    continue
                dist = min(rect_segment_distance(rect, a, b) for a, b in path["segments"])
                if path.get("filled") and path["kind"] == "polygon" and in_polygon(((rect[0]+rect[2])/2, (rect[1]+rect[3])/2), path["points"]):
                    dist = 0.
                net = dist - path["width_mm"] / 2
                if net < clearance + tolerance:
                    result["findings"].append({"kind": "text_stroke_overlap" if net <= 0 else "text_stroke_near",
                        "label": label["id"], "text": label["text"], "path": path["id"],
                        "path_role": path["role"], "net_clearance_mm": net,
                        "text_box": rect, "bounds_source": source})
        for i, (first, ra) in enumerate(valid_labels):
            for second, rb in valid_labels[i+1:]:
                dx, dy = max(ra[0]-rb[2], rb[0]-ra[2], 0), max(ra[1]-rb[3], rb[1]-ra[3], 0)
                distance = math.hypot(dx, dy)
                if distance < clearance:
                    result["findings"].append({"kind": "text_boxes_overlap" if distance == 0 else "text_boxes_near",
                        "labels": [first["id"], second["id"]], "net_clearance_mm": distance})
        # Only annotation paths require line-to-line checks. Geometry-to-geometry
        # intersections belong to CAD/visibility checks outside this tool.
        for i, first in enumerate(paths):
            for second in paths[i+1:]:
                if not ({first["role"], second["role"]} & {"leader", "arrow"}):
                    continue
                pad = clearance + (first["width_mm"] + second["width_mm"]) / 2 + 2*tolerance
                if not boxes_near(first["box"], second["box"], pad):
                    continue
                locations = []
                worst = None
                first_containment = None
                truncated = False
                candidate_count = 0
                merge_distance = max(1e-6, min(tolerance, .05))

                def remember(location):
                    nonlocal worst, truncated, candidate_count
                    candidate_count += 1
                    if worst is None or location["net_clearance_mm"] < worst["net_clearance_mm"]:
                        worst = location
                    anchor = location.get("occupied_point")
                    if anchor is None:
                        anchor = tuple((a+b)/2 for a,b in zip(*location["closest_points"]))
                    for prior in locations:
                        old_anchor = prior.get("occupied_point")
                        if old_anchor is None:
                            old_anchor = tuple((a+b)/2 for a,b in zip(*prior["closest_points"]))
                        if prior["kind"] == location["kind"] and math.dist(anchor, old_anchor) <= merge_distance:
                            pair = location["segment_indices"]
                            if pair not in prior["contributing_segment_pairs"]:
                                prior["contributing_segment_pairs"].append(pair)
                            return
                    if len(locations) < max_conflict_locations:
                        locations.append({**location, "contributing_segment_pairs": [location["segment_indices"]]})
                    else:
                        truncated = True

                # Boundary distances miss a short stroke completely enclosed by
                # a filled arrow. Check the occupied region as well as its rim.
                for fill, stroke in ((first, second), (second, first)):
                    if not (fill["kind"] == "polygon" and fill.get("filled")):
                        continue
                    for segment_index, (a, b) in enumerate(stroke["segments"]):
                        for candidate in (a, b, ((a[0]+b[0])/2, (a[1]+b[1])/2)):
                            if in_polygon(candidate, fill["points"]):
                                location = {"kind": "filled_region_overlap",
                                    "net_clearance_mm": -stroke["width_mm"]/2,
                                    "occupied_point": candidate,
                                    "closest_points": [candidate, candidate],
                                    "filled_polygon": fill["id"],
                                    "segment_indices": {fill["id"]: None, stroke["id"]: segment_index}}
                                if first_containment is None:
                                    first_containment = location
                                remember(location)
                for first_index, (a, b) in enumerate(first["segments"]):
                    for second_index, (c, d) in enumerate(second["segments"]):
                        if not boxes_near(box([a,b]), box([c,d]), pad):
                            continue
                        distance, pa, pb = segment_distance(a,b,c,d)
                        net = distance - (first["width_mm"] + second["width_mm"]) / 2
                        if net < clearance + 2*tolerance:
                            remember({"kind": "boundary_overlap" if net <= 0 else "boundary_near",
                                "net_clearance_mm": net, "closest_points": [pa, pb],
                                "segment_indices": {first["id"]: first_index, second["id"]: second_index}})
                if worst:
                    finding = {"kind": "filled_annotation_covers_stroke" if first_containment else
                               "annotation_stroke_overlap" if worst["net_clearance_mm"] <= 0 else "annotation_stroke_near",
                        "paths": [first["id"], second["id"]],
                        "net_clearance_mm": worst["net_clearance_mm"],
                        "closest_points": worst["closest_points"], "worst": worst,
                        "conflict_locations": locations, "truncated": truncated,
                        "candidate_conflict_count": candidate_count,
                        "max_conflict_locations": max_conflict_locations,
                        "location_merge_distance_mm": merge_distance,
                        "note": "Includes intended target contacts; review every location and declared exception. A valid tip never exempts the whole path pair; truncated output is incomplete."}
                    if first_containment:
                        finding["occupied_point"] = first_containment["occupied_point"]
                    result["findings"].append(finding)
        result["scan_status"] = ("incomplete_inputs" if result["unmeasured"] else
                                 "layout_candidates_found" if result["findings"] else "no_layout_candidates")
        report["pages"].append(result)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scene", type=Path)
    parser.add_argument("--clearance-mm", type=float, required=True, help="Project-specific paper clearance; not a universal acceptance threshold")
    parser.add_argument("--curve-tolerance-mm", type=float, default=.01)
    parser.add_argument("--max-conflict-locations", type=int, default=128, help="Per path pair; limited output explicitly sets truncated=true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        result = audit_scene(json.loads(args.scene.read_text(encoding="utf-8")), args.clearance_mm, args.curve_tolerance_mm, args.max_conflict_locations)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"Invalid scene: {exc}\n")
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 1 if any(p["findings"] or p["unmeasured"] for p in result["pages"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
