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


# ----- config-driven OCR and pixel mark helpers (no AI) -----

import json as _json

_OCR_CFG = None


def ocr_config_path():
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(here), 'config', 'ocr.json')


def load_ocr_config(path=None):
    global _OCR_CFG
    p = path or ocr_config_path()
    if _OCR_CFG is not None and path is None:
        return _OCR_CFG
    try:
        with open(p, encoding='utf-8') as fh:
            data = _json.load(fh)
    except FileNotFoundError:
        data = {}
    if path is None:
        _OCR_CFG = data
    return data


def tesseract_bin():
    import shutil
    return shutil.which('tesseract')


def ensure_tesseract():
    """Return the tesseract path, trying apt (then reporting) if it is missing.

    Never fails hard: callers hold visual items when the binary is still absent.
    """
    import os, shutil, subprocess
    found = shutil.which('tesseract')
    if found:
        return found, None
    apt = shutil.which('apt-get')
    if apt and os.geteuid() == 0:
        pkgs = (load_ocr_config().get('install') or {}).get('apt_packages') or ['tesseract-ocr', 'tesseract-ocr-eng']
        r = subprocess.run([apt, 'install', '-y'] + list(pkgs), capture_output=True, text=True)
        found = shutil.which('tesseract')
        if found:
            return found, 'installed via apt-get'
        return None, 'apt-get install failed: ' + (r.stderr or r.stdout or '')[:400]
    return None, 'tesseract is not on PATH; install tesseract-ocr (apt) or add it to PATH'


def mean_confidence(lines):
    if not lines:
        return None
    vals = []
    for l in lines:
        c = l.get('minconf', l.get('confidence', l.get('c')))
        if c is not None:
            try:
                vals.append(float(c))
            except (TypeError, ValueError):
                pass
    if not vals:
        return None
    return sum(vals) / len(vals)


def ocr_lines_configured(path, cfg=None):
    """OCR one image using settings from config/ocr.json."""
    cfg = cfg or load_ocr_config()
    scale = float(cfg.get('scale') or 2)
    psm = str(cfg.get('psm') or 3)
    lang = cfg.get('lang') or 'eng'
    timeout = int(cfg.get('tesseract_timeout_seconds') or 60)
    g = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if g is None:
        return [], (0, 0), None
    H, W = g.shape
    big = cv2.resize(g, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    tmp = path + '.ocr.png'
    cv2.imwrite(tmp, big)
    import os, shutil
    if not shutil.which('tesseract'):
        os.remove(tmp)
        return [], (W, H), None
    cmd = ['tesseract', tmp, '-', '-l', lang, '--psm', psm, 'tsv']
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout)
    os.remove(tmp)
    rows = list(csv.DictReader(io.StringIO(r.stdout), delimiter='\t', quoting=csv.QUOTE_NONE))
    min_word = float(cfg.get('min_word_confidence') or 0)
    lines = {}
    word_confs = []
    for w in rows:
        if w.get('level') != '5' or not (w.get('text') or '').strip():
            continue
        try:
            conf = float(w['conf'])
        except (TypeError, ValueError, KeyError):
            continue
        if conf < 0:
            continue
        word_confs.append(conf)
        if min_word and conf < min_word:
            # keep the word for layout, but it still counts toward confidence
            pass
        k = (w['block_num'], w['par_num'], w['line_num'])
        x, y, ww, hh = [int(w[c]) / scale for c in ('left', 'top', 'width', 'height')]
        L = lines.setdefault(k, dict(words=[], conf=[]))
        L['words'].append(dict(t=w['text'], x=x, y=y, w=ww, h=hh, conf=conf))
    out = []
    for L in lines.values():
        ws = sorted(L['words'], key=lambda z: z['x'])
        if not ws:
            continue
        seg = [ws[0]]
        for a in ws[1:]:
            if a['x'] - (seg[-1]['x'] + seg[-1]['w']) > 40:
                out.append(seg)
                seg = [a]
            else:
                seg.append(a)
        out.append(seg)
    res = []
    for seg in out:
        x0 = min(z['x'] for z in seg)
        y0 = min(z['y'] for z in seg)
        x1 = max(z['x'] + z['w'] for z in seg)
        y1 = max(z['y'] + z['h'] for z in seg)
        res.append(dict(text=' '.join(z['t'] for z in seg), x=x0 / W, y=y0 / H,
                        x1=x1 / W, y1=y1 / H, minconf=min(z['conf'] for z in seg), words=seg))
    res = sorted(res, key=lambda l: (round(l['y'], 3), l['x']))
    mean = (sum(word_confs) / len(word_confs)) if word_confs else None
    return res, (W, H), mean


