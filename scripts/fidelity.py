#!/usr/bin/env python3
"""Config-driven fidelity gate for the technical export. No AI, no exam-specific rules.

Checks (all must pass to export):
  1. Word coverage of the PDF text block vs the exported question (100%, no extras).
  2. Image OCR: every word at/above the per-word threshold, overall at/above the
     overall threshold, and two OCR passes agree on the text.
  3. Exactly one type rule matches, and the interaction/key shape agrees with it.
  4. The answer key comes from text or from two agreeing pixel methods, and maps
     to existing choice/blank/row ids. Never inferred.
Reports one line per question in export/fidelity.json and export/fidelity.md.
"""
from __future__ import annotations
import json, os, re, sys
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))
import paths
import site_settings
import extract_owner_pdf as X

DEFAULT_TOKEN = r'[A-Za-z0-9]+'


def load_fidelity_config(root=None):
    root = root or paths.skill_root()
    path = os.path.join(root, 'config', 'fidelity.json')
    with open(path, encoding='utf-8') as fh:
        cfg = json.load(fh)
    ocr_path = os.path.join(root, 'config', 'ocr.json')
    if os.path.isfile(ocr_path):
        with open(ocr_path, encoding='utf-8') as fh:
            ocr = json.load(fh)
        if isinstance(ocr.get('fidelity'), dict):
            merged = dict(ocr['fidelity'])
            merged.update(cfg.get('ocr') or {})
            cfg['ocr'] = merged
    return cfg


def _compile_list(patterns):
    out = []
    for p in patterns or []:
        if p:
            out.append(re.compile(p, re.I | re.M))
    return out


def strip_source_text(text, cfg, deny=None):
    """Remove only brand/boilerplate and the configured labels from a source block."""
    text = text or ''
    lines = []
    line_rx = _compile_list(cfg.get('strip_line_patterns'))
    prefix = re.compile(cfg.get('strip_option_prefix') or r'^[A-H][\.\):]\s*', re.I)
    for raw in text.replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        t = raw.strip()
        if not t:
            continue
        if deny is not None and deny.search(t):
            continue
        if any(rx.match(t) for rx in line_rx):
            continue
        t = prefix.sub('', t).strip()
        if t:
            lines.append(t)
    body = ' '.join(lines)
    # Labels are stripped only as whole lines (strip_line_patterns). Do not
    # delete those words when they appear in the stem or choices.
    return re.sub(r'\s+', ' ', body).strip()


def make_deny(cfg=None):
    if cfg is not None and not cfg.get('use_brand_denylist', True) and not cfg.get('use_contact_patterns', True):
        return re.compile(r'a\A')
    S = site_settings.load()
    if cfg is not None and not cfg.get('use_contact_patterns', True):
        S = dict(S)
        pol = dict(S.get('policy') or {})
        pol['contact_patterns'] = {}
        S['policy'] = pol
    if cfg is not None and not cfg.get('use_brand_denylist', True):
        S = dict(S)
        S['brand_denylist'] = []
    return X.compile_deny(S)


def tokenize(text, cfg=None):
    cfg = cfg or {}
    pat = cfg.get('token_pattern') or DEFAULT_TOKEN
    raw = text or ''
    if not cfg.get('case_sensitive'):
        raw = raw.lower()
    return re.findall(pat, raw)


def token_set(text, cfg=None):
    return set(tokenize(text, cfg))


def coverage_report(source_tokens, dest_tokens):
    src = set(source_tokens)
    dest = set(dest_tokens)
    if not src:
        pct = 100.0 if not dest else 0.0
        # empty source and empty dest: 100%. empty source with dest extras: 0? extras still fail separately.
        pct = 100.0
    else:
        pct = 100.0 * len(src & dest) / len(src)
    return {
        'coverage_percent': round(pct, 2),
        'source_word_count': len(src),
        'export_word_count': len(dest),
        'missing_words': sorted(src - dest),
        'extra_words': sorted(dest - src),
        'complete': (not src or src <= dest) and not (dest - src),
    }


def source_pdf_text(item, cfg, deny=None):
    block = item.get('source_text')
    if not block:
        parts = [item.get('stem') or '']
        for k in sorted((item.get('options') or {}), key=lambda x: x.lower()):
            parts.append((item.get('options') or {}).get(k) or '')
        block = '\n'.join(p for p in parts if p)
    return strip_source_text(block, cfg, deny=deny)


