#!/usr/bin/env python3
"""Build the site v2 exam file from a technical PDF extract. No AI, no web.

Usage:
  build_technical_export.py --exam CODE --out-dir DIR [--catalog FILE] [--root DIR]

Reads extracted/split.json, extracted/visual_draft.json, extracted/ocr.json
and catalog.csv. Writes:
  {exam}.site-format.v2.json
  export/technical_report.json
  export/cannot-convert.json
  questions.json  (minimal technical bank for a later research pass)

Exam header comes from the catalog only. Explanation is omitted. Items with
no owner key are exported as answer_not_found (scoring_excluded, reviewer_needed).
Items the type rules cannot represent exactly are held in cannot-convert.
OCR confidence is recorded per item in the report.
"""
from __future__ import annotations
import argparse, csv, json, os, re, sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import paths
import qtypes
import export_question_v2 as E
import vision_util as V

DEFAULT_DOMAIN = 'Unassigned'


def _load_json(path, default=None):
    if not path or not os.path.isfile(path):
        return default
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)


def catalog_row(catalog_path, exam):
    if not catalog_path or not os.path.isfile(catalog_path):
        return {}
    with open(catalog_path, encoding='utf-8', newline='') as fh:
        for row in csv.DictReader(fh):
            if (row.get('exam_code') or '') == exam or (row.get('sheet_label') or '') == exam:
                return row
    return {}


def exam_header(row, exam, question_count):
    label = (row.get('sheet_label') or row.get('exam_code') or exam or '').strip() or exam
    vendor = (row.get('vendor') or '').strip() or 'Vendor'
    cert = (row.get('certification') or '').strip() or label
    name = (row.get('exam_name') or '').strip() or label
    return {
        'vendor': vendor,
        'certification': cert,
        'exam_code': (row.get('exam_code') or exam or label).strip(),
        'name': name,
        'question_count': int(question_count),
    }


def option_keys(opts):
    return sorted((opts or {}), key=lambda k: k.lower())


def letter_indexes(answer_raw, n_options):
    letters = re.findall(r'[A-H]', (answer_raw or '').upper())
    out = []
    for L in letters:
        i = ord(L) - ord('A')
        if 0 <= i < n_options and i not in out:
            out.append(i)
    return out


def alt_for(item, ocr_item, fname):
    lines = []
    for im in (ocr_item or {}).get('images') or []:
        if im.get('file') == fname:
            lines = [ln.get('t') for ln in (im.get('lines') or []) if (ln.get('t') or '').strip()]
            break
    text = ' '.join(lines).strip()
    if text:
        return text[:180]
    stem = (item.get('stem') or '').strip()
    if stem:
        return 'Supporting exhibit for this question.'
    return 'Supporting exhibit from the owner file.'


def media_list(item, exam_code, ocr_item):
    out = []
    for fn in item.get('question_images') or []:
        url = E.site_media_url(f'{exam_code}/media/{os.path.basename(fn)}')
        if not url:
            continue
        out.append({'url': url, 'alt': alt_for(item, ocr_item, fn)})
    return out


def table_block(table):
    if not table or not isinstance(table, list):
        return None
    width = max((len(r) for r in table), default=0)
    if width < 2 or len(table) < 2:
        return None
    rows = [list(r) + [''] * (width - len(r)) for r in table]
    columns = [E.plain_to_rich(c or ' ') for c in rows[0]]
    body = rows[1:]
    row_labels = [E.plain_to_rich(r[0] or ' ') for r in body]
    cells = [[E.plain_to_rich(c or ' ') for c in r] for r in body]
    return {'type': 'table', 'columns': columns, 'rows': row_labels, 'cells': cells}


def empty_key(typ):
    if typ in ('single_choice', 'true_false', 'image_based_choice', 'multiple_select', 'hotspot_multi'):
        return []
    return {}


