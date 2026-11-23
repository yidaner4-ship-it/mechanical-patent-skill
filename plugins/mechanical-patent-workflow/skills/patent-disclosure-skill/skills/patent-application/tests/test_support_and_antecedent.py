# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
if str(PKG / "tools") not in sys.path:
    sys.path.insert(0, str(PKG / "tools"))

from audit_claims import audit, summarize
from check_support import audit_dir


class SaidAntecedentTests(unittest.TestCase):
    def test_generic_product_titles_in_reference_heads_are_not_components(self) -> None:
        for product in ("夹具", "易于组装的防洪挡板"):
            with self.subTest(product=product):
                text = (
                    f"1. 一种{product}，其特征在于，包括底座和夹板。\n"
                    f"2. 根据权利要求1所述的{product}，其特征在于，还包括锁紧套。\n"
                    f"3. 根据权利要求2所述的{product}，其特征在于，所述锁紧套与夹板连接。\n"
                )
                self.assertFalse(any(item.code == "SAID_ANTECEDENT" for item in audit(text)), audit(text))

    def test_common_stem_is_not_antecedent_basis(self) -> None:
        for marker in ("", "（3）"):
            with self.subTest(marker=marker):
                text = (
                    "1. 一种夹具，其特征在于，包括底座、夹板和锁止块。\n"
                    f"2. 根据权利要求1所述的夹具，其特征在于，所述锁止杆{marker}与夹板连接。\n"
                )
                findings = [item for item in audit(text) if item.claim == 2 and item.code == "SAID_ANTECEDENT"]
                self.assertTrue(findings)
                self.assertIn("锁止杆", findings[0].message)

    def test_component_name_is_not_a_longer_components_prefix(self) -> None:
        text = (
            "1. 一种夹具，其特征在于，包括底座、夹板和锁止杆座。\n"
            "2. 根据权利要求1所述的夹具，其特征在于，所述锁止杆与夹板连接。\n"
        )
        self.assertTrue(any(item.claim == 2 and item.code == "SAID_ANTECEDENT" for item in audit(text)))

    def test_normal_mechanical_predicates_and_compound_names_pass(self) -> None:
        for term, predicate in (
            ("底座", "设有安装孔"),
            ("底座", "的上端与夹板连接"),
            ("限位连接件", "与夹板连接"),
            ("第一设置部", "设有安装孔"),
            ("第二安装座", "（3）与夹板连接"),
        ):
            with self.subTest(term=term, predicate=predicate):
                text = (
                    f"1. 一种夹具，其特征在于，包括夹板和{term}。\n"
                    f"2. 根据权利要求1所述的夹具，其特征在于，所述{term}{predicate}。\n"
                )
                self.assertFalse(any(item.claim == 2 and item.code == "SAID_ANTECEDENT" for item in audit(text)), audit(text))

    def test_confirmed_register_alias_can_supply_basis(self) -> None:
        text = (
            "1. 一种夹具，其特征在于，包括底座、夹板和支撑座。\n"
            "2. 根据权利要求1所述的夹具，其特征在于，所述安装座与夹板连接。\n"
        )
        self.assertTrue(any(item.claim == 2 and item.code == "SAID_ANTECEDENT" for item in audit(text)))
        register = {"parts": [{"id": "3", "name": "支撑座", "aliases": ["安装座"]}]}
        self.assertFalse(any(item.claim == 2 and item.code == "SAID_ANTECEDENT" for item in audit(text, register=register)))

    def test_unreferenced_sibling_cannot_supply_a_part(self) -> None:
        text = (
            "1. 一种夹持装置，其特征在于包括底座和夹臂。\n"
            "2. 根据权利要求1所述的装置，其特征在于，还包括锁止杆。\n"
            "3. 根据权利要求1所述的装置，其特征在于，所述锁止杆与底座连接。\n"
        )
        self.assertTrue(any(item.claim == 3 and item.code == "SAID_ANTECEDENT" for item in audit(text)))

    def test_actual_transitive_chain_supplies_a_part(self) -> None:
        text = (
            "1. 一种夹持装置，其特征在于包括底座和夹臂。\n"
            "2. 根据权利要求1所述的装置，其特征在于，还包括锁止杆。\n"
            "3. 根据权利要求2所述的装置，其特征在于，所述锁止杆与底座连接。\n"
        )
        self.assertFalse(any(item.claim == 3 and item.code == "SAID_ANTECEDENT" for item in audit(text)))

    def test_alternative_paths_are_checked_separately(self) -> None:
        text = (
            "1. 一种夹持装置，其特征在于包括底座和夹臂。\n"
            "2. 根据权利要求1所述的装置，其特征在于，还包括锁止杆。\n"
            "3. 根据权利要求1或2所述的装置，其特征在于，所述锁止杆与底座连接。\n"
        )
        findings = [item for item in audit(text) if item.claim == 3 and item.code == "SAID_ANTECEDENT"]
        self.assertTrue(findings)
        self.assertIn("路径（1）", findings[0].message)

    def test_term_shared_by_all_alternative_paths_passes(self) -> None:
        text = (
            "1. 一种夹持装置，其特征在于包括底座和夹臂。\n"
            "2. 根据权利要求1所述的装置，其特征在于，还包括锁止杆。\n"
            "3. 根据权利要求1或2所述的装置，其特征在于，所述夹臂与底座连接。\n"
        )
        self.assertFalse(any(item.claim == 3 and item.code == "SAID_ANTECEDENT" for item in audit(text)))

    def test_local_introduction_supplies_all_paths(self) -> None:
        text = (
            "1. 一种夹持装置，其特征在于包括底座和夹臂。\n"
            "2. 根据权利要求1所述的装置，其特征在于，还包括连接销。\n"
            "3. 根据权利要求1或2所述的装置，其特征在于，还包括锁止杆，所述锁止杆与底座连接。\n"
        )
        self.assertFalse(any(item.claim == 3 and item.code == "SAID_ANTECEDENT" for item in audit(text)))

    def test_said_without_first_mention_warns(self) -> None:
        text = (
            "1. 一种调度方法，其特征在于采集节点指标。\n"
            "2. 根据权利要求1所述的方法，其特征在于所述匹配分大于阈值。\n"
        )
        codes = [item.code for item in audit(text) if item.level == "WARNING"]
        self.assertIn("SAID_ANTECEDENT", codes)

    def test_said_after_introduce_passes(self) -> None:
        text = (
            "1. 一种调度方法，其特征在于计算匹配分。\n"
            "2. 根据权利要求1所述的方法，其特征在于所述匹配分大于阈值。\n"
        )
        codes = [item.code for item in audit(text) if item.code == "SAID_ANTECEDENT"]
        self.assertEqual(codes, [])


