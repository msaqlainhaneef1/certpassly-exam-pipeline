#!/usr/bin/env python3
"""v1.2.0: writing brief, banned AI phrases, search intent, competitor notes as topics only,
and the check-then-fix writing loop. Synthetic fixtures only (offline, no AI)."""
from __future__ import annotations
import hashlib, json, os, re, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

SKILL=Path(__file__).resolve().parents[1]
FIX=SKILL/'tests'/'fixtures'/'v120'
sys.path.insert(0, str(SKILL/'scripts'))
sys.path.insert(0, str(SKILL/'tests'))
import paths, search_intent as SI, check_writing as CW
import demo_kit
from test_demo_end_to_end import run_cli

DASH=re.compile('[\u2013\u2014]')
OFFICIAL_URL='https://vendor.example.com/syn-210'

def _official_text():
    return CW.visible((FIX/'official-page.html').read_text(encoding='utf-8'))

def _brief_examples():
    t=(SKILL/'reference'/'writing-brief.md').read_text(encoding='utf-8')
    bad=re.findall(r'^\s*\d+\.\s+Bad:\s*(.+)$', t, re.M)
    good=re.findall(r'^\s+Good:\s*(.+)$', t, re.M)
    return bad, good


class WritingBriefFile(unittest.TestCase):
    def test_brief_exists_plain_and_has_no_typographic_dashes(self):
        p=SKILL/'reference'/'writing-brief.md'
        self.assertTrue(p.is_file())
        t=p.read_text(encoding='utf-8')
        self.assertIsNone(DASH.search(t))
        for need in ('people-first','Banned AI phrases','Self-check','Competitor notes','search-intent','Fix only'):
            self.assertIn(need.lower(), t.lower(), need)
        bad,good=_brief_examples()
        self.assertGreaterEqual(len(bad), 10); self.assertEqual(len(bad), len(good))

    def test_new_docs_data_and_fixtures_have_no_typographic_dashes(self):
        files=[SKILL/'reference'/'writing-brief.md', SKILL/'config'/'banned_ai_phrases.txt', SKILL/'SKILL.md', SKILL/'SKILL_BODY.md',
               SKILL/'reference'/'lessons-learned.md', SKILL/'CHANGELOG.md', SKILL/'config'/'pipeline.example.yaml']
        files+=sorted(FIX.glob('*'))
        hits=[str(f) for f in files if DASH.search(f.read_text(encoding='utf-8'))]
        self.assertEqual(hits, [])

    def test_skill_files_point_to_the_brief(self):
        for n in ('SKILL.md','SKILL_BODY.md'):
            t=(SKILL/n).read_text(encoding='utf-8')
            self.assertIn('reference/writing-brief.md', t)
            self.assertIn('search-intent', t)
            self.assertIn('competitor-notes', t)


class BannedPhrases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.phrases=CW.banned_phrases(cfg={})

    def test_list_is_data_and_has_the_brief_examples(self):
        self.assertTrue((SKILL/'config'/'banned_ai_phrases.txt').is_file())
        for p in ("in today's digital world",'unlock your potential','delve','moreover','furthermore','in conclusion','game-changer','holistic approach'):
            self.assertIn(p, self.phrases)

    def test_bad_examples_flagged_good_examples_allowed(self):
        bad,good=_brief_examples()
        for b in bad:
            self.assertTrue(CW.find_banned(b, self.phrases), b)
        for g in good:
            self.assertEqual(CW.find_banned(g, self.phrases), [], g)

    def test_vendor_quote_with_formal_phrase_is_allowed_only_when_verbatim(self):
        off=[_official_text()]
        quoted='<p>The vendor says: "Use a robust, seamless sync to move records between orgs."</p>'
        self.assertEqual(CW.find_banned(quoted, self.phrases, off), [])
        self.assertEqual(CW.find_banned('<blockquote>Use a robust, seamless sync to move records between orgs.</blockquote>', self.phrases, off), [])
        # Not on the saved page: the quote marks do not hide it.
        self.assertTrue(CW.find_banned('<p>"Use a robust, seamless platform."</p>', self.phrases, off))
        # Our own wording around the quote is still checked.
        self.assertIn('moreover', CW.find_banned(quoted+'<p>Moreover, it is fast.</p>', self.phrases, off))

    def test_curly_apostrophe_and_case(self):
        self.assertTrue(CW.find_banned('IN TODAY\u2019S DIGITAL WORLD, things move.', self.phrases))


