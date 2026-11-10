#!/usr/bin/env python3
"""Generate draft pages (JSON + HTML) from research JSON plus author-stage page_prose.json.

Vendor and certification pages are built once and skipped when their input hash is unchanged.
Usage: build_pages.py research/<vendor>/<CODE>.json

Original page prose comes from out/<CODE>/authoring/page_prose.json (the author stage).
This script does not call AI.
"""
import csv, hashlib, html, json, os, re, sys, datetime
sys.path.insert(0, os.path.dirname(__file__))
import site_settings, paths, shared_sections
B=paths.root(); S=site_settings.load(); BRAND=S['brand']; BASE=S['base_url']; TODAY=paths.today()
NP=S.get('not_published_label') or 'not published by the vendor'

def srcinfo(url):
    for root,_,fs in os.walk(f'{B}/sources'):
        if root==f'{B}/sources': continue
        for f in fs:
            if f.endswith('.json'):
                d=json.load(open(os.path.join(root,f)))
                if d.get('url')==url: return d
    raise SystemExit('source not fetched: '+url)

def route(kind,**kw): return S['routes'][kind].format(**kw)
def esc(x): return html.escape(str(x))
def link(url,text): return f'<a href="{esc(url)}">{esc(text)}</a>'
def fmt_date(iso):
    d=datetime.date.fromisoformat(iso[:10]); return d.strftime('%B ') + str(d.day) + d.strftime(', %Y')
def pick(cands,lo,hi,used):
    for c in cands:
        if lo<=len(c)<=hi and c not in used: used.add(c); return c
    raise SystemExit(f'no candidate in {lo}-{hi}: '+' || '.join(f'{len(c)}:{c}' for c in cands))
USED_T=set(); USED_D=set()
TLO,THI=S['meta_title_range']; DLO,DHI=S['meta_description_range']

