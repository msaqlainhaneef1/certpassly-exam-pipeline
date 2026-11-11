#!/usr/bin/env python3
"""Step 8 checks for one exam package + shared vendor/cert pages. Exit 1 on any failure.
Usage: validate.py research/<vendor>/<CODE>.json"""
import csv, glob, hashlib, html, json, os, re, subprocess, sys, datetime, argparse
sys.path.insert(0, os.path.dirname(__file__)); import site_settings, paths as pathutil, source_text, fetch_sources
B=pathutil.root(); S=site_settings.load()
ap=argparse.ArgumentParser(description='Validate one exam package. Exit 1 on any failure.')
ap.add_argument('research')
ap.add_argument('--offline', action='store_true', default=os.environ.get('CERTPASSLY_OFFLINE') in ('1','true','yes'))
args,_=ap.parse_known_args()
R=json.load(open(args.research)); code=R['exam_code']; v=R['vendor_slug']; c=R['certification_slug']
OFFLINE=args.offline
OUT=f'{B}/out/{code}'
pfiles=sorted(glob.glob(f'{OUT}/pages/*.json'))+[f'{B}/out/vendors/{v}/vendor.json',f'{B}/out/certifications/{c}/certification.json']
pages=[json.load(open(p)) for p in pfiles]; htmls={p['kind']:open(f[:-5]+'.html').read() for p,f in zip(pages,pfiles)}
res=[]
def chk(name,ok,detail=''): res.append((name,bool(ok),str(detail)[:300]))
def norm(t): t=html.unescape(t); t=re.sub(r'[\u2013\u2014\u2010\u2011\-]','-',t); t=t.replace('\u2019',"'").replace('\u2018',"'"); return re.sub(r'\s+',' ',t).strip().lower()
def text(h): return norm(re.sub(r'<[^>]+>',' ',h))
def prose(h): return ' '.join(re.sub(r'<[^>]+>',' ',x) for x in re.findall(r'<p[^>]*>(.*?)</p>',h,re.S))
# 1 required fields
req=['title','meta_description','canonical_url','robots','h1','slug','path','last_updated','last_checked']
miss=[(p['kind'],k) for p in pages for k in req if not p['meta'].get(k)]
chk('01 required page fields present',not miss,miss)
imp=f'{OUT}/import'
keys={'vendors.csv':'vendor_key','certifications.csv':'certification_key','exams.csv':'exam_key','domains.csv':'domain_key','topics.csv':'topic_key','sources.csv':'evidence_key','page_copy.csv':'copy_key'}
bad=[(f,i) for f,k in keys.items() for i,r in enumerate(csv.DictReader(open(f'{imp}/{f}'))) if not r[k]]
chk('01b import key columns filled',not bad,bad)
ex=next(csv.DictReader(open(f'{imp}/exams.csv')))
_ps_np=R['facts'].get('passing_score',{}).get('value') in (None,'') and bool(R['facts'].get('passing_score',{}).get('reason'))
chk('01c exam row has code, name, duration, passing score, URLs',all(ex[k] for k in ['exam_code','official_exam_name','official_duration_minutes','official_exam_url','official_guide_url']) and (ex['official_passing_score'] or _ps_np),'passing score not published by the vendor' if _ps_np else '')
# 2 facts have source + hash + quote on saved page
srcmeta={}
for root,_,fs in os.walk(f'{B}/sources/{v}'):
    for f in fs:
        if f.endswith('.json'):
            sp=os.path.join(root,f); d=fetch_sources.load_sidecar(sp); srcmeta[d['url']]=d
sid={s['id']:s['url'] for s in R['sources']}
probs=[]
pagetext={u:norm(re.sub(r'<[^>]+>',' ',open(m['path'],encoding='utf8',errors='ignore').read())) for u,m in srcmeta.items()}
def fact_ok(name,f,ids):
    if f.get('value') in (None,''):
        if not f.get('reason'): probs.append(f'{name}: empty without reason')
        return
    u=ids.get(f.get('source_id'));
    if not u or u not in srcmeta: probs.append(f'{name}: no fetched source'); return
    if not f.get('quote') or norm(f['quote']) not in pagetext[u]: probs.append(f'{name}: quote not found on saved page')
