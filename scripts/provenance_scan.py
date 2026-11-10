#!/usr/bin/env python3
"""Download ONE file per sampled folder (size-capped), sha256 it, extract text, scan for provenance signals.
Usage: provenance_scan.py FILE_ID [FILE_ID...]  (ids from drive_inventory.csv). Writes provenance/<id>.json."""
import csv, hashlib, json, os, re, subprocess, sys, zipfile, io
sys.path.insert(0, os.path.dirname(__file__))
import paths
B=paths.root(); OUT=f'{B}/provenance'; os.makedirs(OUT,exist_ok=True)
CAP=40*1024*1024
SIGNALS={
 'third_party_brand':r'\b(examtopics|pass4sure|passleader|braindump\w*|exam[- ]?collection|vceplayer|vce ?exam ?simulator|avanset|certkiller|testking|actualtests|pass4future|certsfire|dumps?(?:base|pedia|\.com)?|killexams|lead2pass|prepaway|itexams|marks4sure|real-?exams|certleader|test-?inside|exam-?labs|dumpsgate|validexamdumps|pass4itsure|realexamdumps|certification-?questions|braindumps|testkings|ensurepass|vcedump\w*|passapply|exam4sure|vmexam|dumpsmate)\b',
 'free_updates':r'free (?:updates?|update)',
 'known_seller_name':r'innovior ?it ?tech',
 'cover_exam_facts':r'(?:Passing Score|Time Limit|File Version|Number):\s*[^\n]{1,20}',
 'shop_or_social_link':r'https?://[^\s"<>]+',
 'copyright_line':r'(?:copyright|\(c\)|©)[^\n]{0,80}',
 'source_wording':r'\b(extracted|source-keyed|source file|redesigned from|original wording kept|real exam|actual exam questions|latest dumps)\b',
 'question_markers':r'\b(?:QUESTION\s+\d+|NO\.\s?\d+|Question\s*#\s*\d+)',
}
def inv():
    return {r['file_id']:r for r in csv.DictReader(open(f'{B}/drive_inventory.csv'))}
def download(fid,dest):
    url=f'https://drive.usercontent.google.com/download?id={fid}&export=download&confirm=t'
    r=subprocess.run(['curl','-sL','--max-time','180','--max-filesize',str(CAP),'-o',dest,'-w','%{http_code} %{content_type}',url],capture_output=True,text=True)
    return r.stdout
def text_of(path,ext):
    if ext=='pdf':
        t=subprocess.run(['pdftotext','-l','6',path,'-'],capture_output=True,text=True).stdout
        t+='\n'+subprocess.run(['pdftotext','-f','9999',path,'-'],capture_output=True,text=True).stdout
        t+='\n[pdfinfo]\n'+subprocess.run(['pdfinfo',path],capture_output=True,text=True).stdout
        return t
    data=open(path,'rb').read()
    if ext in ('docx','xlsx','pptx'):
        try:
            z=zipfile.ZipFile(io.BytesIO(data)); return ' '.join(re.sub(r'<[^>]+>',' ',z.read(n).decode('utf8','ignore')) for n in z.namelist() if n.endswith('.xml'))[:400000]
        except Exception as e: return f'[zip error {e}]'
    # vce and other binary: printable strings only (no decryption attempted)
    return ' '.join(x.decode() for x in re.findall(rb'[\x20-\x7e]{6,}',data[:3_000_000]))
def scan(fid,meta):
    ext=meta['extension']; dest=f'{OUT}/{fid}.{ext or "bin"}'
    st=download(fid,dest) if not os.path.exists(dest) else 'cached'
    if not os.path.exists(dest): return dict(file_id=fid,name=meta['name'],status=f'download_failed {st}')
    data=open(dest,'rb').read(); sha=hashlib.sha256(data).hexdigest()
    head=data[:200]
    if b'<html' in head.lower(): return dict(file_id=fid,name=meta['name'],status='got_html_interstitial (file too large or blocked)',sha256=sha)
    t=text_of(dest,ext); res=dict(file_id=fid,name=meta['name'],path=meta['path'],ext=ext,bytes=len(data),sha256=sha,status='scanned',text_chars=len(t),signals={})
    for k,rx in SIGNALS.items():
        hits=re.findall(rx,t,re.I)
        hits=[h if isinstance(h,str) else h[0] for h in hits]
        if k=='shop_or_social_link':
            try:
                import vendor_reg as _vr; _host='|'.join(re.escape(x) for x in (_vr.harmless_url_hosts() or ['adobe','w3.org','openxmlformats','purl.org','schemas']))
            except Exception:
                _host=r'adobe|w3\.org|openxmlformats|purl\.org|schemas'
            hits=[h for h in hits if not re.search(_host,h)]
        res['signals'][k]={'count':len(hits),'examples':sorted(set(h.strip()[:100] for h in hits))[:8]}
    json.dump(res,open(f'{OUT}/{fid}.json','w'),indent=1); return res
if __name__=='__main__':
    I=inv()
    for fid in sys.argv[1:]: print(json.dumps(scan(fid,I[fid]),indent=1)[:2500])
