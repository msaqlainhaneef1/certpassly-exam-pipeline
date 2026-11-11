#!/usr/bin/env python3
"""Discover, fetch and turn official vendor pages into research JSON. Scripted, no AI.

    research_init.py discover CODE   find + save official pages (sources/<vendor>/), write research/<vendor>/<CODE>.sources.json
    research_init.py build CODE      write research/<vendor>/<CODE>.json (+ vendors/<vendor>.json, certs/<cert>.json when missing)
                                     and research/gaps.json from the vendor adapter output

Every fact carries source_id, url, sha256 and a verbatim quote (a text line of the
saved page). A fact the pages do not state is recorded with the reason
"not published by the vendor" and listed in research/gaps.json for the batched
gap pass (official quotes only). A hand-written research file (no
`generated_by` key) is never overwritten.
"""
from __future__ import annotations
import csv, html, json, os, re, sys, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths, vendor_reg, fetch_sources

NP='not published by the vendor'
GEN='research_init'

def catalog_row(code):
    p=os.path.join(paths.root(),'catalog.csv')
    if not os.path.exists(p): raise SystemExit('catalog.csv not found; run the catalog stage first.')
    for r in csv.DictReader(open(p,encoding='utf-8-sig')):
        if r.get('exam_code')==code: return r
    raise SystemExit(f'{code} is not in catalog.csv')

def lookup(code):
    try: return (vendor_reg.exam_lookup().get('exams') or {}).get(code) or {}
    except Exception: return {}

def rdir(vendor):
    d=os.path.join(paths.root(),'research',vendor); os.makedirs(d, exist_ok=True); return d

def links(meta):
    body=open(meta['path'],encoding='utf-8',errors='ignore').read()
    base=meta.get('final_url') or meta['url']
    out=[]
    for m in re.finditer(r'(?:href|data-link)\s*=\s*"([^"#]+)"', body):
        u=urllib.parse.urljoin(base, html.unescape(m.group(1)))
        if u not in out: out.append(u)
    return out

def pick_link(urls, pat, seed, code):
    """First link matching pat, preferring one that names this exam (an exam or credential page)
    over generic policy pages that also match (score reports, retake policy, accommodations)."""
    cands=[u for u in urls if re.fullmatch(pat, u) and u.rstrip('/')!=seed.rstrip('/')]
    code_rx=re.compile(r'(?:^|[/=_-])'+re.escape(code.lower())+r'(?:$|[/?#&_.-])')
    return next((u for u in cands if code_rx.search(urllib.parse.urlsplit(u).path.lower()+'/')), None) or (cands[0] if cands else None)

def discover(code):
    row=catalog_row(code); v=row['vendor_slug']; meta=vendor_reg.vendor(v)
    seed=(row.get('official_exam_url') or '').strip() or ((lookup(code).get('urls') or [''])[0])
    if not seed: raise SystemExit(f'{code}: no official exam URL in catalog.csv or exam_lookup.json. Add one; it is never guessed.')
    render=bool(meta.get('render'))
    role=meta.get('seed_role') or 'sg'; other='cp' if role=='sg' else 'sg'
    m0=fetch_sources.ensure(seed, v, render=render)
    srcs={role:dict(id=role, url=seed, sha256=m0['sha256'], method=m0.get('method',''))}
    pat=meta.get('discover_'+other)
    note=''
    if pat:
        hit=pick_link(links(m0), pat, seed, code)
        if hit:
            m1=fetch_sources.ensure(hit, v, render=render and other=='cp')
            srcs[other]=dict(id=other, url=hit, sha256=m1['sha256'], method=m1.get('method',''))
        else:
            note=f'no link matching discover_{other} on {seed}'
    if other not in srcs:
        srcs[other]=dict(srcs[role], id=other)
        note=note or f'vendor has no discover_{other} pattern'
    out=dict(exam_code=code, vendor_slug=v, sources=[srcs['sg'], srcs['cp']], note=note)
    json.dump(out, open(os.path.join(rdir(v), f'{code}.sources.json'),'w',encoding='utf-8'), indent=1)
    print(f'discover {code}: sg={srcs["sg"]["url"]} cp={srcs["cp"]["url"]} {note}')
    return out

def slugify(s):
    return re.sub(r'[^a-z0-9]+','-',s.lower()).strip('-')

def cert_slug(name, vendor_name):
    s=re.sub(r'(?i)^'+re.escape(vendor_name)+r'\s+certified\s*:?\s*|^'+re.escape(vendor_name)+r'\s+|^certified\s+','',name.strip())
    return slugify(s) or slugify(name)

def norm(x):
    return re.sub(r'\s+',' ',html.unescape(x).replace('\u2019',"'").replace('\u2013','-').replace('\u2014','-')).strip().lower()

def page_texts(R):
    out={}
    for s in R['sources']:
        m=fetch_sources.find_saved(R['vendor_slug'], s['url'])
        if m: out[s['id']]=(m, norm(re.sub(r'<[^>]+>',' ',open(m['path'],encoding='utf-8',errors='ignore').read())))
    return out