for k,f in R['facts'].items(): fact_ok(k,f,sid)
fact_ok('exam_name',R['exam_name'],sid)
for d in R['objectives']['domains']:
    if norm(d['name']) not in pagetext[sid[R['objectives']['source_id']]]: probs.append('domain not on page: '+d['name'])
    for t in d['topics']:
        for s_ in [t['name']]+t['subtopics']:
            if norm(s_) not in pagetext[sid['sg']]: probs.append('objective text not on page: '+s_)
    if not source_text.weight_on_page(d['name'], d, pagetext[sid['sg']]): probs.append('weight not on page: '+d['name'])
C=json.load(open(f'{B}/research/certs/{c}.json')); cid={s['id']:s['url'] for s in C['sources']}
for k in ['level','roles','practice_assessment','last_updated']: fact_ok('cert.'+k,dict(C[k],source_id='cp'),cid)
V=json.load(open(f'{B}/research/vendors/{v}.json')); vid={s['id']:s['url'] for s in V['sources']}
for k,f in V['facts'].items(): fact_ok('vendor.'+k,f,vid)
chk('02 every fact has official source, saved copy, and quote found on the page',not probs,probs)
hb=[u for u,m in srcmeta.items() if hashlib.sha256(open(m['path'],'rb').read()).hexdigest()!=m['sha256']]
chk('02b saved source files match recorded sha256',not hb and srcmeta,f'{len(srcmeta)} sources')
V=json.load(open(f'{B}/research/vendors/{v}.json'))
off=[s['url'] for p in pages for s in p['sources'] if not site_settings.official_url_ok(s['url'], v, V.get('official_site'))]
chk('02c page sources are official vendor URLs',not off,off)
# 3 slugs
paths=[p['meta']['path'] for p in pages]
chk('03 page paths unique',len(set(paths))==len(paths),paths)
chk('03b slugs and canonicals lowercase, match app routes',all(p['meta']['canonical_url']==p['meta']['canonical_url'].lower()==S['base_url']+p['meta']['path'] for p in pages),'')
# 4 weights
D=R['objectives']['domains']; mn=sum(d['weight_min_pct'] for d in D); mx=sum(d['weight_max_pct'] for d in D)
chk('04 weight ranges cover 100 percent',mn<=100<=mx and all(d['weight_min_pct']<=d['weight_max_pct'] for d in D),f'min sum {mn}, max sum {mx}')
# 5 title/meta/H1
chk('05 titles 50 to 60 chars',all(50<=len(p['meta']['title'])<=60 for p in pages),[len(p['meta']['title']) for p in pages])
chk('05b meta descriptions 140 to 160 chars',all(140<=len(p['meta']['meta_description'])<=160 for p in pages),[len(p['meta']['meta_description']) for p in pages])
chk('05c titles and descriptions unique',len({p['meta']['title'] for p in pages})==len(pages)==len({p['meta']['meta_description'] for p in pages}),'')
chk('05d exactly one H1 per page',all(len(re.findall(r'<h1[\s>]',h))==1 for h in htmls.values()),'')
chk('05e H2 outline present',all(len(re.findall(r'<h2[\s>]',h))>=2 for h in htmls.values()),'')
# OG / Twitter / robots / last updated
need_og=['og:title','og:description','og:url','og:type','og:site_name']; need_tw=['twitter:card','twitter:title','twitter:description']
chk('05f Open Graph tags present in HTML',all(all(f'property="{t}"' in h for t in need_og) for h in htmls.values()),'og:image left empty: no approved image asset')
chk('05g Twitter card tags present in HTML',all(all(f'name="{t}"' in h for t in need_tw) for h in htmls.values()),'')
chk('05h robots noindex while draft',all(p['meta']['robots'].startswith('noindex') and 'content="noindex' in htmls[p['kind']] for p in pages),'')
chk('05i last updated date shown',all('Last updated' in h for h in htmls.values()),'')
chk('05j canonical tag in HTML',all('rel="canonical"' in h for h in htmls.values()),'')
# 6 similarity
def body_only(h): h=re.sub(r'(?s)<nav.*?</nav>','',h); h=re.sub(r'(?s)<table.*?</table>','',h); return text(h).split()
sh={p['kind']:set(tuple(w[i:i+5]) for i in range(len(w)-4)) for p in pages for w in [body_only(p['body_html'])]}
worst=[]
ks=list(sh)
for i in range(len(ks)):
    for j in range(i+1,len(ks)):
        a,b=sh[ks[i]],sh[ks[j]]; s=len(a&b)/max(1,min(len(a),len(b))); worst.append((round(s*100,1),ks[i],ks[j]))