def _plain_rich(value):
    """Flatten site rich_text (list of paragraphs with content/text) to a string."""
    if value is None:
        return ''
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        parts = []
        if value.get('text'):
            parts.append(value['text'])
        if 'content' in value:
            parts.append(_plain_rich(value.get('content')))
        for key in ('spans', 'items', 'children'):
            if value.get(key):
                parts.append(_plain_rich(value.get(key)))
        return ' '.join(p for p in parts if p)
    if isinstance(value, list):
        return ' '.join(p for p in (_plain_rich(v) for v in value) if p)
    return str(value)


def export_text(question):
    """All learner-visible text that will go to the site file, including image alt."""
    parts = []
    learner = (question or {}).get('learner') or {}
    parts.append(_plain_rich(learner.get('stem')))
    for c in learner.get('choices') or []:
        if isinstance(c, dict) and 'text' in c:
            parts.append(_plain_rich(c.get('text')))
            for m in c.get('media') or []:
                if isinstance(m, dict):
                    parts.append(m.get('alt') or '')
        else:
            parts.append(_plain_rich(c))
    for b in learner.get('content_blocks') or []:
        if not isinstance(b, dict):
            continue
        parts.append(_plain_rich(b.get('text')))
        for m in b.get('media') or b.get('images') or []:
            if isinstance(m, dict):
                parts.append(m.get('alt') or '')
    for m in learner.get('media') or []:
        if isinstance(m, dict):
            parts.append(m.get('alt') or '')
    inter = learner.get('interaction') or {}
    matrix = inter.get('matrix') or {}
    for row in matrix.get('rows') or []:
        if isinstance(row, dict):
            parts.append(_plain_rich(row.get('text') or row.get('id') or ''))
        else:
            parts.append(_plain_rich(row))
    for col in matrix.get('columns') or []:
        if isinstance(col, dict):
            parts.append(_plain_rich(col.get('text') or col.get('id') or ''))
        else:
            parts.append(_plain_rich(col))
    cloze = inter.get('cloze') or {}
    for seg in cloze.get('segments') or []:
        if isinstance(seg, dict):
            parts.append(_plain_rich(seg.get('text') or ''))
        else:
            parts.append(_plain_rich(seg))
    for blank in cloze.get('blanks') or []:
        if isinstance(blank, dict):
            # blank ids like blank1 are not PDF words; do not require them in coverage
            for opt in blank.get('options') or []:
                if isinstance(opt, dict):
                    parts.append(_plain_rich(opt.get('text') or opt.get('id') or ''))
                else:
                    parts.append(_plain_rich(opt))
    return ' '.join(p for p in parts if p)


def ocr_words_text(ocr_item, min_word=None):
    """Words from OCR'd images (primary pass), optionally only those at/above min_word."""
    parts = []
    for im in (ocr_item or {}).get('images') or []:
        for w in im.get('words') or []:
            if isinstance(w, dict):
                tok = w.get('text') or ''
                conf = w.get('conf')
                if min_word is not None and conf is not None:
                    try:
                        if float(conf) < float(min_word):
                            continue
                    except (TypeError, ValueError):
                        pass
                parts.append(tok)
            else:
                parts.append(str(w))
        if not im.get('words') and im.get('text'):
            parts.append(im.get('text'))
    if not parts and (ocr_item or {}).get('text'):
        parts.append(ocr_item.get('text'))
    return ' '.join(p for p in parts if p)


def check_pdf_coverage(item, question, cfg, deny=None):
    pdf_text = source_pdf_text(item, cfg, deny=deny)
    src = token_set(pdf_text, cfg)
    dest = token_set(export_text(question), cfg)
    # Image OCR words that belong in the source bag: unioned so dest must cover them too.
    ocr_cfg = cfg.get('ocr') or {}
    min_word = ocr_cfg.get('min_word_confidence')
    ocr_text = ocr_words_text(item.get('_ocr_item') if isinstance(item, dict) else None, min_word=min_word)
    # caller passes ocr via question sidecar? handled in evaluate()
    report = coverage_report(src, dest)
    report['pdf_text_normalized'] = pdf_text
    return report


