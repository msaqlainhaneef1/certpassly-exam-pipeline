#!/usr/bin/env python3
"""Unit tests for site format v2 schema, examples, exporter and migrator."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
V2 = REPO / 'reference' / 'site-format' / 'v2'
SCRIPTS = REPO / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import validate_question_v2 as vq
import parse_question_types_php as parser


def stem_text(doc_or_q):
    q = doc_or_q
    if 'questions' in doc_or_q:
        q = doc_or_q['questions'][0]
    return vq.text_of_stem((q.get('learner') or {}).get('stem'))


class RegistryTests(unittest.TestCase):
    def test_committed_registry_has_exactly_30_keys(self):
        reg = json.loads((V2 / 'question_types.json').read_text(encoding='utf-8'))
        self.assertEqual(reg['counts']['types'], 30)
        self.assertEqual(len(reg['types']), 30)
        self.assertNotIn('image_legacy', reg['types'])
        self.assertEqual(reg['counts']['publishable'], 16)
        self.assertEqual(reg['counts']['staging'], 7)
        self.assertEqual(reg['counts']['blocked'], 7)

    def test_registry_mismatch_file_is_empty(self):
        mis = json.loads((V2 / 'registry-mismatch.json').read_text(encoding='utf-8'))
        self.assertEqual(mis['mismatches'], [])

    def test_parser_adds_no_extra_types(self):
        reg = json.loads((V2 / 'question_types.json').read_text(encoding='utf-8'))
        before = set(reg['types'])
        mm = parser.flag_registry_mismatches(reg, [])
        self.assertEqual(set(reg['types']), before)
        self.assertEqual(mm, [])

    def test_schema_matches_provenance_hash(self):
        import hashlib
        data = (V2 / 'question.schema.json').read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        self.assertEqual(sha, 'da9331c562a0e08cd156cc5efe6181cb8910ec19c523ff83dc43687190dc728e')
        schema = json.loads(data)
        self.assertIn('exam', schema['required'])
        self.assertIn('questions', schema['required'])
        self.assertNotIn('schema_version', schema.get('properties', {}))


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
        self.assertTrue(any('correct_option_ids' in e or 'forbidden' in e.lower() or 'additional' in e.lower() or 'not allowed' in e.lower() for e in errs))

    def test_as_in_source_file_is_rejected(self):
        doc = json.loads((V2 / 'examples' / 'valid-single_choice.json').read_text(encoding='utf-8'))
        doc['questions'][0]['answer']['status'] = 'as_in_source_file'
        errs = vq.validate_doc(doc, self.schema, self.reg, self.allow)
        self.assertTrue(errs, 'v2 must reject as_in_source_file')
        self.assertTrue(any('as_in_source_file' in e for e in errs))

    def test_supporting_image_example_is_real_type(self):
        p = V2 / 'examples' / 'valid-single_choice-supporting-image.json'
        doc = json.loads(p.read_text(encoding='utf-8'))
        q = doc['questions'][0]
        self.assertEqual(q['type'], 'single_choice')
        self.assertEqual(q['learner']['media'][0]['url'][:9], '/storage/')
        self.assertTrue(q['learner']['media'][0]['alt'])
        self.assertNotIn('original_asset', q['learner']['media'][0])
        errs = vq.validate_doc(doc, self.schema, self.reg, self.allow)
        self.assertEqual(errs, [], errs)

    def test_schema_has_no_question_trial_fields(self):
        schema = self.schema
        qprops = (schema.get('$defs') or {}).get('question', {}).get('properties') or {}
        banned = [k for k in qprops if 'trial' in k.lower() or 'free_preview' in k.lower() or 'free_question' in k.lower()]
        self.assertEqual(banned, [])
        # counts_toward_trial is an allowed exam simulator setting, not a question field
        sim = (schema.get('$defs') or {}).get('simulator_settings', {}).get('properties') or {}
        self.assertIn('counts_toward_trial', sim)

    def test_sanitizer_rejects_script_in_text(self):
        doc = json.loads((V2 / 'examples' / 'valid-single_choice.json').read_text(encoding='utf-8'))
        doc['questions'][0]['learner']['stem'][0]['content'][0]['text'] = 'hi <script>alert(1)</script>'
        errs = vq.validate_doc(doc, self.schema, self.reg, self.allow)
        self.assertTrue(any('HTML' in e or 'script' in e.lower() or 'format' in e.lower() for e in errs))

    def test_sanitizer_rejects_javascript_href(self):
        doc = json.loads((V2 / 'examples' / 'valid-single_choice.json').read_text(encoding='utf-8'))
        doc['questions'][0]['learner']['stem'][0]['content'][0]['link'] = 'javascript:alert(1)'
        errs = vq.validate_doc(doc, self.schema, self.reg, self.allow)
        self.assertTrue(errs)

    def test_duplicate_stems_are_reported(self):
        doc = json.loads((V2 / 'examples' / 'valid-single_choice.json').read_text(encoding='utf-8'))
        dup = json.loads(json.dumps(doc['questions'][0]))
        dup['question_key'] = 'ex-single-002'
        doc['questions'].append(dup)
        errs = vq.validate_doc(doc, self.schema, self.reg, self.allow)
        self.assertTrue(any('duplicate' in e.lower() for e in errs), errs)

    def test_repeated_ids_are_reported(self):
        doc = json.loads((V2 / 'examples' / 'valid-hotspot_single.json').read_text(encoding='utf-8'))
        doc['questions'][0]['learner']['interaction']['hotspot_regions'][1]['id'] = 'h1'
        errs = vq.validate_doc(doc, self.schema, self.reg, self.allow)
        self.assertTrue(any('used twice' in e for e in errs), errs)

    def test_cli_examples_exit_0(self):
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / 'validate_question_v2.py'), '--examples', str(V2 / 'examples')],
            cwd=REPO, capture_output=True, text=True,
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_minimal_checker_agrees_on_valid(self):
        doc = json.loads((V2 / 'examples' / 'valid-single_choice.json').read_text(encoding='utf-8'))
        errs = vq.validate_doc(doc, self.schema, self.reg, self.allow, use_jsonschema=False)
        self.assertEqual(errs, [])


class ExporterTests(unittest.TestCase):
    def test_rejects_v1_status(self):
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
        }
        with self.assertRaises(ValueError) as ctx:
            ex.export_item(item)
        self.assertIn('migrate_v1_to_v2', str(ctx.exception))

    def test_canonical_status_exports_site_shape(self):
        import export_question_v2 as ex
        item = {
            'question_key': 'q001',
            'question_version_key': 'q001-v1',
            'question_type': 'single_choice',
            'prompt_text': 'Stem text',
            'domain': 'Format examples',
            'options': [{'id': 'a', 'text': 'A'}, {'id': 'b', 'text': 'B'}],
            'answer_key': {'correct_option_ids': ['b']},
            'answer_key_status': 'owner_key',
            'key_source': 'owner_file',
            'core_explanation': 'Because the official page says so.',
        }
        doc = ex.export_item(item)
        self.assertNotIn('schema_version', doc)
        self.assertNotIn('meta', doc)
        self.assertEqual(doc['version'], 1)
        self.assertEqual(doc['type'], 'single_choice')
        self.assertEqual(doc['domain'], 'Format examples')
        self.assertEqual(doc['answer']['status'], 'owner_key')
        self.assertFalse(doc['answer']['scoring_excluded'])
        self.assertEqual(doc['answer']['answer_key'], [1])
        self.assertNotIn('correct_option_ids', json.dumps(doc['learner']))
        self.assertEqual(doc['learner']['stem'][0]['type'], 'paragraph')
        self.assertIn('Stem text', vq.text_of_stem(doc['learner']['stem']))

    def test_answer_not_found_is_excluded(self):
        import export_question_v2 as ex
        item = {
            'question_key': 'q099',
            'question_type': 'single_choice',
            'prompt_text': 'Unknown',
            'domain': 'Format examples',
            'options': [{'id': 'a', 'text': 'A'}, {'id': 'b', 'text': 'B'}],
            'answer_key': None,
            'answer_key_status': 'answer_not_found',
        }
        doc = ex.export_item(item)
        self.assertTrue(doc['answer']['scoring_excluded'])
        self.assertEqual(doc['answer']['status'], 'answer_not_found')

    def test_html_stem_becomes_rich_text(self):
        import export_question_v2 as ex
        blocks, tables = ex.html_to_rich('<p>Hello <strong>world</strong></p><ul><li>One</li></ul>')
        self.assertEqual(blocks[0]['type'], 'paragraph')
        self.assertIn('bold', blocks[0]['content'][1].get('marks', []))
        self.assertEqual(blocks[1]['type'], 'bullet_list')
        self.assertFalse(tables)

    def test_choose_n_comes_from_stem_not_key(self):
        import export_question_v2 as ex
        item = {
            'question_key': 'q016',
            'question_type': 'multiple_select',
            'prompt_text': 'Which two options apply? Choose two.',
            'domain': 'Format examples',
            'options': [
                {'id': 'a', 'text': 'A'}, {'id': 'b', 'text': 'B'},
                {'id': 'c', 'text': 'C'}, {'id': 'd', 'text': 'D'},
            ],
            'answer_key': {'correct_option_ids': ['b', 'c']},
            'answer_key_status': 'owner_key',
        }
        doc = ex.export_item(item)
        self.assertEqual(doc['learner']['interaction']['choose_n'], 2)
        self.assertEqual(doc['answer']['answer_key'], [1, 2])
        self.assertIn('Choose two', vq.text_of_stem(doc['learner']['stem']))


class MigratorTests(unittest.TestCase):
    def _bank(self, questions, exam_key='EX-TEST'):
        return {'exam_key': exam_key, 'questions': questions, 'held_for_review': [], 'scoring_excluded_question_keys': []}

    def test_maps_as_in_source_file_to_owner_key(self):
        import migrate_v1_to_v2 as mv
        item = {
            'question_key': 'q001',
            'question_version_key': 'q001-v1',
            'question_type': 'single_choice',
            'prompt_text': 'Stem text',
            'domain': 'Format examples',
            'options': [{'id': 'a', 'text': 'A'}, {'id': 'b', 'text': 'B'}],
            'answer_key': {'correct_option_ids': ['b']},
            'answer_key_status': 'as_in_source_file',
            'key_source': 'owner_file',
            'core_explanation': 'Because the official page says so.',
        }
        doc, issues = mv.migrate_item(
            item, exam_key='EX-TEST', media_rows=[], media_dir=None,
            src_root=None, draft=None, trans=None, excluded=set(),
        )
        self.assertEqual(issues, [])
        self.assertEqual(doc['answer']['status'], 'owner_key')
        self.assertEqual(doc['_migration']['legacy_answer_key_status'], 'as_in_source_file')
        self.assertTrue(doc['_migration']['conversion_exact'])
        self.assertEqual(doc['learner']['stem'][0]['type'], 'paragraph')
        self.assertIn('Stem text', vq.text_of_stem(doc['learner']['stem']))
        self.assertNotIn('correct_option_ids', json.dumps(doc['learner']))
        self.assertNotIn('meta', doc)
        self.assertNotIn('schema_version', doc)

    def test_remaps_image_based_choice_and_lists_unconfirmed_exhibit(self):
        import migrate_v1_to_v2 as mv
        item = {
            'question_key': 'q059',
            'question_version_key': 'q059-v1',
            'question_type': 'image_based_choice',
            'prompt_text': 'What does the exhibit show?',
            'domain': 'Format examples',
            'options': [{'id': 'a', 'text': 'A login form'}, {'id': 'b', 'text': 'A settings page'}],
            'answer_key': {'correct_option_ids': ['b']},
            'answer_key_status': 'as_in_source_file',
            'media': {'path': 'media/q059-exhibit.jpg', 'alt': 'A settings page.'},
        }
        doc, issues = mv.migrate_item(
            item, exam_key='EX-TEST', media_rows=[], media_dir=None,
            src_root=None, draft=None, trans=None, excluded=set(),
        )
        self.assertEqual(doc['type'], 'single_choice')
        self.assertNotEqual(doc['type'], 'image_based_choice')
        self.assertTrue(issues)
        self.assertIn('q059', issues[0]['question_key'])
        self.assertTrue(issues[0]['image_path'].endswith('q059-exhibit.jpg'))
        self.assertTrue(doc['answer']['reviewer_needed'])
        self.assertFalse(doc['_migration']['conversion_exact'])
        media = doc['learner'].get('media') or []
        self.assertTrue(media)
        self.assertTrue(media[0]['url'].startswith('/storage/'))

    def test_phrase_match_is_exact_and_mismatch_is_listed(self):
        import migrate_v1_to_v2 as mv
        item = {
            'question_key': 'q002',
            'question_version_key': 'q002-v1',
            'question_type': 'yes_no_matrix',
            'prompt_text': 'For each statement, select Yes or No.',
            'domain': 'Format examples',
            'flags': ['text and key read from images: human confirmation required'],
            'answer_key_status': 'as_in_source_file',
            'answer_key': {'rows': {'r1': 'yes'}},
            'response_schema': {
                'type': 'yes_no_matrix',
                'content': {
                    'rows': [{'id': 'r1', 'text': 'Agents that you create are shared automatically.'}],
                    'columns': [{'id': 'yes', 'text': 'Yes'}, {'id': 'no', 'text': 'No'}],
                },
            },
        }
        draft = {'ocr': [
            {'t': 'Statements'}, {'t': 'Yes'}, {'t': 'No'},
            {'t': 'Agents that you create are shared automatically.'},
        ]}
        trans = {'rows': ['Agents that you create are shared automatically.'], 'columns': ['Yes', 'No']}
        doc, issues = mv.migrate_item(
            item, exam_key='EX-TEST', media_rows=[], media_dir=None,
            src_root=None, draft=draft, trans=trans, excluded=set(),
        )
        self.assertEqual(doc['type'], 'yes_no_matrix')
        self.assertEqual(issues, [])
        self.assertTrue(doc['_migration']['conversion_exact'])
        matrix = doc['learner']['interaction']['matrix']
        self.assertEqual(matrix['rows'][0]['id'], 'r1')
        self.assertEqual(matrix['columns'][0]['id'], 'yes')
        self.assertEqual(doc['answer']['answer_key'], {'r1': 'yes'})

        bad = dict(item)
        bad['response_schema'] = json.loads(json.dumps(item['response_schema']))
        bad['response_schema']['content']['rows'][0]['text'] = 'This sentence is not in the image at all.'
        doc2, issues2 = mv.migrate_item(
            bad, exam_key='EX-TEST', media_rows=[], media_dir=None,
            src_root=None, draft=draft, trans=trans, excluded=set(),
        )
        self.assertTrue(issues2)
        self.assertFalse(doc2['_migration']['conversion_exact'])
        self.assertIn('not confirmed', issues2[0]['reason'])

    def test_normalizes_matrix_key_and_storage_href(self):
        import migrate_v1_to_v2 as mv
        self.assertEqual(mv.normalize_href('media/q.jpg'), '/storage/media/q.jpg')
        self.assertEqual(mv.normalize_answer_key({'rows': {'r1': 'yes'}}, 'yes_no_matrix'), {'cells': {'r1': 'yes'}})

    def test_cli_writes_one_exam_file_and_cannot_convert_report(self):
        import migrate_v1_to_v2 as mv
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            bank = self._bank([{
                'question_key': 'q001',
                'question_version_key': 'q001-v1',
                'question_type': 'single_choice',
                'prompt_text': 'Plain stem',
                'domain': 'Format examples',
                'options': [{'id': 'a', 'text': 'A'}, {'id': 'b', 'text': 'B'}],
                'answer_key': {'correct_option_ids': ['a']},
                'answer_key_status': 'as_in_source_file',
            }])
            (td / 'questions.json').write_text(json.dumps(bank), encoding='utf-8')
            out = td / 'out'
            report = td / 'cannot-convert'
            rc = mv.main([
                '--bank', str(td / 'questions.json'),
                '--out', str(out),
                '--cannot-convert', str(report),
            ])
            self.assertEqual(rc, 0)
            files = list(out.glob('*.site-format.v2.json'))
            self.assertEqual(len(files), 1, files)
            payload = json.loads((td / 'cannot-convert.json').read_text(encoding='utf-8'))
            self.assertEqual(payload['count'], 0)
            self.assertTrue((td / 'cannot-convert.md').is_file())
            doc = json.loads(files[0].read_text(encoding='utf-8'))
            self.assertIn('exam', doc)
            self.assertEqual(len(doc['questions']), 1)
            self.assertEqual(doc['questions'][0]['answer']['status'], 'owner_key')
            errs = vq.validate_doc(doc, vq.load_schema(), vq.load_registry(), vq.load_allowlist())
            self.assertEqual(errs, [], errs)


if __name__ == '__main__':
    unittest.main()
