#!/usr/bin/env python3
"""v1.1.5: sidecar path remap on copied workspaces; Windows pdftohtml top/CRLF extract."""
from __future__ import annotations
import json, os, sys, tempfile, unittest
from pathlib import Path

SKILL=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL/'scripts'))
import fetch_sources
import extract_owner_pdf as extract
from adapters import generic


def _xml_page(lines, crlf=False):
    """Build a minimal pdf2xml page. lines: (top, left, text)."""
    parts=['<?xml version="1.0" encoding="UTF-8"?>', '<pdf2xml>', '<page number="1" width="612" height="792">']
    for top, left, text in lines:
        parts.append(f'<text top="{top}" left="{left}" width="40" height="12" font="0">{text}</text>')
    parts.append('</page></pdf2xml>')
    xml='\n'.join(parts)
    return xml.replace('\n', '\r\n') if crlf else xml


def _qset(q1_top=120, collapse=False, flip_first=False):
    """Two single-choice items with Correct Answer letters."""
    # XML document order is the true reading order.
    lines=[]
    t=1089 if flip_first else q1_top
    lines += [(t, 90, 'QUESTION 1'), (t if collapse else t+20, 90, 'What is the first choice?'),
              (200, 90, 'A. Red'), (220, 90, 'B. Blue'), (240, 90, 'C. Green'), (260, 90, 'D. Yellow')]
    ans_top=260 if collapse else 290
    lines += [(ans_top, 90, 'Correct Answer: '), (ans_top, 210, 'B'), (ans_top if collapse else ans_top+15, 90, 'Section: (none)')]
    q2_top=260 if collapse else 400
    lines += [(q2_top, 90, 'QUESTION 2'), (q2_top if collapse else q2_top+20, 90, 'What is the second choice?'),
              (540, 90, 'A. One'), (560, 90, 'B. Two'), (580, 90, 'C. Three'), (600, 90, 'D. Four'),
              (620 if not collapse else 600, 90, 'Correct Answer: '), (620 if not collapse else 600, 210, 'C')]
    return lines


class SidecarPathRemap(unittest.TestCase):
    def test_resolve_foreign_absolute_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)/'sources'/'acme'; d.mkdir(parents=True)
            html='<p>Exam length is 105 minutes.</p><p>Area one (40-50%)</p><p>Area two (50-60%)</p>'
            (d/'guide.html').write_text(html, encoding='utf-8')
            (d/'guide.txt').write_text('visible', encoding='utf-8')
            sidecar=d/'guide.html.json'
            sidecar.write_text(json.dumps({
                'url':'https://vendor.example/guide',
                'path':'/workspace/runs/other/sources/acme/guide.html',
                'text_path':'/workspace/runs/other/sources/acme/guide.txt',
                'sha256':'abc',
            }), encoding='utf-8')
            meta=fetch_sources.load_sidecar(str(sidecar))
            self.assertEqual(Path(meta['path']).resolve(), (d/'guide.html').resolve())
            self.assertEqual(Path(meta['text_path']).resolve(), (d/'guide.txt').resolve())
            self.assertTrue(os.path.isfile(meta['path']))

    def test_generic_reads_html_next_to_sidecar_not_linux_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)/'sources'/'v'; d.mkdir(parents=True)
            html=('<h2>Skills measured</h2><p>Area one (40-50%)</p><ul><li>Task a</li></ul>'
                  '<p>Area two (50-60%)</p><p>The exam length is 90 minutes.</p>')
            (d/'p.html').write_text(html, encoding='utf-8')
            (d/'p.html.json').write_text(json.dumps({
                'url':'https://x.example/a',
                'path':'/workspace/runs/dc101/sources/v/p.html',
                'sha256':'x',
            }), encoding='utf-8')
            out=generic.parse(dict(vendor_slug='v', sources=[dict(id='sg', url='https://x.example/a')]), tmp)
            self.assertEqual(out['fields']['duration_minutes'], 90)
            self.assertEqual(len(out['fields']['domains'] or []), 2)

    def test_find_saved_uses_helper(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)/'sources'/'v'; d.mkdir(parents=True)
            (d/'p.html').write_text('<p>hi</p>', encoding='utf-8')
            (d/'p.html.json').write_text(json.dumps({
                'url':'https://x.example/a',
                'path':'C:\\\\Users\\\\Other\\\\p.html',
                'sha256':'x',
            }), encoding='utf-8')
            m=fetch_sources.find_saved('v', 'https://x.example/a', root=tmp)
            self.assertIsNotNone(m)
            self.assertEqual(Path(m['path']).resolve(), (d/'p.html').resolve())


