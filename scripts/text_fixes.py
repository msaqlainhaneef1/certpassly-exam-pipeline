#!/usr/bin/env python3
"""Spelling, grammar and punctuation fixes for owner stems and options (script first, author decides the rest).

Owner rule: fix spelling, grammar and punctuation only. Never change meaning, which option is correct,
or option order, and keep official product names exactly as the vendor writes them.

    propose(OUT, vendor)  -> out/<CODE>/text-fixes-proposals.json (auto fixes + proposals that need a decision)
    finalize(OUT, vendor) -> out/<CODE>/text-fixes.json (every applied change) and {item: {field: fixed text}}

Rules (generic, data driven; no exam, vendor or product names in code):
  lost_ligature      auto     a word that is not known but is a known word once fi/fl/ff/ffi/ffl is put back
  repeated_word      auto     "the the" -> "the"
  space_before_punct auto     "word ," -> "word,"
  double_space       auto     two or more spaces -> one
  article            decision "a" before a vowel or "an" before a consonant (sounds vary: "a user", "an SQL")
  typo               decision a word seen once that is one edit from a word the bank or the official pages use
Author decisions live in out/<CODE>/authoring/text_fixes_decisions.json:
  {"decisions": {"<proposal id>": {"accept": true|false, "after": "optional override", "note": "..."}},
   "extra": [{"item": "q001", "field": "stem"|"option.a", "before": "exact text", "after": "fixed", "kind": "grammar"|"spelling"|"punctuation", "reason": "..."}]}
Protected words (vendor terms from the saved official pages, and any word with a capital letter) are never
changed by a script rule; an author fix must keep every protected word of its "before" text.
"""
from __future__ import annotations
import difflib, glob, hashlib, html, json, os, re, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(__file__))
import text_repair as TR

AUTO = ('lost_ligature', 'repeated_word', 'space_before_punct', 'double_space')
DECIDE = ('article', 'typo')
def _rj(p):
    with open(p, encoding='utf-8') as fh:
        return json.load(fh)


def _wj(obj, p):
    with open(p, 'w', encoding='utf-8') as fh:
        json.dump(obj, fh, indent=1, ensure_ascii=False)


WORD = re.compile(r"[A-Za-z][A-Za-z']*")


def fields_of(it):
    return [('stem', it.get('stem') or '')] + [('option.' + k, v or '') for k, v in (it.get('options') or {}).items()]


def official_terms(root, vendor):
    """Words on the saved official pages: lower-case vocabulary, and the vendor's own spelling of capitalized terms."""
    txt = []
    for f in glob.glob(os.path.join(root, 'sources', vendor, '*')):
        if f.endswith(('.txt', '.html', '.htm')):
            with open(f, encoding='utf-8', errors='ignore') as fh:
                t = fh.read()
            txt.append(re.sub(r'<[^>]+>', ' ', html.unescape(t)) if not f.endswith('.txt') else t)
    toks = WORD.findall(' '.join(txt))
    return {t.lower() for t in toks}, {t for t in toks if re.search(r'[A-Z]', t)}


def _protected(tok, vendor_caps):
    return bool(re.search(r'[A-Z]', tok)) or tok in vendor_caps


def _edits1(w):
    letters = 'abcdefghijklmnopqrstuvwxyz'
    sp = [(w[:i], w[i:]) for i in range(len(w) + 1)]
    return {a + b[1:] for a, b in sp if b} | {a + b[1] + b[0] + b[2:] for a, b in sp if len(b) > 1} | \
           {a + c + b[1:] for a, b in sp if b for c in letters} | {a + c + b for a, b in sp for c in letters}


def _inflection(a, b):
    """True when the two words differ only by an ending (threat/threats, enable/enabled): not a typo."""
    s, l = sorted((a, b), key=len)
    return l.startswith(s) and len(l) - len(s) <= 3 or (a[:-1] == b[:-1])


ACRO_VOWEL = set('AEFHILMNORSX')  # letters whose name starts with a vowel sound (A, E, F "ef", H "aitch", ...)
U_YOU = re.compile(r'^(u[bcdfgjklmnpqrstvz][aeiou]|uni|eu|ew|one\b|once\b|ure)', re.I)
SILENT_H = re.compile(r'^(hour|honest|honou?r|heir)', re.I)


def vowel_sound(word):
    """Heuristic: does the word start with a vowel sound? Acronyms by letter name; "user", "one" are consonant sounds."""
    core = word.split('-')[0]
    if len(core) > 1 and core.isupper():
        return core[0] in ACRO_VOWEL or (core[0] == 'U' and False)
    if SILENT_H.match(core):
        return True
    if U_YOU.match(core):
        return False
    return core[:1].lower() in 'aeiou'


def item_digest(letters, option_ids, extra_key=None):
    """Key identity: key letters + option ids in order + option count (+ visual key when present)."""
    d = dict(key=sorted(l.upper() for l in letters), options=list(option_ids), n=len(option_ids))
    if extra_key is not None:
        d['visual_key'] = extra_key
    return hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()[:16]


