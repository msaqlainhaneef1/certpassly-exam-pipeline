#!/usr/bin/env python3
"""Writing check for one exam, after the pages stage (and after every flagged fix). No AI.

    check_writing.py research/<vendor>/<CODE>.json [--no-fail]

Reads the built pages (exam pages plus the shared vendor and certification pages),
the author files (page_prose.json, explanations), the research files, the
search-intent file and the optional competitor notes. Applies the writing brief
(reference/writing-brief.md):

  banned_ai_phrase       a phrase from config/banned_ai_phrases.txt (vendor quotes found
                         word for word on a saved official page are exempt)
  long_sentence          a sentence longer than writing.max_sentence_words
  typographic_dash       an em dash or en dash in authored text
  unsourced_number       a number in authored prose that is not in the research files
  thin_page              page body under writing.min_words words
  reading_grade          prose grade above writing.max_grade
  search_intent_missed   a page does not answer a question assigned to it
                         (topic words, the official answer, and a source link for a fact)
  search_intent_number   the search-intent file holds a number that is not in research
  competitor_copy        a run of writing.competitor_overlap_words words copied from the
                         competitor notes (runs that are also on a saved official page are exempt)
  unflagged_part_changed in a fix round, a part that had no flag was rewritten

Writes out/<CODE>/writing-review.json and out/<CODE>/WRITING-REVIEW.md (failed checks
only; a clean run has zero flags), out/<CODE>/writing-self-check.json (the self-check
ticks the script can make) and, when there are flags, out/<CODE>/authoring/writing_fix_request.json
listing only the flagged parts. Exit 1 when there are flags and writing.fail_on_flags is
true (the default).
"""
from __future__ import annotations
import argparse, glob, hashlib, html, json, os, re, sys
HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths, config_load, search_intent as SIM

DEFAULTS=dict(fail_on_flags=True, validate_gate=False, max_sentence_words=35, competitor_overlap_words=8,
              min_words=150, max_grade=11, answer_window_chars=400)
DASH_RX=re.compile('[\u2013\u2014]')
REVIEW_START='<!-- writing-review:start -->'
REVIEW_END='<!-- writing-review:end -->'

# ------------------------------------------------------------------ settings
def settings(cfg=None):
    cfg=cfg if cfg is not None else config_load.load(os.environ.get('CERTPASSLY_CONFIG'))
    s=dict(DEFAULTS); s.update(SIM.writing_cfg(cfg))
    return s

def load_phrase_file(p):
    out=[]
    if p and os.path.exists(p):
        for line in SIM.read_text(p).splitlines():
            t=line.strip()
            if t and not t.startswith('#'): out.append(t)
    return out

def banned_phrases(cfg=None, root=None):
    """Skill list, plus a workspace list, plus pipeline.yaml banned_phrases. Order kept, duplicates dropped."""
    cfg=cfg if cfg is not None else config_load.load(os.environ.get('CERTPASSLY_CONFIG'))
    lst=load_phrase_file(os.path.join(paths.skill_root(),'config','banned_ai_phrases.txt'))
    lst+=load_phrase_file(os.path.join(root or paths.root(),'config','banned_ai_phrases.txt'))
    lst+=[str(x) for x in cfg.get('banned_phrases') or []]
    seen=set(); out=[]
    for x in lst:
        k=norm(x)
        if k and k not in seen: seen.add(k); out.append(k)
    return out

# ------------------------------------------------------------------ text helpers
def norm(t):
    return SIM.norm(t)

def strip_tags(h):
    return re.sub(r'<[^>]+>',' ',h or '')

def visible(h):
    return norm(strip_tags(h))

def prose_of(h):
    """Text a reader sees as prose: paragraphs and list items, without tables, nav, or sources."""
    h=re.sub(r'(?is)<(table|nav|script|style)[^>]*>.*?</\1>',' ',h or '')
    parts=re.findall(r'(?is)<(?:p|li)[^>]*>(.*?)</(?:p|li)>',h)
    return html.unescape(' '.join(strip_tags(x) for x in parts)) if parts else html.unescape(strip_tags(h))

