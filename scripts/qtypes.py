"""Question-type registry and table-driven type rules.

Rules live in config/question_type_rules.json (not per exam). All matching
rules are recorded. The first match still supplies the type for the bank path;
the fidelity gate exports only when exactly one rule matches. If no rule fits
exactly, the item is held; the type is never guessed.
This module never reads the app repo or a PHP file.
"""
from __future__ import annotations
import json, os, re, sys
sys.path.insert(0, os.path.dirname(__file__))
import paths

_RULES = None
_MARKER_RX = None


def _data(version=None):
    p=os.path.join(paths.site_format_dir(version),'question_types.json')
    return json.load(open(p,encoding='utf-8'))

def registry(version=None):
    d=_data(version)
    types=d['types']; aliases=dict(d.get('aliases') or {})
    return types, aliases

def family_rules(version=None):
    d=_data(version).get('family_rules') or {}
    return {k:(v.get('payload',''), v.get('answer_key','')) for k,v in d.items()}

FAMILY_RULES=None  # filled lazily; gen_site_question_types calls family_rules()

MARKERS=None
def markers_map(version=None):
    return dict(_data(version).get('markers') or {})


def rules_path():
    return os.path.join(paths.skill_root(), 'config', 'question_type_rules.json')


def load_rules(path=None):
    """Load the type-rule table. Cached unless a different path is given."""
    global _RULES, _MARKER_RX
    p = path or rules_path()
    if _RULES is not None and path is None:
        return _RULES
    with open(p, encoding='utf-8') as fh:
        data = json.load(fh)
    if path is None:
        _RULES = data
        _MARKER_RX = None
    return data


def _compile_markers(rules=None):
    global _MARKER_RX
    rules = rules or load_rules()
    if _MARKER_RX is not None and rules is _RULES:
        return _MARKER_RX
    compiled = {}
    for name, spec in (rules.get('markers') or {}).items():
        pats = spec.get('patterns') if isinstance(spec, dict) else spec
        parts = [p for p in (pats or []) if p]
        if not parts:
            continue
        compiled[name] = re.compile('|'.join('(?:%s)' % p for p in parts), re.I)
    if rules is _RULES:
        _MARKER_RX = compiled
    return compiled


def markers(stem, rules=None):
    stem = stem or ''
    return sorted(k for k, rx in _compile_markers(rules).items() if rx.search(stem))


def answer_letters(item):
    raw = item.get('answer_raw') or ''
    return re.sub(r'[^A-H]', '', str(raw).upper())


def _norm_option_texts(item):
    opts = item.get('options') or {}
    return {str(v).strip().lower().rstrip('.') for v in opts.values()}


def _visual(visual):
    return visual if isinstance(visual, dict) else {}


def _condition(cond, item, visual, marks):
    vis = _visual(visual)
    opts = item.get('options') or {}
    letters = answer_letters(item)
    if 'has_options' in cond:
        if bool(opts) != bool(cond['has_options']):
            return False
    if 'option_count' in cond and len(opts) != int(cond['option_count']):
        return False
    if 'option_count_min' in cond and len(opts) < int(cond['option_count_min']):
        return False
    if 'option_count_max' in cond and len(opts) > int(cond['option_count_max']):
        return False
    if 'option_texts_in' in cond:
        vals = _norm_option_texts(item)
        allowed = {frozenset(group) for group in cond['option_texts_in']}
        if vals not in allowed:
            return False
    if 'marker' in cond and cond['marker'] not in marks:
        return False
    if 'markers_any' in cond and not any(m in marks for m in cond['markers_any']):
        return False
    if 'markers_all' in cond and not all(m in marks for m in cond['markers_all']):
        return False
    if 'has_question_image' in cond:
        imgs = item.get('question_images') or []
        if bool(imgs) != bool(cond['has_question_image']):
            return False
    if 'answer_letter_count' in cond and len(letters) != int(cond['answer_letter_count']):
        return False
    if 'answer_letter_count_min' in cond and len(letters) < int(cond['answer_letter_count_min']):
        return False
    if 'answer_letter_count_max' in cond and len(letters) > int(cond['answer_letter_count_max']):
        return False
    if 'visual_rows_min' in cond and len(vis.get('rows') or []) < int(cond['visual_rows_min']):
        return False
    if 'visual_blanks' in cond and len(vis.get('blanks') or []) != int(cond['visual_blanks']):
        return False
    if 'visual_blanks_min' in cond and len(vis.get('blanks') or []) < int(cond['visual_blanks_min']):
        return False
    if 'visual_type' in cond and vis.get('type') != cond['visual_type'] and vis.get('kind') != cond['visual_type']:
        return False
    if 'visual_has' in cond and not vis.get(cond['visual_has']):
        return False
    if 'option_texts_not_in' in cond:
        vals = _norm_option_texts(item)
        banned = {frozenset(group) for group in cond['option_texts_not_in']}
        if vals in banned:
            return False
    if 'not_marker' in cond and cond['not_marker'] in marks:
        return False
    if 'not_markers_any' in cond and any(m in marks for m in cond['not_markers_any']):
        return False
    if 'not_markers_all' in cond and all(m in marks for m in cond['not_markers_all']):
        return False
    if 'visual_regions_min' in cond:
        regions = vis.get('regions') or vis.get('hotspot_regions') or []
        if len(regions) < int(cond['visual_regions_min']):
            return False
    if 'answer_region_count_min' in cond:
        key = vis.get('key')
        n = 0
        if isinstance(key, list):
            n = len(key)
        elif isinstance(key, dict):
            n = len(key)
        if n < int(cond['answer_region_count_min']):
            return False
    return True



