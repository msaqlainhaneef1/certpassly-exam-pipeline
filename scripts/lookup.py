"""Catalog lookup tables loaded from config/exam_lookup.json and config/vendors.yaml.

This module holds no vendor or exam literals. Update the config files when a
vendor or exam is added.
"""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
import vendor_reg

def _vendors_maps():
    data=vendor_reg.vendors().get('vendors') or {}
    # sheet header (compact lowercase) -> (slug, official name, official site)
    VENDORS={}
    EXTRA_VENDORS={}
    for slug, meta in data.items():
        trip=(slug, meta.get('name') or slug, meta.get('official_site') or '')
        aliases=meta.get('sheet_aliases') or [slug]
        for a in aliases:
            key=str(a).replace(' ','').lower()
            VENDORS[key]=trip
        VENDORS[slug.replace(' ','')]=trip
    return VENDORS, EXTRA_VENDORS

def _exams():
    data=vendor_reg.exam_lookup()
    EXAMS=data.get('exams') or {}
    LABEL_FIX=data.get('label_fix') or {}
    CODE_VENDOR=data.get('code_vendor') or {}
    return EXAMS, LABEL_FIX, CODE_VENDOR

# Lazy-friendly module attributes used by build_catalog
def __getattr__(name):
    if name in ('VENDORS','EXTRA_VENDORS'):
        V,E=_vendors_maps()
        return V if name=='VENDORS' else E
    if name in ('EXAMS','LABEL_FIX','CODE_VENDOR'):
        E,L,C=_exams()
        return {'EXAMS':E,'LABEL_FIX':L,'CODE_VENDOR':C}[name]
    raise AttributeError(name)