def check_image_ocr(ocr_item, cfg):
    ocr_cfg = cfg.get('ocr') or {}
    min_word = float(ocr_cfg.get('min_word_confidence', 90))
    min_overall = float(ocr_cfg.get('min_overall_confidence', 95))
    require_agree = bool(ocr_cfg.get('require_pass_agreement', True))
    images = (ocr_item or {}).get('images') or []
    if not images and not (ocr_item or {}).get('text'):
        return {
            'ok': True,
            'min_word_confidence': None,
            'overall_confidence': None,
            'low_words': [],
            'agree': True,
            'reason': None,
        }
    low = []
    mins = []
    overalls = []
    disagree = []
    for im in images:
        words = im.get('words') or []
        confs = []
        for w in words:
            if not isinstance(w, dict):
                continue
            try:
                c = float(w.get('conf'))
            except (TypeError, ValueError):
                continue
            confs.append(c)
            if c < min_word:
                low.append({'file': im.get('file'), 'text': w.get('text'), 'conf': c})
        if confs:
            mins.append(min(confs))
            overalls.append(sum(confs) / len(confs))
        elif im.get('mean_confidence') is not None:
            try:
                overalls.append(float(im.get('mean_confidence')))
            except (TypeError, ValueError):
                pass
        if im.get('min_confidence') is not None:
            try:
                mins.append(float(im['min_confidence']))
            except (TypeError, ValueError):
                pass
        if require_agree and im.get('agree') is False:
            disagree.append(im.get('file') or 'image')
        passes = im.get('passes') or {}
        if require_agree and len(passes) >= 2:
            norms = []
            for p in passes.values():
                txt = (p.get('text') if isinstance(p, dict) else '') or ''
                norms.append(' '.join(tokenize(txt, cfg)))
            if len(set(norms)) > 1:
                disagree.append(im.get('file') or 'image')
    item_agree = (ocr_item or {}).get('agree')
    if require_agree and item_agree is False:
        disagree.append('item')
    min_w = min(mins) if mins else (ocr_item or {}).get('min_confidence')
    overall = None
    if overalls:
        overall = sum(overalls) / len(overalls)
    elif (ocr_item or {}).get('confidence') is not None:
        try:
            overall = float(ocr_item['confidence'])
        except (TypeError, ValueError):
            overall = None
    reasons = []
    if low:
        bits = ['%s (%.1f)' % (w.get('text'), w.get('conf') or 0) for w in low[:12]]
        reasons.append('OCR words below %s: %s' % (int(min_word), ', '.join(bits)))
    if overall is not None and overall < min_overall:
        reasons.append('OCR overall confidence %.1f is below %s' % (overall, int(min_overall)))
    if min_w is not None:
        try:
            if float(min_w) < min_word and not low:
                reasons.append('OCR minimum word confidence %.1f is below %s' % (float(min_w), int(min_word)))
        except (TypeError, ValueError):
            pass
    if disagree:
        reasons.append('OCR passes disagree on: %s' % ', '.join(sorted(set(str(d) for d in disagree))))
    return {
        'ok': not reasons,
        'min_word_confidence': min_w,
        'overall_confidence': overall,
        'low_words': low,
        'agree': not disagree,
        'reason': '; '.join(reasons) if reasons else None,
    }


def unique_type_ok(result):
    matched = result.get('matched_rules')
    if matched is None:
        # fallback: a single rule_id and not held for type ambiguity
        rid = result.get('rule_id')
        return bool(rid) and not result.get('held'), [rid] if rid else []
    ids = [r.get('id') if isinstance(r, dict) else r for r in matched]
    return len(ids) == 1, ids


def _choose_n(stem):
    m = re.search(r'\b(?:which|choose|select)\s+(two|three|four|five)\b', stem or '', re.I)
    if not m:
        return None
    return {'two': 2, 'three': 3, 'four': 4, 'five': 5}[m.group(1).lower()]


