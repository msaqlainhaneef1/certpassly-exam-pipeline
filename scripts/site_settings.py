"""Brand, disclaimer, routes, denylist and meta rules from pipeline config.

This module never reads the app repo, PHP files, artisan or GitHub.
"""
from __future__ import annotations
import json, os, re, sys
sys.path.insert(0, os.path.dirname(__file__))
import config_load, paths

_S=None

def _routes_from_format(cfg):
    routes=cfg.get('routes') or {}
    try:
        fmt=json.load(open(os.path.join(paths.site_format_dir(cfg.get('site_format_version')),'url_routes.json')))
        for k,v in fmt.get('routes',{}).items():
            routes.setdefault(k,v)
    except SystemExit:
        raise
    except Exception:
        pass
    return routes

def load(explicit=None):
    cfg=config_load.load(explicit)
    brand=cfg.get('brand')
    disclaimer=cfg.get('disclaimer')
    if not brand or not disclaimer:
        raise SystemExit('pipeline config must set brand and disclaimer (copy config/pipeline.example.yaml).')
    meta=cfg.get('meta') or {}
    out=dict(
        base_url=cfg.get('base_url') or 'https://certpassly.com',
        base_url_note='From pipeline config.',
        routes=_routes_from_format(cfg),
        robots_draft=cfg.get('robots_draft') or 'noindex, nofollow',
        locale=cfg.get('locale') or 'en',
        brand=brand,
        disclaimer=disclaimer,
        brand_source=cfg.get('brand_source') or (cfg.get('_config_path','config')+' brand'),
        disclaimer_source=cfg.get('disclaimer_source') or (cfg.get('_config_path','config')+' disclaimer'),
        brand_denylist=list(cfg.get('brand_denylist') or []),
        banned_phrases=list(cfg.get('banned_phrases') or []),
        placeholders=list(cfg.get('placeholders') or []),
        policy={'contact_patterns': dict(cfg.get('contact_patterns') or {}),
                'policy_source': cfg.get('_config_path')},
        official_url_patterns=dict(cfg.get('official_url_patterns') or {}),
        not_published_label=cfg.get('not_published_label') or 'not published by the vendor',
        meta_title_range=(int(meta.get('title_min',50)), int(meta.get('title_max',60))),
        meta_description_range=(int(meta.get('description_min',140)), int(meta.get('description_max',160))),
        site_format_version=str(cfg.get('site_format_version') or 'v1'),
        timezone=cfg.get('timezone') or 'Asia/Karachi',
        catalog=cfg.get('catalog') or {},
        raw=cfg,
    )
    out['brand_terms']=out['brand_denylist']
    return out

def _s():
    global _S
    if _S is None: _S=load()
    return _S

def reset():
    """Clear the cached settings (used by tests)."""
    global _S
    _S=None

def _rx(term):
    cs=term.startswith('cs:'); t=term[3:] if cs else term
    pre=r'(?<![A-Za-z0-9])' if t[:1].isalnum() else ''
    post=r'(?![A-Za-z0-9])' if t[-1:].isalnum() else ''
    return re.compile(pre+re.escape(t)+post, 0 if cs else re.I)

def brand_hits(text):
    return sorted({term for term in _s()['brand_terms'] if _rx(term).search(str(text))})

def official_url_ok(url, vendor_slug, official_site=None):
    """True if url is an official vendor URL (from vendors.yaml domains, then optional pattern, then official_site host)."""
    try:
        import vendor_reg
        if vendor_reg.url_is_official(url, vendor_slug):
            return True
    except Exception:
        pass
    pats=_s()['official_url_patterns']
    pat=pats.get(vendor_slug)
    if pat and re.match(pat, url): return True
    if official_site:
        try:
            from urllib.parse import urlparse
            host=urlparse(official_site).netloc.lower()
            uh=urlparse(url).netloc.lower()
            if uh==host or uh.endswith('.'+host) or host.endswith('.'+uh): return True
            def base(h):
                parts=h.split('.')
                return '.'.join(parts[-2:]) if len(parts)>=2 else h
            if base(uh)==base(host): return True
        except Exception:
            pass
    return False