def build_learner(typ, item, visual, ocr_item, exam_code):
    learner = {'stem': E.plain_to_rich(item.get('stem') or ' ')}
    opts = item.get('options') or {}
    keys = option_keys(opts)
    if typ in ('single_choice', 'true_false', 'image_based_choice', 'multiple_select') and keys:
        learner['choices'] = [E.plain_to_rich(opts[k] or ' ') for k in keys]
    media = media_list(item, exam_code, ocr_item)
    if typ in ('image_based_choice', 'active_screen', 'hotspot_single', 'hotspot_multi') or media:
        if typ in ('yes_no_matrix', 'inline_dropdown', 'multi_blank_dropdown') or media:
            if media:
                learner['media'] = media
    elif media:
        learner['media'] = media
    blocks = []
    table = item.get('ocr_table') or (ocr_item or {}).get('table')
    if table and typ not in ('yes_no_matrix',):
        blk = table_block(table)
        if blk:
            blocks.append(blk)
    if blocks:
        learner['content_blocks'] = blocks
    interaction = {}
    if typ == 'multiple_select':
        n = E.choose_n_from_text(item.get('stem') or '')
        if n:
            interaction['choose_n'] = n
    if typ == 'yes_no_matrix':
        rows = []
        for r in (visual or {}).get('rows') or []:
            rows.append({'id': r['id'], 'text': E.plain_to_rich(r.get('text') or ' ')})
        interaction['matrix'] = {
            'rows': rows,
            'columns': [
                {'id': 'yes', 'text': 'Yes'},
                {'id': 'no', 'text': 'No'},
            ],
        }
    if typ in ('inline_dropdown', 'multi_blank_dropdown'):
        content = {'blanks': []}
        texts = (visual or {}).get('text_lines') or []
        prompt = ' '.join(t.get('t') or t.get('text') or '' for t in texts).strip()
        segs = []
        if prompt:
            segs.append({'text': prompt + ' '})
        for b in (visual or {}).get('blanks') or []:
            bid = b['id']
            choices = b.get('choices') or []
            options = []
            seen = set()
            for i, ch in enumerate(choices):
                text = ch if isinstance(ch, str) else (ch.get('text') or '')
                oid = '%s_o%s' % (bid, i + 1)
                if oid in seen:
                    continue
                seen.add(oid)
                options.append({'id': oid, 'text': text or ' '})
            if len(options) < 2:
                return learner, interaction, 'drop-down blank %s has fewer than two options' % bid
            content['blanks'].append({'id': bid, 'choices': options, 'label': bid, 'selected': b.get('selected')})
            segs.append({'blank': bid})
        if not segs:
            segs = [{'blank': b['id']} for b in content['blanks']] or [{'text': ' '}]
        content['prompt_template'] = ''
        cloze = E.cloze_interaction(content, typ)
        cloze.pop('_option_id_map', None)
        # rebuild with unique option ids already set above; use our options directly
        cloze = {'cloze': {'segments': segs, 'blanks': [
            {'id': b['id'], 'label': b.get('label') or b['id'], 'kind': 'dropdown', 'options': b['choices']}
            for b in content['blanks']
        ]}}
        interaction.update(cloze)
        # stash option map for the key
        learner['_dropdown_options'] = {b['id']: b['choices'] for b in content['blanks']}
        learner['_dropdown_selected'] = {b['id']: b.get('selected') for b in content['blanks']}
    if typ in ('hotspot_single', 'hotspot_multi', 'active_screen'):
        regions = E.hotspot_regions(visual or {})
        if regions:
            interaction['hotspot_regions'] = regions
        elif typ != 'active_screen':
            return learner, interaction, 'hotspot regions were not read reliably'
    if typ == 'drag_drop':
        pairs = (visual or {}).get('pairs') or (visual or {}).get('matching_pairs') or []
        if pairs:
            interaction['matching_pairs'] = pairs
        else:
            return learner, interaction, 'drag and drop pairs were not read reliably'
    if typ == 'active_screen' and not interaction:
        # active_screen still needs something representable; keep media only
        pass
    if interaction:
        learner['interaction'] = {k: v for k, v in interaction.items() if not k.startswith('_')}
    return learner, interaction, None


