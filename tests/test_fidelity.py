#!/usr/bin/env python3
"""Fidelity gate: word coverage, dual OCR, unique type, certain key. No AI."""
from __future__ import annotations
import json, os, sys, tempfile, unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / 'scripts'))


def _cfg(**over):
    import fidelity
    cfg = fidelity.load_fidelity_config(str(SKILL))
    cfg.update(over)
    return cfg


def _choice_q(stem, options, key, typ='single_choice'):
    choices = [{'id': k, 'text': {'text': v}} for k, v in options.items()]
    return {
        'question_key': 'q001',
        'version': 1,
        'type': typ,
        'domain': 'Unassigned',
        'learner': {'stem': {'text': stem}, 'choices': choices},
        'answer': {'answer_key': key, 'status': 'owner_key', 'scoring_excluded': False, 'reviewer_needed': False},
    }


class TestFidelityConfig(unittest.TestCase):
    def test_config_has_no_exam_literals_and_has_thresholds(self):
        text = (SKILL / 'config' / 'fidelity.json').read_text(encoding='utf-8')
        for needle in ('AB-730', '4A0-AI1', 'ADM-201', 'KCNA', 'Data-Con-101'):
            self.assertNotIn(needle, text)
        cfg = _cfg()
        self.assertTrue(cfg['require_100_percent_coverage'])
        self.assertTrue(cfg['forbid_extra_words'])
        self.assertTrue(cfg['require_unique_type_rule'])
        self.assertTrue(cfg['require_certain_key'])
        self.assertEqual(cfg['ocr']['min_word_confidence'], 90)
        self.assertEqual(cfg['ocr']['min_overall_confidence'], 95)
        self.assertGreaterEqual(len(cfg['ocr']['passes']), 2)


class TestWordCoverage(unittest.TestCase):
    def test_tokenize_and_strip_labels(self):
        import fidelity
        cfg = _cfg()
        deny = fidelity.make_deny(cfg)
        raw = 'QUESTION 1\nWhich service stores keys?\nA. Vault\nB. Notes\nCorrect Answer: A\nSection: (none)\nExplanation'
        cleaned = fidelity.strip_source_text(raw, cfg, deny=deny)
        self.assertIn('service', cleaned.lower())
        self.assertIn('Vault', cleaned)
        self.assertNotIn('Correct Answer', cleaned)
        self.assertNotIn('QUESTION 1', cleaned)
        toks = fidelity.tokenize(cleaned, cfg)
        self.assertIn('vault', toks)
        self.assertNotIn('a', toks)  # option letter stripped

    def test_label_words_in_stem_are_kept(self):
        import fidelity
        cfg = _cfg()
        deny = fidelity.make_deny(cfg)
        raw = "What is the reference implementation?\nA. runc\nCorrect Answer: A\nSection: (none)\nExplanation"
        cleaned = fidelity.strip_source_text(raw, cfg, deny=deny)
        self.assertIn('reference', cleaned.lower())
        self.assertNotIn('Explanation', cleaned)
        item = dict(stem='What is the reference implementation?', options={'a': 'runc'},
                    answer_raw='A', source_text=raw)
        q = _choice_q(item['stem'], item['options'], [0])
        ev = fidelity.evaluate(item, q, dict(type='single_choice', matched_rules=['single_choice'], held=False),
                               {}, {}, cfg)
        self.assertTrue(ev['ok'], ev['reason'])
        self.assertEqual(ev['coverage_percent'], 100)

    def test_coverage_100_and_no_extras(self):
        import fidelity
        cfg = _cfg()
        item = dict(stem='Which service stores keys?', options={'a': 'Vault', 'b': 'Notes'},
                    answer_raw='A', source_text='Which service stores keys?\nA. Vault\nB. Notes')
        q = _choice_q(item['stem'], item['options'], [0])
        ev = fidelity.evaluate(item, q, dict(type='single_choice', matched_rules=['single_choice'], held=False),
                               {}, {}, cfg)
        self.assertTrue(ev['ok'], ev['reason'])
        self.assertEqual(ev['coverage_percent'], 100)
        self.assertEqual(ev['missing_words'], [])
        self.assertEqual(ev['extra_words'], [])
        self.assertEqual(ev['key_source'], 'text')

    def test_missing_word_holds(self):
        import fidelity
        cfg = _cfg()
        item = dict(stem='Which service stores keys?', options={'a': 'Vault', 'b': 'Notes'},
                    answer_raw='A', source_text='Which service stores keys in Vault and Notes exactly?')
        q = _choice_q('Which service stores keys?', {'a': 'Vault', 'b': 'Notes'}, [0])
        ev = fidelity.evaluate(item, q, dict(type='single_choice', matched_rules=['single_choice'], held=False),
                               {}, {}, cfg)
        self.assertFalse(ev['ok'])
        self.assertIn('exactly', ev['missing_words'])
        self.assertIn('missing words', ev['reason'])

    def test_extra_invented_alt_holds(self):
        import fidelity
        cfg = _cfg()
        item = dict(stem='Which service stores keys?', options={'a': 'Vault', 'b': 'Notes'},
                    answer_raw='A', source_text='Which service stores keys?\nA. Vault\nB. Notes')
        q = _choice_q(item['stem'], item['options'], [0])
        q['learner']['media'] = [{'url': '/storage/EX/media/ex.png', 'alt': 'Supporting exhibit from the owner file'}]
        ev = fidelity.evaluate(item, q, dict(type='single_choice', matched_rules=['single_choice'], held=False),
                               {}, {}, cfg)
        self.assertFalse(ev['ok'])
        self.assertTrue(set(['supporting', 'exhibit', 'owner', 'file']) & set(ev['extra_words']))
        self.assertIn('extra words', ev['reason'])