worst.sort(reverse=True)
chk('06 shingle overlap under 30 percent between pages',worst[0][0]<30,worst[:3])
wc={p['kind']:len(text(p['body_html']).split()) for p in pages}
chk('06b no thin pages (body 150+ words)',min(wc.values())>=150,wc)
# 7 banned phrases, 9 placeholders, 8 dashes
alltext={p['kind']:text(p['body_html']+' '+json.dumps(p['meta'])+' '+json.dumps(p['jsonld'])) for p in pages}
bp=[(k,b) for k,t in alltext.items() for b in S['banned_phrases'] if re.search(r'\b'+re.escape(b)+r'\b',t)]
chk('07 no banned filler phrases',not bp,bp)
ph=[(k,x) for k,h in htmls.items() for x in S['placeholders'] if re.search(r'\b'+re.escape(x)+r'\b' if x.isalpha() else re.escape(x),h.lower())]
chk('09 no placeholder text or placeholder links',not ph,ph)
RAW=('/extracted/','/media/src/','/media/','/answer_research/')
TEXT_EXT=('.json','.csv','.md','.html','.txt','.sha256')
scan=[f for f in glob.glob(f'{OUT}/**/*',recursive=True)+glob.glob(f'{B}/out/vendors/**/*',recursive=True)+glob.glob(f'{B}/out/certifications/**/*',recursive=True)+glob.glob(f'{B}/research/**/*.json',recursive=True)+glob.glob(f'{B}/config/*.json') if os.path.isfile(f)]
scan=[f for f in scan if f.endswith(TEXT_EXT) and not any(r in f.replace(os.sep,'/') for r in RAW)]
# Competitor notes are an input (topics only), never an output; the writing check gates copied wording.
scan=[f for f in scan if not f.endswith('.competitor-notes.json')]
FROZEN_JSON=('prompt_text','text','label','prompt','prompt_template','stem','quote')  # quote: verbatim official text
def prose_view(f):
    t=open(f,encoding='utf8',errors='ignore').read()
    if f.endswith('/questions.json'):
        d=json.loads(t)
        def strip(o):
            if isinstance(o,dict): return {k:('' if k in FROZEN_JSON else strip(v)) for k,v in o.items()}
            if isinstance(o,list): return [strip(x) for x in o]
            return o
        return json.dumps(strip(d),ensure_ascii=False)
    if f.endswith(('/import/questions.csv','/import/answer_options.csv')):
        rows=list(csv.DictReader(open(f)))
        return json.dumps([{k:('' if k in ('prompt_text','option_text') else v) for k,v in r.items()} for r in rows],ensure_ascii=False)
    if f.endswith('/REVIEW.md'):
        return re.sub(r'Quote: ".*?"(?=\s*$)','Quote: ""',t,flags=re.M)  # verbatim official quotes are exempt
    return t
dash=[f for f in scan if re.search('[\u2013\u2014]',prose_view(f))]
chk('08 no em or en dashes in any output, research or report file (owner stems and options exempt, raw extracts exempt)',not dash,dash)
# 9b links
links=set(u for h in htmls.values() for u in re.findall(r'href="([^"]+)"',h))
internal={u for u in links if u.startswith(S['base_url'])}; external=links-internal
known={S['base_url']+p for p in paths}|{S['base_url']+'/'}
bad_int=[u for u in internal if u not in known]
chk('09b internal links point to generated pages or home',not bad_int,bad_int)
cache=f'{B}/cache/linkcheck.json'; os.makedirs(os.path.dirname(cache),exist_ok=True); lc=json.load(open(cache)) if os.path.exists(cache) else {}
missing=[u for u in external if u not in lc]
if OFFLINE:
    chk('09c external links resolve (HTTP 200)',not missing and all(lc[u]=='200' for u in external),f'offline; cached {len(lc)}; missing {missing}; bad {[(u,lc.get(u)) for u in external if lc.get(u)!="200"]}')
else:
    for u in missing:
        r=subprocess.run(['curl','-sL','-o','/dev/null','--max-time','25','-w','%{http_code}',u],capture_output=True,text=True); lc[u]=r.stdout
    json.dump(lc,open(cache,'w'),indent=1)
    bad_ext=[(u,lc[u]) for u in external if lc[u]!='200']
    chk('09c external links resolve (HTTP 200)',not bad_ext,f'{len(external)} checked; bad: {bad_ext}')
