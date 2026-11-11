#!/usr/bin/env python3
"""Render a JavaScript-built official page with headless Chromium and return its HTML.

Optional dependency: pip install "certpassly-exam-pipeline[render]" then
`python -m playwright install chromium`. No AI. Used by fetch_sources.py only when a
plain fetch returns too little readable text, or when the vendor sets render: true.

CLI: render_page.py URL OUT.html   (prints the number of text characters)
"""
from __future__ import annotations
import html as _html, os, re, sys

UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36'

class RenderUnavailable(RuntimeError):
    pass

def visible_text(body: str) -> str:
    body=re.sub(r'(?is)<(script|style|noscript|template)\b.*?</\1>',' ',body or '')
    return _html.unescape(re.sub(r'\s+',' ',re.sub(r'<[^>]+>',' ',body))).strip()

def render(url: str, wait_ms: int=12000, timeout_ms: int=60000) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:  # pragma: no cover - depends on the optional extra
        raise RenderUnavailable('Playwright is not installed. Run: pip install "certpassly-exam-pipeline[render]" '
                                'and python -m playwright install chromium, or save a rendered copy by hand.') from e
    with sync_playwright() as p:
        try:
            b=p.chromium.launch()
        except Exception as e:
            raise RenderUnavailable('Chromium for Playwright is missing. Run: python -m playwright install chromium') from e
        try:
            pg=b.new_page(user_agent=UA)
            pg.goto(url, wait_until='domcontentloaded', timeout=timeout_ms)
            # Single-page apps fill in after load; poll until the text stops growing.
            last=-1; waited=0
            while waited<wait_ms:
                pg.wait_for_timeout(1500); waited+=1500
                n=len(pg.inner_text('body') or '')
                if n==last and n>500: break
                last=n
            return pg.content()
        finally:
            b.close()

if __name__=='__main__':
    out=render(sys.argv[1])
    open(sys.argv[2],'w',encoding='utf-8').write(out)
    print(len(visible_text(out)))
