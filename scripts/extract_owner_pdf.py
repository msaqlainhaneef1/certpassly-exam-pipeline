#!/usr/bin/env python3
"""Split an owner PDF into items. Layout is detected, not assumed for one exam.

Usage: extract_owner_pdf.py <pdf> <out_dir>

Writes extracted/raw.xml, extracted/items/*.json, extracted/split.json,
extracted/cleanups.json, extracted/layout.json, extracted/unparsed.json,
and media/src/* for images. Scripted, no AI. Binary VCE files are not PDFs
and must be skipped by the intake stage, not this script.
"""
from __future__ import annotations
import html, json, os, re, shutil, subprocess, sys, hashlib
sys.path.insert(0, os.path.dirname(__file__))
import site_settings

# Numbering / start-of-item patterns, most specific first.
START_PATTERNS = [
    ('QUESTION n', re.compile(r'^QUESTION\s+(\d+)\s*$', re.I)),
    ('Question n', re.compile(r'^Question\s+(\d+)\s*$', re.I)),
    ('Question n:', re.compile(r'^Question\s+(\d+)\s*[:.)\-]\s*(.*)$', re.I)),
    ('Q n', re.compile(r'^Q(?:uestion)?\s*\.?\s*(\d+)\s*[:.)]?\s*(.*)$', re.I)),
    ('n.', re.compile(r'^(\d{1,3})\.(?:\s+(.*))?$')),
]

ANSWER_PATTERNS = [
    ('Correct Answer:', re.compile(r'^Correct Answers?:\s*(.*)$', re.I)),
    ('Answer:', re.compile(r'^(?:Answer|ANSWER)\s*[:]\s*(.*)$')),
]

AFTER_EXACT = {
    'Section: (none)', 'Explanation', 'Explanation/Reference:',
    'Explanation / Reference:', 'Reference:', 'References:',
}

OPTION_PATTERNS = [
    re.compile(r'^([A-F])\.(?:\s+(.*))?$'),
    re.compile(r'^([A-F])\)(?:\s+(.*))?$'),
    re.compile(r'^\(([A-F])\)(?:\s+(.*))?$'),
    re.compile(r'^([A-F]):(?:\s+(.*))?$'),
]


def load_elements(xml_text):
    els = []
    for pm in re.finditer(r'<page number="(\d+)"(.*?)</page>', xml_text, re.S):
        pg = int(pm.group(1))
        for m in re.finditer(r'<image top="(\d+)" left="(\d+)"[^>]*src="([^"]+)"', pm.group(2)):
            els.append(dict(k='img', page=pg, top=int(m.group(1)), left=int(m.group(2)), src=m.group(3).split('/')[-1]))
        for m in re.finditer(r'<text top="(\d+)" left="(\d+)"[^>]*>(.*?)</text>', pm.group(2), re.S):
            els.append(dict(k='txt', page=pg, top=int(m.group(1)), left=int(m.group(2)),
                            t=html.unescape(re.sub(r'<[^>]+>', '', m.group(3)))))
    els.sort(key=lambda e: (e['page'], e['top'], e['left']))
    return els