def _rule_matches(rule, item, visual, marks):
    alls = rule.get('all') or []
    anys = rule.get('any') or []
    if alls and not all(_condition(c, item, visual, marks) for c in alls):
        return False
    if anys and not any(_condition(c, item, visual, marks) for c in anys):
        return False
    for cond in (rule.get('none') or []):
        if _condition(cond, item, visual, marks):
            return False
    for group in (rule.get('not_all') or []):
        if group and all(_condition(c, item, visual, marks) for c in group):
            return False
    # A rule with no positive conditions must not match everything.
    return bool(alls or anys)


def matching_rules(item, visual=None, rules=None):
    """Every rule whose conditions match. Order is the config order."""
    rules = rules or load_rules()
    marks = markers(item.get('stem') or '', rules)
    return [rule for rule in (rules.get('rules') or []) if _rule_matches(rule, item, visual, marks)]


def _hold_reasons(rules, item, visual, marks, ocr=None, min_confidence=None):
    """Reasons to hold even when a later guess might look tempting."""
    vis = _visual(visual)
    holds = rules.get('hold') or {}
    notes = []
    conf = None
    if ocr and ocr.get('confidence') is not None:
        try:
            conf = float(ocr['confidence'])
        except (TypeError, ValueError):
            conf = None
    if conf is not None and min_confidence is not None and conf < min_confidence:
        notes.append(holds.get('low_ocr_confidence', 'low OCR confidence').format(
            confidence=round(conf, 1), minimum=min_confidence))
    if ocr and ocr.get('missing_tesseract') and (item.get('question_images') or item.get('image_only')) and not item.get('options'):
        notes.append(holds.get('missing_tesseract', 'tesseract is not installed'))
    if 'yes_no' in marks and not (vis.get('rows') or []):
        notes.append(holds.get('yes_no_without_rows', 'Yes/No marker without rows'))
    if 'dropdown' in marks and not (vis.get('blanks') or []):
        notes.append(holds.get('dropdown_without_blanks', 'drop-down marker without blanks'))
    if 'hotspot' in marks and not (vis.get('regions') or vis.get('hotspot_regions') or vis.get('type') == 'active_screen' or vis.get('blanks') or vis.get('rows')):
        # HOTSPOT is also used as a heading for dropdown/matrix items in some files
        if 'yes_no' not in marks and 'dropdown' not in marks:
            notes.append(holds.get('hotspot_without_regions', 'HOTSPOT marker without regions'))
    if 'dragdrop' in marks and not vis.get('pairs'):
        notes.append(holds.get('dragdrop_without_pairs', 'DRAG DROP marker without pairs'))
    if ocr and ocr.get('uncertain_marks'):
        notes.append(holds.get('uncertain_answer_marks', 'answer marks were not reliable'))
    return notes


