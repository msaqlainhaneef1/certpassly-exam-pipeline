#!/usr/bin/env python3
"""Fixes found by the first real v1.2.0 run (synthetic inputs only, offline)."""
from __future__ import annotations
import csv, hashlib, json, os, re, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

SKILL=Path(__file__).resolve().parents[1]


class CatalogCleanSheet(unittest.TestCase):
    def test_clean_sheet_writes_header_only_review_csv(self):
        """A sheet with nothing to review crashed build_catalog (review[0] on an empty list)."""
        sys.path.insert(0, str(SKILL/'scripts'))
        import vendor_reg
        exams=vendor_reg.exam_lookup().get('exams') or {}
        vendors=vendor_reg.vendors().get('vendors') or {}
        code,meta=next((c,m) for c,m in sorted(exams.items()) if m.get('urls') and m.get('vendor') in vendors)
        vname=vendors[meta['vendor']].get('name') or meta['vendor']
        tmp=Path(tempfile.mkdtemp(prefix='cp120-cat-'))
        try:
            (tmp/'config').mkdir()
            shutil.copy2(SKILL/'config'/'pipeline.example.yaml', tmp/'config'/'pipeline.yaml')
            shutil.copy2(SKILL/'config'/'vendors.example.yaml', tmp/'config'/'vendors.yaml')
            (tmp/'sheet.csv').write_text(f'{vname},,\n{code},,https://drive.google.com/drive/folders/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\n', encoding='utf-8')
            # Seed the URL cache so the check never touches the network.
            src=tmp/'sources'; src.mkdir()
            for u in meta['urls']:
                key=hashlib.sha1(u.encode()).hexdigest()[:16]
                body=f'<html><body><h1>{code}</h1></body></html>'
                (src/f'{key}.html').write_text(body, encoding='utf-8')
                (src/f'{key}.html.json').write_text(json.dumps(dict(url=u, http='404', final_url=u, sha256=hashlib.sha256(body.encode()).hexdigest(), path=str(src/f'{key}.html'), retrieved_at='2026-11-11T00:00:00+0500')), encoding='utf-8')
            env=os.environ.copy(); env['CERTPASSLY_ROOT']=str(tmp); env['PYTHONPATH']=str(SKILL/'scripts')
            r=subprocess.run([sys.executable, str(SKILL/'scripts'/'build_catalog.py'), '--root', str(tmp), '--sheet', str(tmp/'sheet.csv')], env=env, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout+r.stderr)
            rows=list(csv.reader(open(tmp/'review.csv', encoding='utf-8')))
            self.assertEqual(rows, [['reason','raw_label','drive_link','sheet_cell','context_vendor','note']])
            cat=list(csv.DictReader(open(tmp/'catalog.csv', encoding='utf-8')))
            self.assertEqual([c['exam_code'] for c in cat], [code])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def _xml(pages):
    out=['<?xml version="1.0"?><pdf2xml>']
    for n,body in pages:
        out.append(f'<page number="{n}" position="absolute" top="0" left="0" height="1000" width="800">{body}</page>')
    out.append('</pdf2xml>'); return ''.join(out)


def _t(top,txt): return f'<text top="{top}" left="50" width="400" height="12" font="0">{txt}</text>'
def _i(top,src): return f'<image top="{top}" left="50" width="400" height="100" src="x/{src}"/>'


