#!/usr/bin/env python3
"""Technical PDF-to-site-v2 path: type rules, OCR, export, no AI."""
from __future__ import annotations
import json, os, shutil, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / 'scripts'))
sys.path.insert(0, str(SKILL / 'tests'))


class TestTypeRules(unittest.TestCase):
    def setUp(self):
        import qtypes
        qtypes._RULES = None
        qtypes._MARKER_RX = None
        self.Q = qtypes

    def test_true_false_and_single_and_multi(self):
        r = self.Q.classify_detailed(dict(stem='The sky is blue.', options={'a': 'True', 'b': 'False'}, answer_raw='A'))
        self.assertEqual((r['type'], r['held'], r['rule_id']), ('true_false', False, 'true_false'))
        r = self.Q.classify_detailed(dict(stem='Which service stores keys?', options={'a': 'Vault', 'b': 'Notes', 'c': 'Theme'}, answer_raw='A'))
        self.assertEqual((r['type'], r['held']), ('single_choice', False))
        r = self.Q.classify_detailed(dict(
            stem='Which two settings reduce risk? Choose two.',
            options={'a': 'MFA', 'b': 'Shared', 'c': 'Policy'},
            answer_raw='AC'))
        self.assertEqual((r['type'], r['held'], r['rule_id']), ('multiple_select', False, 'multiple_select_from_key'))
        # stem marker only, empty key: still multiple_select, not a guess at the letters
        r = self.Q.classify_detailed(dict(
            stem='Which two settings reduce risk? Choose two.',
            options={'a': 'MFA', 'b': 'Shared', 'c': 'Policy'},
            answer_raw=''))
        self.assertEqual((r['type'], r['held']), ('multiple_select', False))

    def test_empty_answer_raw_does_not_crash_and_stays_single_choice(self):
        r = self.Q.classify_detailed(dict(stem='Which tool exports data?', options={'a': 'Export', 'b': 'Theme'}, answer_raw=None))
        self.assertEqual((r['type'], r['held']), ('single_choice', False))
        typ, reason = self.Q.classify(dict(stem='Which tool exports data?', options={'a': 'Export', 'b': 'Theme'}, answer_raw=None))
        self.assertEqual(typ, 'single_choice')

    def test_hold_when_no_rule_matches(self):
        r = self.Q.classify_detailed(dict(stem='Look at the figure and arrange the steps.', options={}, answer_raw=''))
        self.assertTrue(r['held'])
        self.assertIsNone(r['type'])
        typ, reason = self.Q.classify(dict(stem='Look at the figure and arrange the steps.', options={}, answer_raw=''))
        self.assertEqual(typ, 'needs_review')
        self.assertIn('not guessed', reason.lower() + ' ' + reason)

    def test_yes_no_holds_without_rows_and_matches_with_rows(self):
        stem = 'For each of the following statements, select Yes if the statement is true. Otherwise, select No.'
        r = self.Q.classify_detailed(dict(stem=stem, options={}, answer_raw=''))
        self.assertTrue(r['held'])
        r = self.Q.classify_detailed(
            dict(stem=stem, options={}, answer_raw=''),
            visual={'rows': [{'id': 'r1', 'text': 'A role can be assigned at group scope.'}]})
        self.assertEqual((r['type'], r['held']), ('yes_no_matrix', False))

    def test_rules_file_has_no_exam_literals(self):
        text = (SKILL / 'config' / 'question_type_rules.json').read_text(encoding='utf-8')
        for needle in ('Data-Con-101', 'AB-730', 'salesforce', 'Microsoft'):
            self.assertNotIn(needle, text)


