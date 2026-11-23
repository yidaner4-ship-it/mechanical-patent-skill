# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
if str(PKG / "tools") not in sys.path:
    sys.path.insert(0, str(PKG / "tools"))

from audit_claims import audit, references, summarize


GOOD = """
1. 一种壳体装配方法，包括提供电机腔壳体；其特征在于，将减速器腔与电机腔隔开，并使电机沿花键轴向抽拔。
2. 根据权利要求1所述的方法，其特征在于，冷却水套仅布置于电机腔外壁。
"""

INDEPENDENT_REF = """
1. 一种装置，根据权利要求2所述的装置，其特征在于包括壳体。
2. 一种装置，其特征在于包括盖板。
"""

SKIP_NUMBERS = """
1. 一种方法，其特征在于包括采集步骤以及处理步骤。
3. 根据权利要求1所述的方法，其特征在于处理步骤输出缺陷检测结果。
"""

PROMO = """
1. 一种方法，其特征在于采用新算法从而显著提高检测精度并得到缺陷检测结果。
"""


class AuditClaimsTests(unittest.TestCase):
    def test_alternative_and_range_references_are_complete(self) -> None:
        self.assertEqual(references("根据权利要求1或3所述的装置"), [1, 3])
        self.assertEqual(references("根据权利要求1、3或5所述的装置"), [1, 3, 5])
        self.assertEqual(references("根据权利要求1至3或5所述的装置"), [1, 2, 3, 5])

    def test_good_claims_pass(self) -> None:
        findings = audit(GOOD)
        errors, _warnings = summarize(findings)
        self.assertEqual(errors, 0)

    def test_independent_cannot_reference(self) -> None:
        codes = {item.code for item in audit(INDEPENDENT_REF) if item.level == "ERROR"}
        self.assertIn("INDEPENDENT_REFERENCE", codes)
        self.assertIn("FORWARD_REFERENCE", codes)

    def test_number_sequence(self) -> None:
        codes = {item.code for item in audit(SKIP_NUMBERS) if item.level == "ERROR"}
        self.assertIn("NUMBER_SEQUENCE", codes)

    def test_promo_is_warning_only(self) -> None:
        findings = audit(PROMO)
        errors, warnings = summarize(findings)
        self.assertEqual(errors, 0)
        self.assertGreaterEqual(warnings, 1)
        self.assertTrue(any(item.code == "RESULT_LANGUAGE" for item in findings))

    def test_placeholder_is_error(self) -> None:
        text = "1. 一种方法，其特征在于[待确认：步骤未写]包括采集。\n"
        codes = {item.code for item in audit(text) if item.level == "ERROR"}
        self.assertIn("PLACEHOLDER", codes)

    def test_second_independent_system_skips_no_reference(self) -> None:
        text = """
1. 一种调度方法，其特征在于包括以下步骤：步骤一，采集节点指标。
2. 一种调度系统，其特征在于包括配置中心和调度器。
"""
        findings = audit(text)
        self.assertFalse(
            any(item.code == "NO_REFERENCE" for item in findings),
            msg=[(item.claim, item.code) for item in findings],
        )

    def test_component_and_complete_product_can_be_two_independents(self) -> None:
        text = """
1. 一种插拔组件，其特征在于，包括插拔底座和连接于插拔底座的插拔上盖。
2. 一种运动垫，其特征在于，包括垫体以及设置于所述垫体上的插拔组件。
"""
        self.assertFalse(any(item.code == "NO_REFERENCE" for item in audit(text)))

    def test_explicit_product_includes_opening_is_recognized(self) -> None:
        text = """
1. 一种插拔组件，其特征在于，包括插拔底座和插拔上盖。
2. 一种易于组装的防洪挡板，包括立柱和与立柱可拆卸连接的挡板。
"""
        self.assertFalse(any(item.code == "NO_REFERENCE" for item in audit(text)))

    def test_yizhong_alone_does_not_hide_a_missing_dependency(self) -> None:
        text = """
1. 一种插拔组件，其特征在于，包括插拔底座和插拔上盖。
2. 一种进一步的方案，其特征在于，所述插拔上盖与插拔底座可拆卸连接。
"""
        self.assertTrue(any(item.claim == 2 and item.code == "NO_REFERENCE" for item in audit(text)))

    def test_dependent_without_reference_still_warns(self) -> None:
        text = """
1. 一种调度方法，其特征在于包括以下步骤：步骤一，采集节点指标。
2. 进一步，冷却水套仅布置于电机腔外壁并完成装配。
"""
        self.assertTrue(any(item.code == "NO_REFERENCE" for item in audit(text)))


if __name__ == "__main__":
    unittest.main()