class TestImageOcrGate(unittest.TestCase):
    def test_low_word_confidence_holds(self):
        import fidelity
        cfg = _cfg()
        ocr = dict(images=[{
            'file': 'ex.png',
            'words': [{'text': 'Vault', 'conf': 96}, {'text': 'Notes', 'conf': 70}],
            'mean_confidence': 83, 'min_confidence': 70, 'agree': True,
            'passes': {'psm3': {'text': 'Vault Notes'}, 'psm6': {'text': 'Vault Notes'}},
        }], confidence=83, min_confidence=70, agree=True)
        ev = fidelity.check_image_ocr(ocr, cfg)
        self.assertFalse(ev['ok'])
        self.assertEqual(ev['low_words'][0]['text'], 'Notes')
        self.assertIn('Notes', ev['reason'])

    def test_overall_below_95_holds(self):
        import fidelity
        cfg = _cfg()
        ocr = dict(images=[{
            'file': 'ex.png',
            'words': [{'text': 'Vault', 'conf': 93}, {'text': 'Notes', 'conf': 93}],
            'mean_confidence': 93, 'min_confidence': 93, 'agree': True,
            'passes': {'a': {'text': 'Vault Notes'}, 'b': {'text': 'Vault Notes'}},
        }], confidence=93, min_confidence=93, agree=True)
        ev = fidelity.check_image_ocr(ocr, cfg)
        self.assertFalse(ev['ok'])
        self.assertIn('overall', ev['reason'])

    def test_passes_must_agree(self):
        import fidelity
        cfg = _cfg()
        ocr = dict(images=[{
            'file': 'ex.png',
            'words': [{'text': 'Vault', 'conf': 99}, {'text': 'Notes', 'conf': 99}],
            'mean_confidence': 99, 'min_confidence': 99, 'agree': False,
            'passes': {'a': {'text': 'Vault Notes'}, 'b': {'text': 'Vault Nuts'}},
        }], confidence=99, min_confidence=99, agree=False)
        ev = fidelity.check_image_ocr(ocr, cfg)
        self.assertFalse(ev['ok'])
        self.assertIn('disagree', ev['reason'].lower())

    def test_high_confidence_and_agreement_pass(self):
        import fidelity
        cfg = _cfg()
        ocr = dict(images=[{
            'file': 'ex.png',
            'words': [{'text': 'Vault', 'conf': 99}, {'text': 'Notes', 'conf': 98}],
            'mean_confidence': 98.5, 'min_confidence': 98, 'agree': True,
            'passes': {'a': {'text': 'Vault Notes'}, 'b': {'text': 'Vault Notes'}},
        }], confidence=98.5, min_confidence=98, agree=True)
        ev = fidelity.check_image_ocr(ocr, cfg)
        self.assertTrue(ev['ok'], ev['reason'])

    def test_no_images_passes(self):
        import fidelity
        ev = fidelity.check_image_ocr({'images': []}, _cfg())
        self.assertTrue(ev['ok'])
        self.assertIsNone(ev['min_word_confidence'])


