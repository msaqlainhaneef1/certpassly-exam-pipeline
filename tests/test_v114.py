#!/usr/bin/env python3
"""v1.1.4: official weight wording, published question counts, import conformance."""
from __future__ import annotations
import json, sys, tempfile, unittest
from pathlib import Path

SKILL=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL/'scripts'))
import source_text
import check_import_conformance as CIC

class WeightPhrases(unittest.TestCase):
    def test_single_percent_colon_form(self):
        page='The exam outline. Solution Positioning: 14% Describe Data 360 key terminology.'
        d=dict(weight_min_pct=14, weight_max_pct=14)
        self.assertTrue(source_text.weight_on_page('Solution Positioning', d, page))

    def test_range_hyphen_form_still_accepted(self):
        page='Manage identities (40-45%) Configure users'
        d=dict(weight_min_pct=40, weight_max_pct=45)
        self.assertTrue(source_text.weight_on_page('Manage identities', d, page))

    def test_range_en_dash_normalised(self):
        page='Manage identities (40\u201345%) Configure users'
        d=dict(weight_min_pct=40, weight_max_pct=45)
        self.assertTrue(source_text.weight_on_page('Manage identities', d, page))

    def test_wrong_weight_rejected(self):
        page='Solution Positioning: 14% '
        d=dict(weight_min_pct=13, weight_max_pct=13)
        self.assertFalse(source_text.weight_on_page('Solution Positioning', d, page))

    def test_published_helper(self):
        self.assertTrue(source_text.published({'value':60}))
        self.assertFalse(source_text.published({'value':None,'reason':'not published by the vendor'}))
        self.assertFalse(source_text.published({}))

class ImportConformance(unittest.TestCase):
    def _bank(self, tmp, *, anf=(), researched=(), typ='single_choice'):
        out=Path(tmp)/'out'/'EX'
        imp=out/'import'; imp.mkdir(parents=True)
        fmt=SKILL/'reference'/'site-format'/'v1'
        # copy templates as empty contract files + required sidecars the pipeline emits
        for p in (fmt/'csv_templates').glob('*.csv'):
            (imp/p.name).write_bytes(p.read_bytes())
        extras=json.loads((fmt/'import_files.json').read_text())['sidecar_csv_files']
        for name, headers in extras.items():
            with (imp/name).open('w',encoding='utf-8',newline='') as f:
                f.write(','.join(headers)+'\n')
        questions=[]
        excl=list(anf)
        for k in ['q001']+list(anf)+list(researched):
            rec=dict(question_key=k, question_type=typ, answer_key_status='as_in_source_file',
                     key_source='owner_file', scoring_excluded=False)
            if k in anf:
                rec.update(answer_key_status='answer_not_found', key_source=None,
                           verification_status='unverified', scoring_excluded=True)
            if k in researched:
                rec.update(answer_key_status='researched_unverified', key_source='researched_official',
                           verification_status='unverified', human_review_required=True, reviewer_needed=True)
            questions.append(rec)
        Q=dict(status='draft', exam_key='ex', questions=questions, held_for_review=[], scoring_excluded_question_keys=excl)
        (out/'questions.json').write_text(json.dumps(Q), encoding='utf-8')
        sim=dict(exam_key='ex', status='draft', time_limit_minutes={'value':60,'basis':'official','source':'https://example.invalid'},
                 passing_score={'value':70,'basis':'official','source':'https://example.invalid'},
                 question_count={'value':None,'basis':'site_choice','note':'n'},
                 domain_mix=[], rules={}, bank_status='not_ready',
                 scoring_excluded_question_keys=excl)
        (out/'simulator_settings.json').write_text(json.dumps(sim), encoding='utf-8')
        return out

    def test_passes_answer_not_found_and_researched_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=self._bank(tmp, anf=['q005'], researched=['q006'])
            report=CIC.check_dir(out, SKILL)
            failed=[r for r in report if r['status']=='fail']
            self.assertEqual(failed, [], failed)

    def test_fails_when_excluded_list_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=self._bank(tmp, anf=['q005'])
            sim=json.loads((out/'simulator_settings.json').read_text())
            del sim['scoring_excluded_question_keys']
            (out/'simulator_settings.json').write_text(json.dumps(sim), encoding='utf-8')
            report=CIC.check_dir(out, SKILL)
            sim_rep=next(r for r in report if r['file']=='simulator_settings.json')
            self.assertEqual(sim_rep['status'], 'fail')
            self.assertIn('scoring_excluded_question_keys', sim_rep['detail'])

if __name__=='__main__':
    unittest.main()