class TestOcrConfig(unittest.TestCase):
    def test_ocr_config_loads(self):
        import vision_util as V
        V._OCR_CFG = None
        cfg = V.load_ocr_config()
        self.assertEqual(cfg.get('engine'), 'tesseract')
        self.assertIn('psm', cfg)
        self.assertIn('hold_below_confidence', cfg)
        self.assertTrue(cfg.get('highlight', {}).get('hsv_ranges'))

    def test_tesseract_is_available_and_reads_image_text(self):
        import vision_util as V
        from PIL import Image, ImageDraw, ImageFont
        bin_path, note = V.ensure_tesseract()
        self.assertTrue(bin_path, note)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'hello.png')
            im = Image.new('RGB', (400, 80), 'white')
            draw = ImageDraw.Draw(im)
            draw.text((10, 20), 'Hello OCR', fill='black')
            im.save(p)
            lines, size, mean = V.ocr_lines_configured(p)
            blob = ' '.join(l['text'] for l in lines)
            self.assertIn('Hello', blob)
            self.assertIsNotNone(mean)
            self.assertGreater(mean, 40)

    def test_highlight_mark_detected(self):
        import vision_util as V
        import numpy as np, cv2
        V._OCR_CFG = None
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'hi.png')
            img = np.full((100, 200, 3), 255, dtype=np.uint8)
            # BGR yellow block
            img[30:70, 40:120] = (0, 230, 230)
            cv2.imwrite(p, img)
            marks = V.highlight_marks(p)
            self.assertTrue(marks, marks)
            self.assertEqual(marks[0]['kind'], 'highlight')

    def test_ocr_lines_empty_when_tesseract_missing(self):
        import vision_util as V
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'i.png')
            Image.new('RGB', (40, 20), 'white').save(p)
            with mock.patch('shutil.which', return_value=None):
                lines, size, mean = V.ocr_lines_configured(p)
            self.assertEqual(lines, [])
            self.assertEqual(size, (40, 20))
            self.assertIsNone(mean)


class TestTechnicalExport(unittest.TestCase):
    def _workspace(self, items):
        tmp = Path(tempfile.mkdtemp(prefix='cp-tech-'))
        exam = 'EX-DEMO'
        out = tmp / 'out' / exam / 'extracted'
        out.mkdir(parents=True)
        (tmp / 'out' / exam / 'media' / 'src').mkdir(parents=True)
        split = {}
        for i, it in enumerate(items, 1):
            key = it.get('question_key') or f'q{i:03d}'
            rec = dict(question_key=key, source_number=i, pages=[i],
                       stem=it['stem'], options=it.get('options') or {},
                       answer_raw=it.get('answer_raw') or '',
                       question_images=it.get('question_images') or [],
                       answer_images=it.get('answer_images') or [])
            split[key] = rec
        (out / 'split.json').write_text(json.dumps(split, indent=1), encoding='utf-8')
        (out / 'visual_draft.json').write_text('{}', encoding='utf-8')
        (out / 'ocr.json').write_text(json.dumps({'tesseract': '/usr/bin/tesseract', 'items': {
            k: {'confidence': 90.0, 'min_confidence': 80.0, 'images': [], 'marks': [], 'notes': []}
            for k in split
        }}), encoding='utf-8')
        hdr = 'vendor,vendor_slug,certification,exam_code,exam_name,sheet_status,drive_folder_url,sheet_cell,sheet_label'
        (tmp / 'catalog.csv').write_text(hdr + '\nExample Vendor,example,,EX-DEMO,,ready,,,EX-DEMO\n', encoding='utf-8')
        return tmp, exam

    def test_export_detects_keys_and_holds_nothing_for_lettered_items(self):
        import build_technical_export as B
        import paths
        items = [
            dict(stem='Which service stores keys?', options={'a': 'Vault', 'b': 'Notes', 'c': 'Theme', 'd': 'Theme pack'}, answer_raw='A'),
            dict(stem='Which two settings reduce risk? Choose two.', options={'a': 'MFA', 'b': 'Shared', 'c': 'Policy', 'd': 'Public'}, answer_raw='AC'),
            dict(stem='Which tool exports data?', options={'a': 'Export', 'b': 'Theme', 'c': 'Help'}, answer_raw=''),
        ]
        tmp, exam = self._workspace(items)
        try:
            paths.set_root(str(tmp))
            rc = B.main(['--exam', exam, '--out-dir', str(tmp / 'out' / exam), '--root', str(tmp),
                         '--catalog', str(tmp / 'catalog.csv')])
            self.assertEqual(rc, 0)
            doc = json.loads((tmp / 'out' / exam / f'{exam}.site-format.v2.json').read_text(encoding='utf-8'))
            self.assertEqual(doc['exam']['vendor'], 'Example Vendor')
            self.assertEqual(doc['exam']['certification'], 'EX-DEMO')
            self.assertEqual(doc['exam']['name'], 'EX-DEMO')
            self.assertNotIn('simulator_settings', doc['exam'])
            self.assertEqual(len(doc['questions']), 3)
            types = [q['type'] for q in doc['questions']]
            self.assertEqual(types, ['single_choice', 'multiple_select', 'single_choice'])
            self.assertEqual(doc['questions'][0]['answer']['answer_key'], [0])
            self.assertEqual(doc['questions'][0]['answer']['status'], 'owner_key')
            self.assertEqual(doc['questions'][1]['answer']['answer_key'], [0, 2])
            self.assertEqual(doc['questions'][1]['learner']['interaction']['choose_n'], 2)
            q3 = doc['questions'][2]
            self.assertEqual(q3['answer']['status'], 'answer_not_found')
            self.assertTrue(q3['answer']['scoring_excluded'])
            self.assertTrue(q3['answer']['reviewer_needed'])
            self.assertNotIn('explanation', q3['answer'])
            self.assertEqual(q3['domain'], 'Unassigned')
            report = json.loads((tmp / 'out' / exam / 'export' / 'technical_report.json').read_text(encoding='utf-8'))
            self.assertEqual((report['detected'], report['held'], report['total']), (3, 0, 3))
            self.assertEqual(report['items'][0]['ocr_confidence'], 90.0)
            held = json.loads((tmp / 'out' / exam / 'export' / 'cannot-convert.json').read_text(encoding='utf-8'))
            self.assertEqual(held, [])
        finally:
            paths.set_root(os.getcwd())
            shutil.rmtree(tmp, ignore_errors=True)

    def test_site_python_validator_accepts_export(self):
        import build_technical_export as B
        import validate_question_v2 as V
        import paths
        items = [dict(stem='Which service stores keys?', options={'a': 'Vault', 'b': 'Notes'}, answer_raw='A')]
        tmp, exam = self._workspace(items)
        try:
            paths.set_root(str(tmp))
            self.assertEqual(B.main(['--exam', exam, '--out-dir', str(tmp / 'out' / exam), '--root', str(tmp),
                                     '--catalog', str(tmp / 'catalog.csv')]), 0)
            site = tmp / 'out' / exam / f'{exam}.site-format.v2.json'
            rc = V.main([str(site)])
            self.assertEqual(rc, 0)
        finally:
            paths.set_root(os.getcwd())
            shutil.rmtree(tmp, ignore_errors=True)


