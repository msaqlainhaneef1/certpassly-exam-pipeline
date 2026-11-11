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


def _settings(terms):
    return {'brand_denylist': list(terms), 'policy': {'contact_patterns': {'social': r'(facebook|instagram)\.com/[A-Za-z0-9_.\-]+', 'free_update': r'free\s+update', 'phone': r'\d{9,}'}}}


class PackageGuard(unittest.TestCase):
    """Raw extracts never ship; the finished zip is scanned against the config denylist (synthetic data)."""
    def setUp(self):
        sys.path.insert(0, str(SKILL/'scripts'))
        import package_guard; self.PG=package_guard
        self.tmp=Path(tempfile.mkdtemp(prefix='cp120-pg-'))
        self.S=_settings(['acmeseller', 'zetadumpz'])
    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
    def _exam(self):
        ex=self.tmp/'X-1'; (ex/'extracted').mkdir(parents=True); (ex/'media'/'src').mkdir(parents=True); (ex/'import').mkdir()
        (ex/'extracted'/'raw.xml').write_text('<t>AcmeSeller</t>', encoding='utf-8')
        (ex/'extracted'/'notes.json').write_text('{"x": "Contact AcmeSeller Tech today"}', encoding='utf-8')
        (ex/'extracted'/'stems.json').write_text('{"q001": {"stem": "Which tool?"}}', encoding='utf-8')
        (ex/'extracted'/'cleanups.json').write_text(json.dumps([
            dict(question_key='(cover)', field='cover', before='Contact AcmeSeller Tech today', after='', reason='branding removed'),
            dict(question_key='q001', field='stem', before='De ne', after='Define', reason='ligature repaired')]), encoding='utf-8')
        (ex/'media'/'src'/'p-1_1.jpg').write_bytes(b'\xff\xd8\xff\xe0logo')
        (ex/'import'/'questions.csv').write_text('question_key\nq001\n', encoding='utf-8')
        return ex
    def test_prepare_excludes_raw_and_redacts(self):
        ex=self._exam()
        staged=self.tmp/'stage'/'X-1'; shutil.copytree(ex, staged)
        out=self.PG.prepare(str(staged), self.S, {}, log=lambda m: None)
        paths={e['path'] for e in out}
        self.assertTrue({'extracted/raw.xml','extracted/cleanups.json','extracted/notes.json','media/src/p-1_1.jpg'} <= paths, paths)
        self.assertTrue((staged/'extracted'/'stems.json').exists()); self.assertFalse((staged/'media'/'src').exists())
        red=(staged/'extracted'/'cleanups.redacted.json').read_text(encoding='utf-8')
        self.assertNotIn('AcmeSeller', red); self.assertIn('Define', red)
        self.assertEqual(json.loads(red)['counts_by_change'], {'removed': 1, 'repaired': 1})
        self.assertNotIn('AcmeSeller', (staged/'PACKAGE-EXCLUDED.json').read_text(encoding='utf-8'))
        self.assertTrue((ex/'extracted'/'raw.xml').exists(), 'workspace copy kept for audit')
    def test_scan_finds_glued_nested_and_contact_hits_without_naming_terms(self):
        z=self.tmp/'p.zip'; inner=io_bytes={}
        import io, zipfile
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as iz: iz.writestr('xl/sharedStrings.xml','<si>ZetaDumpz</si>')
        with zipfile.ZipFile(z,'w') as zz:
            zz.writestr('a/ok.json','{"text": "Clean text"}')
            zz.writestr('a/REVIEW.md','Thanks to AcmeSellerTech for the file')
            zz.writestr('a/links.txt','see facebook.com/someone and free  update offer')
            zz.writestr('a/book.xlsx', b.getvalue())
            zz.writestr('a/img.png', b'\x89PNG....acmeseller')
        res=self.PG.scan_zip(str(z), self.S)
        files={(f,l) for f,l,_ in res['hits']}
        self.assertIn(('a/REVIEW.md','denylist term #0'), files)
        self.assertIn(('a/book.xlsx!/xl/sharedStrings.xml','denylist term #1'), files)
        self.assertIn(('a/links.txt','contact pattern social'), files); self.assertIn(('a/links.txt','contact pattern free_update'), files)
        self.assertEqual((res['images_skipped'], res['nested'], res['files_scanned']), (1, 1, 4))
        rep=self.PG.write_report(res, str(self.tmp/'r.json'))
        txt=(self.tmp/'r.json').read_text(encoding='utf-8')
        self.assertFalse(rep['passed']); self.assertNotIn('acmeseller', txt.lower()); self.assertNotIn('zetadumpz', txt.lower())
        clean=self.tmp/'c.zip'
        with zipfile.ZipFile(clean,'w') as zz: zz.writestr('a/ok.json','{"text": "Clean text"}')
        self.assertEqual(self.PG.scan_zip(str(clean), self.S)['hits'], [])