def interaction_agrees(typ, question, item=None):
    """Shape of the learner interaction and the answer key must agree with the type."""
    q = question or {}
    learner = q.get('learner') or {}
    inter = learner.get('interaction') or {}
    key = (q.get('answer') or {}).get('answer_key')
    reasons = []
    if typ in ('single_choice', 'true_false', 'image_based_choice'):
        n = len(learner.get('choices') or [])
        if not isinstance(key, list) or len(key) != 1:
            reasons.append('key must be a single index')
        elif n and (key[0] < 0 or key[0] >= n):
            reasons.append('key index %s is not a valid choice' % key[0])
    elif typ == 'multiple_select':
        n = len(learner.get('choices') or [])
        if not isinstance(key, list) or not key:
            reasons.append('multiple_select key is empty')
        else:
            if any((not isinstance(i, int)) or i < 0 or i >= n for i in key):
                reasons.append('multiple_select key has an index that is not a valid choice')
            want = _choose_n(_plain_rich(learner.get('stem')))
            if want is not None and len(key) != want:
                reasons.append('stem asks for %s choices but the key has %s' % (want, len(key)))
    elif typ == 'yes_no_matrix':
        rows = ((inter.get('matrix') or {}).get('rows')) or []
        if not isinstance(key, dict):
            reasons.append('matrix key must be a map of row ids')
        elif len(rows) != len(key):
            reasons.append('matrix has %s rows but the key has %s' % (len(rows), len(key)))
        else:
            row_ids = {r.get('id') if isinstance(r, dict) else str(r) for r in rows}
            if set(key) != row_ids:
                reasons.append('matrix key rows do not match the interaction rows')
    elif typ in ('inline_dropdown', 'multi_blank_dropdown', 'cloze'):
        blanks = ((inter.get('cloze') or {}).get('blanks')) or []
        if not isinstance(key, dict) or not key:
            reasons.append('every cloze blank must have a key')
        else:
            blank_ids = {b.get('id') if isinstance(b, dict) else str(b) for b in blanks}
            if set(key) != blank_ids:
                reasons.append('cloze key does not cover every blank')
            for bid, val in key.items():
                opts = []
                for b in blanks:
                    if isinstance(b, dict) and b.get('id') == bid:
                        opts = [o.get('id') if isinstance(o, dict) else str(o) for o in (b.get('options') or [])]
                if opts and val not in opts:
                    reasons.append('cloze key %s is not an option of blank %s' % (val, bid))
    elif typ == 'hotspot_single':
        if not key:
            reasons.append('hotspot_single key is empty')
    elif typ in ('hotspot_multi', 'drag_drop', 'active_screen'):
        if not key:
            reasons.append('%s key is empty' % typ)
    return not reasons, reasons


def key_certainty(item, typ, question, visual, cfg):
    """Key must come from text or two agreeing pixel methods, and map to existing ids."""
    raw = (item.get('answer_raw') or '').strip()
    letters = re.findall(r'[A-H]', raw.upper())
    key = (question or {}).get('answer', {}).get('answer_key')
    n_choices = len(((question or {}).get('learner') or {}).get('choices') or [])
    if typ in ('single_choice', 'true_false', 'image_based_choice', 'multiple_select') and letters and n_choices:
        mapped = []
        for L in letters:
            i = ord(L) - ord('A')
            if 0 <= i < n_choices and i not in mapped:
                mapped.append(i)
        if typ in ('single_choice', 'true_false', 'image_based_choice'):
            ok = len(mapped) == 1 and key == mapped
        else:
            ok = bool(mapped) and set(key or []) == set(mapped)
        if ok:
            return {'ok': True, 'source': 'text', 'reason': None}
        if not mapped:
            return {'ok': False, 'source': 'text_unmapped', 'reason': 'answer letters do not map to existing choice ids'}
        return {'ok': False, 'source': 'text_mismatch', 'reason': 'text key does not match the exported key'}
    methods = (visual or {}).get('key_by_method') or (item.get('key_by_method')) or {}
    want = int(((cfg.get('key') or {}).get('min_agreeing_methods')) or 2)
    # methods that produced a non-empty key
    present = {name: val for name, val in methods.items() if val not in (None, '', [], {})}
    # group by canonical json
    groups = {}
    for name, val in present.items():
        try:
            sig = json.dumps(val, sort_keys=True, default=str)
        except TypeError:
            sig = str(val)
        groups.setdefault(sig, []).append(name)
    agreed = None
    agreed_names = []
    for sig, names in groups.items():
        if len(names) >= want:
            agreed = present[names[0]]
            agreed_names = names
            break
    if agreed is not None:
        # exported key must equal the pixel agreement (best-effort compare)
        if _keys_equivalent(key, agreed, typ):
            return {'ok': True, 'source': 'pixel:' + '+'.join(sorted(agreed_names)), 'reason': None}
        return {
            'ok': False,
            'source': 'pixel_mismatch',
            'reason': 'two pixel methods agreed but the exported key does not match them',
        }
    if raw and typ in ('single_choice', 'true_false', 'image_based_choice', 'multiple_select'):
        return {'ok': False, 'source': 'text_unmapped', 'reason': 'answer letters do not map to existing choice ids'}
    if not present:
        return {'ok': False, 'source': 'missing', 'reason': 'no text key and no pixel marks'}
    names = sorted(present)
    return {
        'ok': False,
        'source': 'pixel_disagree',
        'reason': 'pixel methods do not agree (%s)' % ', '.join(names),
    }