class TestTypeAndKeyCertainty(unittest.TestCase):
    def test_zero_or_two_rules_hold(self):
        import fidelity
        cfg = _cfg()
        item = dict(stem='Which service stores keys?', options={'a': 'Vault', 'b': 'Notes'},
                    answer_raw='A', source_text='Which service stores keys?\nA. Vault\nB. Notes')
        q = _choice_q(item['stem'], item['options'], [0])
        ev = fidelity.evaluate(item, q, dict(type=None, matched_rules=[], held=True), {}, {}, cfg)
        self.assertFalse(ev['ok'])
        self.assertIn('no type rule', ev['reason'])
        ev = fidelity.evaluate(item, q, dict(type='single_choice', matched_rules=['single_choice', 'image_based_choice'], held=False),
                               {}, {}, cfg)
        self.assertFalse(ev['ok'])
        self.assertIn('not unique', ev['reason'])

    def test_live_rules_are_unique_for_standard_shapes(self):
        import qtypes
        qtypes._RULES = None
        qtypes._MARKER_RX = None
        cases = [
            dict(stem='The sky is blue.', options={'a': 'True', 'b': 'False'}, answer_raw='A'),
            dict(stem='Which service stores keys?', options={'a': 'Vault', 'b': 'Notes'}, answer_raw='A'),
            dict(stem='Which two settings reduce risk? Choose two.', options={'a': 'MFA', 'b': 'Shared', 'c': 'Policy'}, answer_raw='AC'),
            (dict(stem='For each of the following statements, select Yes if the statement is true. Otherwise, select No.',
                  options={}, answer_raw=''),
             {'rows': [{'id': 'r1', 'text': 'A role can be assigned.'}]}),
        ]
        for case in cases:
            if isinstance(case, tuple):
                item, vis = case
            else:
                item, vis = case, None
            r = qtypes.classify_detailed(item, vis)
            self.assertEqual(len(r.get('matched_rules') or []), 1, (item.get('stem'), r))

    def test_choose_n_must_equal_key_count(self):
        import fidelity
        cfg = _cfg()
        item = dict(stem='Which two settings reduce risk? Choose two.',
                    options={'a': 'MFA', 'b': 'Shared', 'c': 'Policy'},
                    answer_raw='A', source_text='Which two settings reduce risk? Choose two.\nA. MFA\nB. Shared\nC. Policy')
        q = _choice_q(item['stem'], item['options'], [0], typ='multiple_select')
        ev = fidelity.evaluate(item, q, dict(type='multiple_select', matched_rules=['multiple_select'], held=False),
                               {}, {}, cfg)
        self.assertFalse(ev['ok'])
        self.assertIn('asks for 2', ev['reason'])

    def test_matrix_rows_must_equal_key_rows(self):
        import fidelity
        cfg = _cfg()
        q = {
            'question_key': 'q001', 'version': 1, 'type': 'yes_no_matrix', 'domain': 'Unassigned',
            'learner': {'stem': {'text': 'Select Yes if the statement is true.'},
                        'interaction': {'matrix': {'rows': [{'id': 'r1', 'text': 'One'}, {'id': 'r2', 'text': 'Two'}],
                                                   'columns': [{'id': 'yes', 'text': 'Yes'}, {'id': 'no', 'text': 'No'}]}}},
            'answer': {'answer_key': {'r1': 'yes'}, 'status': 'owner_key'},
        }
        item = dict(stem='Select Yes if the statement is true.', options={}, answer_raw='',
                    source_text='Select Yes if the statement is true.\nOne\nTwo')
        visual = {'key_by_method': {'marker_box': {'r1': 'yes'}, 'highlight': {'r1': 'yes'}}}
        ev = fidelity.evaluate(item, q, dict(type='yes_no_matrix', matched_rules=['yes_no_matrix'], held=False),
                               {}, visual, cfg)
        self.assertFalse(ev['ok'])
        self.assertIn('matrix has 2 rows', ev['reason'])

    def test_cloze_blank_needs_a_key(self):
        import fidelity
        cfg = _cfg()
        q = {
            'question_key': 'q001', 'version': 1, 'type': 'inline_dropdown', 'domain': 'Unassigned',
            'learner': {'stem': {'text': 'Select the word that completes the sentence.'},
                        'interaction': {'cloze': {'segments': [{'text': 'Use '}, {'text': ' storage.'}],
                                                  'blanks': [{'id': 'blank1', 'options': [{'id': 'hot', 'text': 'hot'}, {'id': 'cool', 'text': 'cool'}]}]}}},
            'answer': {'answer_key': {}, 'status': 'owner_key'},
        }
        item = dict(stem='Select the word that completes the sentence.', options={}, answer_raw='',
                    source_text='Select the word that completes the sentence. Use storage.')
        ev = fidelity.evaluate(item, q, dict(type='inline_dropdown', matched_rules=['inline_dropdown'], held=False),
                               {}, {'key_by_method': {}}, cfg)
        self.assertFalse(ev['ok'])
        self.assertIn('blank', ev['reason'].lower())

    def test_text_key_maps_to_choice_ids(self):
        import fidelity
        cfg = _cfg()
        item = dict(stem='Which service stores keys?', options={'a': 'Vault', 'b': 'Notes'},
                    answer_raw='C', source_text='Which service stores keys?\nA. Vault\nB. Notes')
        q = _choice_q(item['stem'], item['options'], [2])  # invalid
        ev = fidelity.evaluate(item, q, dict(type='single_choice', matched_rules=['single_choice'], held=False),
                               {}, {}, cfg)
        self.assertFalse(ev['ok'])
        self.assertIn('map to existing choice', ev['reason'])

    def test_pixel_two_methods_agree(self):
        import fidelity
        cfg = _cfg()
        q = {
            'question_key': 'q001', 'version': 1, 'type': 'yes_no_matrix', 'domain': 'Unassigned',
            'learner': {'stem': {'text': 'Select Yes if the statement is true One'},
                        'interaction': {'matrix': {'rows': [{'id': 'r1', 'text': 'One'}],
                                                   'columns': [{'id': 'yes', 'text': 'Yes'}, {'id': 'no', 'text': 'No'}]}}},
            'answer': {'answer_key': {'r1': 'yes'}, 'status': 'owner_key'},
        }
        item = dict(stem='Select Yes if the statement is true One', options={}, answer_raw='',
                    source_text='Select Yes if the statement is true One Yes No')
        visual = {'key_by_method': {'marker_box': {'r1': 'yes'}, 'highlight': {'r1': 'yes'}}}
        ev = fidelity.evaluate(item, q, dict(type='yes_no_matrix', matched_rules=['yes_no_matrix'], held=False),
                               {}, visual, cfg)
        self.assertTrue(ev['ok'], ev['reason'])
        self.assertTrue(ev['key_source'].startswith('pixel:'))

    def test_one_pixel_method_is_not_enough(self):
        import fidelity
        cfg = _cfg()
        q = {
            'question_key': 'q001', 'version': 1, 'type': 'yes_no_matrix', 'domain': 'Unassigned',
            'learner': {'stem': {'text': 'Select Yes if the statement is true One'},
                        'interaction': {'matrix': {'rows': [{'id': 'r1', 'text': 'One'}],
                                                   'columns': [{'id': 'yes', 'text': 'Yes'}, {'id': 'no', 'text': 'No'}]}}},
            'answer': {'answer_key': {'r1': 'yes'}, 'status': 'owner_key'},
        }
        item = dict(stem='Select Yes if the statement is true One', options={}, answer_raw='',
                    source_text='Select Yes if the statement is true One Yes No')
        visual = {'key_by_method': {'marker_box': {'r1': 'yes'}}}
        ev = fidelity.evaluate(item, q, dict(type='yes_no_matrix', matched_rules=['yes_no_matrix'], held=False),
                               {}, visual, cfg)
        self.assertFalse(ev['ok'])
        self.assertIn('do not agree', ev['reason'] + ev['key_source'])

    def test_key_is_never_inferred_from_nothing(self):
        import fidelity
        cfg = _cfg()
        item = dict(stem='Which service stores keys?', options={'a': 'Vault', 'b': 'Notes'},
                    answer_raw='', source_text='Which service stores keys?\nA. Vault\nB. Notes')
        q = _choice_q(item['stem'], item['options'], [0])
        ev = fidelity.evaluate(item, q, dict(type='single_choice', matched_rules=['single_choice'], held=False),
                               {}, {}, cfg)
        self.assertFalse(ev['ok'])
        self.assertIn('no text key', ev['reason'])


