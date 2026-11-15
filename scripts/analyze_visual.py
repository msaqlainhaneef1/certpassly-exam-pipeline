#!/usr/bin/env python3
"""Draft structure + key for visual items from images. Scripted (Tesseract + marker boxes). Usage: analyze_visual.py <out_dir>"""
import json, re, sys, os
sys.path.insert(0, os.path.dirname(__file__)); import vision_util as V

def kind_of(stem):
    s = stem.lower()
    if 'select yes if the statement is true' in s: return 'yes_no'
    if 'completes the sentence' in s or 'drop-down' in s or 'answer area' in s: return 'dropdown'
    return 'unknown'

def groups(lines):
    gs = []
    for l in sorted(lines, key=lambda l: l['y']):
        lh = l['y1'] - l['y']
        if gs and l['y'] - gs[-1][-1]['y1'] < 0.6 * lh: gs[-1].append(l)
        else: gs.append([l])
    return gs


def _collect_method_marks(media, images, cfg):
    """Marks grouped by pixel method: marker_box, highlight, checked_box."""
    methods = {'marker_box': [], 'highlight': [], 'checked_box': []}
    for a in images or []:
        ap = os.path.join(media, a)
        if not os.path.isfile(ap):
            continue
        boxes = V.marker_boxes(ap)
        if isinstance(boxes, tuple):
            boxes = boxes[0]
        for b in boxes or []:
            rec = dict(b); rec['img'] = a
            methods['marker_box'].append(rec)
        for h in V.highlight_marks(ap, cfg):
            rec = dict(h); rec['img'] = a
            methods['highlight'].append(rec)
        for c in V.checked_boxes(ap, cfg):
            rec = dict(c); rec['img'] = a
            methods['checked_box'].append(rec)
    return methods


def key_yes_no(L, boxes):
    yes = [l for l in L if l['text'].strip(' .') == 'Yes']; no = [l for l in L if l['text'].strip(' .') == 'No']
    if not (yes and no):
        return {}, [], 'Yes/No headers not found by OCR'
    yx = (yes[0]['x'] + yes[0]['x1']) / 2; nx = (no[0]['x'] + no[0]['x1']) / 2; hy = yes[0]['y1']
    st = [l for l in L if l['y'] > hy - 0.005 and l['x1'] < yx - 0.02 and l['text'].strip() not in ('Statements', 'Statement')]
    gs = groups(st); rows = [dict(id=f'r{i+1}', text=' '.join(x['text'] for x in g), yc=(g[0]['y'] + g[-1]['y1']) / 2, minconf=min(x['minconf'] for x in g)) for i, g in enumerate(gs)]
    key = {}
    for b in boxes:
        cx, cy = b['x'] + b['w'] / 2, b['y'] + b['h'] / 2
        row = min(rows, key=lambda rr: abs(rr['yc'] - cy)) if rows else None
        if row: key.setdefault(row['id'], []).append('yes' if abs(cx - yx) < abs(cx - nx) else 'no')
    row_out = [dict(id=x['id'], text=x['text'], minconf=int(x['minconf'])) for x in rows]
    final = {rid: v[0] for rid, v in key.items() if len(v) == 1}
    note = None
    if len(final) != len(rows) or any(len(v) != 1 for v in key.values()):
        note = f'key rows {len(final)} of {len(rows)}'
    return final, row_out, note


