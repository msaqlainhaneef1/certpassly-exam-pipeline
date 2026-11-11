"""Official-source adapter for Microsoft Learn pages.

This is the only script allowed to name this vendor. Other vendors use adapters/generic.py
or a new adapters/<slug>.py registered in config/vendors.yaml.
"""
from __future__ import annotations
import glob, html, json, os, re, sys

# Default study-guide URL pattern used only when exam_lookup lists no URL.
LEARN_GUIDE='https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/'

def _page(research, workspace, source_id):
    u=next(s['url'] for s in research['sources'] if s['id']==source_id)
    vendor=research['vendor_slug']
    import fetch_sources
    files=glob.glob(os.path.join(workspace,'sources',vendor,'*.json'))
    meta=next(fetch_sources.load_sidecar(f) for f in files if fetch_sources.load_sidecar(f).get('url')==u)
    return open(meta['path'], errors='ignore').read(), meta

def _clean(x):
    return html.unescape(re.sub(r'\s+',' ',re.sub('<[^>]+>','',x))).strip()

def cp_duration(text):
    """Exam length on a credential page: "You will have N minutes" first; never the extra-time rule
    ("you can request an additional N minutes"). Returns a match whose group(1) is N, or None."""
    return (re.search(r'(?:will have|duration|length)[^.]{0,30}?\b(\d+)\s*minutes', text, re.I)
            or re.search(r'(?<!additional )(?<!extra )(?<!more )(?<!up to )\b(\d+)\s*minutes(?! extra)', text))


def parse(research, workspace):
    """Extract skill areas, weights, tasks, passing score, extra time, duration from saved HTML."""
    out={'adapter':'microsoft','fields':{},'gaps':[],'source_sha256':{}}
    try:
        sg,sgm=_page(research, workspace, 'sg')
    except StopIteration:
        out['gaps'].append('study_guide_source_missing')
        return out
    out['source_sha256']['sg']=sgm['sha256']
    sg=re.sub(r'(?s)<script.*?</script>|<style.*?</style>','',sg)
    doms=[]; groups=[]
    for m in re.finditer(r'<h3[^>]*>([^<]*)</h3>|<h4[^>]*>([^<]*)</h4>\s*<ul>(.*?)</ul>',sg,re.S):
        if m.group(1) is not None:
            h=_clean(m.group(1)); w=re.fullmatch(r'(.+?)\s*\((\d+)\s*[\u2013\-]\s*(\d+)%\)',h)
            if w and w.group(1) not in [d['name'] for d in doms]:
                doms.append(dict(name=w.group(1),weight_min_pct=int(w.group(2)),weight_max_pct=int(w.group(3))))
        elif doms:
            groups.append(dict(domain=doms[-1]['name'],name=_clean(m.group(2)),
                               tasks=[_clean(t) for t in re.findall(r'<li[^>]*>((?:(?!<li|</li>).)*)</li>',m.group(3),re.S)]))
    out['fields']['domains']=doms
    out['fields']['task_groups']=groups
    txt=_clean(sg)
    m=re.search(r'A score of (\d+) or greater is required to pass',txt)
    out['fields']['passing_score']=int(m.group(1)) if m else None
    if not m: out['gaps'].append('passing_score')
    m=re.search(r'request an additional (\d+) minutes',txt)
    out['fields']['extra_time_language_minutes']=int(m.group(1)) if m else None
    try:
        cp,cpm=_page(research, workspace, 'cp')
        out['source_sha256']['cp']=cpm['sha256']
        ct=_clean(cp)
        m=cp_duration(ct)
        out['fields']['duration_minutes_candidate']=int(m.group(1)) if m else None
        if not m: out['gaps'].append('duration_minutes')
    except StopIteration:
        out['gaps'].append('credential_page_source_missing')
    # Compare with research when present
    if research.get('objectives') and 'domains' in research['objectives']:
        rd=[(d['name'],d['weight_min_pct'],d['weight_max_pct']) for d in research['objectives']['domains']]
        pd=[(d['name'],d['weight_min_pct'],d['weight_max_pct']) for d in doms]
        rt=[s for d in research['objectives']['domains'] for t in d['topics'] for s in t['subtopics']]
        pt=[s for g in groups for s in g['tasks']]
        agree_d=rd==pd
        agree_p=out['fields']['passing_score']==research.get('facts',{}).get('passing_score',{}).get('value')
        agree_t=[x.replace('\u2019',"'") for x in rt]==[x.replace('\u2019',"'") for x in pt]
        out['agree']=dict(domains=agree_d, passing_score=agree_p, tasks=agree_t,
                          tasks_parsed=len(pt), tasks_research=len(rt),
                          duration_candidate=out['fields'].get('duration_minutes_candidate'))
        print('domains agree:',agree_d,'| passing score agree:',agree_p,
              '| tasks parsed',len(pt),'research',len(rt),'agree (apostrophes normalized):',agree_t,
              '| duration candidate',out['fields'].get('duration_minutes_candidate'))
    parsed_path=None
    # research path may be passed via env
    return out

def parse_catalog_page(exam_code, url, body, text):
    """Read official exam name and credential title from a study guide or exam page."""
    title=re.search(r'<title>([^<]*)', body).group(1) if '<title>' in body else ''
    tm=re.search(r'Exam '+re.escape(exam_code)+r':\s*([^<|]+?)(?:\s*\||\s*-\s*Microsoft Learn|$)', title)
    cm2=re.search(r'Microsoft Certified: [^<"|\n]{3,80}?(?=\s*(?:<|"|\||certification\b|\.|,| - |$))', body)
    rec=dict(exam_name=tm.group(1).strip() if tm else '', certification=cm2.group(0).strip() if cm2 else '', empty_reason='')
    if not rec['certification']:
        rec['empty_reason']='Study guide does not name a certification in parseable text (may be a stand-alone exam or a new credential).'
    return rec

if __name__=='__main__':
    # CLI: adapters/microsoft.py research/<vendor>/<CODE>.json
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    import paths, json as _json
    rpath=sys.argv[1]
    R=_json.load(open(rpath))
    out=parse(R, paths.root())
    dest=rpath.replace('.json','.parsed.json')
    _json.dump(out, open(dest,'w'), indent=1, ensure_ascii=False)
