#!/usr/bin/env python3
"""Unit regressions for defects found in the v1.0.2 demo runs."""
from __future__ import annotations
import json, os, re, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

SKILL=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL/'scripts'))


class TestGenericAdapter(unittest.TestCase):
    def _parse(self, html):
        from adapters import generic
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'sources'/'v'; src.mkdir(parents=True)
            (src/'p.html').write_text(html, encoding='utf-8')
            (src/'p.html.json').write_text(json.dumps(dict(url='https://x.example/a', path=str(src/'p.html'))), encoding='utf-8')
            return generic.parse(dict(vendor_slug='v', sources=[dict(id='sg', url='https://x.example/a')]), d)

    def test_minutes_plural_languages_capital_and_block_domains(self):
        out=self._parse('<h2>Skills measured</h2><p>Area one (40-50%)</p><ul><li>Task a</li></ul><p>Area two (50\u201360%)</p>'
                        '<p>The exam length is 105 minutes.</p><p>Languages: English, Japanese.</p>')
        f=out['fields']
        self.assertEqual(f['duration_minutes'], 105)
        self.assertEqual(f['languages'], ['English','Japanese'])
        self.assertEqual([(d['name'],d['weight_min_pct'],d['weight_max_pct']) for d in f['domains']], [('Area one',40,50),('Area two',50,60)])

    def test_single_language_is_read(self):
        self.assertEqual(self._parse('<p>Languages: English</p>')['fields']['languages'], ['English'])


class TestVisionWithoutTesseract(unittest.TestCase):
    def test_ocr_lines_returns_empty_when_tesseract_missing(self):
        import vision_util
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            p=os.path.join(d, 'i.png'); Image.new('RGB', (40, 20), 'white').save(p)
            with mock.patch('shutil.which', return_value=None):
                lines, size=vision_util.ocr_lines(p)
            self.assertEqual(lines, []); self.assertEqual(size, (40, 20))


class TestDocsMatchCode(unittest.TestCase):
    def test_version_and_changelog(self):
        py=(SKILL/'pyproject.toml').read_text(encoding='utf-8')
        ver=re.search(r'^version\s*=\s*"([^"]+)"', py, re.M).group(1)
        self.assertIn(f'## {ver}', (SKILL/'CHANGELOG.md').read_text(encoding='utf-8'))

    def test_skill_body_matches_skill_md(self):
        md=(SKILL/'SKILL.md').read_text(encoding='utf-8')
        body=md.split('---',2)[2]
        self.assertEqual(body.strip(), (SKILL/'SKILL_BODY.md').read_text(encoding='utf-8').strip())

    def test_no_exam_specific_count_in_review_text(self):
        src=(SKILL/'scripts'/'build_bank.py').read_text(encoding='utf-8')
        self.assertNotIn('All 41 image-based', src)


if __name__=='__main__':
    unittest.main(verbosity=2)
