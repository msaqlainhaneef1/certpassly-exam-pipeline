#!/usr/bin/env python3
"""Package guard: keep raw extracts out of the zip, and scan the finished zip against the denylist.

Owner rule: seller branding, contact lines, free-update lines and any config denylist term must never ship.
1. prepare(): drops raw extracts from the staging copy (config package_exclude globs, plus any file under
   extracted/ that still holds a removed seller line). The workspace copies stay for audit. A redacted
   cleanups log (counts, reasons, sha256 and lengths, no removed text) and PACKAGE-EXCLUDED.json ship instead.
2. scan_zip(): opens every member (nested zip/xlsx/docx too), decodes text, XML and JSON, and matches the
   config denylist (brand_denylist + contact_patterns except phone). Images are counted, not decoded.
Reports name the rule ("denylist term #3"), never the term. Only the console line names the term.
Usage: package_guard.py scan ZIP [--report PATH]
"""
from __future__ import annotations
import fnmatch, hashlib, io, json, os, re, sys, zipfile
sys.path.insert(0, os.path.dirname(__file__))

DEFAULT_EXCLUDE = ['extracted/raw.xml', 'extracted/*.txt', 'extracted/cleanups.json', 'extracted/unparsed.json',
                   'extracted/visual_draft.json', 'media/src/*']
IMAGE_EXT = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tif', '.tiff', '.ico')
IMAGE_MAGIC = (b'\xff\xd8\xff', b'\x89PNG', b'GIF8', b'RIFF', b'BM', b'II*\x00', b'MM\x00*')
NESTED_EXT = ('.zip', '.xlsx', '.docx', '.pptx', '.odt', '.ods')


def rules(S):
    """[(label, term_for_console, compiled)] from site settings (brand_denylist + contact patterns but phone)."""
    out = []
    for i, d in enumerate(S.get('brand_denylist') or []):
        if d:
            out.append((f'denylist term #{i}', d, re.compile(r'(?<![a-z0-9])' + re.escape(d.lower()) + r'(?![a-z0-9])')))
    for n, rx in ((S.get('policy') or {}).get('contact_patterns') or {}).items():
        if n != 'phone' and rx:
            out.append((f'contact pattern {n}', n, re.compile(rx, re.I)))
    return out


def _variants(text):
    """Lower-cased text plus a camelCase-split copy, so a glued brand ("AcmeCoTech") still matches."""
    split = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', text)
    split = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', split)
    return (text.lower(), split.lower())


_GLUED = re.compile(r'[A-Za-z0-9]*[a-z0-9][A-Z][A-Za-z0-9]*')


def text_hits(text, R):
    vs = _variants(text)
    glued = {t.lower() for t in _GLUED.findall(text)}  # camelCase tokens such as a brand glued to another word
    out = []
    for label, term, rx in R:
        if any(rx.search(v) for v in vs) or (label.startswith('denylist') and any(g.startswith(term.lower()) or g.endswith(term.lower()) for g in glued)):
            out.append((label, term))
    return out


def _removed_lines(cleanups, R):
    """Removed lines (after == '') that match a denylist rule: these must never ship anywhere."""
    return [c['before'] for c in cleanups if not c.get('after') and c.get('before') and text_hits(c['before'], R)]


def redact_cleanups(cleanups, R):
    from collections import Counter
    ents = []
    for c in cleanups:
        b = c.get('before') or ''; a = c.get('after') or ''
        e = dict(question_key=c.get('question_key'), field=c.get('field'), reason=c.get('reason'),
                 change='removed' if not a else 'repaired', before_chars=len(b), before_sha256=hashlib.sha256(b.encode()).hexdigest()[:16])
        if a and not text_hits(b, R) and not text_hits(a, R):
            e.update(before=b, after=a)
        ents.append(e)
    return dict(note='Redacted cleanup log: removed text is never shipped. The full log stays in the workspace (extracted/cleanups.json) for audit.',
                counts_by_reason=dict(Counter(c.get('reason') for c in cleanups).most_common()),
                counts_by_change=dict(Counter(e['change'] for e in ents)), entries=ents)