class SearchIntent(unittest.TestCase):
    def setUp(self):
        self.tmp=Path(tempfile.mkdtemp(prefix='cp120-si-')); paths.set_root(str(self.tmp))
        (self.tmp/'research'/'synvendor').mkdir(parents=True); (self.tmp/'research'/'vendors').mkdir(); (self.tmp/'research'/'certs').mkdir()
        self.R=dict(exam_code='SYN-210', vendor_slug='synvendor', certification_slug='syn-cert', exam_slug='syn-210',
            sources=[dict(id='sg',url=OFFICIAL_URL)], exam_name=dict(value='Synthetic Data Exam',source_id='sg',quote='Synthetic Data Exam'),
            facts=dict(duration_minutes=dict(value=90,source_id='sg',quote='The exam length is 90 minutes.'),
                       passing_score=dict(value=None,reason='not published by the vendor'),
                       languages=dict(value=['English','Spanish'],source_id='sg',quote='Languages: English, Spanish.'),
                       price=dict(value=None,reason='not published by the vendor'),
                       prerequisites=dict(value=None,reason='not published by the vendor')),
            objectives=dict(source_id='sg', domains=[dict(code='1',name='Plan the data model',weight_min_pct=40,weight_max_pct=50,topics=[]),
                                                     dict(code='2',name='Load and secure data',weight_min_pct=50,weight_max_pct=60,topics=[])]))
        self.rpath=self.tmp/'research'/'synvendor'/'SYN-210.json'
        self.rpath.write_text(json.dumps(self.R), encoding='utf-8')
        (self.tmp/'research'/'vendors'/'synvendor.json').write_text(json.dumps(dict(name='Synthetic Vendor')), encoding='utf-8')
        (self.tmp/'research'/'certs'/'syn-cert.json').write_text(json.dumps(dict(name='Synthetic Certified Data Pro')), encoding='utf-8')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_questions_come_from_research_facts_without_inventing_numbers(self):
        d=SI.build(str(self.rpath), cfg={}, root=str(self.tmp))
        q={x['id']:x for x in d['questions']}
        self.assertEqual(q['duration']['expected'], ['90']); self.assertEqual(q['duration']['page'], 'faq')
        self.assertEqual(q['duration']['source_url'], OFFICIAL_URL)
        self.assertEqual(q['languages']['expected'], ['English','Spanish'])
        self.assertEqual(q['outline']['expected'], ['Plan the data model','Load and secure data']); self.assertEqual(q['outline']['page'], 'objectives')
        # gaps the research file records: asked, but no answer value and no number
        self.assertEqual((q['passing_score']['basis'], q['passing_score']['expected'], q['passing_score']['published']), ('gap', [], False))
        self.assertNotIn('question_count', q)  # the research file has no such fact: nothing is made up
        self.assertNotIn('prerequisites', q)   # unpublished and not on the ask list
        self.assertIn('duration', d['pages']['faq']['questions'])
        nums={n for x in d['questions'] for t in x['expected'] for n in re.findall(r'\d+', t)}
        self.assertEqual(nums, {'90'})
        self.assertEqual(SI.check_intent(d, self.R), [])
        self.assertNotIn('\\', json.dumps(d))

    def test_numbers_in_prose_must_come_from_research(self):
        nums=SI.research_numbers(self.R)
        self.assertEqual(CW.numbers('The exam lasts 90 minutes and has 77 questions.')-nums, {'77'})
        self.assertNotIn('3', SI.research_numbers({'sha256':'3'*64, 'url':'https://x.example.com/3'}))

    def test_edited_file_with_an_invented_number_is_caught(self):
        d=SI.build(str(self.rpath), cfg={}, root=str(self.tmp))
        for x in d['questions']:
            if x['id']=='duration': x['expected']=['120']
        self.assertTrue(any('120' in p for p in SI.check_intent(d, self.R)))

    def test_competitor_topics_are_labels_only_and_marked_by_official_support(self):
        sdir=self.tmp/'sources'/'synvendor'; sdir.mkdir(parents=True)
        h=(FIX/'official-page.html').read_text(encoding='utf-8'); (sdir/'p.html').write_text(h, encoding='utf-8')
        (sdir/'p.html.json').write_text(json.dumps(dict(url=OFFICIAL_URL, path=str(sdir/'p.html'), sha256=hashlib.sha256(h.encode()).hexdigest())), encoding='utf-8')
        shutil.copy2(FIX/'competitor-notes.json', self.tmp/'research'/'synvendor'/'SYN-210.competitor-notes.json')
        notes=json.loads((FIX/'competitor-notes.json').read_text(encoding='utf-8'))
        cfg=dict(brand_denylist=['renewal steps'])  # a banned term in a label drops the label
        d=SI.build(str(self.rpath), cfg=cfg, root=str(self.tmp))
        self.assertEqual([t['label'] for t in d['competitor_topics']], ['exam length'])
        self.assertTrue(d['competitor_topics'][0]['official_support'])
        self.assertEqual(d['competitor_labels_dropped'], 2)
        d=SI.build(str(self.rpath), cfg={}, root=str(self.tmp))
        self.assertEqual({t['label'] for t in d['competitor_topics']}, {'exam length','renewal steps'})
        blob=json.dumps(d)
        for s in CW.competitor_strings(notes):
            if len(s.split())>4: self.assertNotIn(s, blob)  # no sentence is copied into the intent file


