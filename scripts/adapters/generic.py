"""Heuristic official-source adapter for any vendor.

Reads saved official HTML (and the text of a saved PDF when present) and pulls
common exam facts when the page states them plainly. Missing values are left
empty with the reason "not published by the vendor" and listed in gaps for the
batched author stage to fill only from official quotes.
"""
from __future__ import annotations
import glob, html, json, os, re, sys

NP_REASON='not published by the vendor'

def _clean(x):
    x=re.sub(r'(?is)<(script|style)\b.*?</\1>',' ',x or '')
    return html.unescape(re.sub(r'\s+',' ',re.sub(r'<[^>]+>',' ',x))).strip()

def _lines(raw):
    """One text line per block element (headings, paragraphs, list items, table cells)."""
    raw=re.sub(r'(?is)<(script|style)\b.*?</\1>',' ',raw or '')
    raw=re.sub(r'(?i)<(?:/?(?:p|div|li|ul|ol|h[1-6]|tr|td|th|br|section|article|dt|dd)\b[^>]*)>','\n',raw)
    return [l for l in (_clean(x) for x in raw.split('\n')) if l]

def _load_sources(research, workspace):
    vendor=research.get('vendor_slug') or ''
    pages=[]
    for src in research.get('sources') or []:
        meta=None
        d=os.path.join(workspace,'sources',vendor)
        if os.path.isdir(d):
            for f in glob.glob(os.path.join(d,'*.json')):
                m=json.load(open(f))
                if m.get('url')==src.get('url'):
                    meta=m; break
        if not meta:
            continue
        path=meta.get('path') or ''
        raw=open(path, errors='ignore').read() if path and os.path.exists(path) else ''
        pages.append(dict(id=src.get('id'), url=src.get('url'), meta=meta, html=raw, text=_clean(raw), lines=_lines(raw)))
    return pages

def _first(patterns, text, typ=str):
    for rx in patterns:
        m=re.search(rx, text, re.I)
        if m:
            g=m.group(1) if m.lastindex else m.group(0)
            try:
                return typ(g.replace(',','')), m.group(0)
            except Exception:
                return g, m.group(0)
    return None, None