# 10 readability
def syl(w):
    w=w.lower(); g=re.findall(r'[aeiouy]+',w); n=len(g)-(1 if w.endswith('e') and len(g)>1 else 0); return max(1,n)
grades={}
for p in pages:
    t=html.unescape(prose(p['body_html'])); sents=max(1,len(re.findall(r'[.!?](\s|$)',t))); words=re.findall(r"[A-Za-z][A-Za-z'-]*",t)
    grades[p['kind']]=round(0.39*len(words)/sents+11.8*sum(syl(w) for w in words)/max(1,len(words))-15.59,1)
chk('10 readability near grade 8 to 9 (prose grade 11 or lower)',max(grades.values())<=11,grades)
# 11 intent coverage
need={'exam_hub':['key facts','what the exam covers','what changed'],'objectives':['weights at a glance'],'study_guide':['study plan by skill area','before exam day'],'faq':['how long','pass','cost','languages'],'practice_test':['not ready','free official practice'],'vendor':['exams on'],'certification':['requirements']}
miss=[(k,n) for k,ns in need.items() for n in ns if n not in text(htmls[k])]
chk('11 each page covers its search intent outline',not miss,miss)
chk('11b required tables present (key facts, objectives, study plan, certification, vendor exams)',all(t in p['tables'] for p,t in [(next(x for x in pages if x['kind']==k),t) for k,t in [('exam_hub','key_facts'),('objectives','objectives'),('study_guide','study_plan'),('certification','requirements'),('vendor','exams')]]) and all('<table' in htmls[k] for k in ['exam_hub','objectives','study_guide','certification','vendor']),'')
kf=next(p for p in pages if p['kind']=='exam_hub')['tables']['key_facts']
chk('11c key facts cells show source link and checked date, or not published',all(('source' in r[1] and 'checked' in r[1]) or 'not published by the vendor' in r[1] for r in kf),'')
# 12 questions
import qtypes as QT
_have_bank=os.path.exists(f'{OUT}/questions.json') and os.path.exists(f'{imp}/questions.csv')
if not _have_bank:
    chk('12 every source item imported or held (none dropped)',False,'questions.json or import/questions.csv missing; run the bank stage')
    QJ={'questions':[],'held_for_review':[]}; QS=[]; q=[]; SPL=json.load(open(f'{OUT}/extracted/split.json')) if os.path.exists(f'{OUT}/extracted/split.json') else {}
else:
    q=list(csv.DictReader(open(f'{imp}/questions.csv'))); QJ=json.load(open(f'{OUT}/questions.json')); QS=QJ['questions']; SPL=json.load(open(f'{OUT}/extracted/split.json'))
chk('12 every source item imported or held (none dropped)',len(QS)+len(QJ['held_for_review'])==len(SPL) and len(q)==len(QS),f"{len(SPL)} in file = {len(QS)} imported + {len(QJ['held_for_review'])} held")
TY,_=QT.registry()
chk('12e every question has a canonical registry type, none needs_review',all(x['question_type'] in TY for x in QS),dict(__import__('collections').Counter(x['question_type'] for x in QS)))
bad=[]
for x in QS:
    c=x['response_schema']['content']
    pr=QT.agree(x['question_type'],x['prompt_text'],n_correct=len(x['answer_key'].get('correct_option_ids',[])) or None,n_blanks=len(c.get('blanks',[])) or None,has_exhibit=bool(c.get('image_url')))
    if pr: bad.append((x['question_key'],pr))
chk('12f source markers agree with assigned type (marker-agreement check)',not bad,bad)
VT=json.load(open(f'{OUT}/extracted/visual_transcription.json')) if os.path.exists(f'{OUT}/extracted/visual_transcription.json') else {}; mm=[]
for x in QS:
    v=VT.get(x['question_key']); c=x['response_schema']['content']
    if not v: continue
    if v.get('template') and c.get('prompt_template')!=v['template']: mm.append(x['question_key']+' template')
    for i,b in enumerate(c.get('blanks',[])):
        if v.get('labels') and b['label']!=v['labels'][i]: mm.append(x['question_key']+' label')
        if [ch['text'] for ch in b['choices']]!=v['blanks'][i]: mm.append(x['question_key']+' choices')
    if v.get('rows') and [r['text'] for r in c['rows']]!=v['rows']: mm.append(x['question_key']+' rows')
    if v.get('tiles') and [t['text'] for t in c.get('left',[])]!=v['tiles']: mm.append(x['question_key']+' tiles')
    if v.get('targets') and [t['text'] for t in c.get('right',[])]!=v['targets']: mm.append(x['question_key']+' targets')