class WindowsExtractOrder(unittest.TestCase):
    def _split(self, xml):
        els=extract.load_elements(xml)
        layout=extract.detect_layout(els)
        import re
        deny=re.compile(r'a\A')
        split, cleanups, unparsed=extract.split_items(els, layout, deny)
        return split

    def test_trustworthy_tops_keep_same_line_answer_letter(self):
        # Linux-like: monotonic tops. "D" is to the right of "Correct Answer:" on the same line.
        lines=_qset(q1_top=120, collapse=False, flip_first=False)
        # Put the letter before the label in XML; left-sort must still attach B to the answer.
        # Replace the answer pair with label at left=90 and letter at left=210, XML letter first.
        fixed=[]
        for top,left,text in lines:
            if text=='Correct Answer: ' and left==90 and top==290:
                fixed.append((290, 210, 'B'))  # letter first in XML, further right
                fixed.append((290, 90, 'Correct Answer: '))
            elif text=='B' and left==210 and top==290:
                continue
            else:
                fixed.append((top,left,text))
        split=self._split(_xml_page(fixed, crlf=False))
        self.assertEqual(split['q001']['answer_raw'].strip(), 'B')
        self.assertEqual(split['q002']['answer_raw'].strip(), 'C')
        self.assertEqual(split['q001']['options']['a'], 'Red')

    def test_collapsed_and_flipped_tops_keep_keys(self):
        # Windows Poppler 25.07.0 style: QUESTION 1 has a huge top; many later lines share (top,left).
        xml=_xml_page(_qset(collapse=True, flip_first=True), crlf=False)
        self.assertFalse(extract.page_tops_trustworthy(extract.load_elements(xml)) or
                         extract.page_tops_trustworthy([
                             # load_elements already reorders; test the raw page flag via a hand list
                             dict(k='txt', page=1, top=1089, left=90, t='QUESTION 1'),
                             dict(k='txt', page=1, top=1089, left=90, t='stem'),
                             dict(k='txt', page=1, top=200, left=90, t='A. Red'),
                             dict(k='txt', page=1, top=260, left=90, t='D. Yellow'),
                             dict(k='txt', page=1, top=260, left=90, t='Correct Answer: '),
                             dict(k='txt', page=1, top=260, left=90, t='QUESTION 2'),
                             dict(k='txt', page=1, top=260, left=90, t='stem two'),
                             dict(k='txt', page=1, top=540, left=90, t='A. One'),
                         ]))
        split=self._split(xml)
        self.assertEqual(sorted(split), ['q001', 'q002'])
        self.assertEqual(split['q001']['answer_raw'].strip(), 'B')
        self.assertEqual(split['q002']['answer_raw'].strip(), 'C')
        self.assertEqual(split['q001']['options']['d'], 'Yellow')
        self.assertEqual(split['q002']['options']['a'], 'One')
        # A naive (top,left) sort would put QUESTION 1 last and drop keys; we must not.
        self.assertTrue(split['q001']['stem'].startswith('What is the first'))

    def test_crlf_xml_keeps_keys(self):
        xml=_xml_page(_qset(collapse=True, flip_first=True), crlf=True)
        self.assertIn('\r\n', xml)
        split=self._split(xml)
        self.assertEqual(split['q001']['answer_raw'].strip(), 'B')
        self.assertEqual(split['q002']['answer_raw'].strip(), 'C')
        self.assertEqual(len(split['q001']['options']), 4)


if __name__=='__main__':
    unittest.main()
