#!/usr/bin/env python3
"""Cheap docs checks: no typographic dashes and no emoji in the hand docs."""
from __future__ import annotations
import re
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]

DOC_FILES = [
    'README.md',
    'SKILL.md',
    'SKILL_BODY.md',
    'HANDOVER.md',
    'CHANGELOG.md',
    'docs/question-type-rules.md',
    'docs/ocr.md',
    'docs/fidelity.md',
]

# En dash, em dash, figure dash, horizontal bar, minus, plus emoji / dingbats.
DASH_RE = re.compile(r'[\u2012\u2013\u2014\u2015\u2212]')
EMOJI_RE = re.compile(
    r'[\U0001F300-\U0001FAFF\U00002700-\U000027BF\U00002600-\U000026FF]'
)


class TestDocsPlainEnglish(unittest.TestCase):
    def test_listed_docs_exist(self):
        missing = [p for p in DOC_FILES if not (SKILL / p).is_file()]
        self.assertEqual(missing, [])

    def test_no_typographic_dashes_in_docs(self):
        hits = []
        for rel in DOC_FILES:
            text = (SKILL / rel).read_text(encoding='utf-8')
            for i, line in enumerate(text.splitlines(), 1):
                if DASH_RE.search(line):
                    hits.append('%s:%s' % (rel, i))
        self.assertEqual(hits, [], 'typographic dashes in docs: %s' % hits[:20])

    def test_no_emoji_in_docs(self):
        hits = []
        for rel in DOC_FILES:
            text = (SKILL / rel).read_text(encoding='utf-8')
            for i, line in enumerate(text.splitlines(), 1):
                if EMOJI_RE.search(line):
                    hits.append('%s:%s' % (rel, i))
        self.assertEqual(hits, [], 'emoji in docs: %s' % hits[:20])


if __name__ == '__main__':
    unittest.main(verbosity=2)