class IntentCoverage(unittest.TestCase):
    def _q(self, **kw):
        q=dict(id='x', question='?', page='faq', published=True, expected=[], source_url=None, match_any=[], window=400); q.update(kw); return q

    def test_page_that_answers_passes_and_page_that_misses_is_flagged(self):
        ok=(FIX/'page-answers.html').read_text(encoding='utf-8'); miss=(FIX/'page-misses.html').read_text(encoding='utf-8')
        npw=SI.NOT_PUBLISHED_WORDS; W=CW.DEFAULTS
        dur=self._q(id='duration', expected=['90'], source_url=OFFICIAL_URL, match_any=['how long','minutes'])
        ps=self._q(id='passing_score', published=False, match_any=['to pass','pass mark'])
        lang=self._q(id='languages', expected=['English','Spanish'], match_any=['language'])
        for q in (dur, ps, lang): self.assertEqual(CW.intent_miss(q, ok, npw, W), '', q['id'])
        self.assertIn('never names the topic', CW.intent_miss(dur, miss, npw, W))
        self.assertIn('does not publish', CW.intent_miss(ps, miss, npw, W))
        self.assertEqual(CW.intent_miss(lang, miss, npw, W), '')
        # A fact answer needs the official source link on the page.
        self.assertIn('no link', CW.intent_miss(dur, ok.replace(OFFICIAL_URL, 'https://other.example.com/'), npw, W))


class CompetitorOverlap(unittest.TestCase):
    def setUp(self):
        notes=json.loads((FIX/'competitor-notes.json').read_text(encoding='utf-8'))
        self.n=CW.DEFAULTS['competitor_overlap_words']
        self.cs=set()
        for s in CW.competitor_strings(notes): self.cs|=CW.shingles(CW.tokens(s), self.n)
        self.allowed=frozenset(CW.shingles(CW.tokens(_official_text()), self.n) & self.cs)

    def test_copied_wording_in_html_or_prose_fails(self):
        h=(FIX/'page-copied.html').read_text(encoding='utf-8')
        runs=CW.copied_runs(h, self.cs, self.n, self.allowed)
        self.assertEqual(len(runs), 1); self.assertGreaterEqual(len(runs[0].split()), 15)
        prose=json.dumps({'faq':{'body_html':h}})
        self.assertTrue(CW.copied_runs(prose, self.cs, self.n, self.allowed))

    def test_same_topic_in_original_words_with_official_quote_passes(self):
        h=(FIX/'page-original.html').read_text(encoding='utf-8')
        self.assertEqual(CW.copied_runs(h, self.cs, self.n, self.allowed), [])
        # without the official page the shared renewal sentence would count as copied
        self.assertTrue(CW.copied_runs(h, self.cs, self.n, frozenset()))


