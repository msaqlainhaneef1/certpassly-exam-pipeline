"""Heuristic official-source adapter for any vendor.

Reads saved official HTML and pulls common exam facts when a page states them
plainly. Every value comes with the source id it was read from and a verbatim
quote (a text line of that page). Missing values are listed in `gaps` with the
reason "not published by the vendor"; the batched gap pass may fill them only
from official quotes. No AI, no network.
"""
from __future__ import annotations
import glob, html, json, os, re, sys

NP_REASON='not published by the vendor'

def _clean(x):
    x=re.sub(r'(?is)<(script|style|noscript|template)\b.*?</\1>',' ',x or '')
    return html.unescape(re.sub(r'\s+',' ',re.sub(r'<[^>]+>',' ',x))).replace('\u200b','').strip()

BLOCK=r'(?i)<(?:/?(?:p|div|li|ul|ol|h[1-6]|tr|td|th|br|section|article|dt|dd|header|footer|span\s+class="[^"]*label[^"]*")\b[^>]*)>'

def _lines(raw):
    """One text line per block element (headings, paragraphs, list items, table cells)."""
    raw=re.sub(r'(?is)<(script|style|noscript|template)\b.*?</\1>',' ',raw or '')
    raw=re.sub(BLOCK,'\n',raw)
    return [l for l in (_clean(x) for x in raw.split('\n')) if l]

def _load_sources(research, workspace):
    vendor=research.get('vendor_slug') or ''
    pages=[]
    for src in research.get('sources') or []:
        meta=None
        d=os.path.join(workspace,'sources',vendor)
        if os.path.isdir(d):
            import fetch_sources
            for f in sorted(glob.glob(os.path.join(d,'*.json'))):
                try: m=fetch_sources.load_sidecar(f)
                except Exception: continue
                if m.get('url')==src.get('url'):
                    meta=m; break
        if not meta:
            continue
        path=meta.get('path') or ''
        raw=open(path, encoding='utf-8', errors='ignore').read() if path and os.path.exists(path) else ''
        pages.append(dict(id=src.get('id'), url=src.get('url'), meta=meta, html=raw, text=_clean(raw), lines=_lines(raw)))
    # The study guide / exam guide (sg) is the most specific page: read it first.
    pages.sort(key=lambda p: 0 if p['id']=='sg' else 1)
    return pages

def _num(s):
    try: return int(str(s).replace(',',''))
    except Exception: return None

def _scan(pages, patterns, check=lambda v: True, typ=_num):
    """First line (sg page first) where a pattern matches and the value passes check. Returns (value, quote, source_id)."""
    for rx in patterns:
        for p in pages:
            for line in p['lines']:
                m=re.search(rx, line, re.I)
                if not m: continue
                g=m.group(1) if m.lastindex else m.group(0)
                v=typ(g) if typ else g.strip()
                if v not in (None,'') and check(v):
                    return v, line, p['id']
    return None, None, None

def _labelled(pages, labels):
    """'Label: value' on one line, or 'Label:' followed by the value on the next line."""
    rx=re.compile(r'^(?:'+'|'.join(labels)+r')\s*:\s*(.*)$', re.I)
    for p in pages:
        L=p['lines']
        for i,line in enumerate(L):
            m=rx.match(line)
            if not m: continue
            val=m.group(1).strip()
            if val: return val, line, p['id']
            if i+1<len(L) and not rx.match(L[i+1]) and not L[i+1].endswith(':'):
                return L[i+1].strip(), L[i+1], p['id']
    return None, None, None

DOMAIN_RX=[
    re.compile(r'^([A-Z][^()]{2,100}?)\s*[:\-]?\s*\((\d+)\s*(?:-|\u2013|to)\s*(\d+)\s*%\)$'),
    re.compile(r'^([A-Z][^:]{2,100}?):\s*(\d+)\s*%$'),
]

# 'Passing score: 70%' and similar fact lines look like 'Domain: 14%'; they are never outline domains.
NOT_DOMAIN=re.compile(r'(?i)\b(pass(?:ing)?\s+(?:score|mark)|score|fee|price|discount|cut ?score|time|duration|minutes?)\b')

def _domains(pages):
    for p in pages:
        doms=[]; cur=None
        for line in p['lines']:
            hit=None
            for rx in DOMAIN_RX:
                m=rx.fullmatch(line)
                if m:
                    hit=(m.group(1).strip(' -:\t'), int(m.group(2)), int(m.group(3) if m.lastindex>=3 else m.group(2)))
                    break
            if hit and (hit[0].lower() in ('note','example','total','weight') or NOT_DOMAIN.search(hit[0])):
                hit=None
            if hit:
                if hit[0] in [d['name'] for d in doms]: cur=None; continue
                cur=dict(name=hit[0], weight_min_pct=hit[1], weight_max_pct=hit[2], line=line, tasks=[]); doms.append(cur)
                continue
            if cur is not None:
                # task lines: sentences under the domain until the next heading-like line
                if re.match(r'^[A-Z][^:]{8,240}[.]$', line) and len(cur['tasks'])<40:
                    cur['tasks'].append(line)
                elif cur['tasks']:
                    cur=None
        if doms:
            return doms, p['id']
    return [], None

