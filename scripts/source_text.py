#!/usr/bin/env python3
"""Compare official-page wording to research facts. No AI. Used by validate.py."""
from __future__ import annotations
import html, re

def norm(t):
    t=html.unescape(t or '')
    t=re.sub(r'[\u2013\u2014\u2010\u2011\-]','-',t)
    t=t.replace('\u2019',"'").replace('\u2018',"'")
    return re.sub(r'\s+',' ',t).strip().lower()

def weight_phrases(name, domain):
    """Forms vendors use on official outlines: ranges, a single percent, or a label colon."""
    n=norm(name)
    mn=domain['weight_min_pct']; mx=domain['weight_max_pct']
    phrases=[
        f"{n} ({mn}-{mx}%)",
        f"{n} ({mn}% to {mx}%)",
        f"{n}: {mn}% to {mx}%",
        f"{n}: {mn}-{mx}%",
    ]
    if mn==mx:
        phrases.extend([
            f"{n}: {mn}%",
            f"{n} ({mn}%)",
            f"{n} {mn}%",
        ])
    return phrases

def weight_on_page(name, domain, page_text):
    page=norm(page_text) if page_text and page_text!=norm(page_text) else (page_text or '')
    # Callers usually pass already-normalised page text; also accept raw HTML.
    raw=norm(page_text)
    return any(p in page or p in raw for p in weight_phrases(name, domain))

def published(fact):
    if not isinstance(fact, dict):
        return False
    return fact.get('value') not in (None,'',[])
