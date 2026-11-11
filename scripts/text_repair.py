#!/usr/bin/env python3
"""Repair words whose fi, fl, ff, ffi or ffl ligature glyph was lost by the PDF text layer.

Some owner PDFs embed fonts without a Unicode map for ligature glyphs. Poppler then drops the
glyph and leaves a gap: "De ne" for "Define", "speci c" for "specific", "the rst" for "the first".
The repair is data driven (config/ligature_words.txt). It never touches a word that already reads
as a common word, and every change is returned so the caller can log it in cleanups.json.
Generic: no exam, vendor or product names.
"""
from __future__ import annotations
import os, re

LIGS = ('ffi', 'ffl', 'fi', 'fl', 'ff')
_DATA = None
_KNOWN = set()


def _load(path=None):
    global _DATA
    if _DATA is not None and path is None:
        return _DATA
    path = path or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'ligature_words.txt')
    sec, lig, keep, known = None, set(), set(), set()
    if os.path.exists(path):
        for line in open(path, encoding='utf-8'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if line.startswith('['):
                sec = line.strip('[]')
                continue
            (lig if sec == 'ligature_words' else keep if sec == 'keep_short' else known if sec == 'known_words' else set()).add(line.lower())
    global _KNOWN
    _KNOWN = known
    _DATA = (lig, keep)
    return _DATA


def _case(src: str, word: str) -> str:
    return word[:1].upper() + word[1:] if src[:1].isupper() else word


def _join(a: str, b: str, lig_words):
    for L in LIGS:
        w = (a + L + b).lower()
        if w in lig_words:
            return _case(a, a + L + b)
    return None


def repair(text: str, data=None):
    """Return (fixed_text, [(before, after), ...])."""
    lig_words, keep = data or _load()
    if not text or not lig_words:
        return text, []
    changes = []

    # Glyph lost inside a word: "De ne", "O ce", "con gure". Second part is lower case.
    # Walk every gap so a merge is tried on each adjacent pair ("eDiscovery work ow").
    parts = re.split(r'( )', text)
    out = []
    i = 0
    while i < len(parts):
        tok = parts[i]
        if (i + 2 < len(parts) and re.fullmatch(r'[A-Za-z]+', tok) and re.fullmatch(r'[a-z]+[^A-Za-z]*', parts[i + 2])):
            b = re.match(r'[a-z]+', parts[i + 2]).group(0)
            j = _join(tok, b, lig_words)
            if j and tok.lower() not in lig_words and b not in lig_words:
                changes.append((tok + ' ' + b, j))
                parts[i + 2] = j + parts[i + 2][len(b):]
                i += 2
                continue
        out.append(tok)
        i += 1
    text = ''.join(out)

    def lead(m):
        t = m.group(1)
        if t.lower() in keep or t.lower() in lig_words:
            return t
        j = _join('', t, lig_words)
        if j:
            changes.append((t, j))
            return j
        return t

    # Glyph lost at the start of a word: "the rst", "les", "ngerprint". Lower case only.
    text = re.sub(r'(?<![A-Za-z\-])([a-z]{2,})(?![A-Za-z\-])', lead, text)
    return text, changes


def suspect_lost_ligatures(text: str, data=None, known=None):
    """Words that repair() could not fix because the PDF left no gap ("unied" for "unified").

    A token is suspect when it is not a known word but becomes a ligature word once fi, fl, ff,
    ffi or ffl is put back inside it. Returns [(token, candidate), ...]. Nothing is changed:
    the caller lists these for the owner. Data driven (config/ligature_words.txt), no names.
    """
    lig_words, keep = data or _load()
    if known is None:
        _load()
        known = _KNOWN
    out, seen = [], set()
    for tok in re.findall(r'[A-Za-z]+', text or ''):
        w = tok.lower()
        if len(w) < 4 or w in lig_words or w in keep or w in known or w in seen:
            continue
        for i in range(1, len(w)):
            c = next((w[:i] + L + w[i:] for L in LIGS if w[:i] + L + w[i:] in lig_words), None)
            if c:
                out.append((tok, _case(tok, c))); seen.add(w)
                break
    return out