class TestCliDefaultStages(unittest.TestCase):
    def test_list_stages_and_default_has_no_author(self):
        import subprocess
        r = subprocess.run([sys.executable, str(SKILL / 'scripts' / 'run_pipeline.py'), '--list-stages'],
                           capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('technical (default)', r.stdout)
        self.assertIn('intake, extract, export, validate_site, package', r.stdout)
        self.assertIn('research\t', r.stdout)
        self.assertIn('verify\t', r.stdout)
        # default line must not include the AI stage
        default_line = [ln for ln in r.stdout.splitlines() if ln.startswith('technical (default)')][0]
        self.assertNotIn('author', default_line)
        self.assertNotIn('sources', default_line)


class TestChoiceImages(unittest.TestCase):
    def _imgs(self, files_and_text):
        recs=[]
        for fn, text in files_and_text:
            recs.append(dict(file=fn, role='question', lines=[{'t': line} for line in text.split('\n')]))
        return recs

    def test_last_page_images_become_lettered_options(self):
        import ocr_extract as O
        item=dict(stem='Based on the exhibit, which syntax is correct?', options={}, answer_raw='A')
        recs=self._imgs([
            ('p-2_1.png', '"result": { "avg": 0.026 }'),
            ('p-3_1.png', 'publish: output: <% task().result %>'),
            ('p-3_2.png', 'publish: output: <% task().result.RTT %>'),
            ('p-3_3.png', 'publish: output: <% task().RTT %>'),
            ('p-3_4.png', 'publish: output: <% RTT %>'),
        ])
        opts=O.options_from_choice_images(item, recs)
        self.assertEqual(list(opts), ['a','b','c','d'])
        self.assertIn('task().result %>', opts['a'])
        self.assertIn('<% RTT %>', opts['d'])
        # the earlier-page exhibit is not a choice
        self.assertNotIn('avg', ' '.join(opts.values()))

    def test_visual_marker_items_are_not_turned_into_choices(self):
        import ocr_extract as O
        item=dict(stem='For each of the following statements, select Yes if the statement is true. Otherwise, select No.',
                  options={}, answer_raw='')
        recs=self._imgs([('p-5_1.png','Yes No'),('p-5_2.png','row one')])
        # even with a letter key, a Yes/No stem must not be flattened
        item['answer_raw']='A'
        self.assertIsNone(O.options_from_choice_images(item, recs))


if __name__ == '__main__':
    unittest.main(verbosity=2)
