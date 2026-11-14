#!/usr/bin/env python3
"""One-time migration of a v1 questions.json bank to question format v2 drafts.

Maps v1 answer_key_status values (as_in_source_file and flagged_for_owner) to
canonical v2 statuses. Converts every item, including old image items, to a
real v2 HTML or SVG interactive type. Images become supporting or reference
media only. Does not invent keys or guess image content.

Deterministic checks (OCR or pdftotext versus transcription, table cell counts)
decide whether an image item converted exactly. Anything not exact is written
to cannot-convert.json and cannot-convert.md for the owner.

This script does not add image_legacy and does not map image items to
image_based_choice as a shortcut.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import sys
import zipfile
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import export_question_v2 as ex  # noqa: E402

STATUS_MAP = {
    'as_in_source_file': 'owner_key',
    'flagged_for_owner': 'owner_key',
    'owner_key': 'owner_key',
    'researched_official': 'researched_official',
    'researched_unverified': 'researched_unverified',
    'answer_not_found': 'answer_not_found',
}

# Answer-area / marked-key kinds must not go into the learner payload.
LEARNER_MEDIA_KINDS = {'exhibit'}
REVIEWER_MEDIA_KINDS = {'diagram', 'answer_image_review_only', 'answer_area', 'answer_review'}

UNCONFIRMED_KEY_RE = re.compile(
    r'could not confirm|key read visu|read visually|script found \d+ of',
    re.I,
)
IMAGE_ORIGIN_RE = re.compile(r'text and key read from images', re.I)

DASHES = {
    '\u2013': '-',
    '\u2014': '-',
    '\u2212': '-',
    '\u00ad': '',
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def content_of(item: dict) -> dict:
    return ((item.get('response_schema') or {}).get('content') or {})


def as_list(value):
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    return list(value)


def esc(text: str) -> str:
    return html.escape(text, quote=True)


def html_p(text: str) -> str:
    text = (text or '').strip()
    if not text:
        return ''
    parts = [f'<p>{esc(line.strip())}</p>' for line in text.split('\n') if line.strip()]
    return ''.join(parts) or f'<p>{esc(text)}</p>'


def html_table(headers: list[str], rows: list[list[str]]) -> str:
    thead = '<thead><tr>' + ''.join(f'<th>{esc(h)}</th>' for h in headers) + '</tr></thead>'
    body = []
    for row in rows:
        body.append('<tr>' + ''.join(f'<td>{esc(c)}</td>' for c in row) + '</tr>')
    return f'<table>{thead}<tbody>{"".join(body)}</tbody></table>'


def fold_tokens(text: str) -> list[str]:
    s = text or ''
    for a, b in DASHES.items():
        s = s.replace(a, b)
    s = s.replace('\u2018', "'").replace('\u2019', "'").replace('\u201c', '"').replace('\u201d', '"')
    s = s.lower()
    s = re.sub(r'[^a-z0-9]+', ' ', s)
    out = []
    trans = str.maketrans({'1': 'l', 'i': 'l', '|': 'l'})
    for tok in s.split():
        if len(tok) < 2:
            continue
        tok = tok.translate(trans)
        if tok == 'al':
            tok = 'ai'
        out.append(tok)
    return out


def phrase_in_ocr(phrase: str, ocr_text: str, ratio_min: float = 0.92) -> bool:
    pt = fold_tokens(phrase)
    ot = fold_tokens(ocr_text)
    if not pt:
        return True
    pj, oj = ' '.join(pt), ' '.join(ot)
    if pj in oj:
        return True
    n = len(pt)
    best = SequenceMatcher(None, pj, oj).ratio() if ot else 0.0
    if ot:
        for width in {n, max(1, n - 1), n + 1, n + 2}:
            if width > len(ot):
                best = max(best, SequenceMatcher(None, pj, oj).ratio())
                continue
            for i in range(0, len(ot) - width + 1):
                w = ' '.join(ot[i:i + width])
                best = max(best, SequenceMatcher(None, pj, w).ratio())
    return best >= ratio_min


def map_status(raw: str | None) -> tuple[str, str | None, bool]:
    raw = raw or 'owner_key'
    if raw not in STATUS_MAP:
        raise ValueError(f'unknown v1 answer_key_status {raw!r}')
    canon = STATUS_MAP[raw]
    legacy = raw if raw != canon else None
    reviewer = raw == 'flagged_for_owner'
    return canon, legacy, reviewer


def remap_type(item: dict) -> tuple[str, str | None]:
    typ = item.get('question_type') or item.get('type') or 'single_choice'
    if typ != 'image_based_choice':
        return typ, None
    key = item.get('answer_key') or {}
    ids = key.get('correct_option_ids') or []
    dest = 'multiple_select' if len(ids) >= 2 else 'single_choice'
    note = (
        f'remapped image_based_choice to {dest}; '
        'the exhibit is supporting media only, not the question'
    )
    return dest, note


def normalize_href(path):
    pth = (path or "").replace('\\', "/").strip()
    if not pth:
        return None
    if pth.startswith(("https://", "http://", "/", "#")):
        return pth
    return "/" + pth.lstrip("./")


def normalize_answer_key(key, typ):
    """Map v1 key shapes onto the v2 schema without inventing answers."""
    if not isinstance(key, dict):
        return key
    if typ == "yes_no_matrix" and "cells" not in key and "rows" in key:
        return {"cells": key["rows"]}
    return key


def significant_phrases(item: dict, trans: dict | None) -> list[str]:
    typ = item.get('question_type') or item.get('type')
    content = content_of(item)
    phrases: list[str] = []
    if typ in ('yes_no_matrix',) or (content.get('rows') and content.get('columns')):
        for row in content.get('rows') or []:
            text = row.get('text') if isinstance(row, dict) else str(row)
            if text:
                phrases.append(text)
        for col in content.get('columns') or []:
            text = col.get('text') if isinstance(col, dict) else str(col)
            if text:
                phrases.append(text)
        if trans:
            for row in trans.get('rows') or []:
                phrases.append(row if isinstance(row, str) else str(row))
        return phrases
    if typ in ('inline_dropdown', 'multi_blank_dropdown') or content.get('blanks'):
        tmpl = content.get('prompt_template') or (trans or {}).get('template') or ''
        for part in re.split(r'\{\{[^}]+\}\}', tmpl):
            if part.strip():
                phrases.append(part)
        for blank in content.get('blanks') or []:
            if blank.get('label'):
                # labels often repeat the template line; still check if long
                pass
            for ch in blank.get('choices') or blank.get('options') or []:
                text = ch.get('text') if isinstance(ch, dict) else str(ch)
                if text:
                    phrases.append(text)
        if trans:
            for opts in trans.get('blanks') or []:
                for text in opts:
                    phrases.append(text)
        return phrases
    if typ in ('active_screen', 'hotspot_single', 'hotspot_multi'):
        for region in content.get('regions') or []:
            if region.get('label'):
                phrases.append(region['label'])
        return phrases
    for opt in item.get('options') or []:
        if opt.get('text'):
            phrases.append(opt['text'])
    return phrases


def ocr_text_from_draft(draft: dict | None) -> str:
    if not draft:
        return ''
    if draft.get('ocr_text'):
        return str(draft['ocr_text'])
    parts = []
    for rec in draft.get('ocr') or []:
        if isinstance(rec, dict):
            parts.append(rec.get('t') or rec.get('text') or '')
        else:
            parts.append(str(rec))
    return ' '.join(parts)


def pdftotext_available() -> bool:
    from shutil import which
    return which('pdftotext') is not None


def count_matrix_cells(item: dict, trans: dict | None) -> tuple[int, int, int | None, int | None]:
    content = content_of(item)
    rows = content.get('rows') or []
    cols = content.get('columns') or []
    trows = None
    tcols = None
    if trans:
        if trans.get('rows'):
            trows = len(trans['rows'])
        if trans.get('columns'):
            tcols = len(trans['columns'])
    return len(rows), len(cols), trows, tcols


def is_image_item(item: dict, media_rows: list[dict], draft: dict | None) -> bool:
    typ = item.get('question_type') or ''
    if typ in ('image_based_choice', 'active_screen', 'hotspot_single', 'hotspot_multi', 'multimedia_stimulus'):
        return True
    for flag in item.get('flags') or []:
        if IMAGE_ORIGIN_RE.search(flag or ''):
            return True
    if media_rows or item.get('media') or draft:
        return True
    return False


def load_media_csv(path: Path | None) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    if not path or not path.is_file():
        return out
    with path.open(encoding='utf-8', newline='') as fh:
        for row in csv.DictReader(fh):
            qvk = row.get('question_version_key') or ''
            key = qvk.rsplit('-v', 1)[0] if qvk else ''
            if not key:
                continue
            out.setdefault(key, []).append(row)
    return out


def resolve_media_file(media_dir: Path | None, rel: str) -> Path | None:
    if not media_dir or not rel:
        return None
    rel = rel.replace('\\', '/').lstrip('/')
    candidates = [
        media_dir / rel,
        media_dir / Path(rel).name,
        media_dir / 'media' / Path(rel).name,
    ]
    if rel.startswith('media/'):
        candidates.append(media_dir / rel[len('media/'):])
    for c in candidates:
        if c.is_file():
            return c
    return None


def collect_images(item: dict, media_rows: list[dict], media_dir: Path | None, src_root: Path | None) -> list[dict]:
    found: list[dict] = []
    seen = set()
    for row in media_rows:
        rel = (row.get('path') or '').replace('\\', '/')
        rec = {
            'path': rel,
            'kind': row.get('kind') or '',
            'alt': (row.get('alt_text') or row.get('alt') or '').strip(),
            'sha256': (row.get('sha256') or '').lower(),
            'mime': row.get('mime_type') or '',
            'visibility': row.get('visibility') or '',
            'width': int(row['width']) if row.get('width') and str(row['width']).isdigit() else None,
            'height': int(row['height']) if row.get('height') and str(row['height']).isdigit() else None,
            'file': None,
        }
        path = resolve_media_file(media_dir, rel) or resolve_media_file(src_root, rel)
        if path:
            rec['file'] = path
            rec['sha256_computed'] = file_sha256(path)
        found.append(rec)
        seen.add(rel)
    for i, m in ex.iter_media(item):
        rel = (m.get('path') or m.get('href') or m.get('url') or '').replace('\\', '/')
        if not rel or rel in seen:
            continue
        rec = {
            'path': rel,
            'kind': m.get('kind') or 'exhibit',
            'alt': (m.get('alt') or m.get('alt_text') or '').strip(),
            'sha256': (m.get('sha256') or '').lower(),
            'mime': m.get('mime') or m.get('mime_type') or '',
            'visibility': m.get('visibility') or 'candidate',
            'width': m.get('width'),
            'height': m.get('height'),
            'file': None,
        }
        path = resolve_media_file(media_dir, rel) or resolve_media_file(src_root, rel)
        if path:
            rec['file'] = path
            rec['sha256_computed'] = file_sha256(path)
        found.append(rec)
    return found


def primary_image(images: list[dict]) -> dict | None:
    for kind in ('exhibit', 'diagram', 'answer_area'):
        for im in images:
            k = (im.get('kind') or '').lower()
            if k == kind or kind.replace('_', '-') in (im.get('path') or '').lower():
                if 'review' not in (im.get('path') or '').lower() or kind == 'exhibit':
                    return im
    for im in images:
        if 'review' not in (im.get('path') or '').lower():
            return im
    return images[0] if images else None


def check_image_conversion(item: dict, images: list[dict], draft: dict | None, trans: dict | None) -> list[dict]:
    """Return a list of cannot-convert records (empty if exact). Never guess."""
    issues = []
    qk = item['question_key']
    typ = item.get('question_type') or ''
    flags = item.get('flags') or []
    primary = primary_image(images)
    path = (primary or {}).get('path') or ''
    sha = (primary or {}).get('sha256_computed') or (primary or {}).get('sha256') or ''

    def issue(reason: str, suggested: str, img: dict | None = None):
        im = img or primary or {}
        issues.append({
            'question_key': qk,
            'image_path': im.get('path') or path or '',
            'sha256': (im.get('sha256_computed') or im.get('sha256') or sha or ''),
            'reason': reason,
            'suggested_option': suggested,
        })

    for im in images:
        expected = (im.get('sha256') or '').lower()
        computed = (im.get('sha256_computed') or '').lower()
        if expected and computed and expected != computed:
            issue(
                f"sha256 of {im.get('path')} does not match the media manifest "
                f"(manifest {expected}, file {computed})",
                'Replace the file or the manifest hash so they match, then re-run the migrator.',
                im,
            )
        if (im.get('path') or im.get('kind')) and not (computed or expected):
            issue(
                f"image {im.get('path') or im.get('kind')} has no sha256 and the file was not found",
                'Provide the source image and its sha256, then re-run the migrator.',
                im,
            )

    unconfirmed = [f for f in flags if UNCONFIRMED_KEY_RE.search(f or '')]
    if unconfirmed:
        issue(
            'the v1 bank records that the answer key was read visually and could not be confirmed by script: '
            + unconfirmed[0],
            'Owner should confirm the marked answers on the reviewer-only answer-area image. '
            'Keep the HTML transcription only after that confirmation. Do not invent a key.',
        )

    ocr = ocr_text_from_draft(draft)
    typ_now = typ
    if typ_now in ('yes_no_matrix',) or (content_of(item).get('rows') and content_of(item).get('columns')):
        nrows, ncols, trows, tcols = count_matrix_cells(item, trans)
        if trows is not None and trows != nrows:
            issue(
                f'table row count mismatch: bank has {nrows} rows, visual transcription has {trows}',
                'Recount the statement rows against the source image and correct the bank or the transcription. Do not guess a row.',
            )
        if tcols is not None and tcols != ncols:
            issue(
                f'table column count mismatch: bank has {ncols} columns, visual transcription has {tcols}',
                'Recount the columns against the source image and correct the bank or the transcription.',
            )
        if nrows == 0:
            issue(
                'yes/no matrix has no rows to transcribe',
                'Transcribe each statement row from the source image after a confirmed OCR or pdftotext check.',
            )

    if typ_now in ('active_screen', 'hotspot_single', 'hotspot_multi'):
        issue(
            'the item is a raster UI or hotspot image; an exact SVG transcription of every label and shape is not available, '
            'and region labels are descriptive rather than literal OCR strings',
            'Keep the existing interactive type with the original image as supporting hotspot media and the existing regions. '
            'Supply an exact SVG only if every label and shape can be transcribed without guesswork. Owner should confirm the region boxes.',
        )
        return issues

    if typ_now == 'image_based_choice' and not ocr:
        issue(
            'item was stored as image_based_choice; the exhibit is a raster UI screenshot with no OCR or text layer to confirm alt text or labels, '
            'and no exact SVG is available',
            'Use single_choice (or multiple_select) with the existing HTML stem and choices; keep the screenshot as supporting media; '
            'confirm the alt text against the exhibit or supply OCR. Do not invent an SVG. Do not leave the question as image_based_choice.',
        )
        return issues

    image_origin = any(IMAGE_ORIGIN_RE.search(f or '') for f in flags) or typ_now == 'image_based_choice' or bool(draft)
    if image_origin and typ_now not in ('active_screen', 'hotspot_single', 'hotspot_multi'):
        if not ocr:
            issue(
                'no OCR or text layer was available to confirm an exact transcription of the source image; content will not be guessed',
                'Run OCR or pdftotext on the source image and re-run the migrator, or transcribe manually and confirm every phrase and cell count.',
            )
        else:
            missing = []
            for phrase in significant_phrases(item, trans):
                if len(' '.join(fold_tokens(phrase))) < 8:
                    continue
                if not phrase_in_ocr(phrase, ocr):
                    missing.append(phrase)
            if missing:
                preview = missing[0] if len(missing[0]) <= 160 else missing[0][:157] + '...'
                issue(
                    f'{len(missing)} transcribed phrase(s) are not confirmed in the image OCR or text layer; first unmatched phrase: {preview}',
                    'Re-transcribe the unmatched text from the source image and confirm it against OCR or pdftotext. Do not guess missing words. Then keep the real interactive type as HTML.',
                )

    return _dedupe_issues(issues)


def _dedupe_issues(issues: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for it in issues:
        key = (it['question_key'], it['image_path'], it['reason'])
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def build_stem_and_interaction(item: dict, typ: str) -> tuple[dict, dict, dict | None]:
    content = content_of(item)
    prompt = item.get('prompt_text') or content.get('prompt') or ''
    interaction: dict = {}
    constraints = None

    if typ in ('single_choice', 'true_false', 'multiple_select'):
        opts = ex.options(item)
        interaction = {'options': opts} if opts else {}
        if typ in ('single_choice', 'true_false'):
            interaction['choose_n'] = 1
            constraints = {'choose_n': 1}
        stem_html = html_p(prompt)
        return {'format': 'html', 'text': stem_html}, interaction, constraints

    if typ == 'yes_no_matrix' or (content.get('rows') and content.get('columns')):
        rows = content.get('rows') or []
        cols = content.get('columns') or []
        headers = ['Statement'] + [(c.get('text') or c.get('id') or '') for c in cols]
        table_rows = []
        for row in rows:
            label = row.get('text') or row.get('label') or ''
            table_rows.append([label] + ['' for _ in cols])
        stem_html = html_p(prompt) + html_table(headers, table_rows)
        interaction = {
            'rows': [{'id': r.get('id'), 'text': r.get('text') or ''} for r in rows],
            'columns': [{'id': c.get('id'), 'text': c.get('text') or ''} for c in cols],
        }
        return {'format': 'html', 'text': stem_html}, interaction, constraints

    if typ in ('inline_dropdown', 'multi_blank_dropdown') or content.get('blanks'):
        tmpl = content.get('prompt_template') or ''
        visible = re.sub(r'\{\{([^}]+)\}\}', r'[\1]', tmpl)
        stem_html = html_p(prompt) + (html_p(visible) if visible and visible != prompt else '')
        slots = []
        for blank in content.get('blanks') or []:
            choices = []
            for ch in blank.get('choices') or blank.get('options') or []:
                if isinstance(ch, dict):
                    choices.append({'id': str(ch.get('id')), 'text': ch.get('text') or ''})
                else:
                    choices.append({'id': str(ch), 'text': str(ch)})
            slots.append({
                'id': str(blank.get('id')),
                'input': 'dropdown',
                'choices': choices,
            })
        interaction = {
            'prompt_with_slots': tmpl or visible,
            'slots': slots,
        }
        return {'format': 'html', 'text': stem_html}, interaction, constraints

    if typ in ('active_screen', 'hotspot_single', 'hotspot_multi'):
        regions = []
        for region in content.get('regions') or []:
            coords = region.get('normalized_coordinates') or region.get('coords') or []
            regions.append({
                'id': region.get('id'),
                'shape': region.get('shape') or 'rect',
                'coords': coords,
                'label': region.get('label') or '',
            })
        interaction = {'regions': regions}
        if content.get('image_url') or content.get('image_alt'):
            pass
        return {'format': 'html', 'text': html_p(prompt)}, interaction, constraints

    # Fallback: still emit HTML stem for any other registry type; keep schema content as interaction when present.
    interaction = {k: v for k, v in content.items() if k not in {'prompt', 'image_url', 'image_alt'}}
    opts = ex.options(item)
    if opts and 'options' not in interaction:
        interaction['options'] = opts
    return {'format': 'html', 'text': html_p(prompt)}, interaction, constraints


def learner_and_reference_media(images: list[dict]) -> tuple[list[dict], list[dict]]:
    learner = []
    reference = []
    for i, im in enumerate(images, 1):
        sha = (im.get('sha256_computed') or im.get('sha256') or '').lower()
        if len(sha) != 64:
            continue
        alt = (im.get('alt') or '').strip() or 'Original source image kept as a reviewer-only reference asset.'
        kind = (im.get('kind') or '').lower()
        vis = (im.get('visibility') or '').lower()
        path = im.get('path') or ''
        rec = {
            'id': f'm{i}',
            'kind': 'svg' if path.lower().endswith('.svg') or kind == 'svg' else 'image',
            'alt': alt,
            'sha256': sha,
            'href': normalize_href(path),
            'role': 'exhibit' if kind == 'exhibit' else ('diagram' if kind == 'diagram' else 'reference'),
            'original_asset': {
                'sha256': sha,
                'href': normalize_href(path),
                'note': 'Original image kept as a reference asset.',
            },
        }
        if im.get('width'):
            rec['width'] = int(im['width'])
        if im.get('height'):
            rec['height'] = int(im['height'])
        if im.get('mime'):
            rec['mime'] = im['mime']
            rec['original_asset']['mime'] = im['mime']
        rec = {k: v for k, v in rec.items() if v is not None}
        rec['original_asset'] = {k: v for k, v in rec['original_asset'].items() if v is not None}
        is_review = (
            kind in REVIEWER_MEDIA_KINDS
            or vis in {'reviewer_only', 'reviewer'}
            or 'answer-review' in path.lower()
            or 'answer-area' in path.lower()
        )
        is_exhibit = kind in LEARNER_MEDIA_KINDS or (vis == 'candidate' and 'exhibit' in path.lower())
        if is_exhibit and not is_review and alt:
            learner.append(rec)
        else:
            reference.append(rec)
    return learner, reference


def migrate_item(item: dict, *, exam_key: str | None, media_rows: list[dict],
                 media_dir: Path | None, src_root: Path | None,
                 draft: dict | None, trans: dict | None,
                 excluded: set[str]) -> tuple[dict, list[dict]]:
    aks, legacy, reviewer_from_status = map_status(item.get('answer_key_status'))
    typ, type_note = remap_type(item)
    images = collect_images(item, media_rows, media_dir, src_root)
    image_item = is_image_item(item, media_rows, draft)
    issues = check_image_conversion(item, images, draft, trans) if image_item else []

    # Build a canonical item for the shared exporter, then replace stem/interaction/media.
    prepared = dict(item)
    prepared['question_type'] = typ
    prepared['answer_key_status'] = aks
    prepared['legacy_answer_key_status'] = legacy
    if reviewer_from_status:
        prepared['human_review_required'] = True
    doc = ex.export_item(prepared)
    doc['answer']['answer_key'] = normalize_answer_key(item.get('answer_key'), typ)
    if exam_key and not doc['meta'].get('exam_key'):
        doc['meta']['exam_key'] = exam_key
    if item['question_key'] in excluded:
        doc['meta']['scoring_excluded'] = True
    stem, interaction, constraints = build_stem_and_interaction(item, typ)
    doc['type'] = typ
    doc['learner']['stem'] = stem
    doc['learner']['interaction'] = interaction
    if constraints:
        doc['learner']['constraints'] = constraints
    elif typ not in ('single_choice', 'true_false'):
        doc['learner'].pop('constraints', None)
    learner_media, reference_media = learner_and_reference_media(images)
    if typ in ('active_screen', 'hotspot_single', 'hotspot_multi'):
        # The raster is supporting interaction media, not the question text.
        for rec in reference_media:
            path = (rec.get('href') or '').lower()
            if 'answer-review' in path:
                continue
            if rec.get('alt') and rec not in learner_media:
                rec = dict(rec)
                rec['role'] = 'diagram'
                learner_media.append(rec)
        if learner_media and not interaction.get('media_id'):
            interaction['media_id'] = learner_media[0]['id']
            doc['learner']['interaction'] = interaction
    if learner_media:
        doc['learner']['media'] = learner_media
    else:
        doc['learner'].pop('media', None)
    if reference_media:
        doc['meta']['reference_media'] = reference_media
    if type_note:
        notes = list(doc['meta'].get('conversion_notes') or [])
        notes.append(type_note)
        doc['meta']['conversion_notes'] = notes
    doc['meta']['conversion_exact'] = not issues
    if issues:
        doc['meta']['reviewer_needed'] = True
        flags = list(doc['meta'].get('flags') or [])
        flags.append('v2 conversion not exact; see cannot-convert report')
        doc['meta']['flags'] = flags
    for rec in issues:
        rec['exam_key'] = exam_key or item.get('exam_key') or ''
        rec['v2_type'] = typ
    return doc, issues


def write_cannot_convert(path_stem: Path, records: list[dict], append: bool, summary: dict) -> tuple[Path, Path]:
    json_path = path_stem if path_stem.suffix == '.json' else path_stem.with_suffix('.json')
    if path_stem.suffix in {'.json', '.md'}:
        json_path = path_stem.with_suffix('.json')
        md_path = path_stem.with_suffix('.md')
    else:
        json_path = Path(str(path_stem) + '.json') if path_stem.suffix == '' else path_stem.with_suffix('.json')
        md_path = Path(str(path_stem) + '.md') if path_stem.suffix == '' else path_stem.with_suffix('.md')
    existing = []
    summaries = []
    if append and json_path.is_file():
        prev = load_json(json_path)
        existing = prev.get('items') or []
        if isinstance(prev.get('summaries'), list):
            summaries = list(prev['summaries'])
        elif prev.get('summary'):
            summaries = [prev['summary']]
    items = existing + records
    if summary:
        summaries.append(summary)
    payload = {
        'schema': 'question-v2-cannot-convert.v1',
        'count': len(items),
        'question_keys': sorted({r['question_key'] for r in items}),
        'items': items,
        'summaries': summaries,
    }
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    lines = [
        '# Cannot-convert image questions',
        '',
        'Items the v1-to-v2 migrator could not convert exactly. Content was not guessed.',
        f'Count: {len(items)}',
        '',
    ]
    if not items:
        lines.append('None. Every image question that was present converted exactly, or the bank had no image questions.')
        lines.append('')
    for rec in items:
        lines.append(f"## {rec.get('exam_key') or ''} {rec['question_key']}".strip())
        lines.append('')
        lines.append(f"- question_key: `{rec['question_key']}`")
        if rec.get('exam_key'):
            lines.append(f"- exam_key: `{rec['exam_key']}`")
        if rec.get('v2_type'):
            lines.append(f"- suggested v2 type: `{rec['v2_type']}`")
        lines.append(f"- image path: `{rec.get('image_path') or '(none)'}`")
        lines.append(f"- sha256: `{rec.get('sha256') or '(none)'}`")
        lines.append(f"- reason: {rec['reason']}")
        lines.append(f"- suggested option: {rec['suggested_option']}")
        lines.append('')
    md_path.write_text('\n'.join(lines), encoding='utf-8', newline='\n')
    return json_path, md_path


def discover_from_exam_dir(exam_dir: Path) -> dict:
    bank = exam_dir / 'questions.json'
    if not bank.is_file():
        matches = list(exam_dir.rglob('questions.json'))
        bank = matches[0] if matches else bank
    media_csv = exam_dir / 'import' / 'question_media_assets.csv'
    if not media_csv.is_file():
        found = list(exam_dir.rglob('question_media_assets.csv'))
        media_csv = found[0] if found else None
    else:
        media_csv = media_csv
    draft = exam_dir / 'extracted' / 'visual_draft.json'
    trans = exam_dir / 'extracted' / 'visual_transcription.json'
    media_dir = exam_dir / 'media' if (exam_dir / 'media').is_dir() else exam_dir
    return {
        'bank': bank,
        'media_csv': media_csv if media_csv and media_csv.is_file() else None,
        'visual_draft': draft if draft.is_file() else None,
        'visual_transcription': trans if trans.is_file() else None,
        'media_dir': media_dir if media_dir.is_dir() else None,
        'src_root': exam_dir,
    }


def extract_package_zip(zip_path: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest)
    matches = list(dest.rglob('questions.json'))
    if not matches:
        raise FileNotFoundError(f'no questions.json in {zip_path}')
    return matches[0].parent


def migrate_bank(bank_path: Path, out_dir: Path, *, media_csv: Path | None,
                 visual_draft: Path | None, visual_transcription: Path | None,
                 media_dir: Path | None, src_root: Path | None) -> dict:
    bank = load_json(bank_path)
    items = bank.get('questions') or []
    exam_key = bank.get('exam_key')
    excluded = set(bank.get('scoring_excluded_question_keys') or [])
    media_index = load_media_csv(media_csv)
    draft_index = load_json(visual_draft) if visual_draft else {}
    trans_index = load_json(visual_transcription) if visual_transcription else {}
    if not isinstance(draft_index, dict):
        draft_index = {}
    if not isinstance(trans_index, dict):
        trans_index = {}
    out_dir.mkdir(parents=True, exist_ok=True)
    types = Counter()
    statuses = Counter()
    exact = 0
    image_items = 0
    issues: list[dict] = []
    written = []
    for item in items:
        key = item['question_key']
        doc, item_issues = migrate_item(
            item,
            exam_key=exam_key,
            media_rows=media_index.get(key) or [],
            media_dir=media_dir,
            src_root=src_root,
            draft=draft_index.get(key),
            trans=trans_index.get(key),
            excluded=excluded,
        )
        if is_image_item(item, media_index.get(key) or [], draft_index.get(key)):
            image_items += 1
        if item_issues:
            issues.extend(item_issues)
        else:
            exact += 1
        types[doc['type']] += 1
        statuses[doc['meta']['answer_key_status']] += 1
        dest = out_dir / f"{doc['question_key']}.v{doc['version']}.json"
        dest.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
        written.append(dest)
    summary = {
        'exam_key': exam_key,
        'source': str(bank_path),
        'count': len(written),
        'held_for_review': bank.get('held_for_review') or [],
        'types': dict(types),
        'answer_key_status': dict(statuses),
        'image_items': image_items,
        'converted_exactly': exact,
        'cannot_convert': len({r['question_key'] for r in issues}),
        'cannot_convert_records': len(issues),
        'record_status': 'draft',
        'schema_version': 'question.v2',
    }
    (out_dir / 'migrate-summary.json').write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n'
    )
    return {'summary': summary, 'issues': issues, 'written': written}


def main(argv=None):
    ap = argparse.ArgumentParser(description='Migrate a v1 questions.json bank to v2 drafts.')
    ap.add_argument('--bank', type=Path, help='Path to pipeline questions.json')
    ap.add_argument('--exam-dir', type=Path, help='Exam output folder that contains questions.json')
    ap.add_argument('--package-zip', type=Path, help='A packaged exam zip that contains questions.json')
    ap.add_argument('--out', required=True, type=Path, help='Output directory for v2 drafts')
    ap.add_argument('--cannot-convert', required=True, type=Path,
                    help='Path stem or .json path for the cannot-convert report (writes .json and .md)')
    ap.add_argument('--media-dir', type=Path, help='Folder of media files (optional)')
    ap.add_argument('--media-csv', type=Path, help='question_media_assets.csv (optional)')
    ap.add_argument('--visual-draft', type=Path, help='visual_draft.json with OCR tokens (optional)')
    ap.add_argument('--visual-transcription', type=Path, help='visual_transcription.json (optional)')
    ap.add_argument('--extract-to', type=Path, help='Where to extract --package-zip (default: a sibling work folder)')
    ap.add_argument('--append', action='store_true', help='Append to an existing cannot-convert report')
    args = ap.parse_args(argv)

    discovered = {
        'bank': args.bank,
        'media_csv': args.media_csv,
        'visual_draft': args.visual_draft,
        'visual_transcription': args.visual_transcription,
        'media_dir': args.media_dir,
        'src_root': None,
    }
    if args.package_zip:
        dest = args.extract_to or (args.out.parent / '_pkg' / args.package_zip.stem)
        exam_dir = extract_package_zip(args.package_zip, dest)
        discovered.update({k: v for k, v in discover_from_exam_dir(exam_dir).items() if v})
        discovered['src_root'] = exam_dir
    elif args.exam_dir:
        discovered.update({k: v for k, v in discover_from_exam_dir(args.exam_dir).items() if v})
        discovered['src_root'] = args.exam_dir
    # CLI flags win
    if args.bank:
        discovered['bank'] = args.bank
    if args.media_csv:
        discovered['media_csv'] = args.media_csv
    if args.visual_draft:
        discovered['visual_draft'] = args.visual_draft
    if args.visual_transcription:
        discovered['visual_transcription'] = args.visual_transcription
    if args.media_dir:
        discovered['media_dir'] = args.media_dir
    if not discovered.get('bank') or not Path(discovered['bank']).is_file():
        print('error: a questions.json bank is required (--bank, --exam-dir, or --package-zip)', file=sys.stderr)
        return 2

    result = migrate_bank(
        Path(discovered['bank']),
        args.out,
        media_csv=discovered.get('media_csv'),
        visual_draft=discovered.get('visual_draft'),
        visual_transcription=discovered.get('visual_transcription'),
        media_dir=discovered.get('media_dir'),
        src_root=discovered.get('src_root'),
    )
    json_path, md_path = write_cannot_convert(
        args.cannot_convert, result['issues'], args.append, result['summary']
    )
    print(f"wrote {result['summary']['count']} files to {args.out}")
    print('types', result['summary']['types'])
    print('answer_key_status', result['summary']['answer_key_status'])
    print('image_items', result['summary']['image_items'])
    print('converted_exactly', result['summary']['converted_exactly'])
    print('cannot_convert', result['summary']['cannot_convert'], 'records', result['summary']['cannot_convert_records'])
    print('cannot-convert report', json_path, md_path)
    return 0


if __name__ == '__main__':
    sys.exit(main())