def sentences(text):
    t=re.sub(r'\s+',' ',text or '').strip()
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+(?=[A-Z0-9"\'(])',t) if s.strip()]

def words(text):
    return re.findall(r"[A-Za-z0-9][A-Za-z0-9'\u2019]*",text or '')

def phrase_rx(p):
    pre=r'(?<![a-z0-9])' if p[:1].isalnum() else ''
    post=r'(?![a-z0-9])' if p[-1:].isalnum() else ''
    return re.compile(pre+re.escape(p)+post)

def topic_rx(p):
    """Topic words match at a word start and may take a suffix (language, languages)."""
    pre=r'(?<![a-z0-9])' if p[:1].isalnum() else ''
    return re.compile(pre+re.escape(p))

QUOTE_RX=re.compile(r'(?is)<(blockquote|q)[^>]*>(.*?)</\1>|["\u201c]([^"\u201d]{3,}?)["\u201d]')

def exempt_vendor_quotes(text_or_html, official):
    """Remove quoted spans (blockquote, q, or double quotes) that are found word for word on a saved official page."""
    def repl(m):
        inner=m.group(2) if m.group(2) is not None else m.group(3)
        n=visible(inner)
        if n and any(n in t for t in official):
            return ' '
        return m.group(0)
    return QUOTE_RX.sub(repl, text_or_html or '')

def find_banned(text, phrases, official=()):
    """Banned phrases in text (HTML or plain). A vendor quote found verbatim on an official page is exempt."""
    t=visible(exempt_vendor_quotes(text, list(official)))
    return [p for p in phrases if phrase_rx(p).search(t)]

def long_sentences(text, max_words):
    return [s for s in sentences(text) if len(words(s))>max_words]

def grade(text):
    t=html.unescape(text); sents=max(1,len(re.findall(r'[.!?](\s|$)',t))); ws=re.findall(r"[A-Za-z][A-Za-z'-]*",t)
    def syl(w):
        w=w.lower(); g=re.findall(r'[aeiouy]+',w); n=len(g)-(1 if w.endswith('e') and len(g)>1 else 0); return max(1,n)
    return round(0.39*len(ws)/sents+11.8*sum(syl(w) for w in ws)/max(1,len(ws))-15.59,1)

def tokens(text):
    return re.findall(r"[a-z0-9]+(?:'[a-z]+)?", norm(strip_tags(text)))

def shingles(toks, n):
    return {tuple(toks[i:i+n]) for i in range(len(toks)-n+1)}

def competitor_strings(d):
    """All text values in a competitor-notes file (labels and notes alike)."""
    out=[]
    if isinstance(d, str): out.append(d)
    elif isinstance(d, dict):
        for v in d.values(): out+=competitor_strings(v)
    elif isinstance(d, list):
        for v in d: out+=competitor_strings(v)
    return out

def copied_runs(text, comp_shingles, n, allowed=frozenset()):
    """Copied n-word runs from the competitor notes, merged into phrases."""
    toks=tokens(text); hits=[]; i=0
    while i<=len(toks)-n:
        g=tuple(toks[i:i+n])
        if g in comp_shingles and g not in allowed:
            j=i
            while j+1<=len(toks)-n and tuple(toks[j+1:j+1+n]) in comp_shingles and tuple(toks[j+1:j+1+n]) not in allowed: j+=1
            hits.append(' '.join(toks[i:j+n])); i=j+n
        else:
            i+=1
    return hits

def numbers(text):
    return {m.replace(',','') for m in re.findall(r'(?<![A-Za-z0-9])\d+(?:[.,]\d+)?', text or '')}

def safe(s, n=160):
    """Excerpt for reports: no typographic dashes, no newlines, short."""
    s=DASH_RX.sub('[dash]', re.sub(r'\s+',' ',str(s))).strip()
    return s if len(s)<=n else s[:n-3].rstrip()+'...'

def sha(b):
    return hashlib.sha256(b if isinstance(b,bytes) else json.dumps(b,sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()

def rel(p):
    return SIM.rel(p)

# ------------------------------------------------------------------ inputs
def page_files(root, R):
    code=R['exam_code']
    fs=sorted(glob.glob(os.path.join(root,'out',code,'pages','*.json')))
    fs+=[os.path.join(root,'out','vendors',R['vendor_slug'],'vendor.json'), os.path.join(root,'out','certifications',R['certification_slug'],'certification.json')]
    return [f for f in fs if os.path.exists(f) and not f.endswith('.inputs.sha256')]

def author_files(root, R):
    a=os.path.join(root,'out',R['exam_code'],'authoring')
    return [os.path.join(a,n) for n in ('page_prose.json','explanations_text.json','explanations_visual.json','answer_research.json')]

def input_files(rpath, R, root):
    fs=[os.path.abspath(rpath)]+page_files(root,R)+author_files(root,R)
    fs+=[SIM.intent_path(rpath,R), SIM.competitor_path(rpath,R), os.path.join(paths.skill_root(),'config','banned_ai_phrases.txt'), os.path.join(root,'config','banned_ai_phrases.txt')]
    return [f for f in fs if os.path.exists(f)]

def _label(f, root):
    """Stable name for a file: workspace-relative, or skill:... for skill files. Forward slashes always."""
    for base,prefix in ((root,''),(paths.skill_root(),'skill:')):
        try:
            r=os.path.relpath(os.path.abspath(f), os.path.abspath(base))
        except ValueError:
            continue  # another drive on Windows
        if not r.startswith('..'):
            return prefix+r.replace(os.sep,'/').replace('\\','/')
    return os.path.basename(f)

def inputs_digest(rpath, R=None, root=None):
    """sha256 over the files the writing check reads. Validate compares it to prove the check is current."""
    root=root or paths.root(); R=R or SIM.load_json(rpath)
    rows=[(_label(f, root), hashlib.sha256(SIM.read_bytes(f)).hexdigest()) for f in input_files(rpath,R,root)]
    return sha(rows)

def _j(p, default):
    return SIM.load_json(p) if p and os.path.exists(p) else default

def explanation_parts(root, R):
    """{part_id: [authored strings]} for every explanation the bank will import."""
    a=os.path.join(root,'out',R['exam_code'],'authoring')
    parts={}
    def strings(o):
        if isinstance(o,str): return [o]
        if isinstance(o,list): return [s for x in o for s in strings(x)]
        return []
    for name in ('explanations_text.json','explanations_visual.json'):
        for k,e in (_j(os.path.join(a,name),{}) or {}).items():
            if isinstance(e,dict): parts.setdefault('explanation:'+k,[]).extend(strings(e.get('c'))+strings(e.get('o')))
    for k,r in (_j(os.path.join(a,'answer_research.json'),{}) or {}).items():
        e=r.get('explanation') if isinstance(r,dict) else None
        if isinstance(e,dict): parts.setdefault('explanation:'+k,[]).extend(strings(e.get('c'))+strings(e.get('o')))
    return parts

# ------------------------------------------------------------------ the check
def run(rpath, cfg=None, root=None):
    root=root or paths.root()
    cfg=cfg if cfg is not None else config_load.load(os.environ.get('CERTPASSLY_CONFIG'))
    W=settings(cfg)
    R=SIM.load_json(rpath); code=R['exam_code']
    V=_j(os.path.join(root,'research','vendors',f'{R["vendor_slug"]}.json'),{})
    C=_j(os.path.join(root,'research','certs',f'{R["certification_slug"]}.json'),{})
    phrases=banned_phrases(cfg, root)
    official=SIM.official_texts(root, R['vendor_slug'])
    off_list=list(official.values())
    pages={}
    for f in page_files(root,R):
        p=SIM.load_json(f)
        html_f=f[:-5]+'.html'
        pages[p['kind']]=dict(rec=p, html=SIM.read_text(html_f) if os.path.exists(html_f) else p.get('body_html',''))
    prose_file=os.path.join(root,'out',code,'authoring','page_prose.json')
    prose=_j(prose_file,{})
    exps=explanation_parts(root,R)
    nums=SIM.research_numbers(R,V,C)|set(re.findall(r'\d+',code))
    import shared_sections
    blocks=[]
    for b in shared_sections.iter_blocks():
        h=b.get('body_html') or ''
        if h.strip(): blocks.append(('shared:'+str(b.get('_rel') or b.get('key')).replace(os.sep,'/').replace('\\','/'), h))
    flags=[]
    def flag(check, part, where, detail, excerpt=''):
        fid=sha([check,part,where,detail])[:12]
        flags.append(dict(id=fid, check=check, part=part, where=where, detail=safe(detail,240), excerpt=safe(excerpt)))
    used_blocks={}
    checks=['banned_ai_phrase','long_sentence','typographic_dash','unsourced_number','thin_page','reading_grade']
    # pages
    for kind,pg in sorted(pages.items()):
        rec=pg['rec']; full=rec.get('body_html') or ''; part='page_prose:'+kind
        body=full
        for bpart,bh in blocks:
            if bh in body:
                body=body.replace(bh,' '); used_blocks.setdefault(bpart,bh)
        meta=rec.get('meta') or {}
        for field,txt in (('title',meta.get('title','')),('meta_description',meta.get('meta_description','')),('h1',meta.get('h1','')),('body_html',body)):
            for b in find_banned(txt, phrases, off_list):
                flag('banned_ai_phrase', part, f'{kind}.{field}', f'banned AI phrase "{b}"', b)
            if DASH_RX.search(strip_tags(txt)):
                flag('typographic_dash', part, f'{kind}.{field}', 'em dash or en dash; use a comma, a colon, a hyphen, or "to"', strip_tags(txt)[max(0,DASH_RX.search(strip_tags(txt)).start()-40):][:100])
        ptxt=prose_of(exempt_vendor_quotes(body, off_list))
        for s in long_sentences(ptxt, int(W['max_sentence_words'])):
            flag('long_sentence', part, f'{kind}.body_html', f'{len(words(s))} words; keep sentences to {W["max_sentence_words"]} words or fewer', s)
        authored=(prose.get(kind) or {}).get('body_html') if isinstance(prose.get(kind),dict) else None
        if authored:
            a_txt=prose_of(re.sub(r'\{\{shared:[^}]*\}\}',' ',exempt_vendor_quotes(authored, off_list)))
            for n in sorted(numbers(a_txt)-nums, key=lambda x:(len(x),x)):
                ctx=re.search(r'[^.]*(?<![A-Za-z0-9])'+re.escape(n)+r'(?![0-9])[^.]*', a_txt)
                flag('unsourced_number', part, f'{kind}.body_html', f'number {n} is not in the research files; use the official value or remove it', ctx.group(0) if ctx else n)
        wc=len(visible(full).split())
        if wc<int(W['min_words']):
            flag('thin_page', part, f'{kind}.body_html', f'{wc} words; the body needs {W["min_words"]} or more')
        g=grade(prose_of(full))
        if g>float(W['max_grade']):
            flag('reading_grade', part, f'{kind}.body_html', f'prose grade {g}; shorten sentences and use plainer words (gate {W["max_grade"]})')
    # shared blocks used on these pages: checked once each, fixed under shared/
    for bpart,bh in sorted(used_blocks.items()):
        for b in find_banned(bh, phrases, off_list):
            flag('banned_ai_phrase', bpart, bpart, f'banned AI phrase "{b}"', b)
        if DASH_RX.search(strip_tags(bh)):
            flag('typographic_dash', bpart, bpart, 'em dash or en dash in a shared block', strip_tags(bh))
        for s_ in long_sentences(prose_of(bh), int(W['max_sentence_words'])):
            flag('long_sentence', bpart, bpart, f'{len(words(s_))} words; keep sentences to {W["max_sentence_words"]} words or fewer', s_)
    # explanations
    for part,strs in sorted(exps.items()):
        for s in strs:
            for b in find_banned(s, phrases, off_list):
                flag('banned_ai_phrase', part, part, f'banned AI phrase "{b}"', s)
            if DASH_RX.search(s):
                flag('typographic_dash', part, part, 'em dash or en dash in an explanation', s)
            for ls in long_sentences(s, int(W['max_sentence_words'])):
                flag('long_sentence', part, part, f'{len(words(ls))} words; keep sentences to {W["max_sentence_words"]} words or fewer', ls)
    # search intent
    ipath=SIM.intent_path(rpath,R)
    intent=_j(ipath,None)
    if intent is not None:
        checks+=['search_intent_missed','search_intent_number']
        for p in SIM.check_intent(intent,R,V,C):
            flag('search_intent_number', 'search_intent', rel(ipath), p)
        npw=SIM.NOT_PUBLISHED_WORDS+[norm(cfg.get('not_published_label') or 'not published by the vendor')]
        for q in intent.get('questions') or []:
            kind=q.get('page'); pg=pages.get(kind)
            part='page_prose:'+str(kind)
            if not pg:
                flag('search_intent_missed', part, str(kind), f'question "{q.get("id")}" is planned for page {kind}, which was not built', q.get('question',''))
                continue
            why=intent_miss(q, pg['html'], npw, W)
            if why:
                flag('search_intent_missed', part, f'{kind}', f'question "{q.get("id")}" not answered: {why}', q.get('question',''))
    # competitor overlap
    cpath=SIM.competitor_path(rpath,R)
    comp=_j(cpath,None)
    if comp is not None:
        checks.append('competitor_copy')
        n=int(W['competitor_overlap_words'])
        cs=set()
        for s in competitor_strings(comp): cs|=shingles(tokens(s), n)
        allowed=set()
        for t in off_list: allowed|=shingles(tokens(t), n) & cs
        for q in quotes_in(R)+quotes_in(V)+quotes_in(C): allowed|=shingles(tokens(q), n) & cs
        targets=[]
        for kind,pg in sorted(pages.items()):
            m=pg['rec'].get('meta') or {}
            targets.append(('page_prose:'+kind, f'{kind}.html', pg['html']))
            targets.append(('page_prose:'+kind, f'{kind}.meta', ' . '.join([m.get('title',''),m.get('meta_description',''),m.get('h1','')])))
        for kind,rec in sorted(prose.items()):
            if isinstance(rec,dict): targets.append(('page_prose:'+kind, f'page_prose.{kind}', json.dumps(rec,ensure_ascii=False)))
        for part,strs in sorted(exps.items()): targets.append((part, part, ' . '.join(strs)))
        seen=set()
        for part,where,txt in targets:
            for run_ in copied_runs(txt, cs, n, frozenset(allowed)):
                key=(part,run_)
                if key in seen: continue
                seen.add(key)
                flag('competitor_copy', part, where, f'{len(run_.split())} words copied from the competitor notes; cover the topic in our own words from an official source', run_)
    # parts and the fix round
    part_hashes={('page_prose:'+k):sha(v) for k,v in prose.items() if isinstance(v,dict)}
    part_hashes.update({k:sha(v) for k,v in exps.items()})
    return dict(R=R, W=W, flags=flags, checks=checks, part_hashes=part_hashes, intent_file=rel(ipath) if intent is not None else None,
                competitor_file=rel(cpath) if comp is not None else None, pages=pages, prose=prose)

def quotes_in(d):
    out=[]
    if isinstance(d,dict):
        for k,v in d.items():
            if k=='quote' and isinstance(v,str): out.append(v)
            else: out+=quotes_in(v)
    elif isinstance(d,list):
        for v in d: out+=quotes_in(v)
    return out

def intent_miss(q, page_html, not_pub_words, W):
    """Why a page does not answer a planned question, or '' when it does."""
    text=visible(page_html)
    hits=[m.start() for w in q.get('match_any') or [] for m in topic_rx(norm(w)).finditer(text)]
    if not hits:
        return 'the page never names the topic ('+' / '.join(q.get('match_any') or [])+')'
    win=int(q.get('window') if q.get('window') is not None else W['answer_window_chars'])
    spans=[text] if win<=0 else [text[h:h+win] for h in hits]
    if q.get('published', True):
        exp=[norm(x) for x in q.get('expected') or []]
        if exp and not any(all(e in s for e in exp) for s in spans):
            return 'the official answer is missing near the topic (expected: '+', '.join(exp)+')'
        if q.get('source_url') and ('href="'+html.escape(q['source_url'])+'"') not in page_html and ('href="'+q['source_url']+'"') not in page_html:
            return 'no link to the official source '+q['source_url']
    else:
        if not any(any(w in s for w in not_pub_words) for s in spans):
            return 'the vendor does not publish this; the page must say so near the topic'
    return ''

# ------------------------------------------------------------------ outputs
def write_outputs(result, rpath, root=None):
    root=root or paths.root()
    R=result['R']; code=R['exam_code']; out=os.path.join(root,'out',code)
    os.makedirs(os.path.join(out,'authoring'), exist_ok=True)
    rv_path=os.path.join(out,'writing-review.json')
    prev=_j(rv_path,None)
    digest=inputs_digest(rpath,R,root)
    flags=result['flags']
    if prev and prev.get('inputs_sha256')==digest:
        rnd=prev.get('round',1); baseline=prev.get('baseline')
    elif prev:
        rnd=int(prev.get('round',1))+1
        baseline=dict(round=prev.get('round',1), flag_count=prev.get('flag_count',0),
                      flagged_parts=sorted({f['part'] for f in prev.get('flags') or []}), part_hashes=prev.get('part_hashes') or {})
    else:
        rnd=1; baseline=None
    if baseline and baseline.get('flag_count'):
        for part,h in sorted(result['part_hashes'].items()):
            old=(baseline.get('part_hashes') or {}).get(part)
            if old and old!=h and part not in baseline.get('flagged_parts',[]):
                fid=sha(['unflagged_part_changed',part])[:12]
                flags.append(dict(id=fid, check='unflagged_part_changed', part=part, where=part,
                                  detail='this part had no flag in round '+str(baseline.get('round'))+' but was rewritten; fix only the flagged parts', excerpt=''))
        if 'unflagged_part_changed' not in result['checks']: result['checks'].append('unflagged_part_changed')
    flags.sort(key=lambda f:(f['part'],f['check'],f['where'],f['detail']))
    resolved=sorted({f['id'] for f in (prev or {}).get('flags') or []}-{f['id'] for f in flags}) if prev and prev.get('inputs_sha256')!=digest else (prev or {}).get('resolved_since_previous_round',[])
    review=dict(exam_code=code, generated_by='scripts/check_writing.py', round=rnd, checked_on=paths.today(),
                inputs_sha256=digest, flag_count=len(flags), flags=flags, checks_run=sorted(set(result['checks'])),
                search_intent_file=result['intent_file'], competitor_notes_file=result['competitor_file'],
                resolved_since_previous_round=resolved, part_hashes=result['part_hashes'], baseline=baseline)
    _dump(rv_path, review)
    md=[f'# Writing review: {code}','',f'Round {rnd}. Checked by scripts/check_writing.py on {paths.today()}. Only failed checks are listed.','']
    if flags:
        md+=[f'{len(flags)} flags. Fix only these parts, then rerun the pages and writing stages. See authoring/writing_fix_request.json.','','| Part | Check | Where | Detail | Excerpt |','|---|---|---|---|---|']
        md+=[f'| {f["part"]} | {f["check"]} | {f["where"]} | {f["detail"].replace("|","/")} | {f["excerpt"].replace("|","/")} |' for f in flags]
    else:
        md+=['No flags.']
    _write(os.path.join(out,'WRITING-REVIEW.md'), '\n'.join(md)+'\n')
    fix=os.path.join(out,'authoring','writing_fix_request.json')
    if flags:
        parts={}
        for f in flags: parts.setdefault(f['part'],[]).append({k:f[k] for k in ('id','check','where','detail','excerpt')})
        _dump(fix, dict(exam_code=code, round=rnd, instructions=['Fix only the parts listed here. Do not rewrite parts that passed.',
            'Follow reference/writing-brief.md. Do not change stems, options or keys. Do not invent facts or numbers.',
            'Then rerun: certpassly-pipeline --stage pages --stage writing (a second check is required).'], parts=parts))
    elif os.path.exists(fix):
        os.remove(fix)
    _dump(os.path.join(out,'writing-self-check.json'), self_check(review))
    upsert_review_md(os.path.join(out,'REVIEW.md'), review)
    return review

def self_check(review):
    failed={f['check'] for f in review['flags']}
    def tick(*checks):
        ran=all(c in review['checks_run'] for c in checks)
        if not ran: return 'not_checked'
        return 'fail' if failed & set(checks) else 'pass'
    items=[
        ('Every official number and name matches the research file and a saved page quote.', tick('unsourced_number'), 'Numbers in prose are checked against research. Quotes on saved pages are validate check 02.'),
        ('Short sentences, plain words, no typographic dashes.', tick('long_sentence','typographic_dash'), ''),
        ('No phrase from the banned AI list, unless it is inside a vendor quote.', tick('banned_ai_phrase'), ''),
        ('Each page answers the search-intent questions assigned to it.', tick('search_intent_missed','search_intent_number'), ''),
        ('Competitor notes were used as topics only. No copied wording.', tick('competitor_copy') if 'competitor_copy' in review['checks_run'] else 'not_applicable', '' if 'competitor_copy' in review['checks_run'] else 'No competitor notes file for this exam.'),
        ('No invented key, no invented fact, no invented question.', 'writer', 'The writer confirms. Bank, check_bank and validate keep stems, options and keys as in the source.'),
        ('Grade and word-count gates still pass.', tick('reading_grade','thin_page'), ''),
    ]
    return dict(exam_code=review['exam_code'], round=review['round'], items=[dict(item=a, status=b, note=c) for a,b,c in items])

def review_section(review):
    lines=[REVIEW_START,'','## Writing review (scripts/check_writing.py)','']
    if review['flag_count']:
        lines+=[f'{review["flag_count"]} writing flags are still open in round {review["round"]}. They stay here until a fix passes a second check. Records stay draft.','']
        lines+=[f'* {f["part"]}: {f["check"]} at {f["where"]}. {f["detail"]}' for f in review['flags']]
    else:
        lines+=[f'No open writing flags (round {review["round"]}).']
    return '\n'.join(lines+['',REVIEW_END])+'\n'

def upsert_review_md(path, review):
    if not os.path.exists(path): return
    t=SIM.read_text(path)
    t=re.sub(re.escape(REVIEW_START)+r'.*?'+re.escape(REVIEW_END)+r'\n?','',t,flags=re.S).rstrip('\n')+'\n\n'
    _write(path, t+review_section(review))

def _write(p, s):
    with open(p,'w',encoding='utf-8',newline='\n') as fh: fh.write(s)

def _dump(p, d):
    _write(p, json.dumps(d, indent=1, ensure_ascii=False)+'\n')

def gate_status(rpath, root=None):
    """(ok, detail) for validate: the latest writing check ran on the current files and left zero flags."""
    root=root or paths.root(); R=SIM.load_json(rpath)
    p=os.path.join(root,'out',R['exam_code'],'writing-review.json')
    if not os.path.exists(p): return False, 'no writing-review.json; run the writing stage'
    rv=SIM.load_json(p)
    if rv.get('inputs_sha256')!=inputs_digest(rpath,R,root): return False, 'files changed since the last writing check; rerun the writing stage'
    if rv.get('flag_count'): return False, f'{rv["flag_count"]} open writing flags (round {rv.get("round")})'
    return True, f'round {rv.get("round")}, 0 flags'

def main(argv=None):
    ap=argparse.ArgumentParser(description='Writing check after pages (no AI). Lists only failed checks.')
    ap.add_argument('research'); ap.add_argument('--no-fail', action='store_true', help='Exit 0 even with flags (they stay in REVIEW.md).')
    a=ap.parse_args(argv)
    res=run(a.research)
    rv=write_outputs(res, a.research)
    print(f'writing {rv["exam_code"]}: round {rv["round"]}, {rv["flag_count"]} flags; out/{rv["exam_code"]}/writing-review.json')
    for f in rv['flags']: print(f'FLAG {f["check"]} {f["where"]}: {f["detail"]}')
    fail=bool(rv['flag_count']) and res['W'].get('fail_on_flags', True) and not a.no_fail
    return 1 if fail else 0

if __name__=='__main__':
    sys.exit(main())