class NoModelCalls(unittest.TestCase):
    def test_runner_and_writing_scripts_never_call_a_model(self):
        rx=re.compile(r'openai|anthropic|generativelanguage|api\.mistral|import\s+requests|urllib\.request|http\.client', re.I)
        for n in ('run_pipeline.py','check_writing.py','search_intent.py'):
            self.assertIsNone(rx.search((SKILL/'scripts'/n).read_text(encoding='utf-8')), n)


class WritingLoopOnDemo(unittest.TestCase):
    """Full CLI demo run, then a flagged fix round, then the second check."""
    @classmethod
    def setUpClass(cls):
        cls.tmp=Path(tempfile.mkdtemp(prefix='cp120-loop-'))
        cls.info=demo_kit.build('salesforce', cls.tmp/'ws')
        cls.root=Path(cls.info['root']); cls.exam=cls.info['exam']; cls.out=cls.root/'out'/cls.exam
        cls.r=run_cli(cls.root, cls.exam)
        cls.rpath=cls.root/'research'/cls.info['vendor']/f'{cls.exam}.json'
        paths.set_root(str(cls.root))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _stages(self, *stages):
        env=os.environ.copy(); env['PYTHONIOENCODING']='utf-8'; env.pop('CERTPASSLY_ROOT', None)
        exe=shutil.which('certpassly-pipeline')
        cmd=([exe] if exe else [sys.executable, str(SKILL/'scripts'/'run_pipeline.py')])+['--exam', self.exam, '--root', str(self.root), '--offline', '--date', demo_kit.DATE]
        for s in stages: cmd+=['--stage', s]
        return subprocess.run(cmd, cwd=str(self.root), env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')

    def _review(self):
        return json.loads((self.out/'writing-review.json').read_text(encoding='utf-8'))

    def _core(self):
        q=json.loads((self.out/'questions.json').read_text(encoding='utf-8'))
        return [(x['question_key'], x['question_type'], x['prompt_text'], json.dumps(x['options'], sort_keys=True), json.dumps(x['answer_key'], sort_keys=True)) for x in q['questions']]

    def test_loop(self):
        self.assertEqual(self.r.returncode, 0, (self.r.stdout+self.r.stderr)[-3000:])
        for st in ('intent','writing'): self.assertIn(f'==== stage {st} done ====', self.r.stdout)
        # clean run: zero flags, findings list only failed checks
        rv=self._review()
        self.assertEqual((rv['flag_count'], rv['flags'], rv['round']), (0, [], 1))
        self.assertIn('No flags.', (self.out/'WRITING-REVIEW.md').read_text(encoding='utf-8'))
        self.assertFalse((self.out/'authoring'/'writing_fix_request.json').exists())
        self.assertIn('competitor_copy', rv['checks_run'])
        val=json.loads((self.out/'validation.json').read_text(encoding='utf-8'))
        self.assertTrue(any(r['check'].startswith('19 writing') and r['passed'] for r in val))
        # the competitor phrase never reaches an output
        for p in list(self.out.rglob('*'))+list((self.root/'out').glob('*/*/*')):
            if p.is_file() and p.suffix in ('.html','.json','.csv','.md'):
                self.assertNotIn(demo_kit.COMPETITOR_PHRASE.lower()[:60], p.read_text(encoding='utf-8', errors='replace').lower(), str(p))
        for f in (self.root/'research'/self.info['vendor']/f'{self.exam}.search-intent.json', self.out/'writing-review.json'):
            self.assertNotIn('\\\\', f.read_text(encoding='utf-8'))
        si=json.loads((self.out/'pages'/'faq.json').read_text(encoding='utf-8'))['search_intent']
        self.assertIn('duration', [q['id'] for q in si['questions']])
        core0=self._core(); csv0=hashlib.sha256((self.out/'import'/'questions.csv').read_bytes()).hexdigest()

        # A writer copies competitor wording, adds a banned phrase, and drops an answer on the FAQ page.
        pp=self.out/'authoring'/'page_prose.json'
        orig=pp.read_text(encoding='utf-8'); prose=json.loads(orig)
        good_faq=prose['faq']['body_html']
        prose['faq']['body_html']=good_faq.replace('<h2>How long is the exam?</h2>','<h2>Timing</h2>').replace('105 minutes','the full time')+'<p>Moreover, '+demo_kit.COMPETITOR_PHRASE+'</p>'
        pp.write_text(json.dumps(prose, indent=1, ensure_ascii=False), encoding='utf-8')
        ok,why=CW.gate_status(str(self.rpath), root=str(self.root))
        self.assertFalse(ok); self.assertIn('changed', why)  # validate gate: the check must run again
        r=self._stages('pages','writing')
        self.assertEqual(r.returncode, 1, r.stdout[-2000:])
        rv=self._review()
        checks={f['check'] for f in rv['flags']}
        self.assertEqual(checks, {'banned_ai_phrase','competitor_copy','search_intent_missed'})
        self.assertEqual({f['part'] for f in rv['flags']}, {'page_prose:faq'})
        fix=json.loads((self.out/'authoring'/'writing_fix_request.json').read_text(encoding='utf-8'))
        self.assertEqual(list(fix['parts']), ['page_prose:faq'])  # only the flagged part goes back
        md=(self.out/'WRITING-REVIEW.md').read_text(encoding='utf-8')
        self.assertEqual(md.count('| page_prose:faq |'), rv['flag_count'])
        self.assertIn('writing flags are still open', (self.out/'REVIEW.md').read_text(encoding='utf-8'))

        # The fix touches the FAQ only, but the writer also rewrote a page that had passed.
        prose['faq']['body_html']=good_faq
        prose['objectives']['body_html']=prose['objectives']['body_html'].replace('Use the official task wording','Use the exact official task wording')
        pp.write_text(json.dumps(prose, indent=1, ensure_ascii=False), encoding='utf-8')
        r=self._stages('pages')  # pages alone still runs the second check and records the flags
        self.assertIn('second check', r.stdout)
        self.assertEqual(r.returncode, 0, r.stdout[-2000:])
        self.assertEqual(CW.gate_status(str(self.rpath), root=str(self.root))[0], False)  # validate 19 would fail
        rv=self._review()
        self.assertEqual([(f['check'], f['part']) for f in rv['flags']], [('unflagged_part_changed','page_prose:objectives')])

        # Put the objectives page back: clean, second check passes, keys untouched.
        pp.write_text(orig, encoding='utf-8')
        r=self._stages('pages','writing','import','bank','validate')
        self.assertEqual(r.returncode, 0, r.stdout[-3000:])
        rv=self._review()
        self.assertEqual((rv['flag_count'], rv['round']), (0, 4))
        self.assertTrue(rv['resolved_since_previous_round'])
        self.assertFalse((self.out/'authoring'/'writing_fix_request.json').exists())
        self.assertIn('No open writing flags', (self.out/'REVIEW.md').read_text(encoding='utf-8'))
        self.assertEqual(self._core(), core0)
        self.assertEqual(hashlib.sha256((self.out/'import'/'questions.csv').read_bytes()).hexdigest(), csv0)
        self.assertEqual(CW.gate_status(str(self.rpath), root=str(self.root)), (True, 'round 4, 0 flags'))


if __name__=='__main__':
    unittest.main(verbosity=2)