def detect_layout(els):
    texts = [e['t'].strip() for e in els if e['k'] == 'txt' and e['t'].strip()]
    counts = {}
    start_name, start_rx = 'QUESTION n', START_PATTERNS[0][1]
    best = 0
    for name, rx in START_PATTERNS:
        n = sum(1 for t in texts if rx.match(t))
        counts[name] = n
        # Prefer a named "Question" profile over bare "n." unless n. clearly dominates.
        score = n if name != 'n.' else n * 0.4
        if score > best and n >= 2:
            best, start_name, start_rx = score, name, rx
        elif n >= 1 and best == 0 and name != 'n.':
            best, start_name, start_rx = score, name, rx
    ans_name, ans_rx, ans_best = 'Correct Answer:', ANSWER_PATTERNS[0][1], 0
    for name, rx in ANSWER_PATTERNS:
        n = sum(1 for t in texts if rx.match(t))
        counts[name] = n
        if n > ans_best:
            ans_best, ans_name, ans_rx = n, name, rx
    opt_counts = {}
    for i, rx in enumerate(OPTION_PATTERNS):
        opt_counts[f'opt_{i}'] = sum(1 for t in texts if rx.match(t))
    img_pages = {e['page'] for e in els if e['k'] == 'img'}
    txt_by_page = {}
    for e in els:
        if e['k'] == 'txt' and e['t'].strip():
            txt_by_page.setdefault(e['page'], []).append(e['t'])
    image_only_pages = [p for p in sorted(img_pages) if len(' '.join(txt_by_page.get(p, [])).strip()) < 40]
    # Matrix / dropdown hints (report only; still captured as stem text)
    hints = []
    blob = '\n'.join(texts[:400])
    if re.search(r'\b(Yes|No)\b.+\b(Yes|No)\b', blob) and re.search(r'\b(statement|for each)\b', blob, re.I):
        hints.append('yes_no_matrix')
    if re.search(r'\b(drop-?down|select from)\b', blob, re.I):
        hints.append('dropdown')
    if re.search(r'\b(drag|drop|match each)\b', blob, re.I):
        hints.append('drag_or_match')
    profile = start_name.replace(' ', '_').lower() + '_' + ans_name.replace(' ', '_').replace(':', '').lower()
    if best == 0 and image_only_pages:
        profile = 'image_only_pages'
    return dict(profile=profile, start=start_name, answer=ans_name,
                start_count=counts.get(start_name, 0), answer_count=counts.get(ans_name, 0),
                option_counts=opt_counts, image_only_pages=image_only_pages,
                hints=hints, counts=counts, start_ok=best > 0)


def match_start(t, rx):
    m = rx.match(t)
    if not m:
        return None
    n = int(m.group(1))
    rest = (m.group(2) if m.lastindex and m.lastindex >= 2 else '') or ''
    return n, rest.strip()


def compile_deny(S):
    deny_parts = [re.escape(t) for t in S['brand_denylist'] if t]
    for n, rx in (S['policy'].get('contact_patterns') or {}).items():
        if rx:
            deny_parts.append(rx)
    return re.compile('|'.join(deny_parts), re.I) if deny_parts else re.compile(r'a\A')


