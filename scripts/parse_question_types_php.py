#!/usr/bin/env python3
"""Parse config/question_types.php into a JSON registry. Scripts only, no AI.

The type enum for site-format v2 is exactly the keys in the PHP `types` array.
This script never adds a type that is not in that file (including image_legacy).
"""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from pathlib import Path

def _php_bool(v: str) -> bool | None:
    v = v.strip()
    if v == 'true':
        return True
    if v == 'false':
        return False
    return None

def parse_question_types_php(text: str, source_path: str | None = None) -> dict:
    if "schema_version" not in text:
        raise ValueError('question_types.php has no schema_version')
    sm = re.search(r"'schema_version'\s*=>\s*'([^']+)'", text)
    site_schema = sm.group(1) if sm else None
    aliases = {}
    am = re.search(r"'aliases'\s*=>\s*\[(.*?)\],\s*(?:/\*|')", text, re.S)
    # aliases block ends before types or a comment then types
    am = re.search(r"'aliases'\s*=>\s*\[(.*?)\]\s*,", text, re.S)
    if not am:
        raise ValueError('could not parse aliases')
    for k, v in re.findall(r"'([^']+)'\s*=>\s*'([^']+)'", am.group(1)):
        aliases[k] = v
    types = {}
    tm = re.search(r"'types'\s*=>\s*\[(.*)\];\s*$", text, re.S)
    if not tm:
        # file ends with ]; ]; 
        tm = re.search(r"'types'\s*=>\s*\[(.*)$", text, re.S)
    body = tm.group(1) if tm else ''
    # each 'key' => [ ... ],
    for m in re.finditer(r"'([a-z0-9_]+)'\s*=>\s*\[(.*?)\]\s*,", body, re.S):
        key, block = m.group(1), m.group(2)
        rec = {'key': key}
        for fk, fv in re.findall(r"'([a-z_]+)'\s*=>\s*([^,\n]+)", block):
            raw = fv.strip().rstrip(',')
            if raw.startswith("'") and raw.endswith("'"):
                rec[fk] = raw[1:-1]
            elif raw == 'null':
                rec[fk] = None
            else:
                b = _php_bool(raw)
                rec[fk] = b if b is not None else raw
        types[key] = rec
    if len(types) != 30:
        raise ValueError(f'expected 30 types, parsed {len(types)}: {list(types)}')
    publishable = [k for k, t in types.items() if t.get('enabled') and t.get('publishable')]
    staging = [k for k, t in types.items() if t.get('enabled') and not t.get('publishable')]
    blocked = [k for k, t in types.items() if not t.get('enabled')]
    out = {
        'site_format_version': 'v2',
        'source_schema_version': site_schema,
        'source_path_note': 'Parsed from the site config/question_types.php (read-only). The enum is exactly these 30 keys.',
        'aliases': aliases,
        'types': types,
        'lists': {
            'all': list(types.keys()),
            'publishable': publishable,
            'staging': staging,
            'blocked': blocked,
        },
        'counts': {
            'types': len(types),
            'publishable': len(publishable),
            'staging': len(staging),
            'blocked': len(blocked),
        },
    }
    if source_path:
        data = Path(source_path).read_bytes()
        out['source_sha256'] = hashlib.sha256(data).hexdigest()
        out['source_bytes'] = len(data)
    return out

def flag_registry_mismatches(registry: dict, requested_types=None) -> list:
    """Return mismatch records. Never insert a missing type into the registry."""
    requested_types = list(requested_types or [])
    keys = set(registry['types'])
    aliases = registry.get('aliases') or {}
    mismatches = []
    for name in requested_types:
        if name in keys:
            continue
        if name in aliases:
            mismatches.append({
                'requested_type': name,
                'status': 'alias_only',
                'maps_to': aliases[name],
                'note': 'This name is an alias, not a registry key. Use the canonical key. It was not added as a new type.',
            })
        else:
            mismatches.append({
                'requested_type': name,
                'status': 'not_in_registry',
                'maps_to': None,
                'note': 'Not in question_types.php. Flagged as a mismatch. Not added to the v2 enum.',
            })
    return mismatches

def main(argv=None):
    ap = argparse.ArgumentParser(description='Parse site question_types.php into JSON.')
    ap.add_argument('php', help='Path to question_types.php')
    ap.add_argument('-o', '--output', help='Write registry JSON here')
    ap.add_argument('--mismatch-out', help='Write mismatch report JSON here')
    ap.add_argument('--request', action='append', default=[], help='Extra type names to check against the registry (none by default).')
    args = ap.parse_args(argv)
    p = Path(args.php)
    text = p.read_text(encoding='utf-8')
    reg = parse_question_types_php(text, str(p))
    mismatches = flag_registry_mismatches(reg, args.request)
    if args.output:
        Path(args.output).write_text(json.dumps(reg, indent=2) + '\n', encoding='utf-8', newline='\n')
    if args.mismatch_out:
        Path(args.mismatch_out).write_text(json.dumps({
            'site_format_version': 'v2',
            'mismatches': mismatches,
        }, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(f"types={reg['counts']['types']} publishable={reg['counts']['publishable']} staging={reg['counts']['staging']} blocked={reg['counts']['blocked']}")
    for m in mismatches:
        print(f"MISMATCH {m['requested_type']}: {m['status']}")
    return 0 if not mismatches else 2

if __name__ == '__main__':
    sys.exit(main())