chk('12g image text (rows, choices, labels, templates) matches the transcription exactly',not mm,mm)
shape=[x['question_key'] for x in QS if x.get('answer_key_status')!='answer_not_found' and ((x['question_type'] in ('single_choice','image_based_choice') and len(x['answer_key']['correct_option_ids'])!=1) or (x['question_type']=='multiple_select' and not (2<=len(x['answer_key']['correct_option_ids'])<len(x['options']) and len(x['options'])>=3)) or (x['question_type']=='yes_no_matrix' and set(x['answer_key']['rows'])!={r['id'] for r in x['response_schema']['content']['rows']}) or (x['question_type'].endswith('dropdown') and set(x['answer_key']['slots'])!={b['id'] for b in x['response_schema']['content']['blanks']}) or (x['question_type']=='drag_drop' and (set(x['answer_key'].get('pairs',{}))!={z['id'] for z in x['response_schema']['content'].get('right',[])} or not set(x['answer_key'].get('pairs',{}).values())<={t['id'] for t in x['response_schema']['content'].get('left',[])})))]
chk('12h answer key shapes fit the publish gate rules per type',not shape,shape)
vis=[x['question_key'] for x in QS if x['question_type'] in ('yes_no_matrix','inline_dropdown','multi_blank_dropdown') and not x['human_review_required']]
chk('12i image-keyed items flagged human_review_required',not vis,vis)
from adapters import parse_official
parsed=parse_official(R,B)
agree=parsed.get('agree') or {}
if agree:
    dur_ok=agree.get('duration_candidate')==R['facts']['duration_minutes']['value']
    ok=bool(agree.get('domains') and agree.get('passing_score') and agree.get('tasks') and dur_ok)
    chk('12k script parser of the saved official pages agrees with research facts (domains, weights, tasks, passing score, duration)',ok,agree)
else:
    # generic adapter: every research fact that has a value should match a parsed field, or the field is listed as a gap
    mismatches=[]
    fmap={'duration_minutes':'duration_minutes','passing_score':'passing_score'}
    fields=parsed.get('fields') or {}
    gaps=set(parsed.get('gaps') or [])
    for rk,pk in fmap.items():
        val=(R.get('facts') or {}).get(rk,{}).get('value')
        if val not in (None,'') and fields.get(pk) not in (None,'',val) and pk not in gaps:
            mismatches.append((rk,val,fields.get(pk)))
    if R.get('objectives',{}).get('domains') and fields.get('domains'):
        rd=[(d['name'],d['weight_min_pct'],d['weight_max_pct']) for d in R['objectives']['domains']]
        pd=[(d['name'],d.get('weight_min_pct'),d.get('weight_max_pct')) for d in fields['domains']]
        if rd!=pd: mismatches.append(('domains','research != parsed'))
    chk('12k script parser of the saved official pages agrees with research facts (domains, weights, tasks, passing score, duration)',not mismatches,mismatches or {'gaps':list(gaps)})

rv=open(f'{OUT}/REVIEW.md').read() if os.path.exists(f'{OUT}/REVIEW.md') else ''
_skip_vce=False
if os.path.exists(f'{OUT}/intake/files.json'):
    _skip_vce=any('vce' in str(f).lower() or str(f.get('use','')).startswith('skipped') for f in (json.load(open(f'{OUT}/intake/files.json')).get('files') or []))
