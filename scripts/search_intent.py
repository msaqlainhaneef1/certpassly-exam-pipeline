#!/usr/bin/env python3
"""Build the search-intent file for one exam from research facts only. No AI, no network.

    search_intent.py research/<vendor>/<CODE>.json [--force]

Writes research/<vendor>/<CODE>.search-intent.json:
  * the main query each page should answer (exam hub, objectives, study guide, FAQ,
    practice test, and the shared certification page),
  * people-also-ask style questions built from official facts in the research file
    (duration, pass mark, languages, outline, renewal and so on) and from the gaps
    the research file already records,
  * which page must answer which question,
  * topic labels from the optional competitor notes file
    (research/<vendor>/<CODE>.competitor-notes.json), as topics only, each marked with
    whether a saved official page supports it.

Rules: never invent an official number. Every expected answer token comes from a
research fact value. Never scrape a private or unofficial bank. Competitor notes are
read for topic labels only; their wording is never copied into this file.

A person may edit the file. Set "edited_by_person": true to keep the edits when the
research file changes. Otherwise the file is rebuilt when its inputs change.
"""
from __future__ import annotations
import argparse, hashlib, html, json, os, re, sys
HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths, config_load

PAGE_KINDS=('exam_hub','objectives','study_guide','faq','practice_test','vendor','certification')

# Generic templates. {code}, {exam_name}, {vendor_name} and {cert_name} come from research.
DEFAULT_MAIN_QUERIES={
    'exam_hub':'{code} exam',
    'objectives':'{code} skills measured',
    'study_guide':'{code} study guide',
    'faq':'{code} exam questions and answers',
    'practice_test':'{code} practice test',
    'certification':'{cert_name}',
}

# fact key -> question template, planned page, topic words the page must use.
DEFAULT_FACT_QUESTIONS=[
    dict(id='duration', fact='duration_minutes', question='How long is the {code} exam?', page='faq', match_any=['how long','exam length','minutes']),
    dict(id='passing_score', fact='passing_score', question='What score do I need to pass the {code} exam?', page='faq', match_any=['pass mark','passing score','to pass']),
    dict(id='languages', fact='languages', question='Which languages is the {code} exam offered in?', page='faq', match_any=['language']),
    dict(id='price', fact='price', question='How much does the {code} exam cost?', page='faq', match_any=['cost','price','fee']),
    dict(id='retake_policy', fact='retake_policy', question='Can I retake the {code} exam?', page='faq', match_any=['retake']),
    dict(id='question_count', fact='question_count', question='How many questions are on the {code} exam?', page='exam_hub', match_any=['number of questions','how many questions','question count']),
    dict(id='delivery', fact='delivery', question='How is the {code} exam delivered?', page='exam_hub', match_any=['delivery','delivered','schedule','book']),
    dict(id='prerequisites', fact='prerequisites', question='Are there prerequisites for the {code} exam?', page='exam_hub', match_any=['prerequisite']),
    dict(id='renewal', fact='validity_and_renewal', question='How do I renew the {cert_name} credential?', page='certification', match_any=['renew','renewal','expire','valid']),
]
# Unpublished facts people still ask about. Their planned answer says the vendor does not publish it.
DEFAULT_ASK_WHEN_UNPUBLISHED=['passing_score','price','question_count','validity_and_renewal']
DEFAULT_PAGE_QUESTIONS=[
    dict(id='outline', question='What skills does the {code} exam measure?', page='objectives', basis='official_outline', match_any=['skill']),
    dict(id='study_plan', question='How should I study for the {code} exam?', page='study_guide', basis='page_purpose', match_any=['study plan','study']),
    dict(id='practice_test', question='Is there a practice test for the {code} exam?', page='practice_test', basis='page_purpose', match_any=['practice']),
]
NOT_PUBLISHED_WORDS=['not published','does not publish','not listed','no single','is not stated']
STOP={'the','and','for','with','what','that','this','from','your','about','exam','does','have','will','into','when','which','their','them','they','than','then','there','these','those','page','steps','step'}


def rel(p):
    """Workspace-relative path with forward slashes (portable across OSes)."""
    try:
        r=os.path.relpath(os.path.abspath(p), paths.root())
    except ValueError:
        r=os.path.abspath(p)
    return r.replace(os.sep,'/').replace('\\','/')

def read_bytes(p):
    with open(p,'rb') as fh: return fh.read()

def read_text(p):
    with open(p,encoding='utf-8',errors='ignore') as fh: return fh.read()

def load_json(p):
    with open(p,encoding='utf-8') as fh: return json.load(fh)

def sha_file(p):
    return hashlib.sha256(read_bytes(p)).hexdigest() if p and os.path.exists(p) else None

def norm(t):
    t=html.unescape(str(t or ''))
    t=re.sub(r'[\u2010\u2011\u2013\u2014]','-',t)
    t=t.replace('\u2019',"'").replace('\u2018',"'")
    return re.sub(r'\s+',' ',t).strip().lower()

def html_text(h):
    h=re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>',' ',h or '')
    return norm(re.sub(r'<[^>]+>',' ',h))