def prepare(exam_dir, S, cfg=None, log=print):
    """Remove raw extracts from a staged exam folder. Returns the excluded list (relative paths)."""
    R = rules(S); globs = list((cfg or {}).get('package_exclude') or DEFAULT_EXCLUDE)
    cpath = os.path.join(exam_dir, 'extracted', 'cleanups.json')
    cleanups = json.load(open(cpath, encoding='utf-8')) if os.path.exists(cpath) else []
    removed = _removed_lines(cleanups, R)
    excluded = []
    for dp, _, fs in os.walk(exam_dir):
        for f in fs:
            p = os.path.join(dp, f); rel = os.path.relpath(p, exam_dir).replace(os.sep, '/')
            why = next((f'raw extract (package_exclude {g})' for g in globs if fnmatch.fnmatch(rel, g)), None)
            if not why and rel.startswith('extracted/') and removed and not f.lower().endswith(IMAGE_EXT):
                t = open(p, encoding='utf-8', errors='ignore').read()
                if any(x in t for x in removed): why = 'raw extract: holds a removed seller line'
            if why:
                excluded.append(dict(path=rel, bytes=os.path.getsize(p), sha256=hashlib.sha256(open(p, 'rb').read()).hexdigest(), reason=why))
                os.remove(p)
    for dp, ds, fs in sorted(os.walk(exam_dir), key=lambda x: -len(x[0])):
        if dp != exam_dir and not os.listdir(dp):
            os.rmdir(dp)
    if cleanups:
        os.makedirs(os.path.join(exam_dir, 'extracted'), exist_ok=True)
        json.dump(redact_cleanups(cleanups, R), open(os.path.join(exam_dir, 'extracted', 'cleanups.redacted.json'), 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    json.dump(dict(note='Files kept in the workspace for audit and left out of this package. No file text is listed.', files=excluded),
              open(os.path.join(exam_dir, 'PACKAGE-EXCLUDED.json'), 'w', encoding='utf-8'), indent=1)
    log(f'package: excluded {len(excluded)} raw extract files (kept in the workspace); redacted cleanups log shipped')
    return excluded


def _is_image(name, data):
    return name.lower().endswith(IMAGE_EXT) or data[:4].startswith(IMAGE_MAGIC)


def scan_zip(zip_path, S, _z=None, _prefix='', _acc=None):
    """Scan every member. Returns dict(files_scanned, images_skipped, nested, members, hits=[(file, label, term)])."""
    acc = _acc or dict(files_scanned=0, images_skipped=0, nested=0, members=0, hits=[])
    R = rules(S)
    z = _z or zipfile.ZipFile(zip_path)
    for info in z.infolist():
        if info.is_dir():
            continue
        acc['members'] += 1
        name = _prefix + info.filename; data = z.read(info)
        if info.filename.lower().endswith(NESTED_EXT) and zipfile.is_zipfile(io.BytesIO(data)):
            acc['nested'] += 1
            scan_zip(None, S, zipfile.ZipFile(io.BytesIO(data)), name + '!/', acc)
            continue
        if _is_image(info.filename, data):
            acc['images_skipped'] += 1
            continue
        acc['files_scanned'] += 1
        text = data.decode('utf-8', errors='ignore')
        if '\x00' in text[:2000]:
            text = data.decode('utf_16', errors='ignore') + ' ' + data.decode('latin-1')
        for label, term in text_hits(text, R):
            acc['hits'].append((name, label, term))
    return acc


def write_report(res, path):
    rep = dict(generated_by='scripts/package_guard.py', members=res['members'], files_scanned=res['files_scanned'],
               images_skipped=res['images_skipped'], nested_archives=res['nested'], hit_count=len(res['hits']),
               hits=[dict(file=f, rule=label) for f, label, _ in res['hits']], passed=not res['hits'])
    json.dump(rep, open(path, 'w', encoding='utf-8'), indent=1)
    return rep


if __name__ == '__main__':
    import argparse, site_settings
    ap = argparse.ArgumentParser(); ap.add_argument('cmd', choices=['scan']); ap.add_argument('zip'); ap.add_argument('--report')
    a = ap.parse_args()
    res = scan_zip(a.zip, site_settings.load())
    rep = write_report(res, a.report or a.zip + '.scan.json')
    for f, label, term in res['hits']:
        print(f'DENYLIST HIT {f}: {label} ({term})', file=sys.stderr)
    print(f"scan {a.zip}: {rep['members']} members, {rep['files_scanned']} text files scanned, {rep['images_skipped']} images skipped, {rep['hit_count']} hits")
    sys.exit(1 if res['hits'] else 0)
