#!/usr/bin/env python3
"""Unit tests for question format v2 schema, sanitizer, examples, and exporter."""
from __future__ import annotations
import json, subprocess, sys, tempfile, unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
V2 = REPO / 'reference' / 'site-format' / 'v2'
SCRIPTS = REPO / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import validate_question_v2 as vq
import parse_question_types_php as parser

class RegistryTests(unittest.TestCase):
    def test_committed_registry_has_exactly_30_keys(self):
        reg = json.loads((V2 / 'question_types.json').read_text(encoding='utf-8'))
        self.assertEqual(reg['counts']['types'], 30)
        self.assertEqual(len(reg['types']), 30)
        self.assertNotIn('image_legacy', reg['types'])
        self.assertEqual(reg['counts']['publishable'], 16)
        self.assertEqual(reg['counts']['staging'], 7)
        self.assertEqual(reg['counts']['blocked'], 7)

    def test_image_legacy_is_flagged_not_added(self):
        mis = json.loads((V2 / 'registry-mismatch.json').read_text(encoding='utf-8'))
        names = [m['requested_type'] for m in mis['mismatches']]
        self.assertIn('image_legacy', names)
        self.assertEqual(mis['mismatches'][0]['status'], 'not_in_registry')

    def test_parser_flags_without_inserting(self):
        reg = json.loads((V2 / 'question_types.json').read_text(encoding='utf-8'))
        before = set(reg['types'])
        mm = parser.flag_registry_mismatches(reg, ['image_legacy'])
        self.assertEqual(set(reg['types']), before)
        self.assertEqual(mm[0]['status'], 'not_in_registry')

class SchemaExampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = vq.load_schema()
        cls.reg = vq.load_registry()
        cls.allow = vq.load_allowlist()

    def test_valid_examples_pass(self):
        for p in sorted((V2 / 'examples').glob('valid-*.json')):
            doc = json.loads(p.read_text(encoding='utf-8'))
            errs = vq.validate_doc(doc, self.schema, self.reg, self.allow)
            self.assertEqual(errs, [], f'{p.name} should pass, got {errs}')

    def test_invalid_examples_fail(self):
        for p in sorted((V2 / 'examples').glob('invalid-*.json')):
            doc = json.loads(p.read_text(encoding='utf-8'))
            errs = vq.validate_doc(doc, self.schema, self.reg, self.allow)
            self.assertTrue(errs, f'{p.name} should fail')

    def test_answer_not_found_requires_scoring_excluded(self):
        p = V2 / 'examples' / 'invalid-answer-not-found-scored.json'
        doc = json.loads(p.read_text(encoding='utf-8'))
        errs = vq.validate_doc(doc, self.schema, self.reg, self.allow)
        self.assertTrue(any('scoring_excluded' in e for e in errs))

    def test_learner_must_not_contain_keys(self):
        p = V2 / 'examples' / 'invalid-learner-has-key.json'
        doc = json.loads(p.read_text(encoding='utf-8'))
        errs = vq.validate_doc(doc, self.schema, self.reg, self.allow)
        self.assertTrue(any('correct_option_ids' in e or 'forbidden' in e.lower() or 'additional' in e.lower() for e in errs))

    def test_image_legacy_mismatch(self):
        p = V2 / 'examples' / 'mismatch-image_legacy.json'
        doc = json.loads(p.read_text(encoding='utf-8'))
        errs = vq.validate_doc(doc, self.schema, self.reg, self.allow)
        self.assertTrue(any('image_legacy' in e and 'mismatch' in e for e in errs))

    def test_sanitizer_rejects_script(self):
        doc = json.loads((V2 / 'examples' / 'valid-single_choice.json').read_text(encoding='utf-8'))
        doc['learner']['stem'] = {'format': 'html', 'text': '<p>hi</p><script>alert(1)</script>'}
        errs = vq.validate_doc(doc, self.schema, self.reg, self.allow)
        self.assertTrue(any('script' in e.lower() or 'javascript' in e.lower() for e in errs))

    def test_sanitizer_rejects_javascript_href(self):
        doc = json.loads((V2 / 'examples' / 'valid-single_choice.json').read_text(encoding='utf-8'))
        doc['learner']['stem'] = {'format': 'html', 'text': '<p><a href="javascript:alert(1)">x</a></p>'}
        errs = vq.validate_doc(doc, self.schema, self.reg, self.allow)
        self.assertTrue(errs)

    def test_cli_examples_exit_0(self):
        r = subprocess.run([sys.executable, str(SCRIPTS / 'validate_question_v2.py'), '--examples', str(V2 / 'examples')],
                           cwd=REPO, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_minimal_checker_agrees_on_valid(self):
        doc = json.loads((V2 / 'examples' / 'valid-single_choice.json').read_text(encoding='utf-8'))
        errs = vq.validate_doc(doc, self.schema, self.reg, self.allow, use_jsonschema=False)
        self.assertEqual(errs, [])

class ExporterTests(unittest.TestCase):
    def test_maps_as_in_source_file_and_keeps_draft(self):
        import export_question_v2 as ex
        item = {
            'question_key': 'q001',
            'question_version_key': 'q001-v1',
            'question_type': 'single_choice',
            'prompt_text': 'Stem text',
            'options': [{'id': 'a', 'text': 'A'}, {'id': 'b', 'text': 'B'}],
            'answer_key': {'correct_option_ids': ['b']},
            'answer_key_status': 'as_in_source_file',
            'key_source': 'owner_file',
            'core_explanation': 'Because the official page says so.',
        }
        doc = ex.export_item(item)
        self.assertEqual(doc['schema_version'], 'question.v2')
        self.assertEqual(doc['version'], 1)
        self.assertEqual(doc['meta']['answer_key_status'], 'owner_key')
        self.assertEqual(doc['meta']['legacy_answer_key_status'], 'as_in_source_file')
        self.assertEqual(doc['meta']['record_status'], 'draft')
        self.assertFalse(doc['meta']['scoring_excluded'])
        self.assertNotIn('correct_option_ids', json.dumps(doc['learner']))
        self.assertEqual(doc['answer']['answer_key']['correct_option_ids'], ['b'])

    def test_answer_not_found_is_excluded(self):
        import export_question_v2 as ex
        item = {
            'question_key': 'q099',
            'question_type': 'single_choice',
            'prompt_text': 'Unknown',
            'options': [{'id': 'a', 'text': 'A'}, {'id': 'b', 'text': 'B'}],
            'answer_key': None,
            'answer_key_status': 'answer_not_found',
        }
        doc = ex.export_item(item)
        self.assertTrue(doc['meta']['scoring_excluded'])
        self.assertEqual(doc['meta']['answer_key_status'], 'answer_not_found')

if __name__ == '__main__':
    unittest.main()
