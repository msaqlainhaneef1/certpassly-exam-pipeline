#!/usr/bin/env python3
"""Download an exam's owner files from its public (link-shared) Google Drive folder. No credentials, no AI.

    drive_fetch.py CODE [--dest DIR] [--max-mb N]

Reads the Drive folder link(s) for CODE from catalog.csv (drive_folder_url, several
links separated by " | "), lists each folder with the public embeddedfolderview page
(cached under cache/drive/, same logic as drive_inventory.py), walks subfolders, and
downloads every file into owner-files/<CODE>/ with sha256 in .fetch.json.
Resume: a file already listed in .fetch.json with a matching sha256 is skipped;
partial downloads go to *.part and are redone. Offline mode never runs this.
Env CERTPASSLY_DRIVE_BASE / CERTPASSLY_DRIVE_DL override the Google hosts (tests only).
"""
from __future__ import annotations
import argparse, csv, hashlib, html, json, os, re, sys, time, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths

UA='Mozilla/5.0 (X11; Linux x86_64) certpassly-pipeline'

def base(): return os.environ.get('CERTPASSLY_DRIVE_BASE') or 'https://drive.google.com'
def dl(): return os.environ.get('CERTPASSLY_DRIVE_DL') or 'https://drive.usercontent.google.com'

class DriveError(SystemExit):
    pass

def get(url, timeout=60):
    req=urllib.request.Request(url, headers={'User-Agent':UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.headers.get('Content-Type',''), r.read()
    except urllib.error.HTTPError as e:
        return e.code, '', b''
    except urllib.error.URLError as e:
        raise DriveError(f'drive: network error for {url}: {e.reason}')

def folder_ids(text):
    return re.findall(r'/(?:drive/(?:u/\d+/)?folders|folderview\?id=|embeddedfolderview\?id=)/?([\w-]{10,})', text or '')

def list_folder(fid, cache_dir):
    os.makedirs(cache_dir, exist_ok=True)
    p=os.path.join(cache_dir, f'{fid}.html')
    if os.path.exists(p) and os.path.getsize(p):
        body=open(p,encoding='utf-8',errors='ignore').read()
    else:
        code,_,b=get(f'{base()}/embeddedfolderview?id={fid}')
        body=b.decode('utf-8','ignore')
        if code!=200 or 'flip-entr' not in body:
            raise DriveError(f'drive: folder {fid} is not readable (HTTP {code}). It must be shared as "Anyone with the link".')
        open(p,'w',encoding='utf-8').write(body)
    out=[]
    for chunk in body.split('<div class="flip-entry" id="entry-')[1:]:
        eid=chunk.split('"',1)[0]
        href=(re.search(r'<a href="([^"]+)"',chunk) or [None,''])[1]
        name=html.unescape((re.search(r'<div class="flip-entry-title">([^<]*)',chunk) or [None,''])[1])
        out.append(dict(id=eid, name=name, folder='/drive/folders/' in href or '/folderview' in href))
    return out

def safe_name(name):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',name).strip(' .') or 'file'

def fetch(code, dest=None, max_mb=200, root=None):
    root=root or paths.root()
    rows=[r for r in csv.DictReader(open(os.path.join(root,'catalog.csv'),encoding='utf-8-sig')) if r.get('exam_code')==code]
    if not rows: raise DriveError(f'drive: {code} not in catalog.csv')
    ids=folder_ids(rows[0].get('drive_folder_url',''))
    if not ids: raise DriveError(f'drive: no Drive folder link for {code} in catalog.csv (drive_folder_url).')
    dest=dest or os.path.join(root,'owner-files',code); os.makedirs(dest, exist_ok=True)
    manp=os.path.join(dest,'.fetch.json')
    man=json.load(open(manp,encoding='utf-8')) if os.path.exists(manp) else {'files':{}}
    cache=os.path.join(root,'cache','drive')
    queue=list(ids); seen=set(); got=[]; skipped=[]
    while queue:
        fid=queue.pop(0)
        if fid in seen: continue
        seen.add(fid)
        for e in list_folder(fid, cache):
            if e['folder']: queue.append(e['id']); continue
            name=safe_name(e['name']); path=os.path.join(dest,name)
            prev=man['files'].get(e['id'])
            if prev and os.path.exists(path) and hashlib.sha256(open(path,'rb').read()).hexdigest()==prev['sha256']:
                skipped.append(name); continue
            code_,ctype,data=get(f'{dl()}/download?id={e["id"]}&export=download&confirm=t', timeout=300)
            if code_!=200:
                raise DriveError(f'drive: download of {e["name"]} ({e["id"]}) failed with HTTP {code_}.')
            if 'text/html' in ctype or data[:200].lower().lstrip().startswith((b'<!doctype html', b'<html')):
                raise DriveError(f'drive: {e["name"]} returned an HTML page instead of the file (not shared publicly, quota, or virus-scan page).')
            if len(data)>max_mb*1024*1024:
                raise DriveError(f'drive: {e["name"]} is larger than {max_mb} MB; raise --max-mb if this is expected.')
            open(path+'.part','wb').write(data); os.replace(path+'.part', path)
            man['files'][e['id']]=dict(name=name, sha256=hashlib.sha256(data).hexdigest(), size=len(data), folder=fid,
                                      fetched_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'))
            got.append(name)
            json.dump(man, open(manp,'w',encoding='utf-8'), indent=1)
    json.dump(man, open(manp,'w',encoding='utf-8'), indent=1)
    print(f'drive_fetch {code}: downloaded {len(got)}, already present {len(skipped)} -> {dest}')
    return dict(downloaded=got, skipped=skipped, dest=dest)

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('code'); ap.add_argument('--dest'); ap.add_argument('--max-mb', type=int, default=200)
    a=ap.parse_args(); fetch(a.code, a.dest, a.max_mb)