class ExtractKeyedImageBeforeEmptyMarker(unittest.TestCase):
    """Real run: 33 hotspot items had the keyed answer area image BEFORE an empty "Correct Answer:" line."""
    def _split(self, xml):
        sys.path.insert(0, str(SKILL/'scripts'))
        import extract_owner_pdf as E, site_settings
        els=E.load_elements(xml); lay=E.detect_layout(els)
        s,c,u=E.split_items(els, lay, E.compile_deny(site_settings.load()))
        m=E.promote_answer_copies(s,c)
        return s,c,m

    def test_last_image_becomes_answer_image(self):
        xml=_xml([(1,_t(50,'QUESTION 1')+_t(70,'HOTSPOT -')+_t(90,'Select the answer that correctly completes the sentence.')+_i(120,'p-1_1.png')),
                  (2,_i(40,'p-2_1.png')+_t(160,'A.')+_t(180,'B.')+_t(200,'Correct Answer:')+_t(220,'Section: (none)')),
                  (3,_t(50,'QUESTION 2')+_t(70,'Which service stores keys?')+_t(90,'A. Key Vault')+_t(110,'B. Blob storage')+_t(130,'Correct Answer: A')),
                  (4,_t(50,'QUESTION 3')+_t(70,'HOTSPOT -')+_t(90,'Pick the right setting.')+_i(120,'p-4_1.png')+_t(240,'Correct Answer:')+_i(260,'p-4_2.png'))])
        s,c,m=self._split(xml)
        self.assertEqual(m,1)
        q1=s['q001']
        self.assertEqual(q1['question_images'],['p-1_1.png']); self.assertEqual(q1['answer_images'],['p-2_1.png'])
        self.assertTrue(q1.get('answer_image_inferred'))
        self.assertTrue(any(x['question_key']=='q001' and x['field']=='answer_images' for x in c))
        # Text-keyed and normally image-keyed items are untouched; no private marker leaks out.
        self.assertEqual(s['q002']['answer_raw'],'A'); self.assertEqual(s['q002']['answer_images'],[])
        self.assertEqual(s['q003']['answer_images'],['p-4_2.png']); self.assertNotIn('answer_image_inferred', s['q003'])
        self.assertFalse(any('_answer_marker' in r for r in s.values()))

    def test_single_image_without_key_is_left_for_answer_research(self):
        xml=_xml([(1,_t(50,'QUESTION 1')+_t(70,'HOTSPOT -')+_t(90,'Pick one.')+_i(120,'p-1_1.png')+_t(240,'Correct Answer:')),
                  (2,_t(50,'QUESTION 2')+_t(70,'Which one?')+_t(90,'A. One')+_t(110,'B. Two')+_t(130,'Correct Answer: B'))])
        s,c,m=self._split(xml)
        self.assertEqual(m,0)
        self.assertEqual(s['q001']['answer_images'],[]); self.assertEqual(s['q001']['question_images'],['p-1_1.png'])


class LostLigatureRepair(unittest.TestCase):
    """Real run: the PDF font had no Unicode map for fi/fl/ff/ffi glyphs, so stems read "De ne", "speci c"."""
    def setUp(self):
        sys.path.insert(0, str(SKILL/'scripts'))
        import text_repair
        self.T=text_repair

    def test_gap_inside_word_and_lost_leading_glyph(self):
        cases={'De ne the plan':'Define the plan','a speci c word':'a specific word','for O ce use':'for Office use',
               'in a review work ow, then':'in a review workflow, then','the rst step':'the first step',
               'how long les are kept':'how long files are kept','Con gure it':'Configure it','A. ngerprint':'A. fingerprint',
               'noti cation and certi cate':'notification and certificate'}
        for src,want in cases.items():
            got,ch=self.T.repair(src)
            self.assertEqual(got,want,src); self.assertTrue(ch,src)

    def test_real_words_are_left_alone(self):
        for src in ['a re is lit','do the work now','the risk is low','Yes or No','use SSO on the app','the best one']:
            got,ch=self.T.repair(src)
            self.assertEqual(got,src); self.assertEqual(ch,[])

    def test_extract_logs_each_repair_in_cleanups(self):
        import extract_owner_pdf as E, site_settings
        xml=_xml([(1,_t(50,'QUESTION 1')+_t(70,'Which step comes rst in the work ow?')+_t(90,'A. De ne the scope')+_t(110,'B. Delete les')+_t(130,'Correct Answer: A'))])
        els=E.load_elements(xml); lay=E.detect_layout(els)
        s,c,u=E.split_items(els, lay, E.compile_deny(site_settings.load()))
        self.assertEqual(s['q001']['stem'],'Which step comes first in the workflow?')
        self.assertEqual(s['q001']['options'],{'a':'Define the scope','b':'Delete files'})
        self.assertEqual(s['q001']['answer_raw'],'A')
        fixes=[x for x in c if 'ligature' in x['reason']]
        self.assertEqual(sorted((x['field'],x['after']) for x in fixes),[('option.a','Define'),('option.b','files'),('stem','first'),('stem','workflow')])