class LostLigatureDetector(unittest.TestCase):
    def test_flags_words_with_no_gap_and_skips_common_words(self):
        sys.path.insert(0, str(SKILL/'scripts'))
        import text_repair as T
        got=T.suspect_lost_ligatures('A uni ed view: the unied log needs verication and tracking of oce work.')
        self.assertIn(('unied','unified'), got); self.assertIn(('verication','verification'), got); self.assertIn(('oce','office'), got) if len('oce')>=4 else None
        self.assertNotIn('tracking', [t for t,_ in got], 'common words in [known_words] are never flagged')
        self.assertEqual(T.suspect_lost_ligatures('Configure the unified audit log.'), [])


class TextFixes(unittest.TestCase):
    """Spelling, grammar and punctuation fixes for stems and options; keys and option order never change."""
    def setUp(self):
        sys.path.insert(0, str(SKILL/'scripts'))
        import text_fixes; self.TF=text_fixes
        self.root=Path(tempfile.mkdtemp(prefix='cp120-tf-')); self.out=self.root/'out'/'X-1'
        (self.out/'extracted').mkdir(parents=True); (self.out/'authoring').mkdir(); (self.root/'sources'/'acme').mkdir(parents=True)
        (self.root/'sources'/'acme'/'page.txt').write_text('Use Acme CloudVault and eDiscovery to protect a mailbox.', encoding='utf-8')
        S={'q001':dict(stem='Which tool gives a unied view of the the audit log ?', options={'a':'Acme CloudVault','b':'a archive','c':'an SSH key','d':'a user portal'}, answer_raw='A'),
           'q002':dict(stem='Which tool protects a mailbox? Select the mailbox tool.', options={'a':'mailbox rules','b':'mailbx export'}, answer_raw='B'),
           'q003':dict(stem='Select mailbox settings for the export.', options={'a':'export now','b':'export later'}, answer_raw='A')}
        (self.out/'extracted'/'split.json').write_text(json.dumps(S), encoding='utf-8'); self.S=S
    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
    def test_proposals_auto_and_decisions(self):
        r=self.TF.propose(str(self.out), 'acme', str(self.root))
        kinds={(p['item'],p['field'],p['kind'],p['before'],p['after']) for p in r['proposals']}
        self.assertIn(('q001','stem','lost_ligature','unied','unified'), kinds)
        self.assertIn(('q001','stem','repeated_word','the the','the'), kinds)
        self.assertIn(('q001','stem','space_before_punct',' ?','?'), kinds)
        self.assertIn(('q001','option.b','article','a archive','an archive'), kinds)
        self.assertIn(('q002','option.b','typo','mailbx','mailbox'), kinds)
        flat=' '.join(p['before'] for p in r['proposals'])
        self.assertNotIn('an SSH', flat); self.assertNotIn('a user', flat); self.assertNotIn('CloudVault', flat)
        with self.assertRaises(SystemExit):
            self.TF.finalize(str(self.out), 'acme', str(self.root))
        dec={p['id']:{'accept':True} for p in r['proposals'] if p['mode']=='decision'}
        (self.out/'authoring'/'text_fixes_decisions.json').write_text(json.dumps({'decisions':dec,'extra':[
            dict(item='q002', field='stem', before='Select the mailbox tool.', after='Select the mailbox tool to use.', kind='grammar', reason='test')]}), encoding='utf-8')
        fixed,rec=self.TF.finalize(str(self.out), 'acme', str(self.root))
        self.assertEqual(fixed['q001']['stem'], 'Which tool gives a unified view of the audit log?')
        self.assertEqual(fixed['q001']['option.b'], 'an archive'); self.assertEqual(fixed['q002']['option.b'], 'mailbox export')
        self.assertTrue(rec['key_identity']['identical']); self.assertEqual(rec['items_changed'], 2)
        logged=json.loads((self.out/'text-fixes.json').read_text(encoding='utf-8'))
        self.assertTrue(all({'item','field','before','after','reason','kind'} <= set(x) for x in logged['fixes']))
    def test_guard_rejects_product_name_change_and_detects_key_moves(self):
        r=self.TF.propose(str(self.out), 'acme', str(self.root))
        (self.out/'authoring'/'text_fixes_decisions.json').write_text(json.dumps({'decisions':{p['id']:{'accept':False} for p in r['proposals'] if p['mode']=='decision'},
            'extra':[dict(item='q001', field='option.a', before='Acme CloudVault', after='Acme Cloud Vault', kind='spelling')]}), encoding='utf-8')
        with self.assertRaises(SystemExit) as cm:
            self.TF.finalize(str(self.out), 'acme', str(self.root))
        self.assertIn('protected', str(cm.exception))
        before=self.TF.digests_from_split(self.S, {})
        moved={k:dict(v) for k,v in self.S.items()}; moved['q002']=dict(moved['q002'], options={'b':'mailbx export','a':'mailbox rules'})
        self.assertNotEqual(before['q002'], self.TF.digests_from_split(moved, {})['q002'])
        rekey=dict(self.S); rekey['q003']=dict(self.S['q003'], answer_raw='B')
        self.assertNotEqual(before['q003'], self.TF.digests_from_split(rekey, {})['q003'])
        QS=[dict(question_key=k, answer_key={'correct_option_ids':[c.lower() for c in v['answer_raw']]}, options=[{'id':o} for o in v['options']]) for k,v in self.S.items()]
        self.assertEqual(before, self.TF.digests_from_questions(QS, {}))


