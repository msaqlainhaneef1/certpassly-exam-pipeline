"""Load the vendor registry and exam lookup from config (never hardcode vendor names)."""
from __future__ import annotations
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import config_load, paths

_V=None
_E=None

def _find(name, also_example=True):
    cands=[os.path.join(paths.root(),'config',name)]
    if also_example:
        cands += [
            os.path.join(paths.skill_root(),'config',name),
            os.path.join(paths.skill_root(),'config',name.replace('.yaml','.example.yaml')),
        ]
        if name.endswith('.yaml'):
            cands.append(os.path.join(paths.skill_root(),'config',name.replace('.yaml','.example.yaml')))
    for p in cands:
        if os.path.exists(p): return p
    return None

def vendors():
    global _V
    if _V is not None: return _V
    path=_find('vendors.yaml') or _find('vendors.example.yaml')
    if not path:
        raise SystemExit('No vendors.yaml found. Copy config/vendors.example.yaml to the workspace config/ folder.')
    data=config_load._parse_simple_yaml(open(path,encoding='utf-8').read()) if path.endswith(('.yaml','.yml')) else json.load(open(path))
    _V=data
    _V['_path']=path
    return _V

def vendor(slug):
    v=vendors().get('vendors') or {}
    if slug not in v:
        raise SystemExit(f'Unknown vendor slug {slug!r}. Add it to {vendors().get("_path","vendors.yaml")}.')
    return v[slug]

def all_slugs(catalog_only=False):
    v=vendors().get('vendors') or {}
    if catalog_only:
        return [s for s,m in v.items() if m.get('in_catalog',True)]
    return list(v)

def official_domains(slug):
    meta=vendor(slug)
    return list(meta.get('official_domains') or [])

def url_is_official(url, slug):
    from urllib.parse import urlparse
    try:
        host=(urlparse(url).netloc or '').lower()
    except Exception:
        return False
    for d in official_domains(slug):
        d=d.lower()
        if host==d or host.endswith('.'+d) or d.endswith('.'+host):
            return True
    return False

def harmless_url_hosts():
    return list(vendors().get('harmless_url_hosts') or [])

def retired_official_hosts():
    return list(vendors().get('retired_official_hosts') or [])

def exam_lookup():
    global _E
    if _E is not None: return _E
    path=_find('exam_lookup.json', also_example=True)
    if not path:
        raise SystemExit('Missing config/exam_lookup.json')
    _E=json.load(open(path,encoding='utf-8'))
    return _E

def reset():
    global _V,_E
    _V=_E=None
