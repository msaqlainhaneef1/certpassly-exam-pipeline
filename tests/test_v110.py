#!/usr/bin/env python3
"""v1.1.0 regressions: answer_research, Drive download, render fallback, research JSON generation, catalog hardcode gate. Offline."""
from __future__ import annotations
import glob, hashlib, http.server, importlib, json, os, re, shutil, sys, tempfile, threading, unittest
from pathlib import Path

SKILL=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL/'scripts')); sys.path.insert(0, str(SKILL/'tests'))
import demo_kit

def fresh(mod_names=('paths','vendor_reg','fetch_sources','answer_research','research_init','drive_fetch')):
    for n in mod_names:
        if n in sys.modules: importlib.reload(sys.modules[n])

class Base(unittest.TestCase):
    PROFILE='salesforce'
    def setUp(self):
        self.tmp=Path(tempfile.mkdtemp(prefix='cp110-')); self.info=demo_kit.build(self.PROFILE, self.tmp/'ws')
        self.root=Path(self.info['root']); self.E=self.info['exam']; self.V=self.info['vendor']; self.out=self.root/'out'/self.E
        self.env={k:os.environ.get(k) for k in ('CERTPASSLY_ROOT','CERTPASSLY_OFFLINE','CERTPASSLY_NO_SEARCH')}
        os.environ.update(CERTPASSLY_ROOT=str(self.root), CERTPASSLY_OFFLINE='1', CERTPASSLY_NO_SEARCH='1'); os.chdir(self.root)
        import vendor_reg; vendor_reg._V=None
        fresh()
        import answer_research; self.AR=answer_research
    def tearDown(self):
        os.chdir(SKILL)
        for k,v in self.env.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k]=v
        shutil.rmtree(self.tmp, ignore_errors=True)
    def pick(self, d):
        (self.out/'authoring'/'answer_research.json').write_text(json.dumps(d), encoding='utf-8')

class TestAnswerResearch(Base):
    def setUp(self):
        super().setUp()
        import subprocess
        r=subprocess.run([sys.executable, str(SKILL/'scripts'/'run_pipeline.py'), '--exam', self.E, '--root', str(self.root), '--offline',
                          '--date', demo_kit.DATE, '--stage', 'intake', '--stage', 'extract'], capture_output=True, text=True, cwd=self.root)
        self.assertEqual(r.returncode, 0, r.stdout[-2000:]+r.stderr[-2000:])
    def test_saved_official_page_gives_researched_key_and_quote(self):
        C=self.AR.discover(str(self.out), self.V, self.E, offline=True)
        self.assertEqual(sorted(C), ['q005','q006'])
        self.assertTrue(any('weekly or monthly' in l for c in C['q006']['candidates'] for l in c['lines']))
        self.assertEqual([r['url'] for r in C['q006']['rejected']], ['https://www.example.org/q6'])
        R=self.AR.verify(str(self.out), self.V, self.E)
        r=R['q006']
        self.assertEqual((r['status'], r['key'], r['key_source'], r['confidence'], r['reviewer_needed']),
                         ('researched_official', {'correct_option_ids':['a']}, 'researched_official', 'high', True))
        p=self.root/r['saved_path']
        self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(), r['sha256'])
        self.assertIn(r['quote'], p.read_text(encoding='utf-8'))

    def test_no_evidence_becomes_answer_not_found_with_searched_urls(self):
        self.AR.discover(str(self.out), self.V, self.E, offline=True)
        R=self.AR.verify(str(self.out), self.V, self.E)
        self.assertEqual(R['q005']['status'], 'answer_not_found'); self.assertIsNone(R['q005']['key'])
        self.assertTrue(R['q005']['searched_urls'])
        # an item with no candidates and no pick is answer_not_found too, never dropped
        (self.out/'authoring'/'answer_research.json').unlink()
        doc=next(Path(m['path']) for m in map(lambda f: json.load(open(f)), glob.glob(str(self.root/'sources'/self.V/'*.json'))) if 'demo-data-export' in m['url'])
        doc.write_text('<p>Nothing relevant here.</p>', encoding='utf-8')
        os.environ['CERTPASSLY_NO_SEARCH']='1'
        for f in glob.glob(str(self.root/'research'/self.V/'*.json')): os.remove(f)
        C=self.AR.discover(str(self.out), self.V, self.E, offline=True)
        R=self.AR.verify(str(self.out), self.V, self.E)
        self.assertEqual(R['q006']['status'], 'answer_not_found', C['q006'])

    def test_pick_rejected_when_not_official_or_quote_not_verbatim(self):
        self.AR.discover(str(self.out), self.V, self.E, offline=True)
        good=json.loads((self.out/'authoring'/'answer_research.json').read_text())
        bad=json.loads(json.dumps(good)); bad['q006']['source_url']='https://www.example.org/q6'
        self.pick(bad)
        with self.assertRaisesRegex(SystemExit, 'official_domains'): self.AR.verify(str(self.out), self.V, self.E)
        bad=json.loads(json.dumps(good)); bad['q006']['quote']='The Data export service is the best answer.'
        self.pick(bad)
        with self.assertRaisesRegex(SystemExit, 'verbatim'): self.AR.verify(str(self.out), self.V, self.E)
        bad=json.loads(json.dumps(good)); bad['q006']['key']=['z']
        self.pick(bad)
        with self.assertRaisesRegex(SystemExit, 'key does not fit'): self.AR.verify(str(self.out), self.V, self.E)

    def test_pending_pick_is_listed_by_author_stage(self):
        (self.out/'authoring'/'answer_research.json').unlink()
        self.AR.discover(str(self.out), self.V, self.E, offline=True)
        R=self.AR.verify(str(self.out), self.V, self.E)
        self.assertEqual(R['q006']['status'], 'pending_ai_pick')