def writing_cfg(cfg=None):
    cfg=cfg if cfg is not None else config_load.load(os.environ.get('CERTPASSLY_CONFIG'))
    w=cfg.get('writing') if isinstance(cfg, dict) else None
    return w if isinstance(w, dict) else {}

def intent_path(rpath, R):
    return os.path.join(os.path.dirname(os.path.abspath(rpath)), f'{R["exam_code"]}.search-intent.json')

def competitor_path(rpath, R):
    return os.path.join(os.path.dirname(os.path.abspath(rpath)), f'{R["exam_code"]}.competitor-notes.json')

SKIP_NUMBER_KEYS={'sha256','expected_sha256','url','final_url','path','text_path','saved_path','http'}

def research_numbers(*docs):
    """Every number in the research files (fact values, quotes, weights, dates). Hashes, URLs and paths are skipped."""
    nums=set()
    def walk(o):
        if isinstance(o, dict):
            for k,v in o.items():
                if k not in SKIP_NUMBER_KEYS: walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
        elif isinstance(o, bool) or o is None:
            return
        else:
            for m in re.findall(r'\d+(?:[.,]\d+)?', str(o)):
                nums.add(m.replace(',',''))
    for d in docs: walk(d)
    return nums

def expected_tokens(value):
    """Answer tokens a page must show for a published fact. Short values only; long sentences are checked by topic and source."""
    if isinstance(value, bool) or value in (None,'',[]):
        return []
    if isinstance(value, (int, float)):
        return [str(value)]
    if isinstance(value, str):
        return [value] if len(value)<=40 else []
    if isinstance(value, list):
        return [str(x) for x in value if isinstance(x,(str,int,float)) and len(str(x))<=40]
    return []

def official_texts(root, vendor_slug):
    """{url: visible text} of every saved official page for the vendor."""
    import fetch_sources
    out={}
    d=os.path.join(root,'sources',vendor_slug)
    if not os.path.isdir(d): return out
    for n in sorted(os.listdir(d)):
        if not n.endswith('.json'): continue
        try:
            m=fetch_sources.load_sidecar(os.path.join(d,n))
            p=m.get('text_path') if m.get('text_path') and os.path.exists(m.get('text_path')) else m.get('path')
            raw=read_text(p)
            out[m['url']]=norm(raw) if p.endswith('.txt') else html_text(raw)
        except Exception:
            continue
    return out

def load_competitor_topics(cpath):
    """Topic labels only. Accepts {"topics": [str | {"label": ...}]} or a plain list."""
    if not cpath or not os.path.exists(cpath): return []
    d=load_json(cpath)
    items=d.get('topics') if isinstance(d, dict) else d
    labels=[]
    for it in items or []:
        lab=it.get('label') or it.get('topic') if isinstance(it, dict) else it
        if isinstance(lab, str) and lab.strip(): labels.append(lab.strip())
    return labels

def _label_ok(label, cfg):
    """A topic label is a short noun phrase. Drop long text and anything with a banned brand or contact line."""
    low=label.lower()
    if len(label.split())>8: return False, 'longer than 8 words, not a topic label'
    for d in cfg.get('brand_denylist') or []:
        if re.search(r'(?<![a-z0-9])'+re.escape(str(d).lower())+r'(?![a-z0-9])', low): return False, 'names a banned brand'
    for n,rx in (cfg.get('contact_patterns') or {}).items():
        if rx and re.search(rx, label, re.I): return False, 'contains a contact line ('+n+')'
    return True, ''

def topic_support(label, texts):
    words=[w for w in re.findall(r"[a-z0-9']+", norm(label)) if len(w)>=4 and w not in STOP]
    if not words: return None
    for url,t in texts.items():
        if all(re.search(r'(?<![a-z0-9])'+re.escape(w[:max(4,len(w)-1)]), t) for w in words):
            return url
    return None

