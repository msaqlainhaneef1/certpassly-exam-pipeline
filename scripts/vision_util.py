"""Scripted image helpers: answer-marker box detection and Tesseract OCR lines. No AI."""
import cv2, numpy as np, subprocess, csv, io
def marker_boxes(path, dark=70):
    g = cv2.imread(path, cv2.IMREAD_GRAYSCALE); H, W = g.shape
    m = (g < dark).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
    out = []
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if w < 14 or h < 12 or w > 0.95 * W: continue
        sub = (lab[y:y+h, x:x+w] == i)
        fill = sub.mean(); cy0, cy1, cx0, cx1 = int(h*.3), int(h*.7)+1, int(w*.3), int(w*.7)+1
        core = sub[cy0:cy1, cx0:cx1].mean()
        rows_hit = sub.any(axis=1).mean(); cols_hit = sub.any(axis=0).mean()
        if 0.12 < fill < 0.8 and core < 0.08 and rows_hit > .9 and cols_hit > .9 and sub[:, :max(2,w//8)].any(axis=1).mean() > .7 and sub[:, -max(2,w//8):].any(axis=1).mean() > .7:
            out.append(dict(x=x / W, y=y / H, w=w / W, h=h / H, px=[int(x), int(y), int(w), int(h)]))
    return out, (W, H)
def ocr_lines(path, scale=2):
    g = cv2.imread(path, cv2.IMREAD_GRAYSCALE); H, W = g.shape
    big = cv2.resize(g, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    tmp = path + '.ocr.png'; cv2.imwrite(tmp, big)
    import os, shutil
    if not shutil.which('tesseract'):
        os.remove(tmp)
        return [], (W, H)  # Tesseract missing: no OCR draft; the author stage transcribes the image
    r = subprocess.run(['tesseract', tmp, '-', '--psm', '3', 'tsv'], capture_output=True, text=True, encoding='utf-8', errors='replace')
    os.remove(tmp)
    rows = list(csv.DictReader(io.StringIO(r.stdout), delimiter='\t', quoting=csv.QUOTE_NONE))
    lines = {}
    for w in rows:
        if w['level'] != '5' or not w['text'].strip(): continue
        k = (w['block_num'], w['par_num'], w['line_num'])
        x, y, ww, hh = [int(w[c]) / scale for c in ('left', 'top', 'width', 'height')]
        L = lines.setdefault(k, dict(words=[], conf=[]))
        L['words'].append(dict(t=w['text'], x=x, y=y, w=ww, h=hh, conf=float(w['conf'])))
    out = []
    for L in lines.values():
        ws = sorted(L['words'], key=lambda z: z['x'])
        # split a tesseract line where a big horizontal gap exists (separate columns)
        seg = [ws[0]]
        for a in ws[1:]:
            if a['x'] - (seg[-1]['x'] + seg[-1]['w']) > 40: out.append(seg); seg = [a]
            else: seg.append(a)
        out.append(seg)
    res = []
    for seg in out:
        x0 = min(z['x'] for z in seg); y0 = min(z['y'] for z in seg); x1 = max(z['x'] + z['w'] for z in seg); y1 = max(z['y'] + z['h'] for z in seg)
        res.append(dict(text=' '.join(z['t'] for z in seg), x=x0 / W, y=y0 / H, x1=x1 / W, y1=y1 / H, minconf=min(z['conf'] for z in seg), words=seg))
    return sorted(res, key=lambda l: (round(l['y'], 3), l['x'])), (W, H)
def rects(path, min_w=60, min_h=30):
    """Light grey bordered rectangles (dropdown lists)."""
    g = cv2.imread(path, cv2.IMREAD_GRAYSCALE); H, W = g.shape
    e = (g < 200).astype(np.uint8)
    cs, _ = cv2.findContours(e, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in cs:
        x, y, w, h = cv2.boundingRect(c)
        if w < min_w or h < min_h or w > 0.9 * W: continue
        per = cv2.arcLength(c, True); 
        if abs(per - 2 * (w + h)) / (2 * (w + h)) > 0.15: continue
        out.append((x / W, y / H, w / W, h / H))
    # dedupe nested near-identical
    ded = []
    for r in sorted(out, key=lambda r: -r[2] * r[3]):
        if not any(abs(r[0]-d[0]) < .01 and abs(r[1]-d[1]) < .02 and abs(r[2]-d[2]) < .02 and abs(r[3]-d[3]) < .03 for d in ded): ded.append(r)
    return ded


def boxes(path, min_w=20, min_h=18, dark=200, edge=0.75):
    """Bordered boxes drawn around clickable areas (hotspot / active-screen answer areas).

    Keeps a contour's bounding rectangle when each of its four edges is mostly dark
    (so open or anti-aliased borders still count, unlike rects()). Normalized (x, y, w, h).
    """
    g = cv2.imread(path, cv2.IMREAD_GRAYSCALE); H, W = g.shape
    e = (g < dark).astype(np.uint8)
    cs, _ = cv2.findContours(e, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in cs:
        x, y, w, h = cv2.boundingRect(c)
        if w < min_w or h < min_h or w > 0.9 * W or h > 0.9 * H: continue
        def sides(m):
            return [m[y:y+2, x:x+w].max(axis=0).mean(), m[y+h-2:y+h, x:x+w].max(axis=0).mean(),
                    m[y:y+h, x:x+2].max(axis=1).mean(), m[y:y+h, x+w-2:x+w].max(axis=1).mean()]
        s1 = sides(e)
        if min(s1) < edge:
            # one faint (anti-aliased) border: accept when the other three are dark and the faint one shows at a lighter threshold
            if sorted(s1)[1] < edge or min(sides((g < 235).astype(np.uint8))) < edge: continue
        out.append((x / W, y / H, w / W, h / H))
    ded = []
    for r in sorted(out, key=lambda r: -r[2] * r[3]):
        if not any(abs(r[0]-d[0]) < .01 and abs(r[1]-d[1]) < .02 and abs(r[2]-d[2]) < .02 and abs(r[3]-d[3]) < .03 for d in ded): ded.append(r)
    return ded
