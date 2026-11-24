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

    def test_forbidden_content_and_required_embodiment_have_separate_policies(self):
        c = self.config(2)
        c['regions'] = [
            {'name':'实用新型内容', 'start_paragraph':1, 'end_paragraph':1, 'mode':'forbidden'},
            {'name':'具体实施方式', 'start_paragraph':2, 'end_paragraph':2,
             'mode':'required', 'style':'bare'},
        ]
        r = audit.inspect(self.document(['托持件用于支撑。', '托持件51用于支撑。']), c)
        self.assertEqual(r['issues'], [])
        self.assertEqual([(x['policy'], x['status'], x['actual_label']) for x in r['occurrences']],
                         [('forbidden', 'ok', ''), ('required', 'ok', '51')])

    def test_forbidden_rejects_bare_and_parenthesized_component_labels(self):
        r = audit.inspect(self.document(['托持件51；托持件（51）；托持件99。']),
                          self.config(mode='forbidden'))
        self.assertEqual([x['status'] for x in r['issues']], ['unexpected_label'] * 3)
        self.assertEqual([x['actual_label'] for x in r['issues']], ['51', '51', '99'])
        self.assertEqual([x['label_status'] for x in r['issues']], ['unexpected_label'] * 3)

    def test_forbidden_does_not_exempt_an_unnumbered_alias(self):
        r = audit.inspect(self.document(['托杯用于支撑。']), self.config(mode='forbidden'))
        self.assertEqual([x['status'] for x in r['issues']], ['noncanonical_name'])
        self.assertEqual(r['issues'][0]['actual_label'], '')
        self.assertEqual(r['issues'][0]['label_status'], 'ok')

    def test_forbidden_alias_keeps_both_naming_and_label_failures(self):
        r = audit.inspect(self.document(['托杯（51）']), self.config(mode='forbidden'))
        self.assertEqual(r['issues'][0]['status'], 'noncanonical_name')
        self.assertEqual(r['issues'][0]['label_status'], 'unexpected_label')

    def test_forbidden_preserves_figure_references_parameters_and_explanations(self):
        text = ('如图2所示，托持件的厚度为2mm；托持件2mm厚；托持件2.5mm厚；'
                '托持件2×3mm；托持件2-3mm；托持件2×x；托持件2×(x+y)；托持件2个；'
                '托持件（用于支撑）；计算式（x+y）不变。')
        r = audit.inspect(self.document([text]), self.config(mode='forbidden'))
        self.assertEqual(r['issues'], [])
        self.assertEqual(r['parenthetical_name_candidates'], [])
        self.assertEqual(r['paragraphs'][0]['text'], text)
        self.assertTrue(all(x['actual_label'] == '' for x in r['occurrences']))

    def test_forbidden_label_before_prose_punctuation_is_not_a_quantity(self):
        text = '托持件51—用于支撑；托持件51-用于支撑；托持件51+支承面；托持件51=支撑结构。'
        r = audit.inspect(self.document([text]), self.config(mode='forbidden'))
        self.assertEqual([x['status'] for x in r['issues']], ['unexpected_label'] * 4)
        self.assertEqual([x['actual_label'] for x in r['issues']], ['51'] * 4)

    def test_existing_modes_keep_historical_suffix_behavior(self):
        p = self.document(['托杯51；托持件；托持件99；托持件（51）；托持件2mm。'])
        expected = {
            'required':['ok', 'missing_label', 'unknown_label', 'label_style', 'unknown_label'],
            'optional':['ok', 'optional_unlabeled', 'unknown_label', 'label_style', 'unknown_label'],
            'exempt':['exempt_section'] * 5,
        }
        for mode, statuses in expected.items():
            with self.subTest(mode=mode):
                c = self.config(mode=mode); c.pop('require_canonical_names')
                r = audit.inspect(p, c)
                self.assertEqual([x['status'] for x in r['occurrences']], statuses)
                self.assertEqual([x['actual_label'] for x in r['occurrences']], ['51', '', '99', '51', '2'])
                self.assertTrue(all(x['naming_status'] == 'not_checked' for x in r['occurrences']))

    def test_cli_fails_for_forbidden_label(self):
        p = self.document(['托持件（51）'])
        c = self.base / 'forbidden.json'; c.write_text(json.dumps(self.config(mode='forbidden')))
        output = self.base / 'forbidden-audit'
        r = subprocess.run([sys.executable, str(SCRIPT), str(p), '--config', str(c),
                            '--output', str(output), '--fail-on-issues'], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stderr)
        result = json.loads(output.with_suffix('.json').read_text())
        self.assertEqual(result['summary']['issues'], 1)
        self.assertEqual(result['issues'][0]['status'], 'unexpected_label')

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
