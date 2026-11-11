#!/usr/bin/env python3
"""Check produced import files against reference/site-format (no site application code).

    check_import_conformance.py --root WORKSPACE --exam CODE
    check_import_conformance.py --dir out/CODE
    check_import_conformance.py --package EXAM-package.zip

Reports pass/fail per file. Exit 1 if any file fails. This does not prove that the
live site importer accepts the files; it only checks the published site-format contract.
"""
from __future__ import annotations
import argparse, csv, json, os, sys, zipfile, tempfile, shutil
from pathlib import Path

HERE=Path(__file__).resolve().parent
SKILL=HERE.parent

NEW_BANK_FIELDS=['key_source','verification_status','answer_key_status','scoring_excluded']
NEW_SIM_FIELDS=['scoring_excluded_question_keys']
SITE_MUST_SUPPORT = [
    'questions.json answer_key_status values: as_in_source_file, flagged_for_owner, researched_unverified, answer_not_found',
    'questions.json key_source values: owner_file, researched_official (empty/omitted only for answer_not_found)',
    'questions.json verification_status: unverified (required on researched_unverified and answer_not_found items)',
    'questions.json scoring_excluded: true for answer_not_found items, false/omitted otherwise',
    'questions.json scoring_excluded_question_keys: list of answer_not_found keys',
    'simulator_settings.json scoring_excluded_question_keys: same list; those items are shown for review but never scored',
    'simulator_settings.json scoring_excluded_note (optional string)',
    'questions.json human_review_required and reviewer_needed on researched_unverified items',
    'questions.json research_evidence (official url, sha256, verbatim quote) on researched_unverified items',
]

def fmt_dir(root: Path) -> Path:
    return root / 'reference' / 'site-format' / 'v1'

def load_format(root: Path):
    d=fmt_dir(root)
    statuses=json.loads((d/'allowed_statuses.json').read_text(encoding='utf-8'))
    types=json.loads((d/'question_types.json').read_text(encoding='utf-8'))
    import_files=json.loads((d/'import_files.json').read_text(encoding='utf-8'))
    schema=json.loads((d/'simulator_settings.schema.json').read_text(encoding='utf-8'))
    templates={}
    for p in (d/'csv_templates').glob('*.csv'):
        with p.open(encoding='utf-8-sig', newline='') as f:
            templates[p.name]=next(csv.reader(f))
    return statuses, types, import_files, schema, templates

