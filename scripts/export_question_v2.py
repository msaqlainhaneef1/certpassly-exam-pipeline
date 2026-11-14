#!/usr/bin/env python3
"""Export a pipeline questions.json bank to question format v2 draft files.

Does not invent keys. Maps v1 answer_key_status as_in_source_file to owner_key.
Writes one JSON file per question. Record status is always draft.
"""
from __future__ import annotations
import argparse, json, sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

STATUS_MAP = {
    'as_in_source_file': 'owner_key',
    'owner_key': 'owner_key',
    'researched_official': 'researched_official',
    'researched_unverified': 'researched_unverified',
    'answer_not_found': 'answer_not_found',
    'flagged_for_owner': 'owner_key',
}
KEY_SOURCE_MAP = {
    'owner_file': 'owner_file',
    'researched_official': 'researched_official',
    'none': 'none',
}

def version_int(item) -> int:
    qvk = str(item.get('question_version_key') or '')
    # q001-v1 -> 1
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

def media(item):
    assets = []
    for i, m in enumerate(item.get('media') or [], 1):
        alt = (m.get('alt') or m.get('alt_text') or m.get('description') or '').strip()
        sha = (m.get('sha256') or '').lower()
        href = m.get('href') or m.get('path') or m.get('url') or ''
        kind = 'svg' if str(m.get('mime') or href).lower().endswith('.svg') or m.get('kind') == 'svg' else 'image'
        rec = {
            'id': str(m.get('id') or f'm{i}'),
            'kind': kind,
            'alt': alt or 'Source exhibit. Text was not transcribed in the v1 bank.',
            'sha256': sha if len(sha) == 64 else None,
            'href': href or None,
            'role': m.get('role') or 'exhibit',
        }
        if m.get('original_sha256') or m.get('original_asset'):
            orig = m.get('original_asset') or {}
            rec['original_asset'] = {
                'sha256': orig.get('sha256') or m.get('original_sha256'),
                'href': orig.get('href') or m.get('original_href'),
                'note': 'Original image kept as a reference asset.',
            }
        elif rec['sha256']:
            rec['original_asset'] = {'sha256': rec['sha256'], 'href': rec.get('href'), 'note': 'Original image kept as a reference asset.'}
        # drop Nones except we need sha256 required by schema
        if not rec['sha256']:
            # skip incomplete media rather than invent a hash
            continue
        assets.append({k: v for k, v in rec.items() if v is not None})
    return assets

def export_item(item: dict) -> dict:
    typ = item.get('question_type') or item.get('type') or 'single_choice'
    aks_raw = item.get('answer_key_status') or 'owner_key'
    aks = STATUS_MAP.get(aks_raw, 'owner_key')
    ks_raw = item.get('key_source') or ('owner_file' if aks == 'owner_key' else 'none')
    ks = KEY_SOURCE_MAP.get(ks_raw, 'owner_file' if aks == 'owner_key' else 'none')
    scoring = aks == 'answer_not_found' or (item.get('question_key') in (item.get('scoring_excluded_question_keys') or []))
    if aks == 'answer_not_found':
        scoring = True
        ks = 'none'
    opts = options(item)
    explanation = {'core': item.get('core_explanation') or (item.get('explanations') or {}).get('core') or ''}
    per = {}
    for k, v in (item.get('explanations') or {}).items():
        if k != 'core' and v:
            per[str(k)] = v
    if per:
        explanation['per_option'] = per
    ev = []
    for s in item.get('sources') or []:
        if isinstance(s, dict) and s.get('url') and s.get('sha256') and s.get('quote'):
            ev.append({'url': s['url'], 'sha256': s['sha256'], 'quote': s['quote']})
    choose_n = 1 if typ in ('single_choice', 'true_false', 'image_based_choice') else None
    if typ == 'multiple_select':
        # authored only if the stem or schema already says so; do not count the key
        choose_n = None
    interaction = {'options': opts} if opts else {}
    if choose_n:
        interaction['choose_n'] = choose_n
    constraints = {'choose_n': choose_n} if choose_n else None
    doc = {
        'schema_version': 'question.v2',
        'question_key': item['question_key'],
        'version': version_int(item),
        'type': typ,
        'learner': {
            'stem': {'format': 'plain', 'text': item.get('prompt_text') or ''},
            'interaction': interaction,
        },
        'answer': {
            'answer_key': item.get('answer_key'),
            'explanation': explanation,
            'partial_credit': {'mode': 'all_or_nothing', 'max_points': 1},
        },
        'meta': {
            'answer_key_status': aks,
            'key_source': ks,
            'research_evidence': ev,
            'verification_status': 'unverified',
            'reviewer_needed': bool(item.get('human_review_required')),
            'question_sources': item.get('sources') or [],
            'scoring_excluded': bool(scoring),
            'record_status': 'draft',
            'exam_key': item.get('exam_key'),
            'domain_key': item.get('domain_key'),
            'topic_key': item.get('topic_key'),
            'type_reason': item.get('type_reason'),
            'created_source': item.get('created_source'),
            'legacy_answer_key_status': aks_raw if aks_raw != aks else None,
        },
    }
    assets = media(item)
    if assets:
        doc['learner']['media'] = assets
    if constraints:
        doc['learner']['constraints'] = constraints
    # drop null meta
    doc['meta'] = {k: v for k, v in doc['meta'].items() if v is not None}
    if item.get('flags'):
        doc['meta']['flags'] = item['flags']
    return doc

def main(argv=None):
    ap = argparse.ArgumentParser(description='Export a questions.json bank to v2 draft files.')
    ap.add_argument('--bank', required=True, type=Path, help='Path to pipeline questions.json')
    ap.add_argument('--out', required=True, type=Path, help='Output directory (created).')
    args = ap.parse_args(argv)
    bank = json.loads(args.bank.read_text(encoding='utf-8'))
    items = bank.get('questions') or []
    args.out.mkdir(parents=True, exist_ok=True)
    types = Counter(); statuses = Counter()
    excluded = set(bank.get('scoring_excluded_question_keys') or [])
    written = []
    for item in items:
        if item['question_key'] in excluded:
            item = dict(item)
            item['scoring_flag'] = True
        doc = export_item(item)
        if item['question_key'] in excluded:
            doc['meta']['scoring_excluded'] = True
        types[doc['type']] += 1
        statuses[doc['meta']['answer_key_status']] += 1
        dest = args.out / f"{doc['question_key']}.v{doc['version']}.json"
        dest.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
        written.append(dest)
    summary = {
        'exam_key': bank.get('exam_key'),
        'source': str(args.bank),
        'count': len(written),
        'held_for_review': bank.get('held_for_review') or [],
        'types': dict(types),
        'answer_key_status': dict(statuses),
        'record_status': 'draft',
        'schema_version': 'question.v2',
    }
    (args.out / 'export-summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(f"wrote {len(written)} files to {args.out}")
    print('types', dict(types))
    print('answer_key_status', dict(statuses))
    return 0

if __name__ == '__main__':
    sys.exit(main())
