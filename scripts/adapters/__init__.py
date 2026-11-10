"""Vendor official-source adapters. Chosen from config, never by exam code."""
from __future__ import annotations
import importlib, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import vendor_reg

def load(slug):
    """Return the adapter module for a vendor slug."""
    meta=vendor_reg.vendor(slug)
    name=(meta.get('adapter') or 'generic').strip()
    # Only load a module that lives in this package (no dynamic path tricks).
    allowed={'generic','microsoft'}
    if name not in allowed:
        name='generic'
    return importlib.import_module(f'adapters.{name}')

def parse_official(research: dict, workspace: str):
    """Parse saved official pages for this exam. Returns a dict with fields + gaps."""
    slug=research['vendor_slug']
    mod=load(slug)
    return mod.parse(research, workspace)

def parse_catalog_page(vendor_slug, exam_code, url, body, text):
    """Extract exam name / credential title from a fetched official catalog page, if possible."""
    try:
        mod=load(vendor_slug)
    except SystemExit:
        from . import generic as mod
    fn=getattr(mod, 'parse_catalog_page', None)
    if fn:
        return fn(exam_code, url, body, text)
    from . import generic as g
    return g.parse_catalog_page(exam_code, url, body, text)
