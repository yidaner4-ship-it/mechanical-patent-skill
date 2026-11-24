"""Synthetic behavioural checks; no customer drawing or model is embedded."""
import copy
import math
import unittest
from audit_scene_clearance import audit_scene


def scene(paths, labels):
    return {"schema_version": 1, "units": "mm", "pages": [{"figure": 1, "paths": paths, "labels": labels}]}


def path(identity, points, role="structure", width=.2, kind="polyline", **extra):
    return {"id": identity, "points": points, "role": role, "width_mm": width, "kind": kind, **extra}


def label(rect, **extra):
    return {"id": "label-a", "text": "42", "box": rect, "bounds_source": "measured", **extra}


class SceneClearanceChecks(unittest.TestCase):
    def findings(self, value):
        return audit_scene(value, .7)["pages"][0]["findings"]

    def test_real_target_contact_does_not_exempt_text_over_geometry(self):
        value = scene([path("wall", [[20,0],[20,40]]), path("lead", [[20,10],[23,10],[24,12],[27,12]], "leader", .18, "cubic")],
                      [label([19,14,23,18], target=[20,10])])
        self.assertTrue(any(f["kind"] == "text_stroke_overlap" and f["path"] == "wall" for f in self.findings(value)))

    def test_nonintersecting_centrelines_can_have_overlapping_ink(self):
        value = scene([path("wall", [[0,10],[20,10]], width=.4), path("lead", [[0,10.3],[20,10.3]], "leader", .4)], [label([25,20,29,24])])
        found = next(f for f in self.findings(value) if "paths" in f)
        self.assertEqual(found["kind"], "annotation_stroke_overlap")
        self.assertAlmostEqual(found["net_clearance_mm"], -.1)

    def test_cubic_middle_conflict_is_found_even_with_clear_endpoints(self):
        value = scene([path("arc", [[0,0],[3,10],[7,10],[10,0]], kind="cubic")], [label([4.5,7.4,5.5,7.6])])
        self.assertTrue(any(f["kind"] == "text_stroke_overlap" for f in self.findings(value)))

    def test_clear_scene_still_requires_visual_and_geometry_review(self):
        report = audit_scene(scene([path("wall", [[0,0],[10,0]])], [label([20,20,24,24])]), .7)
        self.assertEqual(report["pages"][0]["scan_status"], "no_layout_candidates")
        self.assertEqual(report["overall_status"], "manual_and_geometry_review_required")
        self.assertEqual(report["pages"][0]["target_ownership"], "not_checked_by_this_tool")

    def test_missing_and_estimated_bounds_do_not_become_passes(self):
        for item in [{"id":"x", "text":"42"}, label([20,20,24,24], bounds_source="estimated")]:
            report = audit_scene(scene([path("wall", [[0,0],[10,0]])], [item]), .7)
            self.assertEqual(report["pages"][0]["scan_status"], "incomplete_inputs")

    def test_declared_exception_remains_visible_and_does_not_hide_conflict(self):
        value = scene([path("wall", [[20,0],[20,40]])], [label([19,14,23,18], exceptions=[{"reason":"existing layout"}])])
        before = copy.deepcopy(value)
        report = audit_scene(value, .7)
        self.assertTrue(report["pages"][0]["findings"])
        self.assertTrue(report["pages"][0]["exceptions"])
        self.assertEqual(value, before)

    def test_translation_does_not_change_clearance(self):
        value = scene([path("wall", [[0,0],[10,0]])], [label([4,.3,8,4])])
        shifted = copy.deepcopy(value)
        for p in shifted["pages"][0]["paths"][0]["points"]:
            p[0] += 93; p[1] -= 57
        shifted["pages"][0]["labels"][0]["box"] = [v + (93 if i%2 == 0 else -57) for i,v in enumerate(value["pages"][0]["labels"][0]["box"])]
        first, second = self.findings(value)[0], self.findings(shifted)[0]
        self.assertEqual(first["kind"], second["kind"])
        self.assertAlmostEqual(first["net_clearance_mm"], second["net_clearance_mm"])

    def test_filled_arrow_enclosing_text_is_not_only_an_edge_distance(self):
        value = scene([path("arrow", [[0,0],[30,0],[15,30]], "arrow", 0, "polygon", filled=True)], [label([14,8,16,10])])
        self.assertEqual(self.findings(value)[0]["kind"], "text_stroke_overlap")

    def test_filled_arrow_can_cover_a_short_stroke_without_rim_intersections(self):
        value = scene([path("arrow", [[0,0],[30,0],[15,30]], "arrow", 0, "polygon", filled=True),
                       path("short-detail", [[14.5,8],[15.5,8]])], [label([40,40,44,44])])
        found = next(f for f in self.findings(value) if f["kind"] == "filled_annotation_covers_stroke")
        self.assertEqual(found["paths"], ["arrow", "short-detail"])
        self.assertLessEqual(found["net_clearance_mm"], 0)
        self.assertIn("intended target contacts", found["note"])

    def test_one_polyline_tip_contact_does_not_swallow_arrow_body_conflict(self):
        value = scene([path("arrow", [[0,0],[2,-1],[2,1]], "arrow", 0, "polygon", filled=True),
                       path("same-outline", [[0,-2],[0,0],[-1,0],[-1,3],[1.2,3],[1.2,-3]])],
                      [label([8,8,12,12])])
        found = next(f for f in self.findings(value) if "conflict_locations" in f)
        places = found["conflict_locations"]
        self.assertTrue(any(p["segment_indices"].get("same-outline") in (0,1) and
                            math.dist(p["closest_points"][0], (0,0)) < 1e-7 for p in places))
        self.assertTrue(any(p["segment_indices"].get("same-outline") == 4 and
                            p.get("occupied_point", [-10,0])[0] > .6 for p in places))
        self.assertIn("worst", found)
        self.assertIn("closest_points", found)
        self.assertFalse(found["truncated"])

    def test_separate_line_crossings_keep_structure_segment_indices(self):
        value = scene([path("leader", [[0,0],[4,0]], "leader", .18),
                       path("wall", [[0,-2],[0,0],[-1,0],[-1,2],[2,2],[2,-2]])],
                      [label([8,8,12,12])])
        found = next(f for f in self.findings(value) if "conflict_locations" in f)
        self.assertTrue(any(p["segment_indices"].get("wall") in (0,1) for p in found["conflict_locations"]))
        self.assertTrue(any(p["segment_indices"].get("wall") == 4 and
                            abs(p["closest_points"][1][0]-2) < 1e-7 for p in found["conflict_locations"]))

    def test_contact_is_not_automatically_exempted_by_shared_owner(self):
        value = scene([path("leader", [[0,0],[4,0]], "leader", .18, owner="a"),
                       path("arrow", [[0,0],[2,-1],[2,1]], "arrow", 0, "polygon", owner="a", filled=True)],
                      [label([8,8,12,12])])
        self.assertTrue(any("conflict_locations" in f for f in self.findings(value)))

    def test_limited_conflict_output_is_explicitly_incomplete(self):
        value = scene([path("arrow", [[0,0],[30,0],[15,30]], "arrow", 0, "polygon", filled=True),
                       path("zigzag", [[14,2],[16,2],[14,4],[16,4],[14,6],[16,6]])],
                      [label([40,40,44,44])])
        report = audit_scene(value, .7, max_conflict_locations=2)
        found = next(f for f in report["pages"][0]["findings"] if "conflict_locations" in f)
        self.assertEqual(len(found["conflict_locations"]), 2)
        self.assertTrue(found["truncated"])
        self.assertGreater(found["candidate_conflict_count"], 2)
        self.assertIn("worst", found)

    def test_missing_geometry_is_unmeasured(self):
        report = audit_scene(scene([], [label([1,1,3,3])]), .7)
        self.assertEqual(report["pages"][0]["scan_status"], "incomplete_inputs")

    def test_invalid_units_nonfinite_or_negative_width_are_rejected(self):
        for change in ["units", "nonfinite", "negative"]:
            value = scene([path("wall", [[0,0],[10,0]])], [label([20,20,24,24])])
            if change == "units": value["units"] = "pixels"
            if change == "nonfinite": value["pages"][0]["paths"][0]["points"][0][0] = float("nan")
            if change == "negative": value["pages"][0]["paths"][0]["width_mm"] = -.1
            with self.assertRaises(ValueError): audit_scene(value, .7)


if __name__ == "__main__":
    unittest.main()