def _keys_equivalent(a, b, typ):
    if a == b:
        return True
    if typ in ('yes_no_matrix', 'inline_dropdown', 'multi_blank_dropdown', 'drag_drop') and isinstance(a, dict) and isinstance(b, dict):
        return {str(k): str(v) for k, v in a.items()} == {str(k): str(v) for k, v in b.items()}
    if isinstance(a, list) and isinstance(b, list):
        return [str(x) for x in a] == [str(x) for x in b] or set(map(str, a)) == set(map(str, b))
    return str(a) == str(b)


def evaluate(item, question, result, ocr_item, visual, cfg, deny=None):
    """Run every fidelity check. Returns a report dict; export only when ok is True."""
    reasons = []
    typ = (question or {}).get('type') or (result or {}).get('type')
    unique, matched = unique_type_ok(result or {})
    if not unique:
        if not matched:
            reasons.append('no type rule matched')
        else:
            reasons.append('type rules not unique: %s' % ', '.join(str(x) for x in matched if x))
    shape_ok, shape_reasons = interaction_agrees(typ, question, item) if (unique and typ and question) else (True, [])
    if unique and typ and question and not shape_ok:
        reasons.extend(shape_reasons)

    key_info = {'ok': False, 'source': 'n/a', 'reason': 'question was not built'}
    if question and typ:
        key_info = key_certainty(item, typ, question, visual, cfg)
        if not key_info['ok']:
            reasons.append(key_info['reason'] or 'answer key is not certain')
    elif cfg.get('require_certain_key', True):
        reasons.append('answer key is not certain')

    # coverage uses union of PDF tokens and high-confidence OCR tokens
    pdf_text = source_pdf_text(item, cfg, deny=deny)
    src = token_set(pdf_text, cfg)
    ocr_cfg = cfg.get('ocr') or {}
    ocr_text = ocr_words_text(ocr_item, min_word=ocr_cfg.get('min_word_confidence'))
    src |= token_set(ocr_text, cfg)
    dest = token_set(export_text(question) if question else '', cfg)
    cov = coverage_report(src, dest)
    cov['pdf_text_normalized'] = pdf_text
    if cfg.get('require_100_percent_coverage', True) and cov['missing_words']:
        reasons.append('missing words: %s' % ', '.join(cov['missing_words'][:40]))
    if cfg.get('forbid_extra_words', True) and cov['extra_words']:
        reasons.append('extra words: %s' % ', '.join(cov['extra_words'][:40]))

    img = check_image_ocr(ocr_item, cfg)
    if not img['ok'] and img.get('reason'):
        reasons.append(img['reason'])

    ok = not reasons
    return {
        'ok': ok,
        'status': 'exported' if ok else 'held',
        'coverage_percent': cov['coverage_percent'],
        'missing_words': cov['missing_words'],
        'extra_words': cov['extra_words'],
        'ocr_min_word_confidence': img.get('min_word_confidence'),
        'ocr_overall_confidence': img.get('overall_confidence'),
        'ocr_agree': img.get('agree'),
        'type_rule': (matched[0] if len(matched) == 1 else None),
        'type_rules': matched,
        'type': typ,
        'key_source': key_info.get('source'),
        'reason': '; '.join(reasons) if reasons else '',
    }


def write_reports(out_dir, exam, rows):
    export_dir = os.path.join(out_dir, 'export')
    os.makedirs(export_dir, exist_ok=True)
    payload = {
        'exam': exam,
        'total': len(rows),
        'exported': sum(1 for r in rows if r.get('status') == 'exported'),
        'held': sum(1 for r in rows if r.get('status') != 'exported'),
        'items': rows,
    }
    with open(os.path.join(export_dir, 'fidelity.json'), 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write('\n')
    lines = [
        '# Fidelity report: %s' % exam,
        '',
        'exported %s of %s; held %s' % (payload['exported'], payload['total'], payload['held']),
        '',
        '| question | status | coverage | OCR min word | type rule | key source | reason |',
        '|---|---|---:|---:|---|---|---|',
    ]
    for r in rows:
        minc = r.get('ocr_min_word_confidence')
        minc = '' if minc is None else ('%.1f' % float(minc))
        cov = r.get('coverage_percent')
        cov = '' if cov is None else ('%.1f' % float(cov))
        reason = (r.get('reason') or '').replace('|', '/')
        lines.append('| %s | %s | %s | %s | %s | %s | %s |' % (
            r.get('question_key'), r.get('status'), cov, minc,
            r.get('type_rule') or '', r.get('key_source') or '', reason,
        ))
    with open(os.path.join(export_dir, 'fidelity.md'), 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')
    return payload


if __name__ == '__main__':
    print('fidelity is a library used by build_technical_export.py', file=sys.stderr)
    sys.exit(2)