def classify_detailed(item, visual=None, ocr=None, rules=None, min_confidence=None):
    """Rule-based type decision. Never guesses.

    Returns a dict with type (or None), reason, held, hold_reasons, rule_id,
    and markers. held is True when the type cannot be assigned exactly.
    """
    rules = rules or load_rules()
    types, _ = registry()
    marks = markers(item.get('stem') or '', rules)
    hold_notes = _hold_reasons(rules, item, visual, marks, ocr=ocr, min_confidence=min_confidence)
    # Low confidence or missing OCR on a visual item: hold before assigning a type.
    hard = [n for n in hold_notes if n.startswith('OCR confidence') or 'tesseract is not installed' in n or 'needs OCR' in n]
    if hard and not (item.get('options') or {}):
        return dict(type=None, reason=hard[0], held=True, hold_reasons=hold_notes,
                    rule_id=None, matched_rules=[], markers=marks)
    matched = [rule for rule in (rules.get('rules') or []) if _rule_matches(rule, item, visual, marks)]
    matched_ids = [rule.get('id') for rule in matched]
    hard_base = dict(matched_rules=matched_ids, markers=marks)
    if hard and not (item.get('options') or {}):
        # already returned above; keep matched_rules on that path too
        pass
    for rule in matched:
        typ = rule.get('type')
        if typ not in types:
            reason = 'rule %s names type %s, which is not in the registry' % (rule.get('id'), typ)
            return dict(type=None, reason=reason, held=True, hold_reasons=hold_notes + [reason],
                        rule_id=rule.get('id'), **hard_base)
        # A matching rule still holds when required layout is uncertain.
        layout_holds = [n for n in hold_notes if typ in n or 'not read reliably' in n or 'not reliable' in n]
        if typ == 'yes_no_matrix':
            layout_holds = [n for n in hold_notes if 'matrix rows' in n or 'Yes/No marker' in n]
        if typ in ('inline_dropdown', 'multi_blank_dropdown'):
            layout_holds = [n for n in hold_notes if 'blanks' in n]
        if typ in ('hotspot_single', 'hotspot_multi'):
            layout_holds = [n for n in hold_notes if 'regions' in n]
        if typ == 'drag_drop':
            layout_holds = [n for n in hold_notes if 'pairs' in n]
        if layout_holds:
            return dict(type=typ, reason=layout_holds[0], held=True, hold_reasons=hold_notes,
                        rule_id=rule.get('id'), **hard_base)
        if ocr and ocr.get('uncertain_marks') and typ in ('yes_no_matrix', 'inline_dropdown', 'multi_blank_dropdown', 'hotspot_single', 'hotspot_multi', 'drag_drop', 'active_screen'):
            return dict(type=typ, reason=hold_notes[0] if hold_notes else 'uncertain answer marks',
                        held=True, hold_reasons=hold_notes, rule_id=rule.get('id'), **hard_base)
        return dict(type=typ, reason=rule.get('reason') or ('rule ' + str(rule.get('id'))),
                    held=False, hold_reasons=[], rule_id=rule.get('id'), **hard_base)
    reason = (rules.get('hold') or {}).get('no_rule_matched', 'no type rule matched; type was not guessed')
    if hold_notes:
        reason = hold_notes[0]
    return dict(type=None, reason=reason, held=True, hold_reasons=hold_notes or [reason],
                rule_id=None, **hard_base)


def classify(item, visual=None):
    """item: split.json record. visual: transcription or OCR draft. Returns (type, reason).

    Kept for the research/bank path. Held items are reported as needs_review so
    existing bank assembly still receives a two-tuple. The technical export uses
    classify_detailed and the type rules. The tiles/targets branch keeps the
    bank path's DRAG DROP mapping when pairs were not filled.
    """
    result = classify_detailed(item, visual)
    if not result['held'] and result['type']:
        return result['type'], result['reason']
    vis = visual if isinstance(visual, dict) else {}
    marks = result.get('markers') or markers(item.get('stem') or '')
    if vis.get('tiles') and vis.get('targets'):
        return 'drag_drop', f"{len(vis['tiles'])} tiles dragged to {len(vis['targets'])} targets"
    if result['held'] or not result['type']:
        return 'needs_review', result['reason']
    return result['type'], result['reason']


def agree(qtype, stem, n_correct=None, n_blanks=None, has_exhibit=False):
    """Marker-agreement check: source markers must agree with the assigned type. Returns list of problems."""
    m=markers(stem); p=[]
    if 'yes_no' in m and qtype!='yes_no_matrix': p.append('Yes/No statement marker but type is '+qtype)
    if qtype=='yes_no_matrix' and 'yes_no' not in m: p.append('yes_no_matrix without Yes/No marker')
    if 'multi' in m and qtype!='multiple_select': p.append('choose-N marker but type is '+qtype)
    if qtype=='multiple_select':
        w=re.search(r'\b(?:which|choose|select|what are) (two|three|four|five)\b',stem,re.I)
        words={'two':2,'three':3,'four':4,'five':5}
        want=words.get(w.group(1).lower()) if w else None
        if want and n_correct!=want: p.append(f'stem asks for {want} but key has {n_correct}')
    if qtype in ('inline_dropdown','multi_blank_dropdown') and not ('dropdown' in m or 'hotspot' in m):
        p.append('DRAG DROP marker but type is '+qtype+'; transcribe tiles and targets as drag_drop' if 'dragdrop' in m else 'drop-down type without answer-area marker')
    if qtype=='drag_drop' and 'dragdrop' not in m: p.append('drag_drop type without DRAG DROP marker')
    if qtype=='inline_dropdown' and n_blanks!=1: p.append('inline_dropdown must have 1 blank')
    if qtype=='multi_blank_dropdown' and (n_blanks or 0)<2: p.append('multi_blank_dropdown needs 2+ blanks')
    if 'hotspot' in m and qtype in ('single_choice','multiple_select','true_false'): p.append('HOTSPOT marker flattened to a plain choice type')
    if 'exhibit' in m and not has_exhibit: p.append('exhibit marker but no exhibit attached')
    if qtype=='image_based_choice' and not has_exhibit: p.append('image_based_choice without image')
    return p
