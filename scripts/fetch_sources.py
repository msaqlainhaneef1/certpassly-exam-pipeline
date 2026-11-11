#!/usr/bin/env python3
"""Fetch or reuse official vendor pages. Saves HTML + visible text + sha256 sidecar under sources/<vendor>/.

    fetch_sources.py research/<vendor>/<CODE>.json [more research files]

A saved copy is always reused (idempotent). When a plain fetch returns too little
readable text (JavaScript-built page) or the vendor sets `render: true` in
vendors.yaml, the page is rendered with headless Chromium (optional extra
`[render]`, see render_page.py). Offline mode never fetches. No AI, no app repo.
"""
from __future__ import annotations
import hashlib, json, os, re, sys, time, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths

UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36'
DEFAULT_MIN_TEXT=1500

def sha_bytes(b): return hashlib.sha256(b).hexdigest()
def sha(p): return sha_bytes(open(p,'rb').read())

def slug_for(url):
    return re.sub(r'[^a-z0-9]+','-',url.split('://',1)[-1].lower()).strip('-')[:90]

def find_saved(vendor, url, root=None):
    d=os.path.join(root or paths.root(),'sources',vendor)
    if not os.path.isdir(d): return None
    for n in sorted(os.listdir(d)):
        if n.endswith('.json'):
            try: m=json.load(open(os.path.join(d,n),encoding='utf-8'))
            except Exception: continue
            if m.get('url')==url:
                # sidecars store absolute paths; a copied or moved workspace resolves them next to the sidecar
                here=os.path.join(d, n[:-5]) if n.endswith('.html.json') else os.path.join(d, os.path.basename(m.get('path','')))
                if os.path.isfile(here): m['path']=os.path.abspath(here)
                if m.get('text_path'):
                    t=os.path.join(d, os.path.basename(m['text_path']))
                    if os.path.isfile(t): m['text_path']=os.path.abspath(t)
                return m
    return None

def plain_fetch(url, timeout=30):
    req=urllib.request.Request(url, headers={'User-Agent':UA,'Accept-Language':'en-US,en;q=0.9'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.geturl(), r.read().decode('utf-8','replace')
    except urllib.error.HTTPError as e:
        return e.code, url, ''

def _renderer():
    import render_page
    return render_page

def ensure(url, vendor, render=False, min_text=None, offline=None, renderer=None):
    """Return the sidecar dict for url, fetching (and rendering if needed) only when no saved copy exists."""
    saved=find_saved(vendor, url)
    if saved: return saved
    offline=os.environ.get('CERTPASSLY_OFFLINE')=='1' if offline is None else offline
    if offline:
        raise SystemExit(f'offline: no saved copy of {url} under sources/{vendor}/. Run once online or save a rendered copy with a sidecar.')
    rp=renderer or _renderer()
    min_text=min_text or int(os.environ.get('CERTPASSLY_RENDER_MIN_TEXT') or DEFAULT_MIN_TEXT)
    code, final, body=plain_fetch(url)
    text=rp.visible_text(body)
    method='plain fetch'
    if render or code!=200 or len(text)<min_text:
        why='vendor sets render: true' if render else (f'HTTP {code}' if code!=200 else f'only {len(text)} text characters in a plain fetch')
        try:
            body=rp.render(url); code=200; final=url
        except rp.RenderUnavailable as e:
            raise SystemExit(f'{url}: {why}, and rendering is not available: {e}')
        text=rp.visible_text(body); method=f'rendered with headless Chromium ({why})'
        if len(text)<min_text//3:
            raise SystemExit(f'{url}: rendered page still has only {len(text)} text characters. Check the URL in a browser.')
    if code!=200:
        raise SystemExit(f'fetch failed {url}: HTTP {code}')
    d=os.path.join(paths.root(),'sources',vendor); os.makedirs(d, exist_ok=True)
    base=os.path.join(d, slug_for(url))
    data=body.encode('utf-8')
    open(base+'.html','wb').write(data)
    open(base+'.txt','w',encoding='utf-8').write(text)
    info=dict(url=url, http=str(code), final_url=final, retrieved_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),
              path=os.path.abspath(base+'.html'), sha256=sha_bytes(data), method=method,
              text_path=os.path.abspath(base+'.txt'), text_sha256=sha(base+'.txt'), text_chars=len(text))
    json.dump(info, open(base+'.html.json','w',encoding='utf-8'), indent=1)
    time.sleep(0.5)
    return info

def save_asset(url, vendor, note='', offline=None):
    """Save a binary official asset (for example a documentation screenshot) with a sha256 sidecar."""
    d=os.path.join(paths.root(),'sources',vendor); os.makedirs(d, exist_ok=True)
    for n in os.listdir(d):
        if n.endswith('.asset.json'):
            m=json.load(open(os.path.join(d,n),encoding='utf-8'))
            if m.get('url')==url: return m
    if offline or os.environ.get('CERTPASSLY_OFFLINE')=='1':
        raise SystemExit(f'offline: asset {url} not saved')
    req=urllib.request.Request(url, headers={'User-Agent':UA})
    data=urllib.request.urlopen(req, timeout=30).read()
    ext=os.path.splitext(url.split('?')[0])[1] or '.bin'
    base=os.path.join(d, slug_for(url))
    open(base+ext,'wb').write(data)
    info=dict(url=url, retrieved_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'), path=os.path.abspath(base+ext), sha256=sha_bytes(data), note=note)
    json.dump(info, open(base+'.asset.json','w',encoding='utf-8'), indent=1)
    return info

if __name__=='__main__':
    import vendor_reg
    for f in sys.argv[1:]:
        R=json.load(open(f,encoding='utf-8'))
        v=R['vendor_slug']
        try: render=bool(vendor_reg.vendor(v).get('render'))
        except SystemExit: render=False
        for s in R.get('sources') or []:
            m=ensure(s['url'], v, render=render)
            print(json.dumps({k:m.get(k) for k in ('url','http','sha256','method','text_chars')}))