def parse(research, workspace):
    pages=_load_sources(research, workspace)
    blob=' '.join(p['text'] for p in pages)
    fields={}; gaps=[]; quotes={}
    # duration
    dur,q=_first([
        r'(\d+)\s*(?:minutes?|mins?)\b',
        r'duration[:\s]+(\d+)',
        r'time\s*limit[:\s]+(\d+)',
    ], blob, int)
    if dur and 15<=dur<=360:
        fields['duration_minutes']=dur; quotes['duration_minutes']=q
    else:
        gaps.append('duration_minutes')
    # passing score
    ps,q=_first([
        r'pass(?:ing)? score[:\s]+(\d+)',
        r'score of (\d+)\s+or (?:greater|higher|more)',
        r'(\d+)\s*(?:/|out of)\s*(1000|100|800|900)\s*to pass',
    ], blob, int)
    if ps:
        fields['passing_score']=ps; quotes['passing_score']=q
    else:
        gaps.append('passing_score')
    # question count (only if stated as a single number, not a range invented later)
    qc,q=_first([
        r'(\d+)\s+questions',
        r'number of questions[:\s]+(\d+)',
    ], blob, int)
    if qc and 10<=qc<=400:
        fields['question_count']=qc; quotes['question_count']=q
    else:
        gaps.append('question_count')
    # price
    price,q=_first([
        r'(?:USD|US\$|\$)\s*(\d{2,4})',
        r'price[:\s]+(?:USD|US\$|\$)?\s*(\d{2,4})',
    ], blob, int)
    if price:
        fields['price']=price; quotes['price']=q
    else:
        gaps.append('price')
    # languages
    langs=None
    m=re.search(r'[Ll]anguages?(?: offered)?[:\s]+([A-Z][A-Za-z ,/()]+)', blob)
    if m:
        langs=[x.strip() for x in re.split(r',| and ', m.group(1)) if x.strip()]
        fields['languages']=langs; quotes['languages']=m.group(0)
    else:
        gaps.append('languages')
    # delivery
    deliv,q=_first([
        r'(online proctored|in[-\s]?person|test center|testing centre|pearson vue|webassessor|psi|prometric)',
    ], blob, str)
    if deliv:
        fields['delivery']=deliv; quotes['delivery']=q
    else:
        gaps.append('delivery')
    # prerequisites
    if re.search(r'\bno (?:formal )?prerequisites?\b', blob, re.I):
        fields['prerequisites']=None
        quotes['prerequisites']='no formal prerequisite stated'
        # not a gap: officially none
    elif re.search(r'prerequisites?', blob, re.I):
        m=re.search(r'prerequisites?[:\s]+(.{20,200})', blob, re.I)
        if m:
            fields['prerequisites']=m.group(1).strip(); quotes['prerequisites']=m.group(0)
        else:
            gaps.append('prerequisites')
    else:
        gaps.append('prerequisites')
    # renewal
    if re.search(r'renew|valid for|expir|recertif', blob, re.I):
        m=re.search(r'((?:renew|valid for|expires?|recertif)[^.!?]{0,200})', blob, re.I)
        if m:
            fields['renewal']=m.group(1).strip(); quotes['renewal']=m.group(0)
        else:
            gaps.append('renewal')
    else:
        gaps.append('renewal')
    # domains / weights: "Name (20-25%)" or "Name 20%"
    doms=[]
    all_lines=[l for p in pages for l in p['lines']]
    for line in all_lines:
        m=re.fullmatch(r'([A-Z][^()]{2,100}?)\s*[:\-]?\s*\((\d+)\s*(?:-|\u2013|to)\s*(\d+)\s*%\)', line)
        if not m: continue
        name=m.group(1).strip(' -:\t')
        if name.lower() in ('note','example','total','weight'): continue
        if name not in [d['name'] for d in doms]:
            doms.append(dict(name=name, weight_min_pct=int(m.group(2)), weight_max_pct=int(m.group(3))))
    for m in (re.finditer(r'([A-Z][^()\n]{3,80}?)\s*\((\d+)\s*[\u2013\-–to]+\s*(\d+)\s*%\)', blob) if not doms else []):
        name=m.group(1).strip(' -:\t')
        if name.lower() in ('note','example','total','weight'): continue
        if name not in [d['name'] for d in doms]:
            doms.append(dict(name=name, weight_min_pct=int(m.group(2)), weight_max_pct=int(m.group(3))))
    if not doms:
        for line in all_lines:
            m=re.fullmatch(r'([A-Z][^:]{3,80}?):\s*(\d+)\s*%', line)
            if not m: continue
            name=m.group(1).strip()
            if name not in [d['name'] for d in doms]:
                doms.append(dict(name=name, weight_min_pct=int(m.group(2)), weight_max_pct=int(m.group(2))))
    if doms:
        fields['domains']=doms
    else:
        gaps.append('domains')
    for g in gaps:
        fields.setdefault(g, None)
    return dict(adapter='generic', fields=fields, quotes=quotes, gaps=gaps,
                missing_reason=NP_REASON, pages_read=len(pages))

def parse_catalog_page(exam_code, url, body, text):
    """Best-effort official name from page title / heading. Never invent a credential title."""
    title=_clean(re.search(r'<title>([^<]*)', body).group(1) if body and '<title>' in body else '')
    h1=_clean(re.search(r'<h1[^>]*>(.*?)</h1>', body or '', re.S).group(1) if body and '<h1' in (body or '') else '')
    exam_name=''; certification=''
    # If the exam code appears next to a title clause, use that clause
    blob=title or h1 or text or ''
    m=re.search(re.escape(exam_code)+r'\s*[:\-]\s*([^|<\n]{3,80})', blob, re.I)
    if m: exam_name=m.group(1).strip()
    elif h1 and exam_code.lower() in (h1.lower()+' '+title.lower()):
        exam_name=re.sub(r'\s*[|\-].*$','',h1).strip()
    return dict(exam_name=exam_name, certification=certification, empty_reason='' if exam_name else
                'Page resolves but the expected name was not found in page text; left empty.')

if __name__=='__main__':
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    import paths
    R=json.load(open(sys.argv[1]))
    out=parse(R, paths.root())
    json.dump(out, open(sys.argv[1].replace('.json','.parsed.json'),'w'), indent=1, ensure_ascii=False)
    print('gaps', out['gaps'], 'fields', {k:v for k,v in out['fields'].items() if v not in (None,'')})