class ExamLengthNotExtraTime(unittest.TestCase):
    """Real run: research took "you can request an additional 30 minutes" as the exam length, and
    discovery picked a generic score-report page as the credential page."""
    def setUp(self):
        sys.path.insert(0, str(SKILL/'scripts')); sys.path.insert(0, str(SKILL/'scripts'/'adapters'))

    def test_generic_scan_skips_extra_time(self):
        import re, generic
        pages=[dict(id='sg', lines=['If the exam is not in your language, you can request an additional 30 minutes to complete the exam.',
                                    'Some candidates get 25 extra minutes.']),
               dict(id='cp', lines=['Take the exam', 'You will have 45 minutes to complete this assessment.'])]
        v,q,sid=generic._scan(pages, generic.DURATION_PATTERNS, check=lambda v: 15<=v<=360)
        self.assertEqual((v,sid),(45,'cp')); self.assertIn('45 minutes', q)

    def test_vendor_adapter_cp_duration(self):
        import microsoft
        m=microsoft.cp_duration('You can request an additional 30 minutes. Take the exam. You will have 45 minutes to complete this assessment.')
        self.assertEqual(m.group(1),'45')
        self.assertIsNone(microsoft.cp_duration('You can request an additional 30 minutes to complete the exam.'))

    def test_discovery_prefers_link_that_names_the_exam(self):
        import research_init, vendor_reg
        pat=r'https://learn\.example\.com/[a-z-]*/?credentials/certifications/(?:exams/[A-Za-z0-9-]+|(?!resources/)[a-z0-9-]+)/?'
        seed='https://learn.example.com/en-us/credentials/certifications/resources/study-guides/zz-101'
        urls=['https://learn.example.com/en-us/credentials/certifications/exam-scoring-reports',
              'https://learn.example.com/en-us/credentials/certifications/request-accommodations',
              'https://learn.example.com/en-us/credentials/certifications/exams/ZZ-101', seed]
        self.assertEqual(research_init.pick_link(urls, pat, seed, 'ZZ-101'), urls[2])
        # No exam-named link: keep the old first-match behaviour.
        self.assertEqual(research_init.pick_link(urls[:2], pat, seed, 'ZZ-101'), urls[0])
        self.assertIsNone(research_init.pick_link([seed], pat, seed, 'ZZ-101'))
        # The shipped Microsoft pattern accepts exam links.
        mp=(vendor_reg.vendors().get('vendors') or {}).get('microsoft',{}).get('discover_cp')
        if mp:
            self.assertTrue(re.fullmatch(mp, 'https://learn.microsoft.com/en-us/credentials/certifications/exams/AB-123'))

    def test_links_keep_hrefs_with_a_fragment(self):
        import research_init
        d=Path(tempfile.mkdtemp(prefix='cp120-links-'))
        try:
            (d/'p.html').write_text('<a href="#top">x</a><a href="/c/exams/ZZ-101#ways">e</a><a href="/c/policy">p</a>', encoding='utf-8')
            L=research_init.links(dict(path=str(d/'p.html'), url='https://learn.example.com/c/guide/zz-101'))
            self.assertEqual(L, ['https://learn.example.com/c/exams/ZZ-101','https://learn.example.com/c/policy'])
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__=='__main__':
    unittest.main(verbosity=2)


class DragDropType(unittest.TestCase):
    """DRAG DROP items were forced into a drop-down type, which the marker gate (validate 12f) rightly rejects."""
    def setUp(self):
        sys.path.insert(0, str(SKILL/'scripts'))
        import qtypes; self.Q=qtypes
    def item(self, stem):
        return dict(stem=stem, options={}, answer_raw='', question_images=['a.png'], answer_images=['b.png'])
    def test_tiles_and_targets_classify_as_drag_drop(self):
        vt=dict(tiles=['Corrective','Detective','Preventative'], targets=['Encrypt data.','Audit access.'], key=[2,1])
        t,reason=self.Q.classify(self.item('DRAG DROP - Match each action to its type. Select and Place:'), vt)
        self.assertEqual(t, 'drag_drop'); self.assertIn('tiles', reason)
        self.assertIn('drag_drop', self.Q.registry()[0])
        self.assertEqual(self.Q.agree('drag_drop', 'DRAG DROP - Match each action.'), [])
    def test_marker_gate_names_the_fix(self):
        p=self.Q.agree('multi_blank_dropdown', 'DRAG DROP - Match each action.', n_blanks=2)
        self.assertTrue(p and 'drag_drop' in p[0], p)
        self.assertEqual(self.Q.agree('drag_drop', 'Select the answer that correctly completes the sentence.'), ['drag_drop type without DRAG DROP marker'])


