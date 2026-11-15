#!/usr/bin/env python3
"""Pull text out of PDF images with local Tesseract OCR. No AI.

Usage: ocr_extract.py <out_dir> [<pdf>]

Reads extracted/split.json and media/src images. When an item has no usable
text layer, OCR text is written into the stem, choices, tables or matrix rows.
Answer marks (highlighted or checked boxes) are detected with pixel rules.
Low-confidence or uncertain items are flagged. Settings come from config/ocr.json.
"""
from __future__ import annotations
import json, os, re, shutil, subprocess, sys
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))
import paths
import vision_util as V
import analyze_visual as AV

OPTION_RX = re.compile(r'^([A-Ha-h])[\.\)\:]\s+(.*)$')
SKIP_OCR_LINES = re.compile(r'^(answer area|statements?|statement|correct answer:?|section:.*|explanation.*|hotspot|drag drop)$', re.I)


def load_cfg():
    return V.load_ocr_config()


def tool(name):
    return shutil.which(name)


def run(cmd, timeout=120):
    return subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout)


def extra_images_from_pdf(pdf, dest, prefix='pdfimages'):
    """Extract embedded images that pdftohtml may have missed."""
    if not pdf or not os.path.isfile(pdf) or not tool('pdfimages'):
        return []
    os.makedirs(dest, exist_ok=True)
    before = set(os.listdir(dest))
    run(['pdfimages', '-png', pdf, os.path.join(dest, prefix)])
    after = [n for n in os.listdir(dest) if n not in before and n.lower().endswith(('.png', '.jpg', '.jpeg', '.ppm'))]
    return sorted(after)


def raster_page(pdf, dest, page, dpi, prefix='page'):
    """Rasterize one 1-based PDF page with pdftoppm. Returns the written filename or None."""
    if not pdf or not os.path.isfile(pdf) or not tool('pdftoppm'):
        return None
    os.makedirs(dest, exist_ok=True)
    out_base = os.path.join(dest, '%s-%s' % (prefix, page))
    run(['pdftoppm', '-png', '-r', str(int(dpi)), '-f', str(page), '-l', str(page), '-singlefile', pdf, out_base])
    for ext in ('.png', '.ppm', '.jpg'):
        p = out_base + ext
        if os.path.isfile(p):
            return os.path.basename(p)
    return None


def ocr_image(media, fname, cfg, role):
    path = os.path.join(media, fname)
    rec = dict(file=fname, role=role, lines=[], mean_confidence=None, min_confidence=None, word_count=0, notes=[])
    if not os.path.isfile(path):
        rec['notes'].append('image file missing')
        return rec
    lines, size, mean = V.ocr_lines_configured(path, cfg)
    rec['size'] = list(size)
    rec['lines'] = [dict(t=l['text'], x=round(l['x'], 3), y=round(l['y'], 3),
                         x1=round(l['x1'], 3), y1=round(l['y1'], 3), c=int(l['minconf']))
                    for l in lines]
    rec['mean_confidence'] = None if mean is None else round(float(mean), 1)
    if lines:
        rec['min_confidence'] = round(min(float(l['minconf']) for l in lines), 1)
        rec['word_count'] = sum(len(l.get('words') or l['text'].split()) for l in lines)
    return rec, lines


def parse_options_from_lines(lines):
    opts = {}
    for l in lines:
        m = OPTION_RX.match((l.get('text') or l.get('t') or '').strip())
        if m:
            opts[m.group(1).lower()] = m.group(2).strip()
    return opts


def stem_from_lines(lines, existing_stem=''):
    parts = []
    for l in lines:
        t = (l.get('text') or l.get('t') or '').strip()
        if not t or SKIP_OCR_LINES.match(t):
            continue
        if OPTION_RX.match(t):
            continue
        if t.strip(' .') in ('Yes', 'No'):
            continue
        parts.append(t)
    text = ' '.join(parts).strip()
    if existing_stem and text:
        # do not replace a usable text-layer stem
        return existing_stem
    return text or existing_stem