def key_dropdown(L, boxes):
    blanks = []
    notes = []
    for b in boxes:
        cx, cy = b['x'] + b['w'] / 2, b['y'] + b['h'] / 2
        hit = [l for l in L if l['x'] - .01 <= cx <= l['x1'] + .02 and l['y'] - .03 <= cy <= l['y1'] + .03]
        if not hit:
            notes.append(f'box at {cx:.2f},{cy:.2f} has no text')
            continue
        sel = min(hit, key=lambda l: abs((l['y'] + l['y1']) / 2 - cy))
        col = sorted([l for l in L if abs(l['x'] - sel['x']) < .02], key=lambda l: l['y'])
        i = col.index(sel); lh = sel['y1'] - sel['y']; run = [sel]
        j = i - 1
        while j >= 0 and run[0]['y'] - col[j]['y1'] < 1.6 * lh: run.insert(0, col[j]); j -= 1
        j = i + 1
        while j < len(col) and col[j]['y'] - run[-1]['y1'] < 1.6 * lh: run.append(col[j]); j += 1
        blanks.append(dict(sel=sel['text'], choices=[x['text'] for x in run], top=run[0]['y'], x=run[0]['x'], minconf=int(min(x['minconf'] for x in run))))
    blanks.sort(key=lambda b: (round(b['top'], 2), b['x']))
    used = {c for b in blanks for c in b['choices']}
    other = [l for l in L if l['text'] not in used and l['text'] != 'Answer Area']
    blank_out = [dict(id=f'blank{i+1}', choices=b['choices'], selected=b['sel'], minconf=b['minconf']) for i, b in enumerate(blanks)]
    key = {b['id']: b['selected'] for b in blank_out}
    return key, blank_out, other, notes


def run(out, split=None):
    if split is None:
        split = json.load(open(f'{out}/extracted/split.json'))
    M = f'{out}/media/src'
    cfg = V.load_ocr_config()
    res = {}
    for k, r in split.items():
        if r.get('options') or not r.get('question_images'): continue
        qimg = r['question_images'][-1]; d = dict(kind=kind_of(r.get('stem') or ''), qimg=qimg, exhibits=r['question_images'][:-1], aimg=r.get('answer_images') or [], notes=[])
        img_path = f'{M}/{qimg}'
        if not os.path.isfile(img_path):
            d['notes'].append('question image missing')
            d['ocr'] = []
            res[k] = d
            continue
        L, (W, H) = V.ocr_lines(img_path); d['ocr'] = [dict(t=l['text'], x=round(l['x'], 3), y=round(l['y'], 3), c=int(l['minconf'])) for l in L]
        if L:
            d['ocr_confidence'] = round(sum(float(l['minconf']) for l in L) / len(L), 1)
            d['ocr_min_confidence'] = round(min(float(l['minconf']) for l in L), 1)
        else:
            d['ocr_confidence'] = None
            d['ocr_min_confidence'] = None
        methods = _collect_method_marks(M, r.get('answer_images') or [], cfg)
        boxes = methods['marker_box']
        d['boxes'] = [dict(x=round(b['x'], 4), y=round(b['y'], 4), w=round(b['w'], 4), h=round(b['h'], 4), img=b['img']) for b in boxes]
        if not r.get('answer_images'): d['notes'].append('no answer image in file');
        if len(r.get('answer_images') or []) > 1: d['notes'].append('several answer images; box coordinates mixed, needs review')
        d['key_by_method'] = {}
        if d['kind'] == 'yes_no':
            key, rows, note = key_yes_no(L, boxes)
            if rows:
                d['rows'] = rows
                d['key'] = key
            if note:
                d['notes'].append(note)
            for name, marks in methods.items():
                k2, _, n2 = key_yes_no(L, marks)
                if k2:
                    d['key_by_method'][name] = k2
        elif d['kind'] == 'dropdown':
            key, blanks, other, notes = key_dropdown(L, boxes)
            d['blanks'] = blanks
            d['text_lines'] = [dict(t=l['text'], x=round(l['x'], 2), y=round(l['y'], 2)) for l in other]
            d['key'] = key
            d['notes'].extend(notes)
            for name, marks in methods.items():
                k2, _, _, _ = key_dropdown(L, marks)
                if k2:
                    d['key_by_method'][name] = k2
        res[k] = d
    os.makedirs(f'{out}/extracted', exist_ok=True)
    json.dump(res, open(f'{out}/extracted/visual_draft.json', 'w'), indent=1, ensure_ascii=False)
    import collections
    print(collections.Counter(v['kind'] for v in res.values()), sum(1 for v in res.values() if v['notes']), 'with notes')
    return res

def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    if len(argv) < 2:
        print('Usage: analyze_visual.py <out_dir>', file=sys.stderr)
        return 2
    run(argv[1])
    return 0

if __name__ == '__main__':
    sys.exit(main())
