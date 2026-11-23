# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
if str(PKG / "tools") not in sys.path:
    sys.path.insert(0, str(PKG / "tools"))

from check_numeral_register import check_register


SCHEMA = {
    "parts": [
        {"id": "1", "name": "壳体"},
        {"id": "2", "name": "端盖"},
    ]
}
PLAN = {
    "figures": [
        {"fig": 1, "kind": "lineart", "use_in_disclosure": True, "covers": ["1", "2"]},
        {"fig": 2, "kind": "lineart", "use_in_disclosure": True, "covers": ["1"]},
    ]
}
REGISTER_OK = {
    "parts": [
        {"id": "1", "name": "壳体", "figures": [1, 2], "claims": [1], "specification": True},
        {"id": "2", "name": "端盖", "figures": [1], "claims": [1], "specification": True},
    ],
    "figures": [
        {"fig": 1, "title": "总装", "kind": "lineart", "disclosure_only": True},
        {"fig": 2, "title": "剖视", "kind": "lineart", "disclosure_only": True},
    ],
}
CLAIMS = "1. 一种装置，包括壳体（1）和端盖（2）；其特征在于二者围成电机腔。\n"
SPEC = "本实用新型包括壳体（1）与端盖（2）。如图1所示。\n"


class NumeralRegisterTests(unittest.TestCase):
    def test_sentence_prefixes_do_not_create_cross_name_errors(self) -> None:
        register = {"parts": [{"id": "1", "name": "支撑座"}]}
        text = "包括支撑座（1）；所述支撑座（1）设有安装孔。"
        findings = check_register(register, spec_text=text)
        self.assertFalse(any(item.level == "ERROR" for item in findings), findings)
        self.assertFalse(any(item.code == "OCCURRENCE_NAME" for item in findings), findings)

    def test_registered_alias_is_the_same_entity(self) -> None:
        register = {"parts": [{"id": "1", "name": "支撑座", "aliases": ["安装座"]}]}
        findings = check_register(register, spec_text="包括支撑座（1）；所述安装座（1）固定于底板。")
        self.assertFalse(any(item.level == "ERROR" or item.code == "OCCURRENCE_NAME" for item in findings), findings)

    def test_unregistered_term_is_manual_hint_not_definite_cross_name(self) -> None:
        register = {"parts": [{"id": "1", "name": "支撑座"}]}
        findings = check_register(register, spec_text="包括支撑座（1）；承托件（1）固定于底板。")
        self.assertTrue(any(item.code == "OCCURRENCE_NAME" for item in findings))
        self.assertFalse(any(item.level == "ERROR" for item in findings), findings)

    def test_same_short_name_for_different_features_needs_context(self) -> None:
        register = {"parts": [{"id": "11", "name": "安装孔"}, {"id": "21", "name": "安装孔"}]}
        findings = check_register(register, spec_text="左板的安装孔（11）与右板的安装孔（21）相对。")
        self.assertTrue(any(item.code == "OCCURRENCE_AMBIGUOUS" for item in findings))
        self.assertFalse(any(item.level == "ERROR" for item in findings), findings)

    def test_longest_name_prevents_parent_substring_confusion(self) -> None:
        register = {"parts": [{"id": "1", "name": "壳体"}, {"id": "2", "name": "内壳体"}]}
        findings = check_register(register, spec_text="包括壳体（1）与内壳体（2）。")
        self.assertFalse(any(item.level == "ERROR" for item in findings), findings)

    def test_unregistered_name_modifier_is_not_silently_discarded(self) -> None:
        register = {"parts": [{"id": "1", "name": "壳体"}]}
        findings = check_register(register, spec_text="壳体（1）包围内壳体（1）。")
        self.assertTrue(any(item.code == "OCCURRENCE_NAME" for item in findings))
        self.assertFalse(any(item.level == "ERROR" for item in findings), findings)

    def test_subfeatures_share_the_number_space_without_becoming_parts(self) -> None:
        schema = {"parts": [{"id": "1", "name": "支撑座"}], "features": [
            {"id": "11", "name": "安装孔", "parent_part_id": "1", "kind": "hole"}
        ]}
        register = {"parts": [{"id": "1", "name": "支撑座"}], "features": [
            {"id": "11", "name": "安装孔", "parent_part_id": "1"}
        ]}
        findings = check_register(register, schema=schema, spec_text="支撑座（1）具有安装孔（11）。")
        self.assertFalse(any(item.level == "ERROR" for item in findings), findings)

    def test_wrong_subfeature_parent_is_error(self) -> None:
        schema = {"parts": [{"id": "1", "name": "支撑座"}], "features": [
            {"id": "11", "name": "安装孔", "parent_part_id": "9"}
        ]}
        register = {"parts": schema["parts"], "features": schema["features"]}
        self.assertTrue(any(item.code == "FEATURE_PARENT_UNKNOWN" for item in check_register(register, schema=schema)))

    def test_subfeature_cannot_reuse_a_part_number(self) -> None:
        schema = {"parts": [{"id": "1", "name": "支撑座"}], "features": [
            {"id": "1", "name": "安装孔", "parent_part_id": "1"}
        ]}
        register = {"parts": [{"id": "1", "name": "支撑座"}]}
        self.assertTrue(any(item.code == "SCHEMA_DUP_ID" for item in check_register(register, schema=schema)))

    def test_conflicting_feature_number_is_error(self) -> None:
        register = {"parts": [{"id": "1", "name": "支撑座"}], "features": [
            {"id": "11", "reference_number": "12", "name": "安装孔", "parent_part_id": "1"}
        ]}
        self.assertTrue(any(item.code == "FEATURE_NUMBER_CONFLICT" for item in check_register(register)))

    def test_aligned_pass(self) -> None:
        findings = check_register(
            REGISTER_OK,
            schema=SCHEMA,
            figure_plan=PLAN,
            claims_text=CLAIMS,
            spec_text=SPEC,
        )
        self.assertEqual([item for item in findings if item.level == "ERROR"], [])

    def test_schema_part_missing(self) -> None:
        slim = {
            "parts": [REGISTER_OK["parts"][0]],
            "figures": REGISTER_OK["figures"],
        }
        codes = {item.code for item in check_register(slim, schema=SCHEMA, figure_plan=PLAN)}
        self.assertIn("SCHEMA_MISSING", codes)

    def test_figure_not_registered(self) -> None:
        slim = {
            "parts": [
                {"id": "1", "name": "壳体", "figures": [1], "claims": [1], "specification": True},
                {"id": "2", "name": "端盖", "figures": [1], "claims": [1], "specification": True},
            ],
            "figures": [{"fig": 1, "title": "总装"}],
        }
        codes = {item.code for item in check_register(slim, schema=SCHEMA, figure_plan=PLAN)}
        self.assertIn("FIG_UNREGISTERED", codes)

    def test_claim_mark_missing(self) -> None:
        findings = check_register(
            REGISTER_OK,
            schema=SCHEMA,
            figure_plan=PLAN,
            claims_text="1. 一种装置，包括若干零件；其特征在于围成腔体。\n",
            spec_text=SPEC,
        )
        codes = {item.code for item in findings if item.level == "ERROR"}
        self.assertIn("CLAIM_MARK_MISSING", codes)

    def test_cross_name_and_unregistered_mark(self) -> None:
        findings = check_register(
            REGISTER_OK,
            schema=SCHEMA,
            figure_plan=PLAN,
            claims_text=CLAIMS,
            spec_text="本实用新型包括壳体（1）与端盖（1）。另有垫片（9）。如图1所示。\n",
        )
        codes = {item.code for item in findings if item.level == "ERROR"}
        self.assertIn("CROSS_NAME", codes)
        self.assertIn("MARK_UNREGISTERED", codes)


if __name__ == "__main__":
    unittest.main()
