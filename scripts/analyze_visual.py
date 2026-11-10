#!/usr/bin/env python3
"""Draft structure + key for visual items from images. Scripted (Tesseract + marker boxes). Usage: analyze_visual.py <out_dir>"""
import json, re, sys, os
sys.path.insert(0, os.path.dirname(__file__)); import vision_util as V
out = sys.argv[1]; S = json.load(open(f'{out}/extracted/split.json')); M = f'{out}/media/src'
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
res = {}
for k, r in S.items():
    if r['options'] or not r['question_images']: continue
    qimg = r['question_images'][-1]; d = dict(kind=kind_of(r['stem']), qimg=qimg, exhibits=r['question_images'][:-1], aimg=r['answer_images'], notes=[])
    L, (W, H) = V.ocr_lines(f'{M}/{qimg}'); d['ocr'] = [dict(t=l['text'], x=round(l['x'], 3), y=round(l['y'], 3), c=int(l['minconf'])) for l in L]
    boxes = []
    for a in r['answer_images']:
        b, _ = V.marker_boxes(f'{M}/{a}'); boxes += [dict(bx, img=a) for bx in b]
    d['boxes'] = [dict(x=round(b['x'], 4), y=round(b['y'], 4), w=round(b['w'], 4), h=round(b['h'], 4), img=b['img']) for b in boxes]
    if not r['answer_images']: d['notes'].append('no answer image in file'); 
    if len(r['answer_images']) > 1: d['notes'].append('several answer images; box coordinates mixed, needs review')
    if d['kind'] == 'yes_no':
        yes = [l for l in L if l['text'].strip(' .') == 'Yes']; no = [l for l in L if l['text'].strip(' .') == 'No']
        if yes and no:
            yx = (yes[0]['x'] + yes[0]['x1']) / 2; nx = (no[0]['x'] + no[0]['x1']) / 2; hy = yes[0]['y1']
            st = [l for l in L if l['y'] > hy - 0.005 and l['x1'] < yx - 0.02 and l['text'].strip() not in ('Statements', 'Statement')]
            gs = groups(st); rows = [dict(id=f'r{i+1}', text=' '.join(x['text'] for x in g), yc=(g[0]['y'] + g[-1]['y1']) / 2, minconf=min(x['minconf'] for x in g)) for i, g in enumerate(gs)]
            key = {}
            for b in boxes:
                cx, cy = b['x'] + b['w'] / 2, b['y'] + b['h'] / 2
                row = min(rows, key=lambda rr: abs(rr['yc'] - cy)) if rows else None
                if row: key.setdefault(row['id'], []).append('yes' if abs(cx - yx) < abs(cx - nx) else 'no')
            d['rows'] = [dict(id=x['id'], text=x['text'], minconf=int(x['minconf'])) for x in rows]
            d['key'] = {rid: v[0] for rid, v in key.items() if len(v) == 1}
            if len(d['key']) != len(rows) or any(len(v) != 1 for v in key.values()): d['notes'].append(f'key rows {len(d["key"])} of {len(rows)}')
        else: d['notes'].append('Yes/No headers not found by OCR')
    elif d['kind'] == 'dropdown':
        blanks = []
        for b in boxes:
            cx, cy = b['x'] + b['w'] / 2, b['y'] + b['h'] / 2
            hit = [l for l in L if l['x'] - .01 <= cx <= l['x1'] + .02 and l['y'] - .03 <= cy <= l['y1'] + .03]
            if not hit: d['notes'].append(f'box at {cx:.2f},{cy:.2f} has no text'); continue
            sel = min(hit, key=lambda l: abs((l['y'] + l['y1']) / 2 - cy))
            col = sorted([l for l in L if abs(l['x'] - sel['x']) < .02], key=lambda l: l['y'])
            # contiguous run around sel
            i = col.index(sel); lh = sel['y1'] - sel['y']; run = [sel]
            j = i - 1
            while j >= 0 and run[0]['y'] - col[j]['y1'] < 1.6 * lh: run.insert(0, col[j]); j -= 1
            j = i + 1
            while j < len(col) and col[j]['y'] - run[-1]['y1'] < 1.6 * lh: run.append(col[j]); j += 1
            blanks.append(dict(sel=sel['text'], choices=[x['text'] for x in run], top=run[0]['y'], x=run[0]['x'], minconf=int(min(x['minconf'] for x in run))))
        blanks.sort(key=lambda b: (round(b['top'], 2), b['x']))
        used = {c for b in blanks for c in b['choices']}
        other = [l for l in L if l['text'] not in used and l['text'] != 'Answer Area']
        d['blanks'] = [dict(id=f'blank{i+1}', choices=b['choices'], selected=b['sel'], minconf=b['minconf']) for i, b in enumerate(blanks)]
        d['text_lines'] = [dict(t=l['text'], x=round(l['x'], 2), y=round(l['y'], 2)) for l in other]
        d['key'] = {b['id']: b['selected'] for b in d['blanks']}
    res[k] = d
json.dump(res, open(f'{out}/extracted/visual_draft.json', 'w'), indent=1, ensure_ascii=False)
import collections; print(collections.Counter(v['kind'] for v in res.values()), sum(1 for v in res.values() if v['notes']), 'with notes')
