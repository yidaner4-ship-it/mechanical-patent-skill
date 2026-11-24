#!/usr/bin/env python3
"""Synthetic regressions for optional final-name enforcement, using stdlib only."""
import importlib.util
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from xml.sax.saxutils import escape
from zipfile import ZipFile

SCRIPT = Path(__file__).with_name('audit_component_occurrences.py')
spec = importlib.util.spec_from_file_location('component_audit', SCRIPT)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'


class FinalNamingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def document(self, paragraphs, raw=False):
        bodies = paragraphs if raw else [f'<w:p><w:r><w:t>{escape(t)}</w:t></w:r></w:p>' for t in paragraphs]
        p = self.base / 'fixture.docx'
        with ZipFile(p, 'w') as z:
            z.writestr('word/document.xml', f'<w:document xmlns:w="{NS}"><w:body>{"".join(bodies)}</w:body></w:document>')
        return p

    def config(self, count=1, strict=True, mode='required', style='bare'):
        return {'require_canonical_names': strict,
                'components': [{'number':'51', 'name':'托持件', 'aliases':['托杯']}],
                'regions':[{'name':'正文', 'start_paragraph':1, 'end_paragraph':count,
                            'mode':mode, 'style':style}], 'exceptions':[]}

    def test_legacy_alias_is_still_readable(self):
        config = self.config(); config.pop('require_canonical_names')
        r = audit.inspect(self.document(['托杯51']), config)
        self.assertEqual(r['issues'], [])
        self.assertEqual(r['occurrences'][0]['canonical_name'], '托持件')

    def test_final_alias_with_correct_number_is_not_canonical(self):
        r = audit.inspect(self.document(['托杯51']), self.config())
        self.assertEqual([x['status'] for x in r['issues']], ['noncanonical_name'])
        self.assertEqual(r['issues'][0]['label_status'], 'ok')

    def test_canonical_bare_and_numeric_parentheses_pass(self):
        config = self.config(2, style='either')
        r = audit.inspect(self.document(['托持件51', '托持件（51）']), config)
        self.assertEqual(r['issues'], [])
        self.assertEqual(r['parenthetical_name_candidates'], [])

    def test_exempt_legend_does_not_exempt_naming(self):
        r = audit.inspect(self.document(['51、托杯']), self.config(mode='exempt'))
        self.assertEqual(r['issues'][0]['status'], 'noncanonical_name')

    def test_known_parenthetical_alias_is_detected(self):
        r = audit.inspect(self.document(['51、托持件（托杯）']), self.config(mode='exempt'))
        self.assertEqual(r['issues'][0]['name'], '托杯')
        self.assertEqual(r['parenthetical_name_candidates'][0]['kind'], 'parenthetical_alias')
        self.assertEqual(r['summary']['parenthetical_naming_reviews'], 1)

    def test_unknown_legend_parentheses_require_manual_review(self):
        r = audit.inspect(self.document(['51、托持件（支承座）']), self.config(mode='exempt'))
        self.assertEqual(r['issues'], [])
        self.assertEqual(r['parenthetical_name_candidates'][0]['kind'], 'legend_parenthetical_text')
        self.assertEqual(r['summary']['parenthetical_naming_reviews'], 1)

    def test_normal_explanations_and_formula_are_preserved(self):
        p = self.document(['托持件（51）（用于支撑）；计算式（x+y）不变。'])
        r = audit.inspect(p, self.config(style='parenthesized'))
        self.assertEqual(r['issues'], [])
        self.assertEqual(r['parenthetical_name_candidates'], [])
        self.assertIn('（x+y）', r['paragraphs'][0]['text'])

    def test_legend_function_explanation_is_not_an_alias(self):
        r = audit.inspect(self.document(['51、托持件（用于支撑）']), self.config(mode='exempt'))
        self.assertEqual(r['issues'], [])
        self.assertEqual(r['parenthetical_name_candidates'], [])

    def test_old_suffix_exception_cannot_waive_final_alias(self):
        c = self.config(); c['exceptions']=[{'paragraph':1,'name':'托杯','start':0,'reason':'旧稿同号别名。'}]
        r = audit.inspect(self.document(['托杯51']), c)
        self.assertEqual(r['issues'][0]['status'], 'noncanonical_name')

    def test_precise_structure_type_exception_keeps_evidence(self):
        c = self.config(); c['exceptions']=[{'paragraph':1,'name':'托杯','start':2,
             'non_component_usage':True,'reason':'采用托杯结构在此描述形态类型，不作为该部件第二名称。'}]
        r = audit.inspect(self.document(['采用托杯结构；托持件51。']), c)
        self.assertEqual(r['issues'], [])
        self.assertEqual(r['occurrences'][0]['status'], 'accepted_exception')
        self.assertEqual(r['occurrences'][0]['naming_status'], 'noncanonical_name')

    def test_precise_parenthetical_explanation_can_be_reviewed(self):
        c = self.config(mode='exempt')
        c['parenthetical_name_exceptions']=[{'paragraph':1,'start':3,'text':'托持件（圆形结构）',
             'reason':'圆形结构为已核形态说明，未另命名；正式名仍为托持件。'}]
        r = audit.inspect(self.document(['51、托持件（圆形结构）']), c)
        self.assertEqual(r['summary']['parenthetical_naming_reviews'], 0)
        self.assertEqual(r['parenthetical_name_candidates'][0]['status'], 'accepted_exception')

    def test_stale_parenthetical_exception_is_rejected(self):
        c = self.config(mode='exempt')
        c['parenthetical_name_exceptions']=[{'paragraph':1,'start':3,'text':'托持件（圆形结构）','reason':'已核形态。'}]
        with self.assertRaisesRegex(ValueError, 'Stale parenthetical'):
            audit.inspect(self.document(['51、托持件（方形结构）']), c)

    def test_one_final_number_cannot_have_two_canonical_names(self):
        c = self.config(); c['components'].append({'number':'51','name':'托杯','aliases':[]})
        with self.assertRaisesRegex(ValueError, 'one canonical'):
            audit.inspect(self.document(['托持件51']), c)

    def test_label_error_remains_visible_alongside_naming_error(self):
        r = audit.inspect(self.document(['托杯（51）']), self.config(style='bare'))
        self.assertEqual(r['issues'][0]['status'], 'noncanonical_name')
        self.assertEqual(r['issues'][0]['label_status'], 'label_style')

    def test_name_spanning_runs_is_still_checked(self):
        p = self.document(['<w:p><w:r><w:t>托</w:t></w:r><w:r><w:t>杯51</w:t></w:r></w:p>'], raw=True)
        self.assertEqual(audit.inspect(p,self.config())['issues'][0]['status'], 'noncanonical_name')

    def test_revision_views_distinguish_historical_name(self):
        p = self.document(['<w:p><w:del><w:r><w:delText>托杯51</w:delText></w:r></w:del>'
                           '<w:ins><w:r><w:t>托持件51</w:t></w:r></w:ins></w:p>'], raw=True)
        self.assertEqual(audit.inspect(p,self.config(),'accepted')['issues'], [])
        self.assertEqual(audit.inspect(p,self.config(),'rejected')['issues'][0]['status'], 'noncanonical_name')

    def test_cli_fails_for_unreviewed_unknown_legend_candidate(self):
        p=self.document(['51、托持件（支承座）']); c=self.base/'config.json'; c.write_text(json.dumps(self.config(mode='exempt')))
        r=subprocess.run([sys.executable,str(SCRIPT),str(p),'--config',str(c),'--output',str(self.base/'audit'),'--fail-on-issues'],capture_output=True,text=True)
        self.assertEqual(r.returncode,1,r.stderr)
        self.assertTrue((self.base/'audit.csv').exists())
        with (self.base/'audit.csv').open(encoding='utf-8-sig',newline='') as stream:
            columns=next(csv.reader(stream))
        self.assertEqual(columns[:15],['occurrence_id','paragraph','source_paragraph','section',
            'start','end','name','canonical_name','expected_label','actual_label',
            'actual_style','policy','status','context','exception_reason'])
        self.assertEqual(json.loads((self.base/'audit.json').read_text())['summary']['parenthetical_naming_reviews'],1)


if __name__ == '__main__':
    unittest.main()
