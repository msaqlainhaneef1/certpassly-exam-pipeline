#!/usr/bin/env python3
"""End-to-end demo runs for both adapter paths (offline, no AI, no network).

Builds the synthetic workspaces from tests/demo_kit.py and runs every default
stage (catalog, intake, sources, research, extract, author, pages, import,
bank, validate, package) through the CLI with no manual step. Runs in CI.
"""
from __future__ import annotations
import json, os, re, shutil, subprocess, sys, tempfile, unittest, zipfile
from pathlib import Path

SKILL=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL/'tests'))
import demo_kit

BANNED=re.compile('|'.join([demo_kit.SELLER.split()[0].lower(), 'it'+'tech', r'facebook\.com', r'free\s+update', re.escape(demo_kit.PHONE), re.escape(demo_kit.EMAIL)]), re.I)  # built from demo_kit so the raw seller name is not repeated

def run_cli(root: Path, exam: str):
    env=os.environ.copy()
    for k in ('https_proxy','http_proxy','HTTPS_PROXY','HTTP_PROXY','ALL_PROXY'):
        env[k]='http://127.0.0.1:9'
    env['no_proxy']=''; env['NO_PROXY']=''
    env['PYTHONIOENCODING']='utf-8'
    env.pop('CERTPASSLY_ROOT', None)
    exe=shutil.which('certpassly-pipeline')
    cmd=[exe] if exe else [sys.executable, str(SKILL/'scripts'/'run_pipeline.py')]
    cmd+=['--exam', exam, '--root', str(root), '--offline', '--date', demo_kit.DATE]
    return subprocess.run(cmd, cwd=str(root), env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')


class _DemoBase:
    PROFILE=''
    @classmethod
    def setUpClass(cls):
        cls.tmp=Path(tempfile.mkdtemp(prefix=f'certpassly-demo-{cls.PROFILE}-'))
        cls.info=demo_kit.build(cls.PROFILE, cls.tmp/'ws')
        cls.root=Path(cls.info['root']); cls.exam=cls.info['exam']
        cls.r=run_cli(cls.root, cls.exam)
        cls.log=cls.r.stdout+'\n'+cls.r.stderr
        cls.out=cls.root/'out'/cls.exam

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_01_cli_exit_zero_no_manual_step(self):
        self.assertEqual(self.r.returncode, 0, self.log[-4000:])
        for st in ('catalog','intake','sources','research','extract','author','pages','import','bank','validate','package'):
            self.assertIn(f'==== stage {st} done ====', self.log)

    def test_02_validate_and_check_bank_all_pass(self):
        rows=json.loads((self.out/'validation.json').read_text(encoding='utf-8'))
        failed=[r for r in rows if not (r.get('passed', r.get('ok')) if isinstance(r, dict) else r[1])]
        self.assertEqual(failed, [])
        self.assertGreaterEqual(len(rows), 55)
        self.assertRegex(self.log, r'Summary: \d+ passed, 0 failed')

    def test_03_types_holds_and_flags(self):
        q=json.loads((self.out/'questions.json').read_text(encoding='utf-8'))
        types=sorted(x['question_type'] for x in q['questions'])
        self.assertEqual(types, ['inline_dropdown','multiple_select','single_choice','yes_no_matrix'])
        held={h['question_key']:h['reason'] for h in q['held_for_review']}
        self.assertEqual(sorted(held), ['q005','q006'])
        self.assertIn('no answer', held['q006'])
        vis=[x for x in q['questions'] if x['question_type'] in ('yes_no_matrix','inline_dropdown')]
        self.assertTrue(all(x['human_review_required'] for x in vis))
        self.assertTrue(all(x['publication_state']=='draft' for x in q['questions']))

    def test_04_review_lists_vce_holds_and_cover_conflict(self):
        rv=(self.out/'REVIEW.md').read_text(encoding='utf-8')
        self.assertIn('.vce', rv)
        self.assertIn('q005', rv); self.assertIn('q006', rv)
        self.assertIn('Cover says', rv)
        self.assertNotIn('41 image-based', rv)
        self.assertIn('2 image-based items', rv)
        files=json.loads((self.out/'intake'/'files.json').read_text(encoding='utf-8'))['files']
        self.assertEqual(sorted(f['use'].split(':')[0] for f in files), ['extracted','skipped'])

    def test_05_branding_stripped_from_site_outputs(self):
        hits=[]
        for base in (self.out/'pages', self.out/'import', self.out/'questions.json', self.root/'out'/'vendors', self.root/'out'/'certifications'):
            paths=[base] if base.is_file() else list(base.rglob('*'))
            for p in paths:
                if p.is_file() and p.suffix in ('.html','.json','.csv','.md'):
                    if BANNED.search(p.read_text(encoding='utf-8', errors='replace')): hits.append(str(p))
        self.assertEqual(hits, [])
        # the extractor really saw the branding, so the gate is exercised, not vacuous
        cl=json.loads((self.out/'extracted'/'cleanups.json').read_text(encoding='utf-8'))
        self.assertGreaterEqual(len(cl), 5)

    def test_06_five_tables_meta_and_jsonld(self):
        pages=[json.loads(p.read_text(encoding='utf-8')) for p in (self.out/'pages').glob('*.json')]
        pages+=[json.loads(p.read_text(encoding='utf-8')) for p in (self.root/'out').glob('*/*/*.json') if p.stem in ('vendor','certification')]
        kinds={p['kind']:p for p in pages}
        for k in ('exam_hub','objectives','study_guide','vendor','certification'):
            self.assertIn('<table', kinds[k]['body_html'], k)
        for p in pages:
            self.assertTrue(50<=len(p['meta']['title'])<=60); self.assertTrue(140<=len(p['meta']['meta_description'])<=160)
        types={k:[j['@type'] for j in p['jsonld']] for k,p in kinds.items()}
        self.assertIn('Course', types['study_guide']); self.assertNotIn('Course', types['practice_test'])
        self.assertIn('EducationalOccupationalCredential', types['certification'])

    def test_07_package_zip(self):
        z=self.root/f'{self.exam}-package.zip'
        self.assertTrue(z.is_file())
        names=zipfile.ZipFile(z).namelist()
        self.assertTrue(any(n.endswith('questions.json') for n in names))
        self.assertTrue(any('/vendors/' in n for n in names))


class TestDemoMicrosoftAdapter(_DemoBase, unittest.TestCase):
    PROFILE='microsoft'
    def test_08_adapter_agrees_and_partner_kept(self):
        self.assertIn('"domains": true', self.log)
        hub=(self.out/'pages'/'exam-hub.html').read_text(encoding='utf-8')
        self.assertIn('Pearson VUE', hub)


class TestDemoGenericAdapter(_DemoBase, unittest.TestCase):
    PROFILE='salesforce'
    def test_08_unpublished_pass_mark_is_honest(self):
        hub=json.loads((self.out/'pages'/'exam-hub.json').read_text(encoding='utf-8'))
        blob=hub['body_html']
        self.assertIn('not published by the vendor', blob)
        self.assertNotIn('None or higher', blob)
        parsed=json.loads((self.root/'research'/'salesforce'/f'{self.exam}.parsed.json').read_text(encoding='utf-8'))
        self.assertEqual(parsed['fields'].get('duration_minutes'), 105)
        self.assertEqual(parsed['fields'].get('languages'), ['English','Japanese'])
        self.assertEqual([d['name'] for d in parsed['fields']['domains']], ['Configuration and setup','Objects, data and security'])
        self.assertIn('passing_score', parsed['gaps'])


if __name__=='__main__':
    unittest.main(verbosity=2)
