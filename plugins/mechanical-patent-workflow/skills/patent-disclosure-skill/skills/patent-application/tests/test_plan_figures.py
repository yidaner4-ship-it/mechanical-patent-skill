# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
if str(PKG / "tools") not in sys.path:
    sys.path.insert(0, str(PKG / "tools"))

from plan_figures import build_plan, suggest_figures, validate_plan


class PlanFiguresTests(unittest.TestCase):
    def test_method_claim_gets_flowchart(self) -> None:
        claims = "1. 一种调度方法，包括以下步骤：步骤一，采集；步骤二，打分。\n"
        kinds = [item["kind"] for item in suggest_figures(claims, patent_type="invention")]
        self.assertIn("flowchart", kinds)

    def test_internal_cavity_gets_section(self) -> None:
        claims = "1. 一种装置，包括壳体，所述壳体内设有冷却腔体。\n"
        kinds = [item["kind"] for item in suggest_figures(claims, patent_type="invention")]
        self.assertIn("section", kinds)
        self.assertNotIn("block_diagram", kinds)
        self.assertIn("lineart", kinds)

    def test_disclosure_lineart_kept_and_claim_kind_appended(self) -> None:
        plan = {
            "figures": [
                {
                    "fig": 1,
                    "kind": "lineart",
                    "use_in_disclosure": True,
                    "covers": ["1"],
                    "reason": "总装",
                    "relates_to": [],
                }
            ]
        }
        claims = "1. 一种装置，所述壳体可拆卸连接端盖。\n"
        figs = suggest_figures(claims, patent_type="utility_model", disclosure_plan=plan)
        kinds = [item["kind"] for item in figs]
        self.assertIn("lineart", kinds)
        self.assertIn("exploded", kinds)
        exploded = next(item for item in figs if item["kind"] == "exploded")
        self.assertEqual(exploded["source"], "pending")

    def test_validate_requires_reason(self) -> None:
        findings = validate_plan({"figures": [{"fig": 1, "kind": "flowchart", "reason": "", "covers": []}]})
        self.assertIn("NO_REASON", {item.code for item in findings})

    def test_build_plan_schema(self) -> None:
        plan = build_plan("1. 一种方法，包括以下步骤：步骤一，采集。\n")
        self.assertEqual(plan["$schema"], "application_figure_plan")
        self.assertTrue(plan["figures"])

    def test_mechanical_name_does_not_switch_to_algorithm_figures(self) -> None:
        for name in ("夹持装置", "夹具", "支架"):
            plan = build_plan(f"1. 一种{name}，包括底座和转动连接于所述底座的夹爪。")
            self.assertEqual(plan["subject_kind"], "mechanical_product")
            self.assertEqual([f["kind"] for f in plan["figures"]], ["lineart"])
            self.assertEqual(plan["figures"][0]["source"], "pending")

    def test_mechanical_module_is_not_a_software_system(self) -> None:
        figs = suggest_figures("1. 一种导向模块，包括底座以及设置于底座的导轨。")
        self.assertFalse({"flowchart", "block_diagram"} & {f["kind"] for f in figs})

    def test_unknown_subject_does_not_invent_diagram(self) -> None:
        plan = build_plan("1. 一种装置，其特征在于，包括功能模块。")
        self.assertEqual(plan["subject_kind"], "unknown")
        self.assertEqual(plan["figures"], [])
        self.assertIn("SUBJECT_UNCONFIRMED", {f.code for f in validate_plan(plan)})

    def test_software_system_still_gets_block_diagram(self) -> None:
        plan = build_plan("1. 一种信号处理系统，包括处理器和存储器。")
        self.assertEqual(plan["subject_kind"], "software_system")
        self.assertIn("block_diagram", {f["kind"] for f in plan["figures"]})

    def test_explicit_subject_overrides_ambiguous_title(self) -> None:
        plan = build_plan("1. 一种装置，包括第一构件和第二构件。", subject_kind="mechanical_product")
        self.assertEqual(plan["subject_kind"], "mechanical_product")
        self.assertEqual(plan["figures"][0]["kind"], "lineart")

    def test_mechanical_invention_inherits_structural_plan(self) -> None:
        disclosure = {"figures": [{"fig": 3, "kind": "lineart", "path": "assembly.svg",
                                   "covers": ["1"], "use_in_disclosure": True, "reason": "总装"}]}
        plan = build_plan("1. 一种装置，包括第一构件。", disclosure_plan=disclosure)
        self.assertEqual(plan["subject_kind"], "mechanical_product")
        self.assertEqual(plan["figures"][0]["path"], "assembly.svg")
        self.assertEqual(len(plan["figures"]), 1)

    def test_product_and_method_preserve_both_view_families(self) -> None:
        plan = build_plan("1. 一种夹具，包括底座和转动连接于底座的夹爪。\n2. 一种夹持方法，包括以下步骤：步骤一，转动夹爪。")
        self.assertEqual(plan["subject_kind"], "mixed")
        self.assertTrue({"lineart", "flowchart"}.issubset({f["kind"] for f in plan["figures"]}))

    def test_explicit_mechanical_plan_rejects_algorithm_kind(self) -> None:
        findings = validate_plan({"subject_kind": "mechanical_product", "figures": [
            {"fig": 1, "kind": "flowchart", "reason": "错误路径", "covers": []}]})
        self.assertIn("SUBJECT_KIND_CONFLICT", {f.code for f in findings})


if __name__ == "__main__":
    unittest.main()
