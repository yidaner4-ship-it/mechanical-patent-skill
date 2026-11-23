from __future__ import annotations
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
from image_gen import decide_mode, is_qualified_existing_lineart, GEN_EXISTING, GEN_CAD, GEN_REVIEW
from structure_entities import entity_index, entity_errors
from check_source_parts import check_source_parts
from structure_lineart_gate import validate_brief
from structure_callout_overlay import drawing_metrics, render_view, validate_manifest, leader_geometry, leader_records

class TestMechanicalCADPipeline(unittest.TestCase):
    def test_cad_source_needs_real_preparation_then_explicit_lineart_promotion(self):
        with tempfile.TemporaryDirectory() as td:
            case = Path(td)
            (case / "drawing.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="80"/>')
            raw = {"kind":"cad", "path":"drawing.svg", "score":90}
            self.assertFalse(is_qualified_existing_lineart(raw, case))
            self.assertEqual(decide_mode({"patent_type":"invention", "subject_kind":"mechanical_product", "figures":[raw]}, case)["mode"], GEN_CAD)
            promoted = dict(raw, kind="lineart", source_kind="cad", source_ref="source-model.step", geometry_verified=True, drawing_ready=True)
            self.assertTrue(is_qualified_existing_lineart(promoted, case))
            self.assertEqual(decide_mode({"patent_type":"invention", "subject_kind":"mechanical_product", "figures":[promoted]}, case)["mode"], GEN_EXISTING)
            for key in ("source_ref", "geometry_verified", "drawing_ready"):
                invalid = dict(promoted); invalid.pop(key)
                self.assertFalse(is_qualified_existing_lineart(invalid, case), key)
            self.assertEqual(decide_mode({"patent_type":"utility_model", "figures":[]}, case)["mode"], GEN_REVIEW)

    def test_features_share_references_without_becoming_physical_layers(self):
        structure = {"parts":[{"id":"1","name":"壳体"}], "features":[{"id":"11","name":"导向槽","parent_part_id":"1","kind":"slot","source":"已核CAD槽面","visible_in":[1]}]}
        self.assertEqual(entity_index(structure), {"1":"壳体", "11":"导向槽"})
        self.assertEqual(entity_errors(structure), [])
        findings = check_source_parts(Path('.'), structure=structure, plan={"figures":[{"fig":1,"path":"drawing.svg","covers":["1","11"]}]}, disclosure_text="壳体（1）设有导向槽（11）。")
        self.assertFalse([x for x in findings if x.level == "ERROR"], findings)
        wrong = {"parts":structure["parts"],"features":[dict(structure["features"][0], parent_part_id="99")]}
        self.assertTrue(entity_errors(wrong))
        mismatch = {"parts":[{"id":"1","name":"壳体"}], "features":[dict(structure["features"][0], reference_number="12")]}
        self.assertTrue(entity_errors(mismatch))
        with tempfile.TemporaryDirectory() as td:
            (Path(td)/'source.svg').write_text('<svg/>')
            brief={"enabled":True,"patent_type":"invention","structure_summary":"壳体与导向槽", "parts_legend":[{"id":"1","name":"壳体"},{"id":"11","name":"导向槽"}], "views":[{"source_paths":["source.svg"],"visible_part_ids":["1","11"]}]}
            self.assertEqual(validate_brief(brief,Path(td),structure=structure),[])

    def test_overlay_uses_paper_scale_and_preserves_confirmed_gap_anchor(self):
        with tempfile.TemporaryDirectory() as td:
            case=Path(td)
            (case/'base.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="600" viewBox="0 0 1000 600"><rect x="200" y="200" width="300" height="200" fill="none" stroke="black"/></svg>')
            view={"base_svg_path":"base.svg","output_svg_path":"out.svg","paper_width_mm":160,"callouts":[{"id":"1","name":"壳体","anchor":[0.4,0.5],"label":[0.47,0.52],"target_kind":"face","marker_type":"primary_arrow","anchor_confirmed":True},{"id":"11","name":"间隙","anchor":[0.6,0.5],"label":[0.67,0.54],"target_kind":"gap","label_placement":"internal","anchor_confirmed":True}]}
            before=json.loads(json.dumps(view))
            with patch('structure_callout_overlay.autolayout_view') as auto:
                output=render_view(view,case)
                auto.assert_not_called()
            self.assertEqual(view,before)
            text=output.read_text()
            root=ET.fromstring(text)
            self.assertEqual(root.attrib['width'],'160.000000mm')
            self.assertEqual(root.attrib['data-drafting-status'],'requires_visual_review')
            ns={'s':'http://www.w3.org/2000/svg'}
            metrics=drawing_metrics(view,1000,600)
            label=root.find('.//s:text',ns)
            self.assertEqual(label.attrib['font-family'],'Times-Roman')
            self.assertEqual(label.attrib['stroke'],'none')
            self.assertAlmostEqual(float(label.attrib['font-size'])/metrics['units_per_pt'],12,places=5)
            group=root.find('.//s:g[@id="structure-callouts"]',ns)
            self.assertAlmostEqual(float(group.attrib['stroke-width'])/metrics['units_per_pt'],0.52,places=5)
            self.assertIsNotNone(root.find('.//s:polygon',ns))
            gap=root.find('.//s:g[@data-part-id="11"]/s:path',ns)
            self.assertTrue(gap.attrib['d'].startswith('M 600.000000,300.000000'))
            view.pop('paper_width_mm'); view['output_svg_path']='preview.svg'
            self.assertIn('preview_missing_paper_size',render_view(view,case).read_text())

    def test_arrow_axis_and_s_initial_tangent_are_smoothly_joined(self):
        view={"paper_width_mm":160}
        item={"id":"1","anchor":[0.4,0.5],"label":[0.48,0.55],"marker_type":"primary_arrow"}
        for axis in (None,[1,0],[0.8,0.6]):
            row=dict(item)
            if axis is not None: row['arrow_axis']=axis
            g=leader_geometry(row,view,1000,600)
            a=(g['start'][0]-g['anchor'][0],g['start'][1]-g['anchor'][1])
            t=(g['c1'][0]-g['start'][0],g['c1'][1]-g['start'][1])
            self.assertAlmostEqual(a[0]*t[1]-a[1]*t[0],0,places=7)
            self.assertGreater(a[0]*t[0]+a[1]*t[1],0)
            self.assertEqual(g['anchor'],(400,300))
            self.assertGreater(g['s_arc_length_mm'],0)
        long=dict(item,label=[0.9,0.9])
        record=leader_records(dict(view,callouts=[long]),1000,600)[0]
        self.assertTrue(record['warnings'])
        self.assertEqual(record['review_status'],'requires_visual_review')
        self.assertAlmostEqual(record['nominal_s_arc_length_mm'],6.311894430073415)
        preview=leader_records({'callouts':[item]},1000,600)[0]
        self.assertIsNone(preview['s_arc_length_mm'])

    def test_nonzero_cad_viewbox_origin_is_kept_when_placing_marks(self):
        with tempfile.TemporaryDirectory() as td:
            case=Path(td)
            (case/'base.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="160mm" height="96mm" viewBox="-200 -100 1000 600"><path d="M -100 0 L 500 0"/></svg>')
            view={"base_svg_path":"base.svg","output_svg_path":"out.svg","paper_width_mm":160,"callouts":[{"id":"1","anchor":[0.4,0.5],"label":[0.47,0.52],"anchor_confirmed":True}]}
            output=render_view(view,case)
            text=output.read_text()
            self.assertIn('translate(-200.000000 -100.000000)',text)
            self.assertIn('width="160.000000mm"',text)

    def test_duplicate_same_entity_can_be_marked_in_distinct_positions(self):
        with tempfile.TemporaryDirectory() as td:
            case=Path(td); (case/'base.svg').write_text('<svg width="100" height="80"/>')
            view={"base_svg_path":"base.svg","output_svg_path":"out.svg","callouts":[{"id":"1","anchor":[0.2,0.2],"label":[0.1,0.1]},{"id":"1","anchor":[0.8,0.8],"label":[0.9,0.9]}]}
            self.assertEqual(validate_manifest({"version":1,"views":[view]},case,structure={"parts":[{"id":"1","name":"壳体"}]}),[])

if __name__=='__main__': unittest.main()
