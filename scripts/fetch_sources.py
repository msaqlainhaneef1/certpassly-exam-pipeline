#!/usr/bin/env python3
"""Fetch or reuse official sources listed in research JSON. Saves copy + sha256 under sources/<vendor>/.
Reuses a saved copy when present. Never requires the app repo. Usage: fetch_sources.py research/<vendor>/<CODE>.json
"""
import re, json, hashlib, os, shutil, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
import paths
B=paths.root()
def sha(p): return hashlib.sha256(open(p,'rb').read()).hexdigest()
def ensure(src, vendor, key):
    d=f'{B}/sources/{vendor}'; os.makedirs(d,exist_ok=True)
    slug=re.sub(r'[^a-z0-9]+','-',src['url'].split('://',1)[1].lower()).strip('-')[:90]
    p=f'{d}/{slug}.html'; m=p+'.json'
    if os.path.exists(m): return json.load(open(m))
    tmp=p+'.new'
    r=subprocess.run(['curl','-sL','--max-time','30','-o',tmp,'-w','%{http_code}',src['url']],capture_output=True,text=True)
    time.sleep(1)
    fresh=sha(tmp) if os.path.exists(tmp) else ''
    info=dict(url=src['url'],http=r.stdout,retrieved_at=time.strftime('%Y-%m-%d'),path=p)
    if src.get('reuse_from') and os.path.exists(src['reuse_from']) and sha(src['reuse_from'])==src.get('expected_sha256')==fresh:
        shutil.copy(src['reuse_from'],p); info['method']='reused earlier copy, fresh fetch hash identical'
    elif r.stdout=='200': shutil.move(tmp,p); info['method']='fresh fetch'
    else: raise SystemExit(f'fetch failed {src["url"]} {r.stdout}')
    if os.path.exists(tmp): os.remove(tmp)
    info['sha256']=sha(p); json.dump(info,open(m,'w'),indent=1); return info
if __name__=='__main__':
    for f in sys.argv[1:]:
        R=json.load(open(f)); key=R.get('exam_slug') or R.get('certification_slug') or 'vendor'
        for s in R['sources']: print(ensure(s,R['vendor_slug'],key))
