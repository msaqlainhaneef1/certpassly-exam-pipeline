#!/usr/bin/env python3
"""Validate CertPassly site format v2 exam files.

Uses reference/site-format/v2/question.schema.json (the site's own schema).
Adds checks the site importer also applies: no HTML in strings, no answer
fields in the learner part, scoring_excluded when status is answer_not_found,
duplicate stems, repeated ids, and the 30-type registry.

v2 rejects the v1 status spelling as_in_source_file. Use scripts/migrate_v1_to_v2.py
to map a v1 bank first.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
V2 = REPO / 'reference' / 'site-format' / 'v2'

FORBIDDEN_LEARNER_KEYS = {
    'answer_key', 'correct_option_ids', 'is_correct', 'server_only_answer_key',
    'correct_answer', 'partial_credit', 'option_rationales', 'status',
    'explanation', 'evidence', 'source', 'references',
}
CANONICAL_STATUS = {
    'owner_key', 'researched_official', 'researched_unverified', 'answer_not_found',
}
HTML_OR_SCRIPT = re.compile(r'<\s*[A-Za-z!/?]|javascript\s*:|data\s*:\s*text/html', re.I)
SKIP_NAMES = {
    'migrate-summary.json', 'export-summary.json', 'cannot-convert.json',
    'registry-mismatch.json', 'question.schema.json', 'question_types.json',
    'sanitizer-allowlist.json',
}
ID_RE = re.compile(r'^[A-Za-z0-9_-]+$')


def load_json(p: Path):
    return json.loads(p.read_text(encoding='utf-8'))


def load_registry():
    return load_json(V2 / 'question_types.json')


def load_schema():
    return load_json(V2 / 'question.schema.json')


def load_allowlist():
    p = V2 / 'sanitizer-allowlist.json'
    return load_json(p) if p.is_file() else {}


def is_exam_doc(doc) -> bool:
    return isinstance(doc, dict) and 'exam' in doc and 'questions' in doc


def iter_questions(doc) -> list[dict]:
    if is_exam_doc(doc):
        return [q for q in (doc.get('questions') or []) if isinstance(q, dict)]
    if isinstance(doc, dict) and 'question_key' in doc and 'learner' in doc:
        return [doc]
    return []


def walk_dicts(obj, path='$'):
    if isinstance(obj, dict):
        yield path, obj
        for k, v in obj.items():
            yield from walk_dicts(v, f'{path}.{k}')
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk_dicts(v, f'{path}[{i}]')


def walk_strings(obj, path='$'):
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk_strings(v, f'{path}.{k}')
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk_strings(v, f'{path}[{i}]')


def check_status_question(q: dict, path: str) -> list[str]:
    status = (q.get('answer') or {}).get('status')
    if status == 'as_in_source_file':
        return [
            f'{path}.answer.status as_in_source_file is not valid in v2; '
            'run scripts/migrate_v1_to_v2.py to map v1 statuses to owner_key'
        ]
    if status not in (None, *CANONICAL_STATUS):
        return [f'{path}.answer.status is invalid: {status!r}']
    return []


def check_learner_leak(q: dict, path: str) -> list[str]:
    errs = []
    learner = q.get('learner') or {}
    for pth, node in walk_dicts(learner, f'{path}.learner'):
        for bad in FORBIDDEN_LEARNER_KEYS:
            if bad in node:
                errs.append(f'{pth}: answer field {bad} is not allowed in the learner part')
    return errs


def check_scoring_rule(q: dict, path: str) -> list[str]:
    ans = q.get('answer') or {}
    if ans.get('status') == 'answer_not_found' and ans.get('scoring_excluded') is not True:
        return [f'{path}.answer.scoring_excluded must be true when status is answer_not_found']
    return []


def check_html(doc) -> list[str]:
    errs = []
    for path, value in walk_strings(doc, '$'):
        if HTML_OR_SCRIPT.search(value):
            errs.append(f'{path}: HTML or script is not allowed')
    return errs


def check_registry(q: dict, registry, path: str) -> list[str]:
    typ = q.get('type')
    keys = set(registry.get('types') or {})
    aliases = registry.get('aliases') or {}
    if typ in keys:
        return []
    if typ in aliases:
        return [f'{path}: registry mismatch: type {typ!r} is an alias for {aliases[typ]!r}; use the canonical key']
    return [f'{path}: registry mismatch: type {typ!r} is not in the 30-key enum']


def text_of_stem(stem) -> str:
    return text_of(stem)


def text_of(obj) -> str:
    parts = []

    def walk(node):
        if isinstance(node, dict):
            if isinstance(node.get('text'), str):
                parts.append(node['text'])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        elif isinstance(node, str):
            parts.append(node)
    walk(obj)
    return ' '.join(parts)


def normalise_stem(stem: str) -> str:
    s = re.sub(r'[^\w]+', ' ', (stem or '').lower(), flags=re.UNICODE)
    return re.sub(r'\s+', ' ', s).strip()


def question_plain_text(q: dict) -> str:
    """Stem plus choices, interaction and content blocks. Shared instruction
    stems (for example 'select Yes or No') are not duplicates when the
    rows, blanks or choices differ."""
    learner = q.get('learner') or {}
    parts = [
        text_of(learner.get('stem')),
        text_of(learner.get('choices')),
        text_of(learner.get('interaction')),
        text_of(learner.get('content_blocks')),
    ]
    return ' '.join(parts)


def check_duplicates(questions: list[dict], prefix: str, min_length: int = 12) -> list[str]:
    errs = []
    seen: dict[str, str] = {}
    for i, q in enumerate(questions):
        key = str(q.get('question_key') or f'#{i}')
        norm = normalise_stem(question_plain_text(q))
        if len(norm) < min_length:
            continue
        if norm in seen and seen[norm] != key:
            errs.append(f'{prefix}.questions[{i}]: duplicate question text of {seen[norm]}')
        else:
            seen[norm] = key
    return errs


def _track_id(seen: dict, ident, where: str, errs: list[str]):
    if not isinstance(ident, str):
        return
    if ident in seen:
        errs.append(f'{where}.id: id {ident} is used twice in this question')
    seen[ident] = True


def check_repeated_ids(q: dict, path: str) -> list[str]:
    errs = []
    seen: dict[str, bool] = {}
    inter = (q.get('learner') or {}).get('interaction') or {}
    for k, r in enumerate(inter.get('hotspot_regions') or []):
        if isinstance(r, dict):
            _track_id(seen, r.get('id'), f'{path}.learner.interaction.hotspot_regions[{k}]', errs)
    matrix = inter.get('matrix') or {}
    for part in ('rows', 'columns'):
        for k, item in enumerate(matrix.get(part) or []):
            if isinstance(item, dict):
                _track_id(seen, item.get('id'), f'{path}.learner.interaction.matrix.{part}[{k}]', errs)
    cloze = inter.get('cloze') or {}
    blanks = {}
    for k, b in enumerate(cloze.get('blanks') or []):
        if not isinstance(b, dict):
            continue
        _track_id(seen, b.get('id'), f'{path}.learner.interaction.cloze.blanks[{k}]', errs)
        blanks[str(b.get('id') or '')] = 0
        for o, opt in enumerate(b.get('options') or []):
            if isinstance(opt, dict):
                _track_id(seen, opt.get('id'), f'{path}.learner.interaction.cloze.blanks[{k}].options[{o}]', errs)
        if b.get('kind') == 'dropdown' and len(b.get('options') or []) < 2:
            errs.append(f'{path}.learner.interaction.cloze.blanks[{k}].options: a dropdown blank needs at least 2 options')
    for k, seg in enumerate(cloze.get('segments') or []):
        if isinstance(seg, dict) and 'blank' in seg:
            ref = str(seg.get('blank'))
            if ref not in blanks:
                errs.append(f'{path}.learner.interaction.cloze.segments[{k}].blank: unknown blank {ref}')
            else:
                blanks[ref] += 1
    for bid, uses in blanks.items():
        if bid and uses != 1:
            errs.append(f'{path}.learner.interaction.cloze.blanks: blank {bid} must be used exactly once in the text (used {uses})')
    for b, block in enumerate((q.get('learner') or {}).get('content_blocks') or []):
        if not isinstance(block, dict) or block.get('type') != 'diagram':
            continue
        ids = {}
        bpath = f'{path}.learner.content_blocks[{b}]'
        for kind in ('nodes', 'connectors', 'regions', 'labels'):
            for k, item in enumerate(block.get(kind) or []):
                if not isinstance(item, dict):
                    continue
                ident = item.get('id')
                if not isinstance(ident, str):
                    continue
                if ident in ids:
                    errs.append(f'{bpath}.{kind}[{k}].id: id {ident} is used twice in this diagram')
                ids[ident] = kind
        for k, c in enumerate(block.get('connectors') or []):
            if not isinstance(c, dict):
                continue
            for end in ('from', 'to'):
                if ids.get(c.get(end)) != 'nodes':
                    errs.append(f'{bpath}.connectors[{k}].{end}: unknown node id')
        for k, lab in enumerate(block.get('labels') or []):
            if not isinstance(lab, dict):
                continue
            if ids.get(lab.get('target')) not in ('nodes', 'connectors', 'regions'):
                errs.append(f'{bpath}.labels[{k}].target: unknown node, connector or region id')
    keys = [q.get('question_key') for q in []]  # placeholder, exam-level below
    return errs


def check_question_keys(questions: list[dict], prefix: str) -> list[str]:
    errs = []
    seen = set()
    for i, q in enumerate(questions):
        key = q.get('question_key')
        if key in seen:
            errs.append(f'{prefix}.questions[{i}].question_key: repeated id {key}')
        seen.add(key)
    return errs


def jsonschema_errors(doc, schema) -> list[str]:
    try:
        import jsonschema
        validator = jsonschema.Draft202012Validator(schema)
        return [e.message if hasattr(e, 'message') else str(e) for e in validator.iter_errors(doc)]
    except ImportError:
        return minimal_exam_check(doc)


def minimal_exam_check(doc) -> list[str]:
    errs = []
    if not is_exam_doc(doc):
        return ['file must be a site format v2 exam object with exam and questions']
    exam = doc.get('exam') or {}
    for req in ('vendor', 'certification', 'exam_code', 'name'):
        if req not in exam:
            errs.append(f'exam missing {req}')
    questions = iter_questions(doc)
    if not questions:
        errs.append('questions must contain at least one question')
    for i, q in enumerate(questions):
        path = f'$.questions[{i}]'
        for req in ('question_key', 'version', 'type', 'domain', 'learner', 'answer'):
            if req not in q:
                errs.append(f'{path} missing {req}')
        if 'schema_version' in q or 'meta' in q:
            errs.append(f'{path}: unknown field schema_version or meta')
        learner = q.get('learner') or {}
        if not isinstance(learner.get('stem'), list) or not learner.get('stem'):
            errs.append(f'{path}.learner.stem must be a non-empty rich_text list')
        ans = q.get('answer') or {}
        if 'answer_key' not in ans or 'status' not in ans:
            errs.append(f'{path}.answer must have answer_key and status')
    return errs


def validate_doc(doc, schema, registry, allow=None, use_jsonschema=True) -> list[str]:
    """Validate a site-format exam document, or a single question wrapped for tests."""
    errs = []
    wrapped = False
    if not is_exam_doc(doc) and isinstance(doc, dict) and 'question_key' in doc:
        # allow unit tests to pass a bare question by wrapping it
        doc = {
            'exam': {
                'vendor': 'Example Vendor',
                'certification': 'Example Certification',
                'exam_code': 'EX-TEST',
                'name': 'Test exam',
            },
            'questions': [doc],
        }
        wrapped = True
    if not is_exam_doc(doc):
        return ['file is not a site format v2 exam object (exam + questions)']
    if use_jsonschema:
        errs.extend(jsonschema_errors(doc, schema))
    else:
        errs.extend(minimal_exam_check(doc))
    errs.extend(check_html(doc))
    questions = iter_questions(doc)
    errs.extend(check_duplicates(questions, '$'))
    errs.extend(check_question_keys(questions, '$'))
    for i, q in enumerate(questions):
        path = f'$.questions[{i}]'
        errs.extend(check_status_question(q, path))
        errs.extend(check_registry(q, registry, path))
        errs.extend(check_learner_leak(q, path))
        errs.extend(check_scoring_rule(q, path))
        errs.extend(check_repeated_ids(q, path))
        if 'schema_version' in q or 'meta' in q or 'constraints' in (q.get('learner') or {}):
            errs.append(f'{path}: site format v2 does not allow schema_version, meta or constraints')
    # unique
    seen = set()
    out = []
    for e in errs:
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out


def iter_files(paths: list[Path]):
    for p in paths:
        if p.is_dir():
            for f in sorted(p.rglob('*.json')):
                if f.name in SKIP_NAMES or f.parent.name == 'retired':
                    continue
                yield f
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
    ap = argparse.ArgumentParser(description='Validate site format v2 exam JSON files.')
    ap.add_argument('paths', nargs='*', type=Path, help='Files or directories of exam JSON.')
    ap.add_argument('--examples', type=Path, help='Validate a bundled examples folder with expected pass/fail.')
    ap.add_argument('--dir', type=Path, help='Alias for a directory of files (for example a migrated exam).')
    ap.add_argument('--no-jsonschema', action='store_true', help='Force the minimal checker even if jsonschema is installed.')
    args = ap.parse_args(argv)
    schema = load_schema()
    registry = load_registry()
    allow = load_allowlist()
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
    counts = {'pass': 0, 'fail': 0, 'questions': 0}
    for f in files:
        try:
            doc = load_json(f)
        except json.JSONDecodeError as e:
            print(f'FAIL {f} (invalid JSON: {e})')
            counts['fail'] += 1
            failed += 1
            continue
        if not isinstance(doc, dict) or not (is_exam_doc(doc) or 'question_key' in doc):
            print(f'SKIP {f} (not a site format v2 exam document)')
            continue
        errs = validate_doc(doc, schema, registry, allow, use_jsonschema=use_js)
        nq = len(iter_questions(doc))
        counts['questions'] += nq
        kind = classify_example(f.name) if expect_mode else 'other'
        if errs:
            counts['fail'] += 1
            print(f'FAIL {f} ({len(errs)} issues, {nq} questions)')
            for e in errs[:20]:
                print(f'  - {e}')
            if expect_mode and kind == 'valid':
                unexpected += 1
                print('  unexpected: this valid example should pass')
                failed += 1
            if not expect_mode:
                failed += 1
        else:
            counts['pass'] += 1
            print(f'PASS {f} ({nq} questions)')
            if expect_mode and kind in ('invalid', 'mismatch'):
                unexpected += 1
                print('  unexpected: this file should fail')
                failed += 1
    print(f"summary pass={counts['pass']} fail={counts['fail']} files={len(files)} questions={counts['questions']}")
    if expect_mode and unexpected:
        print(f'example expectations missed: {unexpected}')
        return 1
    if expect_mode and unexpected == 0 and failed == 0:
        print('examples: valid files passed; invalid and mismatch files failed as expected')
        return 0
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