def build(rpath, cfg=None, root=None):
    root=root or paths.root()
    cfg=cfg if cfg is not None else config_load.load(os.environ.get('CERTPASSLY_CONFIG'))
    W=writing_cfg(cfg); SI=W.get('search_intent') if isinstance(W.get('search_intent'), dict) else {}
    R=load_json(rpath)
    vslug=R['vendor_slug']; cslug=R['certification_slug']
    def _opt(p):
        return load_json(p) if os.path.exists(p) else {}
    V=_opt(os.path.join(root,'research','vendors',f'{vslug}.json')); C=_opt(os.path.join(root,'research','certs',f'{cslug}.json'))
    code=R['exam_code']
    names=dict(code=code, exam_name=(R.get('exam_name') or {}).get('value') or code,
               vendor_name=V.get('name') or vslug, cert_name=C.get('name') or cslug)
    sid={s['id']:s['url'] for s in R.get('sources') or []}
    F=R.get('facts') or {}
    ask_unpub=SI.get('ask_when_unpublished') or DEFAULT_ASK_WHEN_UNPUBLISHED
    window=int(SI.get('answer_window_chars') or 400)
    questions=[]
    for t in SI.get('fact_questions') or DEFAULT_FACT_QUESTIONS:
        f=F.get(t['fact'])
        if not isinstance(f, dict): continue
        pub=f.get('value') not in (None,'',[])
        if not pub and t['fact'] not in ask_unpub: continue
        q=dict(id=t['id'], question=t['question'].format(**names), page=t['page'],
               basis='official_fact' if pub else 'gap', fact=t['fact'], published=pub,
               expected=expected_tokens(f.get('value')) if pub else [],
               source_id=f.get('source_id') if pub else None, source_url=sid.get(f.get('source_id')) if pub else None,
               match_any=list(t['match_any']), window=window)
        if not pub: q['gap_reason']=f.get('reason') or 'not published by the vendor'
        questions.append(q)
    doms=((R.get('objectives') or {}).get('domains')) or []
    for t in SI.get('page_questions') or DEFAULT_PAGE_QUESTIONS:
        q=dict(id=t['id'], question=t['question'].format(**names), page=t['page'], basis=t.get('basis','page_purpose'),
               fact=None, published=True, expected=[], source_id=None, source_url=None, match_any=list(t['match_any']), window=window)
        if t['id']=='outline':
            if not doms: continue
            osid=(R.get('objectives') or {}).get('source_id')
            q.update(fact='objectives.domains', expected=[d['name'] for d in doms], source_id=osid, source_url=sid.get(osid), window=0)
        questions.append(q)
    mq=dict(DEFAULT_MAIN_QUERIES); mq.update(SI.get('main_queries') or {})
    pages={}
    for k in PAGE_KINDS:
        qs=[q['id'] for q in questions if q['page']==k]
        if k in mq or qs:
            pages[k]=dict(main_query=mq[k].format(**names) if k in mq else None, questions=qs)
    cpath=competitor_path(rpath, R)
    topics=[]; dropped=0
    labels=load_competitor_topics(cpath)
    if labels:
        texts=official_texts(root, vslug)
        for lab in labels:
            ok,_why=_label_ok(lab, cfg)
            if not ok: dropped+=1; continue
            clean=re.sub(r'[\u2013\u2014]','-',lab)
            url=topic_support(clean, texts)
            topics.append(dict(label=clean, official_support=bool(url), source_url=url,
                               action='cover only from the official source, in our own words' if url else 'skip, or say the vendor did not publish it'))
    return dict(
        exam_code=code, vendor_slug=vslug, generated_by='scripts/search_intent.py', edited_by_person=False,
        research_file=rel(rpath), research_sha256=sha_file(rpath),
        competitor_notes_file=rel(cpath) if os.path.exists(cpath) else None, competitor_notes_sha256=sha_file(cpath),
        rules=['Built from research facts only. Expected answers are research values; no number is invented.',
               'Each page must answer the questions assigned to it. Facts need a source link on that page.',
               'Competitor topics are topics only. Never copy their wording. Cover a topic only from a saved official page.'],
        pages=pages, questions=questions, competitor_topics=topics, competitor_labels_dropped=dropped)

def check_intent(intent, R, V=None, C=None):
    """Problems with an intent file (built or edited by a person): numbers that are not in research, unknown pages."""
    probs=[]
    nums=research_numbers(R, V or {}, C or {})
    code_nums=set(re.findall(r'\d+', R.get('exam_code','')))
    for q in intent.get('questions') or []:
        for tok in list(q.get('expected') or [])+[q.get('question','')]:
            for n in re.findall(r'\d+(?:[.,]\d+)?', str(tok)):
                n=n.replace(',','')
                if n not in nums and n not in code_nums:
                    probs.append(f'{q.get("id")}: number {n} is not in the research files')
        if q.get('page') not in PAGE_KINDS:
            probs.append(f'{q.get("id")}: unknown page {q.get("page")!r}')
    return probs

def write(rpath, force=False, cfg=None):
    R=load_json(rpath)
    out=intent_path(rpath, R)
    new=build(rpath, cfg=cfg)
    if os.path.exists(out) and not force:
        try: old=load_json(out)
        except Exception: old={}
        if old.get('edited_by_person'):
            return out, old, 'kept (edited_by_person is true)'
        if old==new:
            return out, old, 'unchanged'
    with open(out,'w',encoding='utf-8',newline='\n') as fh:
        json.dump(new, fh, indent=1, ensure_ascii=False); fh.write('\n')
    return out, new, 'written'

def main(argv=None):
    ap=argparse.ArgumentParser(description='Build the search-intent file from research facts (no AI, no network).')
    ap.add_argument('research'); ap.add_argument('--force', action='store_true', help='Rebuild even if a person edited the file.')
    a=ap.parse_args(argv)
    out,intent,state=write(a.research, force=a.force)
    R=load_json(a.research)
    probs=check_intent(intent, R)
    n_t=len(intent.get('competitor_topics') or [])
    print(f'search_intent {R["exam_code"]}: {state} {rel(out)}; {len(intent["questions"])} questions on {len(intent["pages"])} pages; {n_t} competitor topics (labels only)')
    if probs:
        for p in probs: print('PROBLEM', p)
        return 1
    return 0

if __name__=='__main__':
    sys.exit(main())