_vce_ok=(not _skip_vce) or ('.vce' in rv or 'skipped' in rv.lower())
chk('12j held items, flagged keys and skipped VCE listed in REVIEW.md',all(h['question_key'] in rv for h in QJ['held_for_review']) and _vce_ok and all(x['question_key'] in rv for x in QS if x['answer_key_status']=='flagged_for_owner'),'')
# Owner rule v1.1.0: no-answer items are researched from official pages, never held or silently dropped.
import vendor_reg as _VR, answer_research as _AR
_arp=[]; _anf=[]
for x in QS:
    ev=x.get('research_evidence') or {}
    if x.get('answer_key_status')=='researched_unverified':
        sp=os.path.join(B, ev.get('saved_path',''))
        ok=(x.get('key_source')=='researched_official' and x.get('verification_status')=='unverified' and x.get('human_review_required') is True
            and ev.get('reviewer_needed') is True and ev.get('confidence') in ('high','medium','low')
            and _VR.url_is_official(ev.get('source_url',''), R['vendor_slug']) and os.path.isfile(sp)
            and __import__('hashlib').sha256(open(sp,'rb').read()).hexdigest()==ev.get('sha256')
            and _AR.norm(ev.get('quote')) in _AR.page_text({'path':sp}) and x['question_key'] in rv and 'UNVERIFIED' in rv)
        if not ok: _arp.append(x['question_key'])
    elif x.get('answer_key_status')=='answer_not_found':
        _sim=json.load(open(f'{OUT}/simulator_settings.json')) if os.path.exists(f'{OUT}/simulator_settings.json') else {}
        if not (x.get('scoring_excluded') is True and x['question_key'] in rv and x['question_key'] in (_sim.get('scoring_excluded_question_keys') or [])):
            _anf.append(x['question_key'])
    elif x.get('scoring_excluded'): _arp.append(x['question_key']+' excluded but keyed')
chk('12l researched keys: official domain, saved copy sha256, verbatim quote, unverified + reviewer flag, listed in REVIEW.md',not _arp,_arp or f"{sum(1 for x in QS if x.get('answer_key_status')=='researched_unverified')} researched")
chk('12m answer_not_found items kept as drafts, listed in REVIEW.md, excluded from scoring in simulator settings; nothing held',not _anf and not QJ['held_for_review'],_anf or f"{sum(1 for x in QS if x.get('answer_key_status')=='answer_not_found')} answer_not_found, {len(QJ['held_for_review'])} held")
chk('12b practice page states the bank is not ready',"practice bank is not ready" in text(htmls['practice_test']),'')
sim=json.load(open(f'{OUT}/simulator_settings.json'))
_qc=R['facts'].get('question_count') or {}
_qc_ok=(sim['question_count']['basis']=='official' and sim['question_count']['value']==_qc.get('value')) if source_text.published(_qc) else (sim['question_count']['basis']=='site_choice' and sim['question_count']['value'] is None)
chk('12c simulator: official time and pass mark; question count official when published, otherwise site choice',sim['time_limit_minutes']['value']==R['facts']['duration_minutes']['value'] and sim['passing_score']['value']==R['facts']['passing_score']['value'] and _qc_ok,'')
chk('12d simulator domain mix sums to 100',abs(sum(x['planned_share_pct'] for x in sim['domain_mix'])-100)<0.6,'')
# 13 media
chk('13 media: no images shipped, none referenced',not re.search(r'<img',' '.join(htmls.values())),'og:image empty by design')
# 14 single source / brand
other=[(p['kind'],j['publisher']['name']) for p in pages for j in p['jsonld'] if 'publisher' in j and j['publisher']['name']!=S['brand']]
chk('14 brand and disclaimer come from central settings',all(p['brand_source']==S['brand_source'] and S['disclaimer'] in html.unescape(htmls[p['kind']]) for p in pages) and not other,S['brand_source'])
CP=S['policy']['contact_patterns']
def contact_hits(t):
    h=[n for n,rx in CP.items() if n!='phone' and re.search(rx,t,re.I)]
    if re.search(r'(?<![\w.-])(?:\+\d{1,3}[\s-]?\d{2,4}[\s-]?\d{6,8}|\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4})(?![\w.-])',t): h.append('phone')
    return h
deny=[]
for f in scan:
    if f.endswith(('VALIDATION.md','validation.json','site.json','brand_policy.json')): continue
    t=open(f,encoding='utf8',errors='ignore').read()
    deny+=[(os.path.relpath(f,B),'term #'+str(i)) for i,d in enumerate(S['brand_denylist']) if re.search(r'\b'+re.escape(d)+r'\b',t.lower())]
    deny+=[(os.path.relpath(f,B),h) for h in contact_hits(t)]
chk('14b denylist: no seller branding, social links, emails, phone numbers, free-update lines or competitor names in outputs',not deny,deny[:10])
def orgs(o):
    if isinstance(o,dict):
        if o.get('@type')=='Organization': yield o.get('name')
        for x in o.values(): yield from orgs(x)
    elif isinstance(o,list):
        for x in o: yield from orgs(x)