def rows(path: Path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        r=csv.DictReader(f)
        return list(r), r.fieldnames or []

def add(report, file, ok, detail):
    report.append(dict(file=file, status='pass' if ok else 'fail', detail=detail))

def check_dir(out: Path, skill_root: Path):
    report=[]
    statuses, types, import_files, schema, templates = load_format(skill_root)
    allowed_types=set()
    if isinstance(types, dict):
        if 'types' in types and isinstance(types['types'], dict):
            allowed_types=set(types['types'])
        elif 'types' in types and isinstance(types['types'], list):
            allowed_types=set(x.get('id') or x.get('name') or x for x in types['types'])
        else:
            allowed_types=set(types)
    else:
        allowed_types=set(types)
    imp=out/'import'
    if not imp.is_dir():
        add(report, 'import/', False, f'missing import directory: {imp}')
        return report
    for name in import_files['contract_csv_files']:
        path=imp/name
        if not path.is_file():
            add(report, name, False, 'missing contract CSV')
            continue
        _, headers=rows(path)
        expected=templates.get(name)
        if expected is None:
            add(report, name, False, 'no CSV template in site-format')
            continue
        if list(headers)!=list(expected):
            add(report, name, False, f'header mismatch: got {list(headers)} expected {expected}')
        else:
            add(report, name, True, f'{sum(1 for _ in rows(path)[0])} data rows, headers match template')
    for name, expected in (import_files.get('sidecar_csv_files') or {}).items():
        path=imp/name
        if not path.is_file():
            add(report, name, True, 'sidecar absent (optional unless the pipeline emitted it)')
            continue
        _, headers=rows(path)
        if list(headers)!=list(expected):
            add(report, name, False, f'sidecar header mismatch: got {list(headers)} expected {expected}')
        else:
            add(report, name, True, f'{sum(1 for _ in rows(path)[0])} data rows, headers match import_files.json')

    qpath=out/'questions.json'
    if not qpath.is_file():
        add(report, 'questions.json', False, 'missing')
    else:
        Q=json.loads(qpath.read_text(encoding='utf-8'))
        problems=[]
        if Q.get('status') not in (statuses.get('page_status') or ['draft']):
            problems.append(f"status {Q.get('status')!r} not allowed")
        qs=Q.get('questions') or []
        held=Q.get('held_for_review') or []
        excl=list(Q.get('scoring_excluded_question_keys') or [])
        allowed_aks=set(statuses.get('answer_key_status') or [])
        allowed_ks=set(statuses.get('key_source') or [])
        allowed_vs=set(statuses.get('verification_status') or [])
        anf=[]
        for x in qs:
            typ=x.get('question_type')
            if allowed_types and typ not in allowed_types:
                problems.append(f"{x.get('question_key')}: unknown question_type {typ}")
            aks=x.get('answer_key_status')
            if aks not in allowed_aks:
                problems.append(f"{x.get('question_key')}: answer_key_status {aks!r} not in allowed_statuses")
            ks=x.get('key_source')
            if ks not in (None,'') and ks not in allowed_ks:
                problems.append(f"{x.get('question_key')}: key_source {ks!r} not in allowed_statuses")
            vs=x.get('verification_status')
            if vs not in (None,'') and vs not in allowed_vs:
                problems.append(f"{x.get('question_key')}: verification_status {vs!r} not in allowed_statuses")
            if aks=='researched_unverified':
                if ks!='researched_official' or vs!='unverified':
                    problems.append(f"{x.get('question_key')}: researched_unverified must have key_source=researched_official and verification_status=unverified")
            if aks=='answer_not_found':
                anf.append(x.get('question_key'))
                if x.get('scoring_excluded') is not True:
                    problems.append(f"{x.get('question_key')}: answer_not_found must set scoring_excluded true")
            elif x.get('scoring_excluded'):
                problems.append(f"{x.get('question_key')}: scoring_excluded set but item is keyed")
            for fld in statuses.get('forbidden_nonempty_fields') or []:
                if x.get(fld) not in (None,''):
                    problems.append(f"{x.get('question_key')}: forbidden nonempty field {fld}")
        if sorted(excl)!=sorted(anf):
            problems.append(f'scoring_excluded_question_keys {excl} != answer_not_found keys {anf}')
        if held:
            problems.append(f'held_for_review is not empty: {[h.get("question_key") for h in held]}')
        add(report, 'questions.json', not problems, '; '.join(problems) or f'{len(qs)} questions, 0 held, {len(anf)} answer_not_found, fields {", ".join(NEW_BANK_FIELDS)} checked')

    sp=out/'simulator_settings.json'
    if not sp.is_file():
        add(report, 'simulator_settings.json', False, 'missing')
    else:
        sim=json.loads(sp.read_text(encoding='utf-8'))
        problems=[]
        for req in schema.get('required') or []:
            if req not in sim:
                problems.append(f'missing required {req}')
        if sim.get('status')!=schema.get('properties',{}).get('status',{}).get('const','draft') and sim.get('status')!='draft':
            problems.append(f"status {sim.get('status')!r} is not draft")
        if 'scoring_excluded_question_keys' not in sim:
            problems.append('missing scoring_excluded_question_keys (required by v1.1 answer_research contract; use [] when none)')
        else:
            keys=sim['scoring_excluded_question_keys']
            if not isinstance(keys, list) or any(not isinstance(k,str) for k in keys):
                problems.append('scoring_excluded_question_keys must be an array of strings')
            if qpath.is_file():
                Q=json.loads(qpath.read_text(encoding='utf-8'))
                if list(keys)!=list(Q.get('scoring_excluded_question_keys') or []):
                    problems.append('simulator scoring_excluded_question_keys does not match questions.json')
        add(report, 'simulator_settings.json', not problems, '; '.join(problems) or f"schema required fields present; scoring_excluded_question_keys={sim.get('scoring_excluded_question_keys')}")
    return report

def resolve_package(zip_path: Path):
    tmp=Path(tempfile.mkdtemp(prefix='cp-conformance-'))
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(tmp)
    # find questions.json
    hits=list(tmp.rglob('questions.json'))
    if not hits:
        return tmp, None
    return tmp, hits[0].parent

def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--root', help='Pipeline workspace root (used with --exam)')
    ap.add_argument('--exam', help='Exam code under <root>/out/<CODE>')
    ap.add_argument('--dir', help='Path to an exam out directory (contains import/ and questions.json)')
    ap.add_argument('--package', help='Path to an exam package zip')
    ap.add_argument('--skill-root', default=str(SKILL), help='Skill repo with reference/site-format')
    ap.add_argument('--json', action='store_true', help='Print JSON report')
    a=ap.parse_args(argv)
    cleanup=None
    if a.package:
        cleanup, out=resolve_package(Path(a.package))
        if out is None:
            print('FAIL: no questions.json in package', a.package); sys.exit(2)
    elif a.dir:
        out=Path(a.dir)
    elif a.root and a.exam:
        out=Path(a.root)/'out'/a.exam
    else:
        ap.error('provide --dir, --package, or --root plus --exam')
    report=check_dir(out, Path(a.skill_root))
    if cleanup:
        shutil.rmtree(cleanup, ignore_errors=True)
    failed=[r for r in report if r['status']=='fail']
    if a.json:
        print(json.dumps(dict(out=str(out), files=report, failed=len(failed), passed=len(report)-len(failed)), indent=1))
    else:
        print(f'conformance: {out}')
        for r in report:
            print(f"  {r['status'].upper():4}  {r['file']}: {r['detail']}")
        print(f"{len(report)-len(failed)} passed, {len(failed)} failed, {len(report)} files")
        print('Live site importer acceptance is untested (no site application or database was used).')
        print('Fields the site team must support:')
        for line in SITE_MUST_SUPPORT:
            print('  - '+line)
    return 1 if failed else 0

if __name__=='__main__':
    sys.exit(main())
