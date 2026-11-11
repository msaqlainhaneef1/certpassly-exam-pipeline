#!/usr/bin/env python3
"""answer_research stage: find a key for owner-file items that have no answer, from OFFICIAL vendor pages only.

    answer_research.py OUT_DIR VENDOR [--offline]

Owner rule (v1.1.0): an item with no answer in the owner file is never dropped or held.
Scripted part (no AI):
  1. targets   = items with no answer letter and no answer image (split.json), plus image
                 items the visual pass marked held (no key visible).
  2. candidate URLs = the exam's official sources (research sources + bank sources), URLs
                 listed for the item in authoring/answer_research_urls.json, and (online)
                 a site-restricted web search over the vendor's official_domains.
                 Any URL whose host is not on official_domains is rejected and logged.
  3. fetch / render each candidate into sources/<vendor>/ with a sha256 sidecar.
  4. quote matching: rank the saved page's text lines by overlap with the stem and options.
  -> answer_research/candidates.json (input to ONE batched AI pick per exam).
AI part (author stage, one call per exam): authoring/answer_research.json
  {qkey: {"key": [...letters] | {"region_ids": [...]} ..., "source_url": ..., "quote": "verbatim line",
          "confidence": "high|medium|low", "content": {...optional regions for image items}}}
  or {qkey: {"answer_not_found": true, "note": "..."}}.
Verification (scripted): the source must be official and saved, the quote must appear verbatim
in the saved page text, the key must fit the item. Result -> answer_research/result.json with
status researched_official | answer_not_found (searched URLs logged) | pending_ai_pick.
"""
from __future__ import annotations
import html, json, os, re, sys, urllib.parse, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths, vendor_reg, fetch_sources

CONF={'high','medium','low'}
STOP=set('a an the of to in on for and or is are be you your what which should use need with from that this by as at it its can do does how when will select appropriate options answer area each correct'.split())

def _j(p, d):
    try: return json.load(open(p, encoding='utf-8'))
    except Exception: return d

def norm(x):
    x=html.unescape(x or '').replace('\u2019',"'").replace('\u2018',"'").replace('\u201c','"').replace('\u201d','"').replace('\u2013','-').replace('\u2014','-').replace('\xa0',' ')
    return re.sub(r'\s+',' ',x).strip().lower()

def page_lines(meta):
    from adapters.generic import _lines
    return _lines(open(meta['path'], encoding='utf-8', errors='ignore').read())

def page_text(meta):
    body=open(meta['path'], encoding='utf-8', errors='ignore').read()
    body=re.sub(r'(?is)<(script|style|noscript|template)\b.*?</\1>',' ',body)
    return norm(re.sub(r'<[^>]+>',' ',body))

def words(t):
    return [w for w in re.findall(r"[a-z0-9][a-z0-9+#.\-]*", norm(t)) if w not in STOP and len(w)>2]

def targets(out):
    S=_j(os.path.join(out,'extracted','split.json'),{})
    VT=_j(os.path.join(out,'extracted','visual_transcription.json'),{})
    T={}
    for k,it in S.items():
        vt=VT.get(k)
        if vt and vt.get('held'):
            T[k]=dict(kind='image', type=vt.get('type','active_screen'), stem=it['stem'], options=it.get('options') or {},
                      regions=vt.get('candidate_regions') or [], images=it.get('question_images') or [])
        elif not vt and not re.sub(r'[^A-H]','',(it.get('answer_raw') or '').upper()) and not it.get('answer_images'):
            T[k]=dict(kind='text', type=None, stem=it['stem'], options=it.get('options') or {}, regions=[], images=it.get('question_images') or [])
    return T

def search_urls(query, vendor, n=3):
    """Site-restricted web search (DuckDuckGo HTML endpoint). Optional; failures are logged, never fatal."""
    if os.environ.get('CERTPASSLY_NO_SEARCH')=='1': return [], 'search disabled (CERTPASSLY_NO_SEARCH=1)'
    doms=vendor_reg.official_domains(vendor)
    if not doms: return [], 'vendor has no official_domains'
    q=query+' '+' OR '.join('site:'+d for d in doms[:3])
    url='https://html.duckduckgo.com/html/?q='+urllib.parse.quote(q)
    try:
        req=urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0 certpassly-pipeline'})
        body=urllib.request.urlopen(req, timeout=20).read().decode('utf-8','ignore')
    except Exception as e:
        return [], f'search failed: {e}'
    out=[]
    for m in re.finditer(r'href="[^"]*?uddg=([^&"]+)', body):
        u=urllib.parse.unquote(m.group(1))
        if vendor_reg.url_is_official(u, vendor) and u not in out: out.append(u)
        if len(out)>=n: break
    return out, f'search "{q}": {len(out)} official results'

def base_urls(root, vendor, code):
    out=[]
    for name in (f'{code}.json', f'{code}-bank-sources.json'):
        for s in _j(os.path.join(root,'research',vendor,name),{}).get('sources') or []:
            if s.get('url') and s['url'] not in out: out.append(s['url'])
    return out

def rank(meta, item, n=5):
    want=set(words(item['stem']+' '+' '.join(item['options'].values())+' '+' '.join(item['regions'])))
    if not want: return []
    scored=[]
    for line in page_lines(meta):
        if len(line)<20 or len(line)>600: continue
        w=set(words(line)); hit=len(w & want)
        if hit>=2: scored.append((hit/ (1+len(want))**0.5, line))
    scored.sort(key=lambda x:-x[0])
    return [l for _,l in scored[:n]]