def highlight_marks(path, cfg=None):
    """Find highlighted (yellow/green/cyan) regions with simple HSV rules."""
    cfg = (cfg or load_ocr_config()).get('highlight') or {}
    if cfg.get('enabled') is False:
        return []
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        return []
    H, W = img.shape[:2]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    min_area = int(cfg.get('min_area_px') or 80)
    max_ratio = float(cfg.get('max_area_ratio') or 0.25)
    out = []
    for rng in cfg.get('hsv_ranges') or []:
        lo = np.array([int(rng.get('h_min', 0)), int(rng.get('s_min', 0)), int(rng.get('v_min', 0))], dtype=np.uint8)
        hi = np.array([int(rng.get('h_max', 179)), int(rng.get('s_max', 255)), int(rng.get('v_max', 255))], dtype=np.uint8)
        mask = cv2.inRange(hsv, lo, hi)
        n, lab, st, _ = cv2.connectedComponentsWithStats((mask > 0).astype(np.uint8), 8)
        for i in range(1, n):
            x, y, w, h, a = st[i]
            if a < min_area or a > max_ratio * W * H:
                continue
            out.append(dict(kind='highlight', color=rng.get('name') or 'highlight',
                            x=x / W, y=y / H, w=w / W, h=h / H,
                            px=[int(x), int(y), int(w), int(h)], area=int(a)))
    # dedupe overlaps
    ded = []
    for m in sorted(out, key=lambda z: -z['area']):
        cx, cy = m['x'] + m['w'] / 2, m['y'] + m['h'] / 2
        if any(abs(cx - (d['x'] + d['w'] / 2)) < 0.02 and abs(cy - (d['y'] + d['h'] / 2)) < 0.02 for d in ded):
            continue
        ded.append(m)
    return ded


def checked_boxes(path, cfg=None):
    """Find small square boxes whose interior is filled enough to be a check mark."""
    cfg = (cfg or load_ocr_config()).get('checkbox') or {}
    if cfg.get('enabled') is False:
        return []
    g = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if g is None:
        return []
    H, W = g.shape
    min_s = int(cfg.get('min_side_px') or 8)
    max_s = int(cfg.get('max_side_px') or 40)
    fill_min = float(cfg.get('fill_min') or 0.15)
    fill_max = float(cfg.get('fill_max') or 0.85)
    border_dark = int(cfg.get('border_dark') or 140)
    e = (g < border_dark).astype(np.uint8)
    cs, _ = cv2.findContours(e, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in cs:
        x, y, w, h = cv2.boundingRect(c)
        if w < min_s or h < min_s or w > max_s or h > max_s:
            continue
        if abs(w - h) > 0.4 * max(w, h):
            continue
        # border should be darker than the immediate outside; interior fill from ink
        pad = 1
        xi, yi, wi, hi = x + pad, y + pad, max(1, w - 2 * pad), max(1, h - 2 * pad)
        interior = e[yi:yi + hi, xi:xi + wi]
        if interior.size == 0:
            continue
        fill = float(interior.mean())
        if fill_min <= fill <= fill_max:
            out.append(dict(kind='checked_box', x=x / W, y=y / H, w=w / W, h=h / H,
                            px=[int(x), int(y), int(w), int(h)], fill=round(fill, 3)))
    ded = []
    for m in out:
        if not any(abs(m['x'] - d['x']) < 0.01 and abs(m['y'] - d['y']) < 0.01 for d in ded):
            ded.append(m)
    return ded