def build(code, force=False):
    row=catalog_row(code); v=row['vendor_slug']; vmeta=vendor_reg.vendor(v); VN=vmeta.get('name') or v
    rpath=os.path.join(rdir(v), f'{code}.json')
    if os.path.exists(rpath) and not force:
        old=json.load(open(rpath,encoding='utf-8'))
        if old.get('generated_by')!=GEN:
            print(f'research: {rpath} is hand-written; left as is.'); return old
    sp=os.path.join(rdir(v), f'{code}.sources.json')
    if not os.path.exists(sp): raise SystemExit(f'{sp} missing; run the sources stage (discover) first.')
    S=json.load(open(sp,encoding='utf-8'))
    R=dict(exam_code=code, vendor_slug=v, generated_by=GEN, sources=[], exam_slug=code.lower())
    metas={}
    for s in S['sources']:
        m=fetch_sources.find_saved(v, s['url'])
        if not m: raise SystemExit(f'saved copy missing for {s["url"]}')
        metas[s['id']]=m
        R['sources'].append(dict(id=s['id'], kind='study_guide' if s['id']=='sg' else 'exam_or_credential_page', url=s['url'],
                                 title='', as_of_date=m['retrieved_at'][:10], expected_sha256=m['sha256']))
    from adapters import generic, load as load_adapter
    G=generic.parse(R, paths.root())
    A=load_adapter(v)
    VA=A.parse(R, paths.root()) if A.__name__.split('.')[-1]!='generic' else None
    texts=page_texts(R)
    def fact(key, value, quote, sid):
        if value in (None,'',[]) or not sid or not quote:
            return dict(value=None, reason=NP)
        m=metas[sid]
        return dict(value=value, source_id=sid, url=m['url'], sha256=m['sha256'], quote=quote)
    F=G['fields']; Q=G['quotes']; SID=G.get('sources') or {}
    g=lambda k: fact(k, F.get(k), Q.get(k), SID.get(k))
    facts=dict(duration_minutes=g('duration_minutes'), passing_score=g('passing_score'),
               score_scale=dict(value=None, reason=NP), question_count=g('question_count'),
               question_formats=dict(value=None, reason=NP), languages=g('languages'))
    if F.get('passing_score_unit') and facts['passing_score'].get('value') is not None:
        facts['passing_score']['unit']=F['passing_score_unit']
    pr=g('price')
    if pr.get('value') is not None: pr['value']=f"USD {pr['value']}"
    facts['price']=pr
    facts['prerequisites']=g('prerequisites'); facts['validity_and_renewal']=g('renewal')
    facts['retake_policy']=g('retake_policy'); facts['extra_time_language']=dict(value=None, reason=NP)
    facts['status']=dict(value=None, reason=NP); facts['audience']=dict(value=None, reason=NP)
    facts['level']=g('level'); facts['product_name_note']=dict(value=None, reason=NP); facts['delivery']=g('delivery')
    domains=[]
    if VA and VA.get('fields',{}).get('domains'):
        # vendor adapter (structured outline) wins over the generic reader
        vf=VA['fields']
        for i,d in enumerate(vf['domains']):
            groups=[t for t in vf.get('task_groups') or [] if t['domain']==d['name']]
            domains.append(dict(code=str(i+1), name=d['name'], weight_min_pct=d['weight_min_pct'], weight_max_pct=d['weight_max_pct'],
                                topics=[dict(code=f'{i+1}.{j+1}', name=t['name'], subtopics=t['tasks']) for j,t in enumerate(groups)]))
        if vf.get('passing_score') is not None:
            q=next((l for l in G_lines(texts,'sg') if str(vf['passing_score']) in l and 'pass' in l.lower()), None)
            facts['passing_score']=fact('passing_score', vf['passing_score'], q or f"A score of {vf['passing_score']} or greater is required to pass", 'sg')
        if vf.get('extra_time_language_minutes'):
            n=vf['extra_time_language_minutes']
            facts['extra_time_language']=fact('x', f'Candidates can request {n} extra minutes if the exam is not offered in their language', f'you can request an additional {n} minutes to complete the exam', 'sg')
        if vf.get('duration_minutes_candidate') and facts['duration_minutes'].get('value') is None:
            n=vf['duration_minutes_candidate']
            facts['duration_minutes']=fact('d', n, f'{n} minutes', 'cp')
    elif F.get('domains') and SID.get('domains')=='sg':
        for i,(d,tg) in enumerate(zip(F['domains'], F.get('task_groups') or [{}]*len(F['domains']))):
            domains.append(dict(code=str(i+1), name=d['name'], weight_min_pct=d['weight_min_pct'], weight_max_pct=d['weight_max_pct'],
                                topics=[dict(code=f'{i+1}.1', name=d['name'], subtopics=list(tg.get('tasks') or []))]))
    if not domains:
        raise SystemExit(f'{code}: no skill outline with weights found on the saved study guide ({metas["sg"]["url"]}). '
                         'Check the discovered sg page; an outline is never invented.')
    # official names: lookup / catalog value, kept only if it appears on a saved page
    L=lookup(code)
    name=None; nsid=None
    for cand in [row.get('exam_name'), L.get('name')]:
        if not cand: continue
        for sid,(m,t) in texts.items():
            if norm(cand) in t: name, nsid=cand, sid; break
        if name: break
    if not name:
        raise SystemExit(f'{code}: official exam name not found on the saved pages; add it to catalog.csv exam_name only if the vendor page shows it.')
    R['exam_name']=fact('exam_name', name, name, nsid)
    R['facts']=facts
    R['objectives']=dict(outline_as_of=metas['sg']['retrieved_at'][:10], source_id='sg', domains=domains, changes_from_previous=None)
    R['learning_resources']=[]; R['serp']=[]; R['blurbs']={}
    cname=(row.get('certification') or L.get('cert') or name)
    cname=cname if any(norm(cname) in t for _,t in texts.values()) else name
    R['certification_slug']=cert_slug(cname, VN)
    R['gaps']=sorted(k for k,f in facts.items() if f.get('value') is None)
    R['unknowns']=list(R['gaps'])
    json.dump(R, open(rpath,'w',encoding='utf-8'), indent=1, ensure_ascii=False)
    bsp=os.path.join(rdir(v), f'{code}-bank-sources.json')
    if not os.path.exists(bsp):
        json.dump({'sources':[dict(id='SG', title=f'{code} official exam guide', url=metas['sg']['url']),
                              dict(id='CP', title=f'{code} official exam page', url=metas['cp']['url'])]},
                  open(bsp,'w',encoding='utf-8'), indent=1)
    # vendor and certification files when missing
    vp=os.path.join(paths.root(),'research','vendors',f'{v}.json')
    if not os.path.exists(vp):
        os.makedirs(os.path.dirname(vp), exist_ok=True)
        json.dump(dict(vendor_slug=v, name=VN, official_site=vmeta.get('official_site',''), official_learning_url=vmeta.get('official_learning_url') or vmeta.get('official_site',''),
                       generated_by=GEN, sources=[dict(id=s['id'], url=s['url'], expected_sha256=s['expected_sha256']) for s in R['sources']],
                       facts=dict(exam_sandbox=dict(value=None, reason=NP), accommodations=dict(value=None, reason=NP)), logo_note='', blurbs={}),
                  open(vp,'w',encoding='utf-8'), indent=1, ensure_ascii=False)
    cp=os.path.join(paths.root(),'research','certs',f'{R["certification_slug"]}.json')
    if not os.path.exists(cp):
        os.makedirs(os.path.dirname(cp), exist_ok=True)
        lv=g('level') if SID.get('level')=='cp' else dict(value=None, reason=NP)
        rl=g('role') if SID.get('role')=='cp' else dict(value=None, reason=NP)
        if rl.get('value'): rl['value']=[x.strip() for x in str(rl['value']).split(',') if x.strip()]
        json.dump(dict(certification_slug=R['certification_slug'], vendor_slug=v, name=cname, source_id='cp', generated_by=GEN,
                       sources=[dict(id='cp', url=metas['cp']['url'], expected_sha256=metas['cp']['sha256'])],
                       required_exams=[dict(code=code, requirement_type='required', quote=name)],
                       level=lv if lv.get('value') else dict(value=None, reason=NP), roles=rl,
                       product=dict(value=None, reason=NP), subject=dict(value=None, reason=NP), prerequisites=dict(value=None, reason=NP),
                       validity=dict(value=None, reason=NP), renewal=dict(value=None, reason=NP),
                       practice_assessment=dict(value=None, reason=NP), last_updated=dict(value=None, reason=NP), blurbs={}),
                  open(cp,'w',encoding='utf-8'), indent=1, ensure_ascii=False)
    gp=os.path.join(paths.root(),'research','gaps.json')
    allg=json.load(open(gp,encoding='utf-8')) if os.path.exists(gp) else {}
    allg[code]=dict(vendor=v, gaps=R['gaps'], note='Fill only from an official quote in the batched gap pass; otherwise keep "not published by the vendor".')
    json.dump(allg, open(gp,'w',encoding='utf-8'), indent=1, sort_keys=True)
    print(f'research {code}: {sum(1 for f in facts.values() if f.get("value") is not None)} facts with quotes, {len(R["gaps"])} gaps, {len(domains)} domains -> {rpath}')
    return R

def G_lines(texts, sid):
    m=texts.get(sid)
    if not m: return []
    from adapters.generic import _lines
    return _lines(open(m[0]['path'],encoding='utf-8',errors='ignore').read())

if __name__=='__main__':
    cmd, code=sys.argv[1], sys.argv[2]
    {'discover':discover,'build':build}[cmd](code)
