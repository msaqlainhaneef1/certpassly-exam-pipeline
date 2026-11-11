#!/usr/bin/env python3
"""Fixes found by the first real v1.2.0 run (synthetic inputs only, offline)."""
from __future__ import annotations
import csv, hashlib, json, os, shutil, subprocess, sys, tempfile, unittest
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


if __name__=='__main__':
    unittest.main(verbosity=2)