class TestResearchInit(Base):
    def test_build_from_saved_pages_every_fact_quoted(self):
        import research_init
        rp=self.root/'research'/self.V/f'{self.E}.json'
        rp.unlink()
        research_init.discover(self.E)
        R=research_init.build(self.E)
        self.assertEqual(R['generated_by'], 'research_init')
        for k,f in R['facts'].items():
            if f.get('value') is None: self.assertEqual(f['reason'], 'not published by the vendor', k)
            else:
                self.assertTrue(f['url'] and f['sha256'] and f['quote'], k)
        self.assertEqual(R['facts']['duration_minutes']['value'], 105)
        self.assertEqual([d['weight_min_pct'] for d in R['objectives']['domains']], [40,50])
        gaps=json.loads((self.root/'research'/'gaps.json').read_text())
        self.assertIn(self.E, gaps)

class TestRenderFallback(Base):
    def test_short_plain_fetch_is_rendered_and_hashed(self):
        import fetch_sources
        class FakeRender:
            class RenderUnavailable(Exception): pass
            @staticmethod
            def visible_text(b): return re.sub(r'<[^>]+>',' ',b or '').strip()
            @staticmethod
            def render(url): return '<html><body>'+('Rendered official text. '*100)+'</body></html>'
        orig=fetch_sources.plain_fetch
        fetch_sources.plain_fetch=lambda url, timeout=30: (200, url, '<html><body><div id=app></div></body></html>')
        try:
            m=fetch_sources.ensure('https://trailheadacademy.salesforce.com/js-only', self.V, offline=False, renderer=FakeRender)
        finally:
            fetch_sources.plain_fetch=orig
        self.assertIn('rendered with headless Chromium', m['method'])
        self.assertEqual(hashlib.sha256(Path(m['path']).read_bytes()).hexdigest(), m['sha256'])
        self.assertTrue(Path(m['text_path']).read_text().startswith('Rendered official text.'))
        # second call reuses the saved copy (no fetch)
        self.assertEqual(fetch_sources.ensure('https://trailheadacademy.salesforce.com/js-only', self.V)['sha256'], m['sha256'])