def discover(out, vendor, code, offline=False, root=None):
    root=root or paths.root(); T=targets(out)
    extra=_j(os.path.join(out,'authoring','answer_research_urls.json'),{})
    if not extra: extra=_j(os.path.join(root,'authoring',code,'answer_research_urls.json'),{})
    C={}
    for k,it in T.items():
        searched=[]; rejected=[]; notes=[]; cands=[]
        urls=list(extra.get(k) or [])+base_urls(root, vendor, code)
        if not offline:
            found,note=search_urls(' '.join(words(it['stem']))[:180], vendor); notes.append(note); urls+=found
        seen=set()
        for u in urls:
            if u in seen: continue
            seen.add(u)
            if not vendor_reg.url_is_official(u, vendor):
                rejected.append(dict(url=u, reason='host not on the vendor official_domains list')); continue
            try:
                m=fetch_sources.ensure(u, vendor, offline=offline)
            except SystemExit as e:
                searched.append(dict(url=u, result=f'not saved: {e}')); continue
            except Exception as e:
                searched.append(dict(url=u, result=f'fetch failed: {e}')); continue
            lines=rank(m, it)
            searched.append(dict(url=u, saved_path=os.path.relpath(m['path'], root).replace(os.sep, '/'), sha256=m['sha256'], result=f'{len(lines)} matching lines'))
            if lines: cands.append(dict(url=u, saved_path=os.path.relpath(m['path'], root).replace(os.sep, '/'), sha256=m['sha256'], lines=lines))
        boxes=[]
        if it['kind']=='image' and it['images']:
            # scripted region proposals (bordered boxes in the answer-area image) so the pick only maps labels to boxes
            try:
                import vision_util
                img=os.path.join(out,'media','src',it['images'][-1])
                boxes=[[round(v,4) for v in r] for r in vision_util.boxes(img)]
            except Exception as e:
                notes.append(f'region proposal failed: {type(e).__name__}')
        C[k]=dict(item=it, candidates=cands, searched=searched, rejected=rejected, notes=notes, proposed_boxes=boxes)
    os.makedirs(os.path.join(out,'answer_research'), exist_ok=True)
    json.dump(C, open(os.path.join(out,'answer_research','candidates.json'),'w',encoding='utf-8'), indent=1, ensure_ascii=False)
    return C

def _key_ok(it, key, content):
    if it['kind']=='text' or it['options']:
        letters=[str(x).lower() for x in (key if isinstance(key,list) else (key or {}).get('correct_option_ids') or [])]
        return bool(letters) and all(l in it['options'] for l in letters), {'correct_option_ids':letters}
    rid=(key or {}).get('region_ids') if isinstance(key,dict) else None
    ids=[r.get('id') for r in ((content or {}).get('regions') or []) if isinstance(r,dict)]
    return bool(rid) and all(r in ids for r in rid), {'region_ids':list(rid or [])}

def verify(out, vendor, code, root=None):
    """Merge candidates.json with the AI pick file; every claim is re-checked against the saved official page."""
    root=root or paths.root()
    C=_j(os.path.join(out,'answer_research','candidates.json'),None)
    if C is None: C=discover(out, vendor, code, offline=True, root=root)
    P=_j(os.path.join(out,'authoring','answer_research.json'),{}) or _j(os.path.join(root,'authoring',code,'answer_research.json'),{})
    R={}
    for k,c in C.items():
        it=c['item']; p=P.get(k) or {}
        base=dict(question_key=k, kind=it['kind'], type=it['type'], reviewer_needed=True,
                  searched_urls=[s['url'] for s in c['searched']], rejected_urls=c['rejected'], search_notes=c.get('notes',[]))
        if p and not p.get('answer_not_found'):
            u=p.get('source_url',''); problems=[]
            if not vendor_reg.url_is_official(u, vendor): problems.append('source not on official_domains')
            m=fetch_sources.find_saved(vendor, u, root) if u else None
            if not m: problems.append('source page not saved under sources/')
            elif norm(p.get('quote')) not in page_text(m): problems.append('quote not found verbatim on the saved page')
            ok,key=_key_ok(it, p.get('key'), p.get('content'))
            if not ok: problems.append('key does not fit the item')
            if p.get('confidence') not in CONF: problems.append('confidence must be high, medium or low')
            if not problems:
                R[k]=dict(base, status='researched_official', key=key, key_source='researched_official', source_url=u,
                          saved_path=os.path.relpath(m['path'], root).replace(os.sep, '/'), sha256=m['sha256'], quote=p['quote'], confidence=p['confidence'],
                          content=p.get('content'), explanation=p.get('explanation'), note=p.get('note',''))
                continue
            raise SystemExit(f'answer_research {k}: pick rejected: {"; ".join(problems)}. Fix authoring/answer_research.json (official saved page + verbatim quote).')
        if p.get('answer_not_found') or not c['candidates']:
            R[k]=dict(base, status='answer_not_found', key=None, key_source=None, note=p.get('note') or 'no official page among the searched URLs states the answer')
        else:
            R[k]=dict(base, status='pending_ai_pick', key=None, candidates=len(c['candidates']))
    json.dump(R, open(os.path.join(out,'answer_research','result.json'),'w',encoding='utf-8'), indent=1, ensure_ascii=False)
    return R

if __name__=='__main__':
    out, vendor=sys.argv[1], sys.argv[2]; code=os.path.basename(os.path.normpath(out))
    off='--offline' in sys.argv or os.environ.get('CERTPASSLY_OFFLINE')=='1'
    C=discover(out, vendor, code, offline=off)
    R=verify(out, vendor, code)
    from collections import Counter
    print('answer_research', code, len(C), 'no-answer items', dict(Counter(r['status'] for r in R.values())))