def digests_from_split(S, VT):
    out = {}
    for k, it in S.items():
        letters = list(re.sub(r'[^A-H]', '', (it.get('answer_raw') or '').upper()))
        out[k] = item_digest(letters, [o.lower() for o in (it.get('options') or {})], (VT.get(k) or {}).get('key'))
    return out


def digests_from_questions(QS, VT):
    out = {}
    for q in QS:
        k = q['question_key']; key = q.get('answer_key') or {}
        out[k] = item_digest(key.get('correct_option_ids') or [], [o['id'].lower() for o in q.get('options') or []], (VT.get(k) or {}).get('key'))
    return out


def overall(d):
    return hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()


def settings(cfg=None):
    """text_fixes block of pipeline.yaml: enabled, auto (kinds fixed by script), typo_min_length."""
    if cfg is None:
        try:
            import config_load
            cfg = config_load.load(os.environ.get('CERTPASSLY_CONFIG'))
        except Exception:
            cfg = {}
    t = dict((cfg or {}).get('text_fixes') or {})
    return dict(enabled=t.get('enabled', True) is not False, auto=tuple(t.get('auto') or AUTO), typo_min_length=int(t.get('typo_min_length') or 5))


def propose(OUT, vendor, root=None, cfg=None):
    root = root or os.path.dirname(os.path.dirname(OUT))
    T = settings(cfg)
    S = _rj(os.path.join(OUT, 'extracted', 'split.json'))
    lig, keep = TR._load(); TR.suspect_lost_ligatures('')
    off_lower, vendor_caps = official_terms(root, vendor)
    corpus = Counter(t.lower() for it in S.values() for _, txt in fields_of(it) for t in WORD.findall(txt))
    trusted = {w for w, n in corpus.items() if n >= 2} | off_lower | lig | keep | TR._KNOWN
    props = []
    def add(k, f, kind, start, end, before, after, reason):
        props.append(dict(id=f'{k}:{f}:{kind}:{start}', item=k, field=f, kind=kind, start=start, end=end, before=before, after=after,
                          reason=reason, mode='auto' if kind in T['auto'] else 'decision'))
    for k, it in (S.items() if T['enabled'] else []):
        for f, txt in fields_of(it):
            for m in re.finditer(r' {2,}', txt):
                add(k, f, 'double_space', m.start(), m.end(), m.group(0), ' ', 'two or more spaces')
            for m in re.finditer(r'(?<=[A-Za-z]) ([,;:?!])(?=\s|$)', txt):
                add(k, f, 'space_before_punct', m.start(), m.end(), m.group(0), m.group(1), 'space before punctuation')
            for m in re.finditer(r'\b([A-Za-z]+) (\1)\b', txt, re.I):
                if m.group(1).lower() not in ('that', 'had'):
                    add(k, f, 'repeated_word', m.start(), m.end(), m.group(0), m.group(1), 'repeated word')
            for m in WORD.finditer(txt):
                tok = m.group(0); w = tok.lower()
                if tok in vendor_caps and not TR.suspect_lost_ligatures(tok):
                    continue
                sus = TR.suspect_lost_ligatures(tok)
                if sus and w not in off_lower:
                    add(k, f, 'lost_ligature', m.start(), m.end(), tok, sus[0][1], 'lost fi/fl/ff/ffi/ffl ligature glyph in the PDF text layer')
                    continue
                if _protected(tok, vendor_caps) or w in trusted or len(w) < T['typo_min_length'] or corpus[w] != 1:
                    continue
                cands = sorted(c for c in _edits1(w) if c in trusted and c != w and (corpus[c] >= 2 or c in off_lower) and not _inflection(w, c))
                if cands:
                    add(k, f, 'typo', m.start(), m.end(), tok, cands[0], 'seen once; one edit from a word used elsewhere: ' + ', '.join(cands[:3]))
            for m in re.finditer(r'\b(an|a) ([A-Za-z][A-Za-z-]*)', txt, re.I):
                art, nxt = m.group(1), m.group(2)
                want = 'an' if vowel_sound(nxt) else 'a'
                if art.lower() != want:
                    fixed_art = (want[0].upper() + want[1:]) if art[0].isupper() else want
                    add(k, f, 'article', m.start(), m.end(), m.group(0), fixed_art + ' ' + nxt, f'"{art}" before "{nxt}"')
    rec = dict(generated_by='scripts/text_fixes.py', counts=dict(Counter(p['kind'] for p in props)),
               undecided=[p['id'] for p in props if p['mode'] == 'decision'], proposals=props)
    _wj(rec, os.path.join(OUT, 'text-fixes-proposals.json'))
    return rec


def _check_extra(e, field_text, vendor_caps):
    b, a = e.get('before') or '', e.get('after') or ''
    if not b or b not in field_text:
        return 'before text is not in the field'
    if not a.strip():
        return 'after text is empty'
    lost = [t for t in WORD.findall(b) if _protected(t, vendor_caps) and t not in WORD.findall(a)]
    if lost:
        return 'changes protected words: ' + ', '.join(lost)
    if difflib.SequenceMatcher(None, b, a).ratio() < 0.6:
        return 'too large for a spelling or grammar fix'
    return ''