on={n for p in pages for n in orgs(p['jsonld'])}
chk('14c JSON-LD organizations limited to the brand (publisher) and the exam vendor (issuer)',on<= {S['brand'],V['name']},on)
# JSON-LD rules
types={p['kind']:[j['@type'] for j in p['jsonld']] for p in pages}
chk('14d BreadcrumbList on every page',all('BreadcrumbList' in t for t in types.values()),types)
chk('14e EducationalOccupationalCredential on certification page',  'EducationalOccupationalCredential' in types['certification'],'')
chk('14f Course on study guide only (app rule: none on practice test)','Course' in types['study_guide'] and all('Course' not in t for k,t in types.items() if k!='study_guide'),'')
fq=next(p for p in pages if p['kind']=='faq'); fl=next(j for j in fq['jsonld'] if j['@type']=='FAQPage')
chk('14g FAQPage on FAQ page with sourced answers only',len(fl['mainEntity'])==len(fq['tables']['faq_sourced']) and not set(q_['name'] for q_ in fl['mainEntity'])&set(fq['tables']['faq_unsourced']),f"{len(fl['mainEntity'])} in schema, {len(fq['tables']['faq_unsourced'])} kept out")
chk('14h no Review or AggregateRating markup',not re.search(r'"(Review|AggregateRating)"',json.dumps([p['jsonld'] for p in pages])),'')
# 15 draft flags
viol=[]
for f in glob.glob(f'{imp}/*.csv'):
    for r in csv.DictReader(open(f)):
        for k,val in r.items():
            if val and (k.endswith('verified_at') or k in ('reviewed_at','published_at','checked_at','approval_date','verified_by','reviewer','approved_by','verified_on')): viol.append((os.path.basename(f),k))
            if k in ('catalog_gate','content_gate','practice_gate','commerce_gate','structural_gate','review_gate') and val not in ('','not_checked'): viol.append((f,k,val))
            if k in ('status','page_copy_status','publication_state') and val and val not in ('draft','unverified'): viol.append((f,k,val))
            if k in ('catalog_enabled','requirements_verified') and val not in ('','no'): viol.append((f,k,val))
            if k=='is_published' and val not in ('','false'): viol.append((f,k,val))
chk('15 no record marked verified, reviewed, approved, published or active',not viol and all(p['status']=='draft' for p in pages),viol[:5])
man=f'{OUT}/import/MANIFEST.json'
if os.path.exists(man):
    M=json.load(open(man)); mm=[x['path'] for x in M['files'] if not os.path.exists(x['path']) or hashlib.sha256(open(x['path'],'rb').read()).hexdigest()!=x['sha256']]
    chk('16 manifest hashes match files',not mm,mm)
# Lesson gates (from reference/lessons-learned.md)
cover_note=(open(f'{OUT}/REVIEW.md').read() if os.path.exists(f'{OUT}/REVIEW.md') else '')
sim=json.load(open(f'{OUT}/simulator_settings.json'))
# never trust owner-file cover facts for settings
if 'Cover says' in cover_note or 'cover' in cover_note.lower():
    official_dur=R['facts']['duration_minutes']['value']; official_ps=R['facts']['passing_score']['value']
    chk('17 simulator uses official duration and pass mark, not cover-page numbers',sim['time_limit_minutes']['value']==official_dur and sim['passing_score']['value']==official_ps,f"settings {sim['time_limit_minutes']['value']}/{sim['passing_score']['value']} official {official_dur}/{official_ps}")
else:
    chk('17 simulator uses official duration and pass mark, not cover-page numbers',True,'no cover conflict noted')
# skipped binary VCE / other skipped files listed when intake says so
intake=f'{OUT}/intake/files.json'
need_skip=False
if os.path.exists(intake):
    files=json.load(open(intake)).get('files') or []
    need_skip=any('vce' in str(f).lower() or str(f.get('use','')).startswith('skipped') for f in files)