def split_items(els, layout, deny):
    start_rx = dict(START_PATTERNS)[layout['start']]
    ans_rx = dict(ANSWER_PATTERNS)[layout['answer']]
    cleanups, items, unparsed = [], [], []
    first = None
    for i, e in enumerate(els):
        if e['k'] == 'txt' and match_start(e['t'].strip(), start_rx):
            first = i
            break
    if first is None:
        # No numbering found. Record cover text and image-only pages as unparsed.
        for e in els:
            if e['k'] == 'txt' and e['t'].strip():
                cleanups.append(dict(question_key='(cover)', field='cover', before=e['t'], after='',
                                     reason='no question numbering detected; text held as cover or unparsed'))
        for p in layout.get('image_only_pages') or []:
            imgs = [e['src'] for e in els if e['k'] == 'img' and e['page'] == p]
            unparsed.append(dict(reason='image_only_page', page=p, images=imgs,
                                 note='Page is almost only an image. Needs the visual / author stage, not a guessed stem.'))
        leftover = [e['t'] for e in els if e['k'] == 'txt' and e['t'].strip()]
        if leftover:
            unparsed.append(dict(reason='no_question_markers', sample=leftover[:12], text_lines=len(leftover)))
        return {}, cleanups, unparsed

    for e in els[:first]:
        cleanups.append(dict(question_key='(cover)', field='cover', before=e.get('t') or f'image {e.get("src")}', after='',
                             reason='cover page, branding, contact link, update offer or cover exam facts: removed with owner authorization'))
    cur = None
    used_pages = set()
    for e in els[first:]:
        if e['k'] == 'txt':
            hit = match_start(e['t'].strip(), start_rx)
            if hit:
                n, rest = hit
                cur = dict(n=n, els=[], rest=rest)
                items.append(cur)
                continue
        if cur is None:
            continue
        cur['els'].append(e)
        used_pages.add(e['page'])

    split = {}
    for it in items:
        n = it['n']
        key = f'q{n:03d}'
        state = 'stem'
        stem, opts, ans, qimg, aimg, pages = [], [], [], [], [], set()
        if it.get('rest'):
            stem.append(it['rest'])
        for e in it['els']:
            pages.add(e['page'])
            if e['k'] == 'img':
                (aimg if state in ('answer', 'after') else qimg).append(e['src'])
                continue
            t = e['t'].strip()
            if not t:
                continue
            if deny.search(t):
                cleanups.append(dict(question_key=key, field='body', before=t, after='',
                                     reason='branding or contact line removed with owner authorization'))
                continue
            am = ans_rx.match(t)
            if am:
                state = 'answer'
                if am.group(1).strip():
                    ans.append(am.group(1).strip())
                continue
            if t in AFTER_EXACT or t.lower() in {x.lower() for x in AFTER_EXACT}:
                state = 'after'
                continue
            if state == 'answer':
                ans.append(t)
                continue
            if state == 'after':
                continue
            om = None
            for rx in OPTION_PATTERNS:
                om = rx.match(t)
                if om:
                    break
            if om and (state == 'opts' or len(stem) > 0 or it.get('rest')):
                state = 'opts'
                opts.append([om.group(1).lower(), om.group(2) or ''])
                continue
            if state == 'opts':
                opts[-1][1] = (opts[-1][1] + ' ' + t).strip()
            else:
                stem.append(t)
        empty = [o for o in opts if not o[1]]
        if opts and len(empty) == len(opts):
            cleanups.append(dict(question_key=key, field='options',
                                 before=' '.join(o[0].upper() + '.' for o in opts), after='',
                                 reason='empty option letters left by the text layer; the real choices are in the answer area image'))
            opts = []
        rec = dict(question_key=key, source_number=n, marker=f"{layout['start']} {n}",
                   pages=sorted(pages), stem=' '.join(stem), options={k: v for k, v in opts},
                   answer_raw=' '.join(ans), question_images=qimg, answer_images=aimg,
                   layout_profile=layout['profile'])
        if not rec['stem'] and not rec['options'] and (qimg or aimg):
            rec['image_only'] = True
            unparsed.append(dict(reason='image_only_item', question_key=key, pages=rec['pages'],
                                 question_images=qimg, answer_images=aimg,
                                 note='Item has no usable text stem. Flag for the visual / author stage.'))
        split[key] = rec

    # Pages with images but no captured item: report them.
    all_img_pages = {e['page'] for e in els if e['k'] == 'img'}
    captured = set()
    for rec in split.values():
        captured.update(rec['pages'])
    for p in sorted(all_img_pages - captured):
        if p in (layout.get('image_only_pages') or []) or True:
            # skip if this page is clearly only a cover (before first item)
            if first is not None and any(e['page'] == p for e in els[:first]):
                continue
            imgs = [e['src'] for e in els if e['k'] == 'img' and e['page'] == p]
            txts = [e['t'] for e in els if e['k'] == 'txt' and e['page'] == p and e['t'].strip()]
            if imgs and len(' '.join(txts)) < 40:
                unparsed.append(dict(reason='image_only_page_unassigned', page=p, images=imgs, text=txts[:8]))
    return split, cleanups, unparsed


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    if len(argv) < 3:
        print('Usage: extract_owner_pdf.py <pdf> <out_dir>', file=sys.stderr)
        return 2
    pdf, out = argv[1], argv[2]
    ex = f'{out}/extracted'
    os.makedirs(f'{ex}/items', exist_ok=True)
    src = f'{out}/media/src'
    os.makedirs(src, exist_ok=True)
    subprocess.run(['pdftohtml', '-xml', '-q', '-nodrm', pdf, f'{src}/p'], check=True)
    x = open(f'{src}/p.xml', encoding='utf8').read()
    shutil.move(f'{src}/p.xml', f'{ex}/raw.xml')
    els = load_elements(x)
    layout = detect_layout(els)
    S = site_settings.load()
    deny = compile_deny(S)
    split, cleanups, unparsed = split_items(els, layout, deny)
    for rec in split.values():
        json.dump(rec, open(f"{ex}/items/{rec['question_key']}.json", 'w'), indent=1, ensure_ascii=False)
    json.dump(split, open(f'{ex}/split.json', 'w'), indent=1, ensure_ascii=False)
    json.dump(cleanups, open(f'{ex}/cleanups.json', 'w'), indent=1, ensure_ascii=False)
    json.dump(layout, open(f'{ex}/layout.json', 'w'), indent=1, ensure_ascii=False)
    json.dump(unparsed, open(f'{ex}/unparsed.json', 'w'), indent=1, ensure_ascii=False)
    print(len(split), 'items;', sum(1 for r in split.values() if r['answer_images']), 'image-keyed;',
          len(cleanups), 'cleanups;', len(unparsed), 'unparsed;', 'layout=' + layout['profile'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
