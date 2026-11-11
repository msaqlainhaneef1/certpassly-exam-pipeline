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


def _load(path=None):
    global _DATA
    if _DATA is not None and path is None:
        return _DATA
    path = path or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'ligature_words.txt')
    sec, lig, keep = None, set(), set()
    if os.path.exists(path):
        for line in open(path, encoding='utf-8'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if line.startswith('['):
                sec = line.strip('[]')
                continue
            (lig if sec == 'ligature_words' else keep if sec == 'keep_short' else set()).add(line.lower())
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