def table_from_lines(lines, min_cols=2):
    """Group OCR lines that share a y-band into table rows when columns line up.

    Returns a list of rows (each a list of cell strings), or None when the
    layout is not a reliable table.
    """
    if len(lines) < min_cols:
        return None
    # x-clusters of line starts
    xs = sorted(l['x'] if 'x' in l else l.get('x', 0) for l in lines)
    if not xs:
        return None
    cols = []
    for x in xs:
        if not cols or x - cols[-1][-1] > 0.06:
            cols.append([x])
        else:
            cols[-1].append(x)
    if len(cols) < min_cols:
        return None
    centers = [sum(c) / len(c) for c in cols]
    # y-groups
    ordered = sorted(lines, key=lambda l: (l.get('y') or 0, l.get('x') or 0))
    rows = []
    for l in ordered:
        t = (l.get('text') or l.get('t') or '').strip()
        if not t:
            continue
        y = l.get('y') or 0
        if rows and abs(y - rows[-1]['y']) < 0.025:
            rows[-1]['cells'].append(l)
        else:
            rows.append(dict(y=y, cells=[l]))
    if len(rows) < 2:
        return None
    table = []
    for r in rows:
        buckets = ['' for _ in centers]
        for cell in r['cells']:
            x = cell.get('x') or 0
            i = min(range(len(centers)), key=lambda k: abs(centers[k] - x))
            buckets[i] = (buckets[i] + ' ' + (cell.get('text') or cell.get('t') or '')).strip()
        table.append(buckets)
    # drop a table that is really just a stem (one non-empty column)
    if all(sum(1 for c in row if c) <= 1 for row in table):
        return None
    return table


def collect_marks(media, fnames, cfg):
    marks = []
    uncertain = False
    for fn in fnames:
        path = os.path.join(media, fn)
        if not os.path.isfile(path):
            continue
        boxes, _ = V.marker_boxes(path, dark=int((cfg.get('marker') or {}).get('dark') or 70))
        for b in boxes:
            marks.append(dict(kind='marker_box', img=fn, x=round(b['x'], 4), y=round(b['y'], 4),
                              w=round(b['w'], 4), h=round(b['h'], 4)))
        for h in V.highlight_marks(path, cfg):
            h = dict(h)
            h['img'] = fn
            h['x'] = round(h['x'], 4); h['y'] = round(h['y'], 4)
            h['w'] = round(h['w'], 4); h['h'] = round(h['h'], 4)
            marks.append(h)
        for c in V.checked_boxes(path, cfg):
            c = dict(c)
            c['img'] = fn
            c['x'] = round(c['x'], 4); c['y'] = round(c['y'], 4)
            c['w'] = round(c['w'], 4); c['h'] = round(c['h'], 4)
            marks.append(c)
    return marks, uncertain


def process_item(rec, media, pdf, cfg, tess_ok):
    qimg = list(rec.get('question_images') or [])
    aimg = list(rec.get('answer_images') or [])
    notes = []
    images = []
    all_q_lines = []
    confs = []
    if not tess_ok:
        if qimg or aimg or rec.get('image_only') or not (rec.get('stem') or rec.get('options')):
            return dict(question_key=rec['question_key'], images=[], confidence=None,
                        min_confidence=None, marks=[], notes=['tesseract is not installed'],
                        missing_tesseract=True, stem_filled_from_ocr=False,
                        options_filled_from_ocr=False, table=None), rec
        return dict(question_key=rec['question_key'], images=[], confidence=None,
                    min_confidence=None, marks=[], notes=[], missing_tesseract=False,
                    stem_filled_from_ocr=False, options_filled_from_ocr=False, table=None), rec

    # raster a page when the item has no images but also no usable text
    if not qimg and pdf and (rec.get('image_only') or not (rec.get('stem') or rec.get('options'))):
        if cfg.get('rasterize_pages_when_no_images', True):
            for p in rec.get('pages') or []:
                fn = raster_page(pdf, media, p, cfg.get('dpi') or 200, prefix='raster-%s' % rec['question_key'])
                if fn:
                    qimg.append(fn)
                    notes.append('rasterized page %s with pdftoppm' % p)

    for fn in qimg:
        rec_img, lines = ocr_image(media, fn, cfg, 'question')
        images.append(rec_img)
        all_q_lines.extend(lines)
        if rec_img['mean_confidence'] is not None:
            confs.append(rec_img['mean_confidence'])
        if rec_img.get('notes'):
            notes.extend(rec_img['notes'])
    for fn in aimg:
        rec_img, lines = ocr_image(media, fn, cfg, 'answer')
        images.append(rec_img)
        if rec_img['mean_confidence'] is not None:
            confs.append(rec_img['mean_confidence'])

    mean = round(sum(confs) / len(confs), 1) if confs else None
    minc = None
    mins = [im['min_confidence'] for im in images if im.get('min_confidence') is not None]
    if mins:
        minc = min(mins)

    stem_filled = False
    options_filled = False
    table = None
    if all_q_lines:
        if not (rec.get('stem') or '').strip() or rec.get('image_only'):
            filled = stem_from_lines(all_q_lines, rec.get('stem') or '')
            if filled:
                rec['stem'] = filled
                rec.pop('image_only', None)
                stem_filled = True
        if not rec.get('options'):
            opts = parse_options_from_lines(all_q_lines)
            if opts:
                rec['options'] = opts
                options_filled = True
        table = table_from_lines(all_q_lines)
        if table:
            rec['ocr_table'] = table

    marks, uncertain = collect_marks(media, aimg or qimg, cfg)
    if rec.get('question_images') != qimg and qimg:
        rec['question_images'] = qimg

    item_ocr = dict(question_key=rec['question_key'], images=images, confidence=mean,
                    min_confidence=minc, marks=marks, notes=notes, missing_tesseract=False,
                    stem_filled_from_ocr=stem_filled, options_filled_from_ocr=options_filled,
                    table=table, uncertain_marks=uncertain)
    rec['ocr_confidence'] = mean
    rec['ocr_min_confidence'] = minc
    return item_ocr, rec


