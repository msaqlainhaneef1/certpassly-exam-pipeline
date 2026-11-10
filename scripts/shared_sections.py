"""Reusable content blocks, written once and reused across exams.

Levels: site, vendor, certification, question-type.
The author stage writes a block only when it does not already exist.
Templates insert a block by key. validate.py caps how much of a page may be shared.
"""
from __future__ import annotations
import json, os, re, sys
sys.path.insert(0, os.path.dirname(__file__))
import paths

LEVELS=('site','vendor','certification','question-type')

def _roots():
    """Search workspace first, then the skill seed copies."""
    return [os.path.join(paths.root(),'shared'), os.path.join(paths.skill_root(),'shared')]

def _candidates(level, slug, key):
    paths_=[]
    for root in _roots():
        if level=='site':
            paths_.append(os.path.join(root,'site',f'{key}.json'))
        elif level=='question-type':
            paths_.append(os.path.join(root,'question-type',f'{key}.json'))
        else:
            paths_.append(os.path.join(root, level, slug or '_', f'{key}.json'))
    return paths_

def load_block(level, key, slug=None):
    for p in _candidates(level, slug, key):
        if os.path.exists(p):
            with open(p,encoding='utf-8') as fh:
                d=json.load(fh)
            d['_path']=p
            return d
    return None

def exists(level, key, slug=None):
    return load_block(level, key, slug) is not None

def render(level, key, slug=None):
    b=load_block(level, key, slug)
    if not b: return ''
    return b.get('body_html') or (f"<h2>{_esc(b.get('title') or key)}</h2><p>{_esc(b.get('body') or '')}</p>" if b.get('body') else '')

def _esc(x):
    import html
    return html.escape(str(x))

def list_missing(wanted):
    """wanted: iterable of dicts with level, key, optional slug. Returns those that do not exist yet (for the author stage)."""
    return [w for w in wanted if not exists(w['level'], w['key'], w.get('slug'))]

def insert_into(html, keys, context=None):
    """Replace {{shared:level:key}} or {{shared:level:slug:key}} markers. If html has no markers, return it unchanged."""
    context=context or {}
    def repl(m):
        parts=m.group(1).split(':')
        if len(parts)==2:
            level,key=parts; slug=context.get('vendor_slug') if level=='vendor' else context.get('certification_slug') if level=='certification' else None
        elif len(parts)==3:
            level,slug,key=parts
        else:
            return m.group(0)
        return render(level, key, slug)
    return re.sub(r'\{\{shared:([a-z0-9_:\-]+)\}\}', repl, html)

def iter_blocks():
    seen=set()
    for root in _roots():
        if not os.path.isdir(root): continue
        for dirpath,_,fs in os.walk(root):
            for f in fs:
                if f.endswith('.json'):
                    p=os.path.join(dirpath,f)
                    rel=os.path.relpath(p, root)
                    if rel in seen: continue
                    seen.add(rel)
                    try:
                        with open(p,encoding='utf-8') as fh:
                            d=json.load(fh)
                    except Exception:
                        continue
                    d['_path']=p; d['_rel']=rel
                    yield d

def word_count(html_or_text):
    t=re.sub(r'<[^>]+>',' ', html_or_text or '')
    return len(re.findall(r"[A-Za-z0-9']+", t))

def shared_share(page_html, blocks=None):
    """Fraction of page words that also appear as a 5-word shingle in a shared block."""
    blocks=list(blocks if blocks is not None else iter_blocks())
    def shingles(text, n=5):
        w=re.findall(r"[A-Za-z0-9']+", re.sub(r'<[^>]+>',' ', text or '').lower())
        return set(tuple(w[i:i+n]) for i in range(len(w)-n+1))
    page=shingles(page_html)
    if not page: return 0.0
    shared=set()
    for b in blocks:
        shared |= shingles((b.get('body_html') or '')+' '+(b.get('body') or ''))
    if not shared: return 0.0
    return len(page & shared)/len(page)