class DragDropAndUnpublishedFactsEndToEnd(unittest.TestCase):
    """End to end on the demo: a DRAG DROP item becomes drag_drop with pairs, and unpublished
    languages, formats and level render as not published instead of crashing build_pages."""
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(SKILL/'tests'))
        import demo_kit
        from test_demo_end_to_end import run_cli
        cls.tmp=Path(tempfile.mkdtemp(prefix='cp120-dd-'))
        info=demo_kit.build('microsoft', cls.tmp/'ws'); cls.root=Path(info['root']); E=cls.exam=info['exam']
        out=cls.root/'out'/E
        r=run_cli(cls.root, E)  # full run first: baseline must pass
        cls.base_rc=r.returncode; cls.base_log=r.stdout+r.stderr
        # unpublished facts
        rp=cls.root/'research'/info['vendor']/f'{E}.json'; R=json.loads(rp.read_text(encoding='utf-8'))
        for k in ('languages','question_formats','level'):
            R['facts'][k]={'value':None,'reason':'not published by the vendor'}
        rp.write_text(json.dumps(R, indent=1), encoding='utf-8')
        pp=out/'authoring'/'page_prose.json'; P=json.loads(pp.read_text(encoding='utf-8'))
        P['faq']['body_html']=re.sub(r'(<h2>Which languages are offered\?</h2><p>)[^<]*', r'\1The list of languages is not published by the vendor.', P['faq']['body_html'])
        P['faq']['faq_sourced']=[q for q in P['faq'].get('faq_sourced',[]) if 'language' not in q]
        P['faq']['faq_unsourced']=list(P['faq'].get('faq_unsourced',[]))+['Which languages are offered?']
        pp.write_text(json.dumps(P, indent=1), encoding='utf-8')
        # q004 becomes a DRAG DROP item (stem marker + tiles/targets transcription + per target, per tile explanations)
        sp=out/'extracted'/'split.json'; S=json.loads(sp.read_text(encoding='utf-8'))
        S['q004']['stem']='DRAG DROP - '+S['q004']['stem']; sp.write_text(json.dumps(S, indent=1), encoding='utf-8')
        vp=out/'extracted'/'visual_transcription.json'; V=json.loads(vp.read_text(encoding='utf-8'))
        V['q004']=dict(tiles=['daily','weekly','monthly'], targets=['Backups run','Reports run'], key=[0,1], note='drag-and-drop item')
        vp.write_text(json.dumps(V, indent=1), encoding='utf-8')
        ep=out/'authoring'/'explanations_visual.json'; X=json.loads(ep.read_text(encoding='utf-8'))
        X['q004']=dict(c='Backups run daily and reports run weekly in this demo.', o=[['Right. Daily.','Wrong. Too sparse.','Wrong. Too sparse.'],['Wrong. Too often.','Right. Weekly.','Wrong. Too sparse.']], s=['SG'], a='key_matches_current_docs')
        ep.write_text(json.dumps(X, indent=1), encoding='utf-8')
        env=os.environ.copy(); env.pop('CERTPASSLY_ROOT', None)
        exe=shutil.which('certpassly-pipeline'); cmd=[exe] if exe else [sys.executable, str(SKILL/'scripts'/'run_pipeline.py')]
        cmd+=['--exam',E,'--root',str(cls.root),'--offline','--date',demo_kit.DATE]
        for st in ('intent','pages','writing','import','bank','validate','package'): cmd+=['--stage',st]
        r2=subprocess.run(cmd, cwd=str(cls.root), env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
        cls.rc=r2.returncode; cls.log=r2.stdout+r2.stderr; cls.out=out
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)
    def test_baseline_run_passes(self):
        self.assertEqual(self.base_rc, 0, self.base_log[-3000:])
    def test_rerun_passes_every_gate(self):
        self.assertEqual(self.rc, 0, self.log[-4000:])
        self.assertNotIn('Traceback', self.log)
        rows=json.loads((self.out/'validation.json').read_text(encoding='utf-8'))
        failed=[r for r in rows if not (r.get('passed', r.get('ok')) if isinstance(r, dict) else r[1])]
        self.assertEqual(failed, [])
        self.assertRegex(self.log, r'Summary: \d+ passed, 0 failed')
    def test_drag_drop_item_shape(self):
        q=next(x for x in json.loads((self.out/'questions.json').read_text(encoding='utf-8'))['questions'] if x['question_key']=='q004')
        self.assertEqual(q['question_type'], 'drag_drop')
        c=q['response_schema']['content']
        self.assertEqual([t['text'] for t in c['left']], ['daily','weekly','monthly'])
        self.assertEqual([t['text'] for t in c['right']], ['Backups run','Reports run'])
        self.assertEqual(q['answer_key'], {'pairs':{'z1':'t1','z2':'t2'}})
        self.assertEqual(q['explanations']['z2.t2'], 'Right. Weekly.')
        self.assertFalse([f for f in q['flags'] if f.startswith('MARKER')])
    def test_unpublished_facts_render_as_not_published(self):
        hub=(self.out/'pages'/'exam-hub.html').read_text(encoding='utf-8')
        for label in ('Languages','Format','Level'):
            m=re.search(r'<t[dh]>'+label+r'</t[dh]>\s*<td>([^<]*)', hub)
            self.assertTrue(m, label); self.assertIn('not published', m.group(1).lower())