class SupportCheckTests(unittest.TestCase):
    def test_step_mismatch_and_abstract_length(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "figures").mkdir()
            (root / "权利要求书.md").write_text(
                "1. 一种方法，包括以下步骤：步骤一，采集；步骤二，打分。\n",
                encoding="utf-8",
            )
            (root / "说明书.md").write_text(
                "本发明涉及调度。图1为框图。图2为流程。采集模块用于采集。\n",
                encoding="utf-8",
            )
            (root / "说明书摘要.md").write_text("公开。" + "字" * 320, encoding="utf-8")
            (root / "figures" / "invention_figures.yaml").write_text(
                """
figures:
  - fig: 1
    kind: block_diagram
    columns:
      - id: a
        nodes:
          - {id: n1, label: 采集模块}
  - fig: 2
    kind: flowchart
    nodes:
      - {id: s1, label: "步骤一，采集"}
      - {id: s2, label: "步骤二，派发"}
""",
                encoding="utf-8",
            )
            findings = audit_dir(root)
            codes = {item.code for item in findings}
            self.assertIn("STEP_MISMATCH", codes)
            self.assertIn("ABSTRACT_TOO_LONG", codes)

    def test_aligned_steps_pass_step_check(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "figures").mkdir()
            (root / "权利要求书.md").write_text(
                "1. 一种方法，包括以下步骤：步骤一，采集；步骤二，打分。\n",
                encoding="utf-8",
            )
            (root / "说明书.md").write_text(
                "图1为框图。图2为流程。采集模块用于采集。\n",
                encoding="utf-8",
            )
            (root / "说明书摘要.md").write_text(
                "本发明涉及调度。现有按队列派发不足。本发明通过采集与打分完成派发。",
                encoding="utf-8",
            )
            (root / "figures" / "invention_figures.yaml").write_text(
                """
figures:
  - fig: 1
    kind: block_diagram
    columns:
      - id: a
        nodes:
          - {id: n1, label: 采集模块}
  - fig: 2
    kind: flowchart
    abstract: true
    nodes:
      - {id: s1, label: "步骤一，采集"}
      - {id: s2, label: "步骤二，打分"}
""",
                encoding="utf-8",
            )
            codes = {item.code for item in audit_dir(root)}
            self.assertNotIn("STEP_MISMATCH", codes)
            self.assertNotIn("ABSTRACT_TOO_LONG", codes)
            self.assertNotIn("MODULE_MISSING_SPEC", codes)


if __name__ == "__main__":
    unittest.main()