chk('17b skipped VCE or binary files are listed in REVIEW.md',(not need_skip) or ('.vce' in cover_note or 'skipped' in cover_note.lower()),'')
# official vendor brand appears on pages (final brand rule)
vname=V['name']
chk('17c official vendor brand is present on every page',all(vname.lower() in text(htmls[p['kind']]) or vname.lower() in text(p['body_html']) for p in pages),vname)
# sidecar for fields the app cannot store yet
chk('17d page_meta_extras.csv sidecar exists',os.path.exists(f'{imp}/page_meta_extras.csv'),'')
# created_source points at the owner file, not generated questions
if os.path.exists(f'{OUT}/questions.json'):
    QJ=json.load(open(f'{OUT}/questions.json'))
    chk('17e imported questions cite an owner file as created_source',all('owner_file' in (q.get('created_source') or '') for q in QJ.get('questions') or []), '')
# Pearson-style official delivery partner: if official pages mention it, exam pages should not have stripped it
# (checked only when the vendor fact or a source quote names the partner)
partner=None
for f in R.get('facts',{}).values():
    if isinstance(f,dict) and 'pearson' in (str(f.get('value'))+' '+str(f.get('quote',''))).lower():
        partner='Pearson VUE'; break
if partner:
    hub=htmls.get('exam_hub') or ''
    chk('17f official delivery partner named by the vendor is kept on the exam hub',partner.lower() in text(hub),partner)
else:
    chk('17f official delivery partner named by the vendor is kept on the exam hub',True,'not named in research facts')

# Shared-section gates
import shared_sections
max_share=(S.get('raw') or {}).get('shared_max_share')
if max_share is None: max_share=0.4
shares={p['kind']:round(shared_sections.shared_share(p['body_html']),3) for p in pages}
over={k:v for k,v in shares.items() if v>float(max_share)+1e-9}
chk('18 shared blocks are at most the configured share of each page body',not over,{'max':max_share,'shares':shares,'over':over})
# banned terms and dashes in shared blocks themselves
shared_hits=[]
for b in shared_sections.iter_blocks():
    raw=(b.get('body_html') or '')+' '+(b.get('body') or '')+' '+(b.get('title') or '')
    if re.search('[\u2013\u2014]', raw):
        shared_hits.append((b.get('_rel') or b.get('key'),'dash'))
    for d in S['brand_denylist']:
        if re.search(r'\b'+re.escape(d)+r'\b', raw.lower()):
            shared_hits.append((b.get('_rel') or b.get('key'),'term '+d))
    for n,rx in (S.get('policy') or {}).get('contact_patterns',{}).items():
        if n!='phone' and rx and re.search(rx, raw, re.I):
            shared_hits.append((b.get('_rel') or b.get('key'),n))
chk('18b shared blocks have no banned terms, contact lines or typographic dashes',not shared_hits,shared_hits[:12])

# 19 optional writing gate (writing.validate_gate in pipeline.yaml)
_W=(S.get('raw') or {}).get('writing') or {}
if isinstance(_W,dict) and _W.get('validate_gate'):
    import check_writing
    _ok,_det=check_writing.gate_status(args.research)
    chk('19 writing check ran on the current files and left zero flags (second check after any fix)',_ok,_det)
fails=[r for r in res if not r[1]]
lines=[f'# VALIDATION: {code} pages pilot','',f'Run {pathutil.now_label()} by scripts/validate.py.','',f'Result: {len(res)-len(fails)} of {len(res)} checks passed, {len(fails)} failed.','',
       'These are structural checks. They do not replace human source verification in the admin, subject expert review, or the app publish gates. All records are drafts.','','| Check | Result | Detail |','|---|---|---|']
lines+= [f'| {n} | {"pass" if ok else "FAIL"} | {d.replace("|","/")} |' for n,ok,d in res]
lines+=['','## Pages','','| Page | Path | Title | Title length | Meta length | Prose grade | Words |','|---|---|---|---|---|---|---|']
lines+=[f'| {p["kind"]} | {p["meta"]["path"]} | {p["meta"]["title"]} | {len(p["meta"]["title"])} | {len(p["meta"]["meta_description"])} | {grades[p["kind"]]} | {wc[p["kind"]]} |' for p in pages]
open(f'{OUT}/VALIDATION.md','w').write('\n'.join(lines)+'\n')
json.dump([dict(check=n,passed=ok,detail=d) for n,ok,d in res],open(f'{OUT}/validation.json','w'),indent=1)
print('\n'.join(f'{"ok  " if ok else "FAIL"} {n} :: {d[:160]}' for n,ok,d in res)); sys.exit(1 if fails else 0)