class _Drive(http.server.BaseHTTPRequestHandler):
    FILES={'f1':(b'%PDF-1.4 demo', 'Demo (2 Questions).pdf'), 'f2':(b'VCEBIN', 'Demo.vce')}
    def log_message(self,*a): pass
    def do_GET(self):
        if self.path.startswith('/embeddedfolderview?id=FOLDER1234567'):
            body=''.join(f'<div class="flip-entry" id="entry-{k}"><a href="https://drive.google.com/file/d/{k}/view"><div class="flip-entry-title">{n}</div></a></div>' for k,(d,n) in self.FILES.items())
            self.send_response(200); self.send_header('Content-Type','text/html'); self.end_headers(); self.wfile.write(body.encode()); return
        m=re.search(r'id=(\w+)', self.path)
        if self.path.startswith('/download') and m and m.group(1) in self.FILES:
            self.send_response(200); self.send_header('Content-Type','application/octet-stream'); self.end_headers(); self.wfile.write(self.FILES[m.group(1)][0]); return
        self.send_response(404); self.end_headers()

class TestDriveFetch(Base):
    def test_download_hash_resume(self):
        srv=http.server.HTTPServer(('127.0.0.1',0), _Drive); threading.Thread(target=srv.serve_forever, daemon=True).start()
        base=f'http://127.0.0.1:{srv.server_port}'
        os.environ['CERTPASSLY_DRIVE_BASE']=base; os.environ['CERTPASSLY_DRIVE_DL']=base
        try:
            cat=(self.root/'catalog.csv').read_text(encoding='utf-8').splitlines()
            import csv, io
            rows=list(csv.DictReader(io.StringIO('\n'.join(cat))))
            for r in rows: r['drive_folder_url']='https://drive.google.com/drive/folders/FOLDER1234567?usp=sharing'
            with open(self.root/'catalog.csv','w',newline='',encoding='utf-8') as f:
                w=csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
            import drive_fetch; importlib.reload(drive_fetch)
            dest=self.tmp/'dl'
            r=drive_fetch.fetch(self.E, str(dest))
            self.assertEqual(sorted(r['downloaded']), ['Demo (2 Questions).pdf','Demo.vce'])
            man=json.loads((dest/'.fetch.json').read_text())
            self.assertEqual(man['files']['f1']['sha256'], hashlib.sha256(b'%PDF-1.4 demo').hexdigest())
            r2=drive_fetch.fetch(self.E, str(dest))
            self.assertEqual((r2['downloaded'], len(r2['skipped'])), ([], 2))
            _Drive.FILES['f3']=(b'<!doctype html><html>quota</html>', 'x.pdf')
            with self.assertRaisesRegex(SystemExit, 'HTML page instead of the file'):
                shutil.rmtree(self.root/'cache'/'drive'); drive_fetch.fetch(self.E, str(dest))
        finally:
            _Drive.FILES.pop('f3', None); srv.shutdown()
            os.environ.pop('CERTPASSLY_DRIVE_BASE'); os.environ.pop('CERTPASSLY_DRIVE_DL')

class TestCatalogHardcodeGate(unittest.TestCase):
    def test_no_exam_literals_in_scripts_outside_adapters(self):
        o=json.loads((SKILL/'config'/'catalog_overrides.json').read_text())
        lits=[x['label'] for x in o['skip_labels']+o['label_merges']]+[x['code'] for x in o['label_merges']]+[c for x in o['code_notes'] for c in x['codes']]
        code_rx=re.compile(r"""['"][A-Za-z]{2,6}(-[A-Za-z]{2,6})?-\d{2,4}[A-Za-z0-9.-]*['"]""")
        hits=[]
        for f in (SKILL/'scripts').rglob('*.py'):
            if 'adapters' in f.parts: continue
            t=f.read_text(encoding='utf-8')
            hits+=[f'{f.name}: {l}' for l in lits if re.search(r'(?<![\w-])'+re.escape(l)+r'(?![\w-])', t, re.I)]
            hits+=[f'{f.name}: {m.group(0)}' for m in code_rx.finditer(t)]
        self.assertEqual(hits, [])

if __name__=='__main__':
    unittest.main(verbosity=2)