def build_answer_key(typ, item, visual, learner):
    raw = item.get('answer_raw') or ''
    opts = item.get('options') or {}
    keys = option_keys(opts)
    if typ in ('single_choice', 'true_false', 'image_based_choice'):
        idx = letter_indexes(raw, len(keys))
        if not idx:
            return empty_key(typ), False
        return [idx[0]], True
    if typ == 'multiple_select':
        idx = letter_indexes(raw, len(keys))
        if not idx:
            return empty_key(typ), False
        return idx, True
    if typ == 'yes_no_matrix':
        key = dict((visual or {}).get('key') or {})
        rows = [r['id'] for r in (visual or {}).get('rows') or []]
        if not key or set(key) != set(rows):
            return key or {}, False
        return key, True
    if typ in ('inline_dropdown', 'multi_blank_dropdown'):
        selected = learner.get('_dropdown_selected') or {}
        options = learner.get('_dropdown_options') or {}
        key = {}
        complete = True
        for bid, sel in selected.items():
            opts_b = options.get(bid) or []
            match = None
            for o in opts_b:
                if o['text'] == sel or o['id'] == sel:
                    match = o['id']
                    break
            if match is None:
                complete = False
            else:
                key[bid] = match
        blanks = [b['id'] for b in ((learner.get('interaction') or {}).get('cloze') or {}).get('blanks') or []]
        if set(key) != set(blanks) or not key:
            complete = False
        return key, complete
    if typ == 'hotspot_single':
        key = (visual or {}).get('key')
        if isinstance(key, list) and key:
            return key[0], True
        if isinstance(key, str) and key:
            return key, True
        return {}, False
    if typ == 'hotspot_multi':
        key = (visual or {}).get('key')
        if isinstance(key, list) and key:
            return key, True
        return [], False
    if typ == 'drag_drop':
        key = (visual or {}).get('key')
        if isinstance(key, dict) and key:
            return key, True
        return {}, False
    if typ == 'active_screen':
        key = (visual or {}).get('key')
        if key:
            return key, True
        return {}, False
    return empty_key(typ), False


def strip_private(learner):
    learner = dict(learner)
    learner.pop('_dropdown_options', None)
    learner.pop('_dropdown_selected', None)
    if 'interaction' in learner:
        inter = {k: v for k, v in learner['interaction'].items() if not k.startswith('_')}
        if inter:
            learner['interaction'] = inter
        else:
            learner.pop('interaction', None)
    return learner


def export_one(item, visual, ocr_item, exam_code, domain, min_conf):
    result = qtypes.classify_detailed(item, visual, ocr=ocr_item, min_confidence=min_conf)
    hold = {
        'question_key': item.get('question_key'),
        'reason': result['reason'],
        'ocr_confidence': (ocr_item or {}).get('confidence'),
        'ocr_min_confidence': (ocr_item or {}).get('min_confidence'),
        'rule_id': result.get('rule_id'),
        'markers': result.get('markers') or [],
        'suggested_type': result.get('type'),
    }
    if result['held'] or not result['type']:
        return None, hold, result

    typ = result['type']
    learner, interaction, err = build_learner(typ, item, visual, ocr_item, exam_code)
    if err:
        hold['reason'] = err
        return None, hold, result
    key, complete = build_answer_key(typ, item, visual, learner)
    learner = strip_private(learner)
    has_owner_key = bool((item.get('answer_raw') or '').strip()) or complete
    if typ in ('yes_no_matrix', 'inline_dropdown', 'multi_blank_dropdown', 'hotspot_single', 'hotspot_multi', 'drag_drop'):
        has_owner_key = complete
        if typ in ('yes_no_matrix', 'inline_dropdown', 'multi_blank_dropdown') and not complete:
            hold['reason'] = 'answer marks in the image were not reliable enough to set a key'
            return None, hold, result
    status = 'owner_key' if has_owner_key else 'answer_not_found'
    if not has_owner_key:
        key = empty_key(typ)
    answer = {
        'answer_key': key,
        'status': status,
    }
    if status == 'answer_not_found':
        answer['scoring_excluded'] = True
        answer['reviewer_needed'] = True
    else:
        answer['scoring_excluded'] = False
        answer['reviewer_needed'] = False
    q = {
        'question_key': item['question_key'],
        'version': 1,
        'type': typ,
        'domain': domain,
        'learner': learner,
        'answer': answer,
    }
    return q, None, result


