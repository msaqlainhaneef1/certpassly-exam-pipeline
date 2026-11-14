#!/usr/bin/env python3
"""Validate CertPassly question format v2 documents.

Uses the jsonschema package when it is installed (Draft 2020-12). Otherwise a
minimal built-in checker covers required fields, the type enum, learner/answer
separation, scoring_excluded, and the sanitizer allow-list.

v2 rejects the v1 status spelling as_in_source_file. Use scripts/migrate_v1_to_v2.py
to map a v1 bank first.
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
V2 = REPO / 'reference' / 'site-format' / 'v2'
FORBIDDEN_LEARNER_KEYS = {
    'answer_key', 'correct_option_ids', 'is_correct', 'server_only_answer_key',
    'correct_answer', 'partial_credit', 'option_rationales',
}

CANONICAL_STATUS = {
    'owner_key', 'researched_official', 'researched_unverified', 'answer_not_found',
}

def check_status(doc: dict) -> list[str]:
    """v2 rejects v1 status spellings. Do not normalize them here."""
    meta = doc.get('meta')
    if not isinstance(meta, dict):
        return []
    raw = meta.get('answer_key_status')
    if raw == 'as_in_source_file':
        return [
            'answer_key_status as_in_source_file is not valid in v2; '
            'run scripts/migrate_v1_to_v2.py to map v1 statuses to owner_key'
        ]
    if raw not in (None, *CANONICAL_STATUS):
        return [f'invalid answer_key_status {raw!r}']
    return []


def load_json(p: Path):
    return json.loads(p.read_text(encoding='utf-8'))

def load_registry():
    return load_json(V2 / 'question_types.json')

def load_schema():
    return load_json(V2 / 'question.schema.json')

def load_allowlist():
    return load_json(V2 / 'sanitizer-allowlist.json')

def walk_dicts(obj, path='$'):
    if isinstance(obj, dict):
        yield path, obj
        for k, v in obj.items():
            yield from walk_dicts(v, f'{path}.{k}')
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk_dicts(v, f'{path}[{i}]')

def check_learner_leak(doc) -> list[str]:
    errs = []
    learner = doc.get('learner') or {}
    for path, node in walk_dicts(learner, 'learner'):
        for bad in FORBIDDEN_LEARNER_KEYS:
            if bad in node:
                errs.append(f'learner payload contains forbidden key {bad} at {path}')
    return errs

def check_scoring_rule(doc) -> list[str]:
    meta = doc.get('meta') or {}
    if meta.get('answer_key_status') == 'answer_not_found' and meta.get('scoring_excluded') is not True:
        return ['meta.scoring_excluded must be true when answer_key_status is answer_not_found']
    return []

def check_registry(doc, registry) -> list[str]:
    typ = doc.get('type')
    keys = set(registry.get('types') or {})
    aliases = registry.get('aliases') or {}
    if typ in keys:
        return []
    if typ in aliases:
        return [f'registry mismatch: type {typ!r} is an alias for {aliases[typ]!r}; use the canonical key']
    return [f'registry mismatch: type {typ!r} is not in the 30-key enum']

TAG_RE = re.compile(r'<\s*(/?)\s*([A-Za-z][A-Za-z0-9:-]*)\b([^>]*)>', re.S)
ATTR_RE = re.compile(r'([A-Za-z_:][A-Za-z0-9:_.-]*)\s*=\s*("([^"]*)"|\'([^\']*)\')', re.S)
ON_RE = re.compile(r'^on', re.I)

def _href_ok(value: str, allow_data_image: bool, svg_fragment_only: bool) -> bool:
    v = (value or '').strip()
    compact = re.sub(r'[\x00-\x20]+', '', v)
    low = compact.lower()
    if low.startswith('javascript:') or low.startswith('vbscript:'):
        return False
    if svg_fragment_only:
        return compact.startswith('#')
    if low.startswith('data:'):
        if not allow_data_image:
            return False
        return low.startswith('data:image/')
    if low.startswith('https:') or low.startswith('http:') or compact.startswith('#') or compact.startswith('/'):
        return True
    return False

def check_markup(text: str, kind: str, allow, allow_data_image: bool) -> list[str]:
    errs = []
    if not text:
        return errs
    if kind == 'svg' and re.search(r'<!DOCTYPE|<!ENTITY', text, re.I):
        errs.append('SVG must not contain DOCTYPE or ENTITY declarations')
    forbidden_el = {e.lower() for e in allow['forbidden']['elements']}
    if kind == 'html':
        allowed_el = {t.lower() for t in allow['html']['tags']}
        allowed_attr = {a.lower() for a in allow['html']['attributes']}
        fragment_only = False
    else:
        allowed_el = set(allow['svg']['elements_match_lowercase'])
        allowed_attr = {a.lower() for a in allow['svg']['attributes']}
        fragment_only = True
    for m in TAG_RE.finditer(text):
        closing, name, attr_s = m.group(1), m.group(2).lower(), m.group(3) or ''
        if name in forbidden_el:
            errs.append(f'forbidden element <{name}>')
            continue
        if name not in allowed_el:
            errs.append(f'element <{name}> is not on the {kind} allow-list')
            continue
        if closing:
            continue
        for am in ATTR_RE.finditer(attr_s):
            an = am.group(1).lower()
            av = am.group(3) if am.group(3) is not None else (am.group(4) or '')
            if ON_RE.match(an) or an in ('onclick',):
                errs.append(f'forbidden attribute {an}')
                continue
            if 'url(' in av.lower():
                errs.append(f'attribute {an} contains url()')
            if an not in allowed_attr:
                errs.append(f'attribute {an} is not on the {kind} allow-list')
                continue
            if an in ('href', 'xlink:href') and not _href_ok(av, allow_data_image, fragment_only or kind == 'svg'):
                errs.append(f'href value is not allowed: {av[:80]}')
    if re.search(r'<script\b', text, re.I):
        errs.append('author JavaScript is forbidden')
    return errs

def check_sanitizer(doc, allow) -> list[str]:
    errs = []
    meta = doc.get('meta') or {}
    allow_data = bool(meta.get('allow_data_image')) and bool((meta.get('data_image_justification') or '').strip())
    stem = (doc.get('learner') or {}).get('stem') or {}
    fmt = stem.get('format')
    text = stem.get('text') or ''
    if fmt == 'html':
        errs.extend(check_markup(text, 'html', allow, allow_data))
    if fmt == 'svg':
        errs.extend(check_markup(text, 'svg', allow, allow_data))
    for asset in (doc.get('learner') or {}).get('media') or []:
        if not (asset.get('alt') or '').strip():
            errs.append(f"media {asset.get('id')!r} is missing alt text")
        href = asset.get('href') or ''
        if href and not _href_ok(href, allow_data, svg_fragment_only=False):
            errs.append(f"media {asset.get('id')!r} href is not allowed")
        if (asset.get('kind') == 'svg') and asset.get('text'):
            errs.extend(check_markup(asset['text'], 'svg', allow, allow_data))
    return errs

def minimal_check(doc, registry) -> list[str]:
    errs = []
    if doc.get('schema_version') != 'question.v2':
        errs.append('schema_version must be the const question.v2')
    for req in ('question_key', 'version', 'type', 'learner', 'answer', 'meta'):
        if req not in doc:
            errs.append(f'missing required field {req}')
    if not isinstance(doc.get('version'), int) or doc.get('version') < 1:
        errs.append('version must be an integer >= 1')
    typ = doc.get('type')
    if typ not in (registry.get('types') or {}):
        errs.extend(check_registry(doc, registry) or [f'unknown type {typ!r}'])
    learner = doc.get('learner') or {}
    if not isinstance(learner, dict) or 'stem' not in learner:
        errs.append('learner.stem is required')
    else:
        stem = learner.get('stem') or {}
        if stem.get('format') not in ('plain', 'html', 'svg') or 'text' not in stem:
            errs.append('learner.stem must have format (plain|html|svg) and text')
    meta = doc.get('meta') or {}
    if meta.get('record_status') not in (None, 'draft'):
        errs.append('record_status must be draft')
    if meta.get('answer_key_status') not in ('owner_key', 'researched_official', 'researched_unverified', 'answer_not_found', None):
        errs.append('invalid answer_key_status')
    return errs

def validate_doc(doc, schema, registry, allow, use_jsonschema=True) -> list[str]:
    errs = []
    errs.extend(check_status(doc))
    typ = doc.get('type')
    if typ not in (registry.get('types') or {}):
        errs.extend(check_registry(doc, registry))
        # still run leak and sanitizer checks
        errs.extend(check_learner_leak(doc))
        errs.extend(check_scoring_rule(doc))
        errs.extend(check_sanitizer(doc, allow))
        return errs
    if use_jsonschema:
        try:
            import jsonschema
            validator = jsonschema.Draft202012Validator(schema)
            errs.extend([e.message if hasattr(e, 'message') else str(e) for e in validator.iter_errors(doc)])
        except ImportError:
            use_jsonschema = False
    if not use_jsonschema:
        errs.extend(minimal_check(doc, registry))
    errs.extend(check_learner_leak(doc))
    errs.extend(check_scoring_rule(doc))
    errs.extend(check_sanitizer(doc, allow))
    # unique
    seen = set(); out = []
    for e in errs:
        if e not in seen:
            seen.add(e); out.append(e)
    return out

def iter_files(paths: list[Path]):
    for p in paths:
        if p.is_dir():
            yield from sorted(p.glob('*.json'))
        elif p.is_file():
            yield p

def classify_example(name: str) -> str:
    n = name.lower()
    if n.startswith('invalid') or 'invalid-' in n:
        return 'invalid'
    if n.startswith('mismatch') or 'mismatch-' in n:
        return 'mismatch'
    if n.startswith('valid') or 'valid-' in n:
        return 'valid'
    return 'other'

def main(argv=None):
    ap = argparse.ArgumentParser(description='Validate question format v2 JSON files.')
    ap.add_argument('paths', nargs='*', type=Path, help='Files or directories of question JSON.')
    ap.add_argument('--examples', type=Path, help='Validate a bundled examples folder with expected pass/fail.')
    ap.add_argument('--dir', type=Path, help='Alias for a directory of files (for example a pilot export).')
    ap.add_argument('--no-jsonschema', action='store_true', help='Force the minimal checker even if jsonschema is installed.')
    args = ap.parse_args(argv)
    schema = load_schema(); registry = load_registry(); allow = load_allowlist()
    use_js = not args.no_jsonschema
    paths = list(args.paths)
    if args.dir:
        paths.append(args.dir)
    expect_mode = False
    if args.examples:
        paths.append(args.examples)
        expect_mode = True
    if not paths:
        ap.error('pass files, --dir, or --examples')
    files = list(iter_files(paths))
    if not files:
        print('no JSON files found', file=sys.stderr)
        return 2
    failed = 0
    unexpected = 0
    counts = {'pass': 0, 'fail': 0}
    for f in files:
        doc = load_json(f)
        if not isinstance(doc, dict) or doc.get('schema_version') != 'question.v2' or 'question_key' not in doc:
            print(f'SKIP {f} (not a question.v2 document)')
            continue
        errs = validate_doc(doc, schema, registry, allow, use_jsonschema=use_js)
        kind = classify_example(f.name) if expect_mode else 'other'
        if errs:
            counts['fail'] += 1
            print(f'FAIL {f} ({len(errs)} issues)')
            for e in errs[:12]:
                print(f'  - {e}')
            if expect_mode and kind == 'valid':
                unexpected += 1
                print('  unexpected: this valid example should pass')
            # invalid and mismatch are expected to fail
        else:
            counts['pass'] += 1
            print(f'PASS {f}')
            if expect_mode and kind in ('invalid', 'mismatch'):
                unexpected += 1
                print('  unexpected: this file should fail')
                failed += 1
        if errs and not expect_mode:
            failed += 1
        if errs and expect_mode and kind == 'valid':
            failed += 1
    print(f"summary pass={counts['pass']} fail={counts['fail']} files={len(files)}")
    if expect_mode and unexpected:
        print(f'example expectations missed: {unexpected}')
        return 1
    if expect_mode and unexpected == 0 and failed == 0:
        print('examples: valid files passed; invalid and mismatch files failed as expected')
        return 0
    return 1 if failed else 0

if __name__ == '__main__':
    sys.exit(main())