class TestFidelityReport(unittest.TestCase):
    def test_write_reports(self):
        import fidelity
        with tempfile.TemporaryDirectory() as d:
            rows = [
                dict(question_key='q001', status='exported', coverage_percent=100, ocr_min_word_confidence=None,
                     type_rule='single_choice', key_source='text', reason=''),
                dict(question_key='q002', status='held', coverage_percent=80, ocr_min_word_confidence=70.0,
                     type_rule=None, key_source='missing', reason='missing words: foo'),
            ]
            payload = fidelity.write_reports(d, 'EX-DEMO', rows)
            self.assertEqual((payload['exported'], payload['held']), (1, 1))
            self.assertTrue(os.path.isfile(os.path.join(d, 'export', 'fidelity.json')))
            md = open(os.path.join(d, 'export', 'fidelity.md'), encoding='utf-8').read()
            self.assertIn('q001', md)
            self.assertIn('held', md)


class TestSourceTextCaptured(unittest.TestCase):
    def test_split_items_stores_source_text(self):
        import extract_owner_pdf as X
        import re
        els = [
            dict(k='txt', page=1, top=10, left=10, t='QUESTION 1'),
            dict(k='txt', page=1, top=20, left=10, t='Which service stores keys?'),
            dict(k='txt', page=1, top=30, left=10, t='A. Vault'),
            dict(k='txt', page=1, top=40, left=10, t='B. Notes'),
            dict(k='txt', page=1, top=50, left=10, t='Correct Answer: A'),
            dict(k='txt', page=1, top=60, left=10, t='Section: (none)'),
            dict(k='txt', page=1, top=70, left=10, t='Explanation'),
        ]
        layout = dict(start='QUESTION n', answer='Correct Answer:', profile='test')
        deny = re.compile(r'a\A')
        split, _, _ = X.split_items(els, layout, deny)
        self.assertIn('Which service stores keys?', split['q001']['source_text'])
        self.assertIn('A. Vault', split['q001']['source_text'])
        self.assertNotIn('Correct Answer', split['q001']['source_text'])
        self.assertNotIn('Explanation', split['q001']['source_text'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