def finalize(OUT, vendor, root=None, strict=True):
    """Apply auto fixes and author decisions. Returns ({item: {field: fixed}}, record)."""
    root = root or os.path.dirname(os.path.dirname(OUT))
    rec = propose(OUT, vendor, root)
    S = _rj(os.path.join(OUT, 'extracted', 'split.json'))
    vtp = os.path.join(OUT, 'extracted', 'visual_transcription.json')
    VT = _rj(vtp) if os.path.exists(vtp) else {}
    dp = os.path.join(OUT, 'authoring', 'text_fixes_decisions.json')
    D = _rj(dp) if os.path.exists(dp) else {}
    dec = D.get('decisions') or {}
    pend = [i for i in rec['undecided'] if i not in dec]
    if pend and strict:
        raise SystemExit(f'text_fixes: {len(pend)} proposals need a decision in authoring/text_fixes_decisions.json (author batch): {pend[:8]}')
    _, vendor_caps = official_terms(root, vendor)
    per = {}; rejected = []
    for p in rec['proposals']:
        if p['mode'] == 'decision':
            d = dec.get(p['id']) or {}
            if not d.get('accept'):
                rejected.append(dict(id=p['id'], kind=p['kind'], note=d.get('note', 'undecided' if p['id'] in pend else 'rejected')))
                continue
            if d.get('after'):
                p = dict(p, after=d['after'])
            p = dict(p, source='author', note=d.get('note', ''))
        else:
            p = dict(p, source='script')
        per.setdefault((p['item'], p['field']), []).append(p)
    fixed = {}; log = []
    for (k, f), ps in per.items():
        txt = dict(fields_of(S[k]))[f]; new = txt
        for p in sorted(ps, key=lambda x: -x['start']):
            if any(q is not p and q['start'] < p['end'] and p['start'] < q['end'] for q in ps):
                if p['kind'] == 'double_space':
                    continue
            new = new[:p['start']] + p['after'] + new[p['end']:]
            log.append(dict(item=k, field=f, before=p['before'], after=p['after'], kind=p['kind'], reason=p['reason'] + (('; ' + p['note']) if p.get('note') else ''), source=p['source']))
        fixed.setdefault(k, {})[f] = new
    bad = []
    for e in D.get('extra') or []:
        k, f = e.get('item'), e.get('field')
        if k not in S or f not in dict(fields_of(S[k])):
            bad.append((k, f, 'unknown item or field')); continue
        cur = fixed.get(k, {}).get(f, dict(fields_of(S[k]))[f])
        why = _check_extra(e, cur, vendor_caps)
        if why:
            bad.append((k, f, why)); continue
        fixed.setdefault(k, {})[f] = cur.replace(e['before'], e['after'], 1)
        log.append(dict(item=k, field=f, before=e['before'], after=e['after'], kind=e.get('kind') or 'grammar', reason=e.get('reason') or 'author fix', source='author'))
    if bad and strict:
        raise SystemExit(f'text_fixes: author fixes rejected by the guard: {bad[:8]}')
    for k in list(fixed):
        for f in list(fixed[k]):
            if fixed[k][f] == dict(fields_of(S[k]))[f]:
                del fixed[k][f]
        if not fixed[k]:
            del fixed[k]
    before = digests_from_split(S, VT)
    after_items = {k: dict(S[k], stem=fixed.get(k, {}).get('stem', S[k]['stem']),
                           options={o: fixed.get(k, {}).get('option.' + o, v) for o, v in S[k]['options'].items()}) for k in S}
    after = digests_from_split(after_items, VT)
    out = dict(generated_by='scripts/text_fixes.py', rule='spelling, grammar and punctuation only; keys and option order unchanged',
               counts_by_kind=dict(Counter(x['kind'] for x in log)), counts_by_source=dict(Counter(x['source'] for x in log)),
               fix_count=len(log), items_changed=len(fixed), rejected_proposals=rejected, guard_rejected=bad,
               key_identity=dict(before_sha256=overall(before), after_sha256=overall(after), identical=before == after, items=len(before), per_item=before),
               fixes=sorted(log, key=lambda x: (x['item'], x['field'])), fields=fixed)
    _wj(out, os.path.join(OUT, 'text-fixes.json'))
    if before != after:
        raise SystemExit('text_fixes: key identity changed; refusing to apply')
    return fixed, out


if __name__ == '__main__':
    import argparse, paths
    ap = argparse.ArgumentParser(); ap.add_argument('cmd', choices=['propose', 'finalize']); ap.add_argument('--exam', required=True); ap.add_argument('--vendor', required=True)
    a = ap.parse_args(); OUT = os.path.join(paths.root(), 'out', a.exam)
    r = propose(OUT, a.vendor) if a.cmd == 'propose' else finalize(OUT, a.vendor)[1]
    print(json.dumps({k: r[k] for k in r if k in ('counts', 'undecided', 'counts_by_kind', 'fix_count', 'items_changed')})[:1500])
