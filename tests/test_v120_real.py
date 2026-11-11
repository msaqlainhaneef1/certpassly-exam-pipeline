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


if __name__=='__main__':
    unittest.main(verbosity=2)