def find_pdf(out, explicit=None):
    if explicit and os.path.isfile(explicit):
        return explicit
    intake = os.path.join(out, 'intake', 'files.json')
    if os.path.isfile(intake):
        files = json.load(open(intake)).get('files') or []
        for f in files:
            p = f.get('path') or ''
            if (f.get('use') == 'extracted' or str(f.get('name', '')).lower().endswith('.pdf')) and os.path.isfile(p):
                return p
    return None


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    if len(argv) < 2:
        print('Usage: ocr_extract.py <out_dir> [<pdf>]', file=sys.stderr)
        return 2
    out = argv[1]
    pdf = find_pdf(out, argv[2] if len(argv) > 2 else None)
    split_path = os.path.join(out, 'extracted', 'split.json')
    if not os.path.isfile(split_path):
        print('ocr_extract: missing extracted/split.json', file=sys.stderr)
        return 2
    media = os.path.join(out, 'media', 'src')
    os.makedirs(media, exist_ok=True)
    cfg = load_cfg()
    tess, tess_note = V.ensure_tesseract()
    tess_ok = bool(tess)
    split = json.load(open(split_path, encoding='utf-8'))

    if pdf:
        extra = extra_images_from_pdf(pdf, media)
    else:
        extra = []

    report = dict(tesseract=tess or '', tesseract_note=tess_note, extra_images=extra, items={})
    for key, rec in split.items():
        item_ocr, rec = process_item(rec, media, pdf, cfg, tess_ok)
        report['items'][key] = item_ocr
        split[key] = rec

    json.dump(split, open(split_path, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    for rec in split.values():
        item_path = os.path.join(out, 'extracted', 'items', rec['question_key'] + '.json')
        if os.path.isdir(os.path.dirname(item_path)):
            json.dump(rec, open(item_path, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)

    # Reuse the existing visual structure pass (matrix rows, dropdown blanks).
    AV.run(out, split=split)

    visual_path = os.path.join(out, 'extracted', 'visual_draft.json')
    visual = {}
    if os.path.isfile(visual_path):
        visual = json.load(open(visual_path, encoding='utf-8'))
    # attach OCR confidence onto visual rows already stored there
    for key, vis in visual.items():
        o = report['items'].get(key) or {}
        vis['ocr_confidence'] = o.get('confidence')
        vis['ocr_min_confidence'] = o.get('min_confidence')
        if o.get('marks') and not vis.get('marks'):
            vis['marks'] = o['marks']
    json.dump(visual, open(visual_path, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)

    report_path = os.path.join(out, 'extracted', 'ocr.json')
    json.dump(report, open(report_path, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)

    n = len(report['items'])
    filled = sum(1 for v in report['items'].values() if v.get('stem_filled_from_ocr') or v.get('options_filled_from_ocr'))
    with_ocr = sum(1 for v in report['items'].values() if v.get('confidence') is not None)
    print('ocr: tesseract=%s items=%s with_text=%s filled=%s visual=%s extra_images=%s%s' % (
        tess or 'MISSING', n, with_ocr, filled, len(visual), len(extra),
        ('; ' + tess_note) if tess_note else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