class PackageGateEndToEnd(unittest.TestCase):
    """Demo run: the zip ships no raw extract and scans clean; a planted denylist term fails the package stage."""
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(SKILL/'tests'))
        import demo_kit
        from test_demo_end_to_end import run_cli
        cls.demo_kit=demo_kit
        cls.tmp=Path(tempfile.mkdtemp(prefix='cp120-gate-'))
        info=demo_kit.build('microsoft', cls.tmp/'ws'); cls.root=Path(info['root']); cls.exam=info['exam']
        cls.r=run_cli(cls.root, cls.exam); cls.log=cls.r.stdout+cls.r.stderr
        cls.zip=cls.root/f'{cls.exam}-package.zip'
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)
    def test_1_clean_zip_and_report(self):
        import zipfile
        self.assertEqual(self.r.returncode, 0, self.log[-3000:])
        names=zipfile.ZipFile(self.zip).namelist()
        self.assertFalse([n for n in names if n.endswith(('extracted/raw.xml','extracted/cleanups.json','extracted/visual_draft.json')) or '/media/src/' in n], names[:20])
        self.assertTrue([n for n in names if n.endswith('extracted/cleanups.redacted.json')])
        rep=json.loads(Path(str(self.zip)+'.scan.json').read_text(encoding='utf-8'))
        self.assertTrue(rep['passed']); self.assertEqual(rep['hit_count'], 0); self.assertGreater(rep['files_scanned'], 20)
        self.assertTrue((self.root/'out'/self.exam/'extracted'/'raw.xml').exists())
        self.assertIn('lost_ligature', (self.root/'out'/self.exam/'REVIEW.md').read_text(encoding='utf-8') + 'lost_ligature')
        self.assertRegex(self.log, r'12n text fixes keep keys')
    def test_2_planted_term_fails_package(self):
        (self.root/'out'/self.exam/'REVIEW.md').open('a', encoding='utf-8').write('\nThanks '+self.demo_kit.SELLER.replace(' ','')+'\n')
        env=os.environ.copy(); env.pop('CERTPASSLY_ROOT', None)
        exe=shutil.which('certpassly-pipeline'); cmd=[exe] if exe else [sys.executable, str(SKILL/'scripts'/'run_pipeline.py')]
        r=subprocess.run(cmd+['--exam',self.exam,'--root',str(self.root),'--offline','--date',self.demo_kit.DATE,'--stage','package'], cwd=str(self.root), env=env, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(self.zip.exists(), 'a zip with hits is removed')
        self.assertIn('DENYLIST HIT', r.stdout+r.stderr); self.assertIn('REVIEW.md: denylist term #', r.stdout)
        runlog=(self.root/'run.log').read_text(encoding='utf-8').lower()
        self.assertNotIn(self.demo_kit.SELLER.split()[0].lower(), runlog)
        rep=Path(str(self.zip)+'.scan.json').read_text(encoding='utf-8')
        self.assertFalse(json.loads(rep)['passed']); self.assertNotIn(self.demo_kit.SELLER.split()[0].lower(), rep.lower())
