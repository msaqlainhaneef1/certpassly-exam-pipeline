#!/usr/bin/env python3
"""Export a pipeline questions.json bank to the CertPassly site format v2.

Writes ONE file per exam that matches reference/site-format/v2/question.schema.json
(the site's own schema). No schema_version, meta, or constraints fields. No raw
HTML or SVG. Does not invent keys. Expects canonical v2 answer statuses.

Do not use this script on a raw v1 bank. Use scripts/migrate_v1_to_v2.py, which
maps v1 statuses (including as_in_source_file) and converts image items.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

CANONICAL_STATUS = {
    'owner_key', 'researched_official', 'researched_unverified', 'answer_not_found',
}
V1_ONLY_STATUS = {'as_in_source_file', 'flagged_for_owner'}

CHOOSE_N_WORDS = {
    'two': 2, 'three': 3, 'four': 4, 'five': 5,
    'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
}
CHOOSE_N_RE = re.compile(
    r'\b(?:choose|select|pick)\s+(?:the\s+)?(two|three|four|five|six|seven|eight|nine|ten|\d+)\b',
    re.I,
)
HTML_TAG_RE = re.compile(r'<\s*[A-Za-z!/?]')
MARK_TAGS = {
    'b': 'bold', 'strong': 'bold',
    'i': 'italic', 'em': 'italic',
    'code': 'code',
}


def version_int(item) -> int:
    qvk = str(item.get('question_version_key') or '')
    if '-v' in qvk:
        tail = qvk.rsplit('-v', 1)[-1]
        if tail.isdigit():
            return max(1, int(tail))
    v = item.get('version')
    if isinstance(v, int) and v >= 1:
        return v
    return 1


def options(item):
    out = []
    for o in item.get('options') or []:
        oid = str(o.get('id') or o.get('option_letter') or '').strip()
        text = o.get('text') or o.get('option_text') or ''
        if oid:
            out.append({'id': oid, 'text': text})
    if out:
        return out
    content = ((item.get('response_schema') or {}).get('content') or {})
    for o in content.get('options') or []:
        out.append({'id': str(o.get('id')), 'text': o.get('text') or ''})
    return out


def iter_media(item):
    raw = item.get('media') or []
    if isinstance(raw, dict):
        raw = [raw]
    for i, m in enumerate(raw, 1):
        if isinstance(m, dict):
            yield i, m


def site_media_url(path: str | None) -> str | None:
    pth = (path or '').replace('\\', '/').strip()
    if not pth:
        return None
    if pth.startswith('https://'):
        return pth
    if pth.startswith('http://'):
        return None
    if pth.startswith('/storage/'):
        return pth
    pth = pth.lstrip('./')
    if pth.startswith('/'):
        return '/storage' + pth
    return '/storage/' + pth


def option_index(opts: list[dict], oid: str) -> int | None:
    for i, o in enumerate(opts):
        if str(o.get('id')) == str(oid):
            return i
    return None


def choose_n_from_text(text: str) -> int | None:
    m = CHOOSE_N_RE.search(text or '')
    if not m:
        return None
    raw = m.group(1).lower()
    if raw.isdigit():
        n = int(raw)
        return n if n >= 1 else None
    return CHOOSE_N_WORDS.get(raw)


def rich_paragraph(text: str) -> dict:
    return {'type': 'paragraph', 'content': [{'text': text if text != '' else ' '}]}


def plain_to_rich(text: str) -> list[dict]:
    parts = [p.strip() for p in (text or '').split('\n') if p.strip()]
    if not parts:
        parts = [(text or '').strip() or ' ']
    return [rich_paragraph(p) for p in parts]


def _flush_inline(buf: list[str], marks: set[str], link: str | None, out: list[dict]):
    text = ''.join(buf)
    if text == '':
        return
    node = {'text': text}
    if marks:
        node['marks'] = [m for m in ('bold', 'italic', 'code') if m in marks]
    if link and link.startswith('https://') and '<' not in link and '>' not in link and ' ' not in link:
        node['link'] = link
    out.append(node)
    buf.clear()


class _RichParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks: list[dict] = []
        self.tables: list[dict] = []
        self._inline: list[dict] = []
        self._buf: list[str] = []
        self._marks: list[str] = []
        self._link: list[str] = []
        self._list_type: str | None = None
        self._list_items: list[list[dict]] = []
        self._item_inline: list[dict] | None = None
        self._in_table = False
        self._table_cols: list[list[dict]] = []
        self._table_rows: list[list[dict]] = []
        self._table_cells: list[list[list[dict]]] = []
        self._row_cells: list[list[dict]] = []
        self._cell_is_header = False
        self._skip = 0

    def _current_marks(self) -> set[str]:
        return set(self._marks)

    def _current_link(self) -> str | None:
        return self._link[-1] if self._link else None

    def _target(self) -> list[dict]:
        if self._item_inline is not None:
            return self._item_inline
        return self._inline

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in ('script', 'style'):
            self._skip += 1
            return
        if self._skip:
            return
        if tag in MARK_TAGS:
            _flush_inline(self._buf, self._current_marks(), self._current_link(), self._target())
            self._marks.append(MARK_TAGS[tag])
            return
        if tag == 'a':
            _flush_inline(self._buf, self._current_marks(), self._current_link(), self._target())
            href = dict(attrs).get('href') or ''
            self._link.append(href)
            return
        if tag in ('p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'br'):
            _flush_inline(self._buf, self._current_marks(), self._current_link(), self._target())
            if tag != 'br':
                self._close_paragraph()
            else:
                if self._inline:
                    self._close_paragraph()
            return
        if tag in ('ul', 'ol'):
            _flush_inline(self._buf, self._current_marks(), self._current_link(), self._target())
            self._close_paragraph()
            self._list_type = 'bullet_list' if tag == 'ul' else 'ordered_list'
            self._list_items = []
            return
        if tag == 'li':
            _flush_inline(self._buf, self._current_marks(), self._current_link(), self._target())
            self._item_inline = []
            return
        if tag == 'table':
            _flush_inline(self._buf, self._current_marks(), self._current_link(), self._target())
            self._close_paragraph()
            self._in_table = True
            self._table_cols = []
            self._table_rows = []
            self._table_cells = []
            self._row_cells = []
            return
        if tag == 'tr' and self._in_table:
            self._row_cells = []
            self._cell_is_header = False
            return
        if tag in ('td', 'th') and self._in_table:
            self._cell_is_header = tag == 'th'
            self._item_inline = []
            return

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in ('script', 'style'):
            self._skip = max(0, self._skip - 1)
            return
        if self._skip:
            return
        if tag in MARK_TAGS:
            _flush_inline(self._buf, self._current_marks(), self._current_link(), self._target())
            mark = MARK_TAGS[tag]
            if mark in self._marks:
                # remove last occurrence
                idx = len(self._marks) - 1 - self._marks[::-1].index(mark)
                self._marks.pop(idx)
            return
        if tag == 'a':
            _flush_inline(self._buf, self._current_marks(), self._current_link(), self._target())
            if self._link:
                self._link.pop()
            return
        if tag in ('p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            _flush_inline(self._buf, self._current_marks(), self._current_link(), self._target())
            self._close_paragraph()
            return
        if tag == 'li':
            _flush_inline(self._buf, self._current_marks(), self._current_link(), self._target())
            item = self._item_inline or [{'text': ' '}]
            self._item_inline = None
            if self._list_type is not None:
                self._list_items.append(item)
            else:
                self._inline.extend(item)
            return
        if tag in ('ul', 'ol'):
            _flush_inline(self._buf, self._current_marks(), self._current_link(), self._target())
            if self._list_items:
                self.blocks.append({'type': self._list_type or 'bullet_list', 'items': self._list_items})
            self._list_type = None
            self._list_items = []
            return
        if tag in ('td', 'th') and self._in_table:
            _flush_inline(self._buf, self._current_marks(), self._current_link(), self._target())
            cell_inline = self._item_inline or [{'text': ' '}]
            self._item_inline = None
            cell_rich = [{'type': 'paragraph', 'content': cell_inline}]
            self._row_cells.append(cell_rich)
            return
        if tag == 'tr' and self._in_table:
            if self._cell_is_header or (self._table_cells == [] and self._table_cols == [] and all(True for _ in self._row_cells)):
                # first row of th becomes columns; if all th, treat as header
                if self._table_cols == [] and self._row_cells and self._cell_is_header:
                    self._table_cols = self._row_cells
                else:
                    self._table_cells.append(self._row_cells)
                    self._table_rows.append([rich_paragraph(f'Row {len(self._table_rows) + 1}')])
            else:
                if self._table_cols == [] and not self._table_cells:
                    # no header row yet: first row is columns if it came from th only; else body
                    self._table_cells.append(self._row_cells)
                    self._table_rows.append([rich_paragraph(f'Row {len(self._table_rows) + 1}')])
                else:
                    self._table_cells.append(self._row_cells)
                    self._table_rows.append([rich_paragraph(f'Row {len(self._table_rows) + 1}')])
            self._row_cells = []
            return
        if tag == 'table':
            cols = self._table_cols or [[rich_paragraph(f'Col {i + 1}')] for i in range(max((len(r) for r in self._table_cells), default=1))]
            rows = self._table_rows
            cells = self._table_cells
            if rows or cells or cols:
                self.tables.append({'type': 'table', 'columns': cols, 'rows': rows, 'cells': cells})
            self._in_table = False
            return

    def handle_data(self, data):
        if self._skip:
            return
        if data:
            self._buf.append(data)

    def _close_paragraph(self):
        if self._item_inline is not None:
            return
        if self._inline:
            self.blocks.append({'type': 'paragraph', 'content': self._inline})
            self._inline = []

    def close(self):
        _flush_inline(self._buf, self._current_marks(), self._current_link(), self._target())
        self._close_paragraph()
        super().close()


def html_to_rich(text: str) -> tuple[list[dict], list[dict]]:
    """Convert HTML or plain text to (rich_text, content_blocks)."""
    raw = text or ''
    if not HTML_TAG_RE.search(raw):
        return plain_to_rich(html.unescape(raw)), []
    parser = _RichParser()
    try:
        parser.feed(raw)
        parser.close()
    except Exception:
        return plain_to_rich(re.sub(r'<[^>]+>', ' ', raw)), []
    blocks = parser.blocks or []
    if not blocks:
        stripped = re.sub(r'<[^>]+>', ' ', raw)
        stripped = html.unescape(re.sub(r'\s+', ' ', stripped)).strip()
        blocks = plain_to_rich(stripped or ' ')
    return blocks, parser.tables


def text_of_rich(rich) -> str:
    parts = []

    def walk(obj):
        if isinstance(obj, dict):
            if 'text' in obj and isinstance(obj['text'], str):
                parts.append(obj['text'])
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)
    walk(rich)
    return ' '.join(parts)


def content_of(item: dict) -> dict:
    return ((item.get('response_schema') or {}).get('content') or {})


def parse_template_segments(template: str, blank_ids: list[str]) -> list[dict]:
    """Split a {{blank}} template into cloze segments."""
    if not template:
        segs = []
        for bid in blank_ids:
            segs.append({'blank': bid})
        return segs or [{'text': ' '}]
    segs = []
    last = 0
    for m in re.finditer(r'\{\{([^}]+)\}\}', template):
        before = template[last:m.start()]
        if before:
            segs.append({'text': before})
        name = m.group(1).strip()
        segs.append({'blank': name})
        last = m.end()
    after = template[last:]
    if after:
        segs.append({'text': after})
    return segs or [{'text': template}]


def matrix_interaction(content: dict) -> dict:
    rows = []
    cols = []
    for r in content.get('rows') or []:
        rid = str(r.get('id') or '')
        text = r.get('text') or r.get('label') or ''
        rows.append({'id': rid or 'row', 'text': plain_to_rich(text)})
    for c in content.get('columns') or []:
        cid = str(c.get('id') or '')
        text = c.get('text') or c.get('label') or ''
        cols.append({'id': cid or 'col', 'text': text or ' '})
    return {'matrix': {'rows': rows, 'columns': cols}}


def cloze_interaction(content: dict, typ: str) -> dict:
    """Build a cloze interaction. Option ids are unique in the question.

    When several blanks reuse the same source option ids (c1, c2, ...), the
    export prefixes each id with the blank id so the site importer accepts the
    file. The returned map is also used to rewrite answer_key values.
    """
    blanks_out = []
    ids = []
    option_id_map = {}  # (blank_id, source_option_id) -> unique id
    seen_ids: set[str] = set()
    for blank in content.get('blanks') or []:
        bid = str(blank.get('id') or '')
        ids.append(bid)
        if bid:
            seen_ids.add(bid)
        choices = blank.get('choices') or blank.get('options') or []
        options = []
        for ch in choices:
            if isinstance(ch, dict):
                src = str(ch.get('id'))
                text = ch.get('text') or ' '
            else:
                src = str(ch)
                text = str(ch)
            oid = src
            if oid in seen_ids:
                oid = f'{bid}_{src}' if bid else src
            # still unique?
            base = oid
            n = 2
            while oid in seen_ids:
                oid = f'{base}_{n}'
                n += 1
            seen_ids.add(oid)
            option_id_map[(bid, src)] = oid
            options.append({'id': oid, 'text': text})
        rec = {
            'id': bid,
            'label': (blank.get('label') or bid or 'Blank'),
            'kind': 'dropdown' if typ != 'text_cloze' or options else 'text',
        }
        if rec['kind'] == 'dropdown':
            rec['options'] = options
        blanks_out.append(rec)
    tmpl = content.get('prompt_template') or ''
    segments = parse_template_segments(tmpl, ids)
    used = [s.get('blank') for s in segments if 'blank' in s]
    for bid in ids:
        if bid not in used:
            segments.append({'blank': bid})
    return {'cloze': {'segments': segments, 'blanks': blanks_out}, '_option_id_map': option_id_map}


def hotspot_regions(content: dict) -> list[dict]:
    out = []
    for region in content.get('regions') or []:
        coords = region.get('normalized_coordinates') or region.get('coords') or []
        nums = []
        for c in coords:
            try:
                nums.append(float(c))
            except (TypeError, ValueError):
                continue
        # clamp 0..1
        nums = [0.0 if n < 0 else (1.0 if n > 1 else n) for n in nums]
        shape = region.get('shape') or 'rect'
        if shape == 'rect' and len(nums) != 4:
            # pad or trim to 4 if we have something
            if len(nums) >= 4:
                nums = nums[:4]
            elif len(nums) == 2:
                nums = [nums[0], nums[1], 0.05, 0.05]
            else:
                continue
        elif shape == 'circle' and len(nums) != 3:
            if len(nums) >= 3:
                nums = nums[:3]
            else:
                continue
        elif shape == 'polygon' and (len(nums) < 6 or len(nums) % 2 != 0):
            if len(nums) >= 6 and len(nums) % 2 == 1:
                nums = nums[:-1]
            elif len(nums) < 6:
                continue
        out.append({
            'id': str(region.get('id') or f"r{len(out) + 1}"),
            'label': region.get('label') or str(region.get('id') or f"r{len(out) + 1}"),
            'shape': shape,
            'coords': nums,
        })
    return out


def map_answer_key(item: dict, typ: str, opts: list[dict]) -> object:
    """Map a v1 bank key onto the site grader shape. Does not invent answers."""
    key = item.get('answer_key')
    if typ == 'answer_not_found' or (item.get('answer_key_status') == 'answer_not_found' and not key):
        return None
    if typ in ('single_choice', 'true_false', 'image_based_choice'):
        ids = []
        if isinstance(key, dict):
            ids = key.get('correct_option_ids') or []
            if not ids and key.get('correct_option_id'):
                ids = [key['correct_option_id']]
        elif isinstance(key, list):
            ids = key
        elif key is not None:
            ids = [key]
        if not ids:
            return []
        idx = option_index(opts, str(ids[0]))
        return [idx] if idx is not None else [str(ids[0])]
    if typ == 'multiple_select':
        ids = (key or {}).get('correct_option_ids') if isinstance(key, dict) else key
        ids = list(ids or [])
        out = []
        for oid in ids:
            idx = option_index(opts, str(oid))
            out.append(idx if idx is not None else str(oid))
        return out
    if typ in ('yes_no_matrix', 'single_choice_matrix', 'multi_select_matrix'):
        if not isinstance(key, dict):
            return key
        if 'cells' in key and isinstance(key['cells'], dict):
            return key['cells']
        if 'rows' in key and isinstance(key['rows'], dict):
            return key['rows']
        # already a row-id map?
        return {k: v for k, v in key.items() if k not in ('correct_option_ids',)}
    if typ in ('inline_dropdown', 'multi_blank_dropdown', 'text_cloze'):
        raw = key['slots'] if isinstance(key, dict) and 'slots' in key else key
        idmap = item.get('_cloze_option_id_map') or {}
        if isinstance(raw, dict) and idmap:
            out = {}
            for bid, oid in raw.items():
                out[str(bid)] = idmap.get((str(bid), str(oid)), oid)
            return out
        return raw
    if typ in ('hotspot_single', 'active_screen'):
        if isinstance(key, dict):
            ids = key.get('region_ids') or key.get('correct_region_ids') or []
            if ids:
                return ids[0] if typ != 'hotspot_multi' else ids
            if key.get('region_id'):
                return key['region_id']
        return key
    if typ == 'hotspot_multi':
        if isinstance(key, dict):
            return key.get('region_ids') or key.get('correct_region_ids') or key
        return key
    if typ == 'ordering':
        if isinstance(key, dict):
            return key.get('order') or key.get('ordered_ids') or list(key.values())
        return key
    if typ in ('drag_drop', 'categorization', 'matching'):
        if isinstance(key, dict):
            return key.get('slots') or key.get('pairs') or key.get('assignments') or key
        return key
    return key


def learner_media_from_item(item: dict) -> list[dict]:
    assets = []
    for i, m in iter_media(item):
        kind = (m.get('kind') or m.get('role') or '').lower()
        vis = (m.get('visibility') or '').lower()
        href = m.get('href') or m.get('path') or m.get('url') or ''
        path_l = href.lower()
        is_review = (
            kind in {'diagram', 'answer_image_review_only', 'answer_area', 'answer_review'}
            or vis in {'reviewer_only', 'reviewer'}
            or 'answer-review' in path_l
            or 'answer-area' in path_l
        )
        is_exhibit = kind in {'exhibit', ''} or 'exhibit' in path_l or vis == 'candidate'
        if is_review and 'exhibit' not in path_l:
            continue
        if not is_exhibit and not (kind in {'exhibit'} or 'exhibit' in path_l):
            # keep only supporting exhibits in the learner payload
            if kind not in {'exhibit', 'image', 'svg', ''}:
                continue
        url = site_media_url(href)
        alt = (m.get('alt') or m.get('alt_text') or m.get('description') or '').strip()
        if not url or not alt:
            continue
        assets.append({'url': url, 'alt': alt})
    return assets


def references_and_evidence(item: dict) -> tuple[list[str], str | None, str | None]:
    refs = []
    evidence_parts = []
    source_parts = []
    for s in item.get('sources') or []:
        if not isinstance(s, dict):
            continue
        url = s.get('url') or s.get('source_url') or ''
        if isinstance(url, str) and url.startswith('https://'):
            refs.append(url)
        if s.get('quote') or s.get('evidence') or s.get('title'):
            evidence_parts.append(str(s.get('quote') or s.get('evidence') or s.get('title')))
        if url:
            source_parts.append(str(url))
        elif s.get('name') or s.get('title'):
            source_parts.append(str(s.get('name') or s.get('title')))
    top = item.get('source_url') or ''
    if isinstance(top, str) and top.startswith('https://') and top not in refs:
        refs.append(top)
        if not source_parts:
            source_parts.append(top)
    ks = item.get('key_source') or ''
    if ks == 'owner_file' and not source_parts:
        source_parts.append('owner file')
    evidence = ' '.join(evidence_parts).strip() or None
    source = '; '.join(source_parts).strip() or None
    # drop duplicate refs
    seen = set()
    uniq = []
    for u in refs:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq, source, evidence


def explanation_rich(item: dict) -> list[dict] | None:
    core = item.get('core_explanation') or (item.get('explanations') or {}).get('core') or ''
    if not core or not str(core).strip():
        return None
    blocks, _tables = html_to_rich(str(core))
    return blocks


def domain_name_of(item: dict, domain_names: dict[str, str] | None) -> str:
    name = item.get('domain') or item.get('domain_name') or ''
    if name and not str(name).startswith(str(item.get('exam_key') or '')):
        # already a display name if it has spaces or is not a key
        if ' ' in str(name) or (domain_names and name in domain_names.values()):
            return str(name)
    key = item.get('domain_key') or name
    if domain_names and key in domain_names:
        return domain_names[key]
    if domain_names and name in domain_names:
        return domain_names[name]
    if name:
        return str(name)
    return 'Unassigned'


def export_item(item: dict, domain_names: dict[str, str] | None = None) -> dict:
    typ = item.get('question_type') or item.get('type') or 'single_choice'
    aks_raw = item.get('answer_key_status') or 'owner_key'
    if aks_raw in V1_ONLY_STATUS or aks_raw not in CANONICAL_STATUS:
        raise ValueError(
            f"v1 answer_key_status {aks_raw!r} is not valid in v2; "
            'use scripts/migrate_v1_to_v2.py'
        )
    aks = aks_raw
    scoring = aks == 'answer_not_found' or bool(item.get('scoring_flag'))
    if item.get('question_key') in (item.get('scoring_excluded_question_keys') or []):
        scoring = True
    if aks == 'answer_not_found':
        scoring = True
    reviewer = bool(item.get('human_review_required') or item.get('reviewer_needed'))
    opts = options(item)
    content = content_of(item)
    prompt = item.get('prompt_text') or content.get('prompt') or ''
    stem, table_blocks = html_to_rich(prompt)
    learner: dict = {'stem': stem}
    interaction: dict = {}

    if typ in ('single_choice', 'true_false', 'multiple_select', 'image_based_choice'):
        if opts:
            learner['choices'] = [plain_to_rich(o.get('text') or ' ') for o in opts]
        n = choose_n_from_text(text_of_rich(stem) + ' ' + prompt)
        if typ == 'multiple_select' and n:
            interaction['choose_n'] = n
    elif typ in ('yes_no_matrix', 'single_choice_matrix', 'multi_select_matrix') or (
        typ not in ('inline_dropdown', 'multi_blank_dropdown') and content.get('rows') and content.get('columns')
    ):
        interaction.update(matrix_interaction(content))
    elif typ in ('inline_dropdown', 'multi_blank_dropdown', 'text_cloze') or content.get('blanks'):
        cloze = cloze_interaction(content, typ)
        option_id_map = cloze.pop('_option_id_map', {})
        interaction.update(cloze)
        item = dict(item)
        item['_cloze_option_id_map'] = option_id_map
        # keep the spoken prompt in the stem; the cloze text lives in interaction
        tmpl = content.get('prompt_template') or ''
        visible = re.sub(r'\{\{[^}]+\}\}', ' ____ ', tmpl).strip()
        if visible and visible not in prompt:
            extra, _ = html_to_rich(visible)
            # avoid duplicating if stem already has it
            if text_of_rich(extra).strip() and text_of_rich(extra).strip() not in text_of_rich(stem):
                # actually: keep choose-n / instruction in stem only; cloze segments carry the template
                pass
    elif typ in ('active_screen', 'hotspot_single', 'hotspot_multi'):
        regions = hotspot_regions(content)
        if regions:
            interaction['hotspot_regions'] = regions
    elif typ == 'ordering':
        items = content.get('items') or content.get('ordering') or []
        if items:
            interaction['ordering'] = [
                (it.get('text') if isinstance(it, dict) else str(it)) or ' ' for it in items
            ]
    elif typ == 'matching':
        pairs = content.get('pairs') or content.get('matching_pairs') or []
        if pairs:
            interaction['matching_pairs'] = [
                [
                    (p[0] if not isinstance(p, dict) else (p.get('left') or p.get('a') or '')),
                    (p[1] if not isinstance(p, dict) else (p.get('right') or p.get('b') or '')),
                ]
                if isinstance(p, (list, tuple))
                else [str(p.get('left') or ''), str(p.get('right') or '')]
                for p in pairs
            ]
    elif typ == 'drag_drop':
        slots = content.get('slots') or content.get('drag_slots') or []
        if slots:
            interaction['drag_slots'] = [
                (s.get('label') or s.get('text') or s.get('id') if isinstance(s, dict) else str(s)) or ' '
                for s in slots
            ]

    if table_blocks:
        learner['content_blocks'] = table_blocks
    media = learner_media_from_item(item)
    # also from response_schema image_url
    img_url = content.get('image_url')
    img_alt = (content.get('image_alt') or '').strip()
    if img_url and img_alt:
        url = site_media_url(img_url)
        if url and not any(m['url'] == url for m in media):
            media.append({'url': url, 'alt': img_alt})
    if media:
        learner['media'] = media
    if interaction:
        learner['interaction'] = interaction

    refs, source, evidence = references_and_evidence(item)
    expl = explanation_rich(item)
    answer = {
        'answer_key': map_answer_key(item, typ, opts),
        'status': aks,
        'scoring_excluded': bool(scoring),
        'reviewer_needed': bool(reviewer),
    }
    if source:
        answer['source'] = source
    if evidence:
        answer['evidence'] = evidence
    if expl:
        answer['explanation'] = expl
    if refs:
        answer['references'] = refs

    doc = {
        'question_key': item['question_key'],
        'version': version_int(item),
        'type': typ,
        'domain': domain_name_of(item, domain_names),
        'learner': learner,
        'answer': answer,
    }
    difficulty = (item.get('difficulty') or '').strip()
    if difficulty:
        doc['difficulty'] = difficulty
    tags = item.get('tags') or []
    if tags:
        doc['tags'] = [str(t) for t in tags]
    tpp = item.get('time_per_question')
    if isinstance(tpp, int) and tpp >= 1:
        doc['time_per_question'] = tpp
    return doc


def _read_csv(path: Path | None) -> list[dict]:
    if not path or not path.is_file():
        return []
    with path.open(encoding='utf-8', newline='') as fh:
        return list(csv.DictReader(fh))


def load_domain_names(domains_csv: Path | None) -> dict[str, str]:
    out = {}
    for row in _read_csv(domains_csv):
        key = row.get('domain_key') or ''
        name = (row.get('domain_name') or '').strip()
        if key and name:
            out[key] = name
    return out


def exam_domains_from_csv(domains_csv: Path | None) -> list[dict]:
    out = []
    for row in _read_csv(domains_csv):
        name = (row.get('domain_name') or '').strip()
        if not name:
            continue
        try:
            lo = float(row.get('weight_min_pct') or 0)
            hi = float(row.get('weight_max_pct') or lo)
        except ValueError:
            lo = hi = 0.0
        weight = lo if lo == hi else (lo + hi) / 2.0
        out.append({'name': name, 'weight': weight})
    return out


def _fact_value(facts: dict, key: str):
    raw = (facts or {}).get(key)
    if isinstance(raw, dict) and 'value' in raw:
        return raw.get('value')
    return raw


def build_exam_section(
    bank: dict,
    *,
    exams_csv: Path | None = None,
    domains_csv: Path | None = None,
    vendors_csv: Path | None = None,
    research: dict | None = None,
    simulator: dict | None = None,
) -> dict:
    rows = _read_csv(exams_csv)
    exam_row = rows[0] if rows else {}
    vendor_rows = _read_csv(vendors_csv)
    vendor_map = {r.get('vendor_key'): r for r in vendor_rows}
    exam_key = bank.get('exam_key') or exam_row.get('exam_key') or ''
    exam_code = exam_row.get('exam_code') or (research or {}).get('exam_code') or str(exam_key or 'EXAM')
    # restore official spelling from exam_key if needed
    if exam_code == exam_key and '-' in str(exam_key):
        # prefer official code from research or csv; if missing, title-case poorly. leave as-is.
        pass
    name = exam_row.get('official_exam_name') or ''
    if not name and research:
        en = research.get('exam_name')
        if isinstance(en, dict):
            name = en.get('value') or ''
        elif en:
            name = str(en)
    name = name or exam_code
    vendor_key = exam_row.get('vendor_key') or (research or {}).get('vendor_slug') or ''
    vendor = (vendor_map.get(vendor_key) or {}).get('display_name') or vendor_key or 'Vendor'
    cert = exam_row.get('certification_key') or (research or {}).get('certification_slug') or name
    # prefer a readable certification title
    if cert and '-' in str(cert) and name:
        certification = name
    else:
        certification = cert or name

    exam: dict = {
        'vendor': str(vendor),
        'certification': str(certification),
        'exam_code': str(exam_code),
        'name': str(name or exam_code),
    }
    duration = exam_row.get('official_duration_minutes')
    if duration in (None, ''):
        facts = (research or {}).get('facts') or {}
        duration = _fact_value(facts, 'duration_minutes')
        if duration is None and simulator and isinstance(simulator.get('time_limit_minutes'), dict):
            duration = simulator['time_limit_minutes'].get('value')
    try:
        if duration not in (None, ''):
            exam['duration'] = int(duration)
    except (TypeError, ValueError):
        pass
    passing = exam_row.get('official_passing_score')
    if passing in (None, ''):
        facts = (research or {}).get('facts') or {}
        passing = _fact_value(facts, 'passing_score')
        if passing is None and simulator and isinstance(simulator.get('passing_score'), dict):
            passing = simulator['passing_score'].get('value')
    try:
        if passing not in (None, ''):
            exam['passing_score'] = float(passing) if '.' in str(passing) else int(float(passing))
    except (TypeError, ValueError):
        pass
    qcount = None
    if simulator and isinstance(simulator.get('question_count'), dict):
        qcount = simulator['question_count'].get('value')
    facts = (research or {}).get('facts') or {}
    if qcount is None:
        qcount = _fact_value(facts, 'question_count')
    try:
        if qcount not in (None, ''):
            exam['question_count'] = int(qcount)
    except (TypeError, ValueError):
        pass
    domains = exam_domains_from_csv(domains_csv)
    if not domains and research:
        for d in ((research.get('objectives') or {}).get('domains') or []):
            lo = d.get('weight_min_pct')
            hi = d.get('weight_max_pct')
            if lo is None:
                continue
            hi = hi if hi is not None else lo
            weight = lo if lo == hi else (float(lo) + float(hi)) / 2.0
            domains.append({'name': d.get('name') or f"Domain {d.get('code')}", 'weight': weight})
    if domains:
        exam['domains'] = domains
    # last_vendor_update
    date = None
    if research:
        date = (research.get('objectives') or {}).get('outline_as_of')
    evk = exam_row.get('exam_version_key') or ''
    if not date and evk:
        m = re.search(r'(20\d{2}-\d{2}-\d{2})', evk)
        if m:
            date = m.group(1)
    if date and re.match(r'^\d{4}-\d{2}-\d{2}$', str(date)):
        exam['last_vendor_update'] = str(date)
    settings = {}
    if simulator:
        settings['mode'] = 'exam'
        if simulator.get('status') == 'draft':
            settings['mode'] = 'exam'
        settings['flagging'] = True
        settings['review'] = True
        settings['counts_toward_trial'] = True
        if settings:
            exam['simulator_settings'] = settings
    else:
        exam['simulator_settings'] = {
            'mode': 'exam',
            'flagging': True,
            'review': True,
            'counts_toward_trial': True,
        }
    return exam


def wrap_exam(exam: dict, questions: list[dict]) -> dict:
    return {'exam': exam, 'questions': questions}


def discover_sidecars(bank_path: Path, src_root: Path | None = None) -> dict:
    roots = []
    if src_root:
        roots.append(src_root)
    roots.append(bank_path.parent)
    if bank_path.parent.name and bank_path.parent.parent:
        roots.append(bank_path.parent)
    found = {}
    for root in roots:
        imp = root / 'import'
        for key, rel in [
            ('exams_csv', ('import/exams.csv', 'exams.csv')),
            ('domains_csv', ('import/domains.csv', 'domains.csv')),
            ('vendors_csv', ('import/vendors.csv', 'vendors.csv')),
            ('simulator', ('simulator_settings.json',)),
        ]:
            if found.get(key):
                continue
            for r in rel:
                p = root / r
                if p.is_file():
                    found[key] = p
                    break
        if not found.get('research'):
            # optional
            pass
    return found


def count_external_references(doc: dict, site_hosts=('certpassly.com',)) -> list[str]:
    urls = []
    for q in doc.get('questions') or []:
        for u in (q.get('answer') or {}).get('references') or []:
            urls.append(u)
        def walk(obj):
            if isinstance(obj, dict):
                if isinstance(obj.get('link'), str):
                    urls.append(obj['link'])
                for v in obj.values():
                    walk(v)
            elif isinstance(obj, list):
                for v in obj:
                    walk(v)
        walk((q.get('learner') or {}))
    external = []
    for u in urls:
        host = (urlparse(u).hostname or '').lower()
        if not host:
            continue
        if any(host == h or host.endswith('.' + h) for h in site_hosts):
            continue
        external.append(u)
    return external


def default_exam_for_item(item: dict, exam_key: str | None = None) -> dict:
    code = item.get('exam_code') or (exam_key or item.get('exam_key') or 'EX-TEST')
    return {
        'vendor': 'Example Vendor',
        'certification': 'Example Certification',
        'exam_code': str(code),
        'name': str(code),
    }


def export_bank(bank: dict, *, exam: dict | None = None, domain_names: dict[str, str] | None = None,
                excluded: set[str] | None = None) -> dict:
    items = bank.get('questions') or []
    excluded = set(excluded or bank.get('scoring_excluded_question_keys') or [])
    questions = []
    for item in items:
        rec = dict(item)
        if rec.get('question_key') in excluded:
            rec['scoring_flag'] = True
        questions.append(export_item(rec, domain_names=domain_names))
    if exam is None:
        exam = default_exam_for_item(items[0] if items else {}, bank.get('exam_key'))
        exam['exam_code'] = exam.get('exam_code') or (bank.get('exam_key') or 'EXAM')
    return wrap_exam(exam, questions)


def main(argv=None):
    ap = argparse.ArgumentParser(description='Export a questions.json bank to one site-format v2 exam file.')
    ap.add_argument('--bank', required=True, type=Path, help='Path to pipeline questions.json')
    ap.add_argument('--out', required=True, type=Path, help='Output file or directory.')
    ap.add_argument('--exams-csv', type=Path)
    ap.add_argument('--domains-csv', type=Path)
    ap.add_argument('--vendors-csv', type=Path)
    ap.add_argument('--research', type=Path, help='Optional official research JSON for exam facts.')
    ap.add_argument('--simulator', type=Path, help='Optional simulator_settings.json')
    ap.add_argument('--src-root', type=Path, help='Exam output folder used to discover CSVs.')
    args = ap.parse_args(argv)
    bank = json.loads(args.bank.read_text(encoding='utf-8'))
    found = discover_sidecars(args.bank, args.src_root)
    exams_csv = args.exams_csv or found.get('exams_csv')
    domains_csv = args.domains_csv or found.get('domains_csv')
    vendors_csv = args.vendors_csv or found.get('vendors_csv')
    sim_path = args.simulator or found.get('simulator')
    simulator = json.loads(sim_path.read_text(encoding='utf-8')) if sim_path and Path(sim_path).is_file() else None
    research = json.loads(args.research.read_text(encoding='utf-8')) if args.research and args.research.is_file() else None
    domain_names = load_domain_names(domains_csv)
    exam = build_exam_section(
        bank, exams_csv=exams_csv, domains_csv=domains_csv,
        vendors_csv=vendors_csv, research=research, simulator=simulator,
    )
    doc = export_bank(bank, exam=exam, domain_names=domain_names)
    types = Counter(q['type'] for q in doc['questions'])
    statuses = Counter(q['answer']['status'] for q in doc['questions'])
    if args.out.suffix.lower() == '.json':
        dest = args.out
        dest.parent.mkdir(parents=True, exist_ok=True)
    else:
        args.out.mkdir(parents=True, exist_ok=True)
        dest = args.out / f"{exam['exam_code']}.site-format.v2.json"
    dest.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    ext = count_external_references(doc)
    summary = {
        'exam_key': bank.get('exam_key'),
        'exam_code': exam['exam_code'],
        'source': str(args.bank),
        'output': str(dest),
        'count': len(doc['questions']),
        'held_for_review': bank.get('held_for_review') or [],
        'types': dict(types),
        'answer_status': dict(statuses),
        'external_reference_links': len(ext),
        'external_reference_urls': ext,
    }
    (dest.parent / 'export-summary.json').write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n'
    )
    print(f"wrote {len(doc['questions'])} questions to {dest}")
    print('types', dict(types))
    print('answer_status', dict(statuses))
    print('external_reference_links', len(ext))
    return 0


if __name__ == '__main__':
    sys.exit(main())