def technical_question_record(item, typ, result, ocr_item, answer, held):
    rec = {
        'question_key': item.get('question_key'),
        'stem': item.get('stem') or '',
        'options': item.get('options') or {},
        'answer_raw': item.get('answer_raw') or '',
        'question_type': typ or 'cannot_convert',
        'type_reason': result.get('reason'),
        'type_rule_id': result.get('rule_id'),
        'ocr_confidence': (ocr_item or {}).get('confidence'),
        'ocr_min_confidence': (ocr_item or {}).get('min_confidence'),
        'held': bool(held),
        'pages': item.get('pages') or [],
        'question_images': item.get('question_images') or [],
        'answer_images': item.get('answer_images') or [],
    }
    if answer:
        rec['answer_key'] = answer.get('answer_key')
        rec['answer_key_status'] = answer.get('status')
        rec['scoring_excluded'] = answer.get('scoring_excluded', False)
        rec['reviewer_needed'] = answer.get('reviewer_needed', False)
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser(description='Build a site v2 exam file from a PDF extract (no AI).')
    ap.add_argument('--exam', required=True)
    ap.add_argument('--out-dir', required=True, help='Exam output folder (out/CODE).')
    ap.add_argument('--catalog', help='catalog.csv (defaults to workspace catalog.csv).')
    ap.add_argument('--root', help='Workspace root.')
    args = ap.parse_args(argv)
    if args.root:
        paths.set_root(args.root)
    out = args.out_dir
    exam = args.exam
    split = _load_json(os.path.join(out, 'extracted', 'split.json'))
    if not isinstance(split, dict) or not split:
        print('build_technical_export: missing or empty extracted/split.json', file=sys.stderr)
        return 2
    visual = _load_json(os.path.join(out, 'extracted', 'visual_draft.json'), {}) or {}
    ocr = _load_json(os.path.join(out, 'extracted', 'ocr.json'), {}) or {}
    ocr_items = ocr.get('items') or {}
    catalog = args.catalog or os.path.join(paths.root(), 'catalog.csv')
    row = catalog_row(catalog, exam)
    rules = qtypes.load_rules()
    domain = (rules.get('default_domain') or DEFAULT_DOMAIN)
    min_conf = (V.load_ocr_config() or {}).get('hold_below_confidence')
    try:
        min_conf = float(min_conf) if min_conf is not None else None
    except (TypeError, ValueError):
        min_conf = 40.0

    questions = []
    held = []
    bank_qs = []
    by_type = {}
    for key in sorted(split, key=lambda k: (split[k].get('source_number') or 0, k)):
        item = split[key]
        vis = visual.get(key)
        ocr_item = ocr_items.get(key) or {}
        q, hold, result = export_one(item, vis, ocr_item, exam, domain, min_conf)
        if hold:
            held.append(hold)
            bank_qs.append(technical_question_record(item, result.get('type'), result, ocr_item, None, True))
            continue
        questions.append(q)
        by_type[q['type']] = by_type.get(q['type'], 0) + 1
        bank_qs.append(technical_question_record(item, q['type'], result, ocr_item, q['answer'], False))

    exam_sec = exam_header(row, exam, len(questions))
    doc = E.wrap_exam(exam_sec, questions)
    os.makedirs(os.path.join(out, 'export'), exist_ok=True)
    dest = os.path.join(out, f'{exam}.site-format.v2.json')
    with open(dest, 'w', encoding='utf-8') as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
        fh.write('\n')
    cannot_path = os.path.join(out, 'export', 'cannot-convert.json')
    with open(cannot_path, 'w', encoding='utf-8') as fh:
        json.dump(held, fh, indent=2, ensure_ascii=False)
        fh.write('\n')
    report = {
        'exam': exam,
        'detected': len(questions),
        'held': len(held),
        'total': len(split),
        'by_type': by_type,
        'site_file': dest,
        'tesseract': ocr.get('tesseract') or '',
        'tesseract_note': ocr.get('tesseract_note'),
        'items': [
            {
                'question_key': r['question_key'],
                'type': r['question_type'],
                'held': r['held'],
                'reason': r.get('type_reason'),
                'ocr_confidence': r.get('ocr_confidence'),
                'ocr_min_confidence': r.get('ocr_min_confidence'),
                'answer_key_status': r.get('answer_key_status'),
            }
            for r in bank_qs
        ],
    }
    with open(os.path.join(out, 'export', 'technical_report.json'), 'w', encoding='utf-8') as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
        fh.write('\n')
    bank = {
        'exam_key': exam,
        'exam_code': exam_sec['exam_code'],
        'questions': bank_qs,
        'cannot_convert': held,
        'counts': {'detected': len(questions), 'held': len(held), 'total': len(split)},
        'scoring_excluded_question_keys': [r['question_key'] for r in bank_qs if r.get('scoring_excluded')],
    }
    with open(os.path.join(out, 'questions.json'), 'w', encoding='utf-8') as fh:
        json.dump(bank, fh, indent=2, ensure_ascii=False)
        fh.write('\n')
    print('technical export: %s detected=%s held=%s types=%s file=%s' % (
        exam, len(questions), len(held), by_type, dest))
    return 0


if __name__ == '__main__':
    sys.exit(main())