def page(key,kind,path,title_c,desc_c,h1,crumbs,body,tables,jsonld_extra,sources,out_dir,entity):
    title=pick(title_c,TLO,THI,USED_T); desc=pick(desc_c,DLO,DHI,USED_D); url=BASE+path
    bc={"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[{"@type":"ListItem","position":i+1,"name":n,"item":BASE+p} for i,(n,p) in enumerate(crumbs)]}
    web={"@context":"https://schema.org","@type":"WebPage","name":title,"url":url,"dateModified":TODAY,"inLanguage":S['locale'],
         "publisher":{"@type":"Organization","name":BRAND,"url":BASE}}
    jsonld=[web,bc]+jsonld_extra
    meta=dict(title=title,meta_description=desc,canonical_url=url,robots=S['robots_draft'],h1=h1,slug=path.rstrip('/').split('/')[-1],path=path,
        og={"og:title":title,"og:description":desc,"og:url":url,"og:type":"website","og:site_name":BRAND,"og:locale":"en_US","og:image":""},
        twitter={"twitter:card":"summary","twitter:title":title,"twitter:description":desc},
        last_updated=TODAY,last_checked=max(s['retrieved_at'] for s in sources) if sources else TODAY)
    crumb_html=' / '.join(link(BASE+p,n) for n,p in crumbs[:-1])+' / '+esc(crumbs[-1][0])
    head='\n'.join([f'<title>{esc(title)}</title>',f'<meta name="description" content="{esc(desc)}">',f'<link rel="canonical" href="{esc(url)}">',
        f'<meta name="robots" content="{esc(S["robots_draft"])}">']+[f'<meta property="{k}" content="{esc(v)}">' for k,v in meta['og'].items() if v]+
        [f'<meta name="{k}" content="{esc(v)}">' for k,v in meta['twitter'].items()]+
        [f'<script type="application/ld+json">{json.dumps(j,ensure_ascii=False)}</script>' for j in jsonld])
    disclaimer=f'<aside class="disclaimer" data-source="central-setting">{esc(S["disclaimer"])}</aside>'
    srcs='<section class="sources"><h2>Sources</h2><ul>'+''.join(f'<li>{link(s["url"],s["url"])} (checked {fmt_date(s["retrieved_at"])})</li>' for s in sources)+'</ul></section>'
    main=f'<main><nav class="breadcrumb">{crumb_html}</nav><h1>{esc(h1)}</h1><p class="updated">Last updated {fmt_date(TODAY)}</p>{body}</main>'
    doc=f'<!doctype html><html lang="en"><head><meta charset="utf-8">\n{head}\n</head><body>{main}{srcs}{disclaimer}</body></html>'
    os.makedirs(out_dir,exist_ok=True)
    rec=dict(key=key,kind=kind,entity=entity,status='draft',meta=meta,jsonld=jsonld,tables=tables,body_html=body,sources=[dict(url=s['url'],sha256=s['sha256'],retrieved_at=s['retrieved_at']) for s in sources],
             brand_source=S['brand_source'],disclaimer_source=S['disclaimer_source'])
    json.dump(rec,open(f'{out_dir}/{key}.json','w'),indent=1,ensure_ascii=False); open(f'{out_dir}/{key}.html','w').write(doc)
    return rec

def table(cols,rows,caption):
    h=f'<table><caption>{esc(caption)}</caption><thead><tr>'+''.join(f'<th scope="col">{esc(c)}</th>' for c in cols)+'</tr></thead><tbody>'
    for r in rows: h+='<tr>'+''.join(f'<td>{c}</td>' for c in r)+'</tr>'
    return h+'</tbody></table>'
def inhash(*files):
    parts=[]
    for f in files:
        if f and os.path.exists(f): parts.append(open(f,'rb').read())
    parts.append(open(__file__,'rb').read())
    return hashlib.sha256(b''.join(parts)).hexdigest()
def skip(out_dir,key,h):
    p=f'{out_dir}/{key}.inputs.sha256'
    return os.path.exists(p) and open(p).read()==h and os.path.exists(f'{out_dir}/{key}.json')
def mark(out_dir,key,h): open(f'{out_dir}/{key}.inputs.sha256','w').write(h)

def load_prose(code):
    p=f'{B}/out/{code}/authoring/page_prose.json'
    if not os.path.exists(p):
        raise SystemExit(f'missing {p}. Run the author stage first (it is the only AI stage: original page prose).')
    return json.load(open(p))

def prose_body(prose, kind, nav_html=None, context=None):
    rec=prose[kind]
    body=rec['body_html']
    body=shared_sections.insert_into(body, rec.get('shared_keys') or [], context or {})
    # Optional keys listed in page_prose: append any not already inserted by a marker
    for item in rec.get('shared_keys') or []:
        level=item.get('level'); key=item.get('key'); slug=item.get('slug')
        html=shared_sections.render(level, key, slug)
        if html and html not in body:
            body=body+html
    if nav_html and '<nav class="exam-links">' not in body:
        body=body+nav_html
    return body

def build_exam(rpath):
    R=json.load(open(rpath)); V=json.load(open(f'{B}/research/vendors/{R["vendor_slug"]}.json')); C=json.load(open(f'{B}/research/certs/{R["certification_slug"]}.json'))
    v,e,c=R['vendor_slug'],R['exam_slug'],R['certification_slug']; code=R['exam_code']; name=R['exam_name']['value']; F=R['facts']; O=R['objectives']
    src={s['id']:srcinfo(s['url']) for s in R['sources']}
    out=f'{B}/out/{code}/pages'
    prose=load_prose(code)
    ctx=dict(vendor_slug=v, certification_slug=c, exam_code=code)
    P={k:route(k,vendor=v,exam=e,cert=c) for k in ('exam_hub','objectives','study_guide','faq','practice_test')}
    P['vendor']=route('vendor',vendor=v); P['certification']=route('certification',cert=c)
    asof=fmt_date(O['outline_as_of']); dur=F['duration_minutes']['value']; ps=F['passing_score']['value']; langs=F['languages']['value']
    def cell(fk,val):
        f=F[fk]; s=src[f['source_id']] if f.get('source_id') else None
        v_=esc(val) if val not in (None,'') else esc(NP)
        return v_+(f' ({link(s["url"],"source")}, checked {fmt_date(s["retrieved_at"])})' if s else '')
    nav=lambda here: '<nav class="exam-links"><h2>More on '+esc(code)+'</h2><ul>'+''.join(f'<li>{link(BASE+P[k],t)}</li>' for k,t in [('exam_hub',f'{code} exam overview'),('objectives',f'{code} skills measured'),('study_guide',f'{code} study guide'),('faq',f'{code} FAQ'),('practice_test',f'{code} practice test'),('certification',C['name']),('vendor',f'All {V["name"]} exams on {BRAND}')] if k!=here)+'</ul></nav>'
    crumbs=lambda last: [('Home','/'),(V['name'],P['vendor']),(code,P['exam_hub'])]+([last] if last else [])
    doms=O['domains']
    pages=[]
    # tables are computed from official facts; body prose comes from the author stage
    kf_rows=[['Exam length',cell('duration_minutes',f'{dur} minutes')],['Passing score',cell('passing_score',f'{ps} or higher')],
             ['Price',cell('price','')+(prose.get('exam_hub',{}).get('price_note') or '')],
             ['Languages',cell('languages',', '.join(langs))],['Format',cell('question_formats',F['question_formats']['value'])],
             ['Number of questions',esc(NP)],['Level',cell('level',F['level']['value'])],['Delivery',cell('delivery',F['delivery']['value'])]]
    # If cached body already includes tables (approved pilot), keep it so HTML stays stable.
    hub_tables=prose['exam_hub'].get('tables') or {'key_facts':kf_rows}
    if 'key_facts' not in hub_tables: hub_tables['key_facts']=kf_rows
    pages.append(page('exam-hub','exam_hub',P['exam_hub'],
        prose['exam_hub']['title_candidates'], prose['exam_hub']['desc_candidates'],
        prose['exam_hub']['h1'], crumbs(None)[:-1]+[(code,P['exam_hub'])],
        prose_body(prose,'exam_hub',nav('exam_hub'),ctx), hub_tables, [], list(src.values()), out, code))
    wmin=sum(d['weight_min_pct'] for d in doms); wmax=sum(d['weight_max_pct'] for d in doms)
    ob_rows=[[esc(d['code']),esc(d['name']),f'{d["weight_min_pct"]} to {d["weight_max_pct"]} percent'] for d in doms]
    ob_tables=prose['objectives'].get('tables') or {'objectives':ob_rows,'weight_min_sum':wmin,'weight_max_sum':wmax}
    pages.append(page('objectives','objectives',P['objectives'],
        prose['objectives']['title_candidates'], prose['objectives']['desc_candidates'],
        prose['objectives']['h1'], crumbs(('Objectives',P['objectives'])),
        prose_body(prose,'objectives',nav('objectives'),ctx), ob_tables, [], [src['sg']], out, code))
    plan_rows=[[esc(d['name']),f'{d["weight_min_pct"]} to {d["weight_max_pct"]} percent','<br>'.join(link(r['url'],r['title']) for r in R['learning_resources'] if d['code'] in r['domains'])] for d in doms]
    sg_tables=prose['study_guide'].get('tables') or {'study_plan':plan_rows}
    course={"@context":"https://schema.org","@type":"Course","name":f'{code} study guide',"description":prose['study_guide'].get('course_description') or f'Study plan for the {code} exam built from the official skills outline dated {asof}.',
            "provider":{"@type":"Organization","name":BRAND,"url":BASE},"url":BASE+P['study_guide'],"inLanguage":"en","isAccessibleForFree":True,
            "educationalCredentialAwarded":C['name'],"about":[d['name'] for d in doms]}
    pages.append(page('study-guide','study_guide',P['study_guide'],
        prose['study_guide']['title_candidates'], prose['study_guide']['desc_candidates'],
        prose['study_guide']['h1'], crumbs(('Study guide',P['study_guide'])),
        prose_body(prose,'study_guide',nav('study_guide'),ctx), sg_tables, [course], [src['sg'],src['cp']], out, code))
    # FAQ schema: sourced answers only
    faq_src=prose['faq'].get('faq_sourced') or []
    faq_uns=prose['faq'].get('faq_unsourced') or []
    # Recover Q/A from body if the author file listed names only
    qa=re.findall(r'<h2>(.*?)</h2><p>(.*?)</p>', prose['faq']['body_html'])
    def unesc(x): return html.unescape(re.sub(r'<[^>]+>','',x))
    sourced_names=set(faq_src)
    faq_ld={"@context":"https://schema.org","@type":"FAQPage","mainEntity":[{"@type":"Question","name":unesc(q),"acceptedAnswer":{"@type":"Answer","text":unesc(re.sub(r'<a [^>]+>source</a>','',a).strip(' ()'))}} for q,a in qa if unesc(q) in sourced_names]}
    pages.append(page('faq','faq',P['faq'],
        prose['faq']['title_candidates'], prose['faq']['desc_candidates'],
        prose['faq']['h1'], crumbs(('FAQ',P['faq'])),
        prose_body(prose,'faq',nav('faq'),ctx), {'faq_sourced':faq_src,'faq_unsourced':faq_uns}, [faq_ld], [src['sg'],src['cp']], out, code))
    mix=[(d['name'],(d['weight_min_pct']+d['weight_max_pct'])/2) for d in doms]; tot=sum(m for _,m in mix)
    mix_rows=[[esc(n),f'{round(m*100/tot)} percent'] for n,m in mix]
    pt_tables=prose['practice_test'].get('tables') or {'planned_mix':mix_rows}
    # No Course schema on the practice test page (app rule).
    pages.append(page('practice-test','practice_test',P['practice_test'],
        prose['practice_test']['title_candidates'], prose['practice_test']['desc_candidates'],
        prose['practice_test']['h1'], crumbs(('Practice test',P['practice_test'])),
        prose_body(prose,'practice_test',nav('practice_test'),ctx), pt_tables, [], [src['sg'],src['cp']], out, code))
    return R,V,C,P,pages,prose

def build_vendor(V,catalog_rows,current_code,prose):
    ctx=dict(vendor_slug=V.get("vendor_slug"))
    out=f'{B}/out/vendors/{V["vendor_slug"]}'; h=inhash(f'{B}/research/vendors/{V["vendor_slug"]}.json',f'{B}/catalog.csv',f'{B}/out/{current_code}/authoring/page_prose.json')
    if skip(out,'vendor',h): print('skip vendor (unchanged)'); return json.load(open(f'{out}/vendor.json'))
    vs={s['id']:srcinfo(s['url']) for s in V['sources']}; path=route('vendor',vendor=V['vendor_slug'])
    built={r['exam_code'] for r in catalog_rows if os.path.exists(f'{B}/out/{r["exam_code"]}/pages/exam-hub.json')}
    built.add(current_code)
    rec=page('vendor','vendor',path,prose['vendor']['title_candidates'],prose['vendor']['desc_candidates'],
        prose['vendor']['h1'],[('Home','/'),(V['name'],path)],
        prose_body(prose,'vendor',None,ctx), prose['vendor'].get('tables') or {'exams':[]}, [], list(vs.values()), out, V['vendor_slug'])
    mark(out,'vendor',h); return rec

def build_cert(C,V,P,R,prose):
    ctx=dict(vendor_slug=V.get("vendor_slug"), certification_slug=C.get("certification_slug"), exam_code=R.get("exam_code"))
    out=f'{B}/out/certifications/{C["certification_slug"]}'; h=inhash(f'{B}/research/certs/{C["certification_slug"]}.json',f'{B}/research/{R["vendor_slug"]}/{R["exam_code"]}.json',f'{B}/out/{R["exam_code"]}/authoring/page_prose.json')
    if skip(out,'certification',h): print('skip cert (unchanged)'); return json.load(open(f'{out}/certification.json'))
    cs=srcinfo(C['sources'][0]['url']); path=route('certification',cert=C['certification_slug'])
    cred={"@context":"https://schema.org","@type":"EducationalOccupationalCredential","name":C['name'],"credentialCategory":"certification","educationalLevel":C['level']['value'],
          "url":cs['url'],"recognizedBy":{"@type":"Organization","name":V['name'],"url":V['official_site']},"competencyRequired":[d['name'] for d in R['objectives']['domains']]}
    rec=page('certification','certification',path,prose['certification']['title_candidates'],prose['certification']['desc_candidates'],
        prose['certification']['h1'],[('Home','/'),(V['name'],route('vendor',vendor=V['vendor_slug'])),(prose['certification'].get('crumb_name') or C['name'].split(':')[-1].strip(),path)],
        prose_body(prose,'certification',None,ctx), prose['certification'].get('tables') or {'requirements':[]}, [cred], [cs], out, C['certification_slug'])
    mark(out,'certification',h); return rec

if __name__=='__main__':
    R,V,C,P,pages,prose=build_exam(sys.argv[1])
    cat=[r for r in csv.DictReader(open(f'{B}/catalog.csv')) if r['vendor_slug']==R['vendor_slug']]
    vend=build_vendor(V,cat,R['exam_code'],prose); cert=build_cert(C,V,P,R,prose)
    for p in [vend,cert]+pages: print(p['kind'],len(p['meta']['title']),p['meta']['title'],'|',len(p['meta']['meta_description']))