def parse(research, workspace):
    pages=_load_sources(research, workspace)
    fields={}; gaps=[]; quotes={}; src={}
    def put(k, v, q, sid):
        if v in (None,'',[]):
            gaps.append(k); fields[k]=None; return
        fields[k]=v; quotes[k]=q; src[k]=sid
    # duration: labelled lines first, then any "N minutes" in a plausible range
    put('duration_minutes', *_scan(pages, [
        r'(?:time allotted|duration|time limit|exam length|length)[^0-9]{0,60}?(\d+)\s*(?:minutes?|mins?)\b',
        r'(\d+)\s*(?:minutes?|mins?)\b(?! and \d+ seconds)',
    ], check=lambda v: 15<=v<=360))
    # passing score: number or percent
    ps, q, sid=_scan(pages, [r'pass(?:ing)? (?:score|mark)\s*(?:is|:)?\s*(\d+)\s*%?', r'score of (\d+)\s+or (?:greater|higher|more)'], check=lambda v: 1<=v<=1000)
    put('passing_score', ps, q, sid)
    if ps is not None and re.search(r'pass(?:ing)? (?:score|mark)\s*(?:is|:)?\s*\d+\s*%', q or '', re.I):
        fields['passing_score_unit']='percent'
    put('question_count', *_scan(pages, [r'(\d+)\s+(?:[\w-]+\s+){0,2}questions'], check=lambda v: 10<=v<=400))
    put('price', *_scan(pages, [r'(?:registration fee|price|cost)[^0-9$]{0,40}(?:USD|US\$|\$)\s*(\d{2,4})', r'(?:USD|US\$)\s*(\d{2,4})'], check=lambda v: 10<=v<=5000))
    if fields.get('price') is not None: fields['price_currency']='USD'
    v,q,sid=_labelled(pages, [r'languages?(?: offered)?'])
    langs=[x.strip(' .') for x in re.split(r',|\band\b', v) if x.strip(' .')] if v else None
    if langs and all(re.fullmatch(r'[A-Z][A-Za-z ()]{1,40}', x) for x in langs): put('languages', langs, q, sid)
    else: put('languages', None, None, None)
    put('delivery', *_labelled(pages, [r'delivery options?', r'delivery', r'exam delivery']))
    if fields.get('delivery') is None:
        gaps.remove('delivery')
        put('delivery', *_scan(pages, [r'((?:online[- ]proctored|onsite at a testing center|test(?:ing)? cent(?:er|re)|pearson vue|webassessor|prometric|psi exams)[^.]{0,120})'], typ=None))
    pre,q,sid=_labelled(pages, [r'prerequisites?'])
    if pre and re.fullmatch(r'(?i)none\.?', pre):
        fields['prerequisites']='None'; quotes['prerequisites']=q; src['prerequisites']=sid
    else: put('prerequisites', pre, q, sid)
    # whole words only ('maintainable' is not renewal); the sentence must carry a period of time or an expiry
    put('renewal', *_scan(pages, [r'([^.]*\b(?:renew(?:al|ed|s)?|recertif\w*|maintenance)\b[^.]*\b(?:years?|annual(?:ly)?|months?|expire\w*)\b[^.!]*[.!])'], typ=None))
    put('level', *_labelled(pages, [r'level']))
    put('role', *_labelled(pages, [r'roles?']))
    put('retake_policy', *_labelled(pages, [r'retake fee', r'retake policy', r'retakes?']))
    doms, dsid=_domains(pages)
    if doms:
        fields['domains']=[dict(name=d['name'], weight_min_pct=d['weight_min_pct'], weight_max_pct=d['weight_max_pct']) for d in doms]
        fields['task_groups']=[dict(domain=d['name'], name=d['name'], tasks=d['tasks']) for d in doms]
        quotes['domains']=[d['line'] for d in doms]; src['domains']=dsid
    else:
        gaps.append('domains'); fields['domains']=None
    return dict(adapter='generic', fields=fields, quotes=quotes, sources=src, gaps=gaps,
                missing_reason=NP_REASON, pages_read=len(pages))

def parse_catalog_page(exam_code, url, body, text):
    """Best-effort official name from page title / heading. Never invent a credential title."""
    title=_clean(re.search(r'<title>([^<]*)', body).group(1) if body and '<title>' in body else '')
    h1=_clean(re.search(r'<h1[^>]*>(.*?)</h1>', body or '', re.S).group(1) if body and '<h1' in (body or '') else '')
    exam_name=''; certification=''
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
    R=json.load(open(sys.argv[1],encoding='utf-8'))
    out=parse(R, paths.root())
    json.dump(out, open(sys.argv[1].replace('.json','.parsed.json'),'w',encoding='utf-8'), indent=1, ensure_ascii=False)
    print('gaps', out['gaps'], 'fields', {k:v for k,v in out['fields'].items() if v not in (None,'')})
