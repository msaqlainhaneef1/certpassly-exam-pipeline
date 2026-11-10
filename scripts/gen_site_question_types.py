#!/usr/bin/env python3
"""Write SITE-QUESTION-TYPES.md from the bundled site-format registry (no app repo)."""
import sys,os,json
sys.path.insert(0,os.path.dirname(__file__))
import qtypes as Q, paths
types,aliases=Q.registry(); out=sys.argv[1]
fmt=os.path.join(paths.site_format_dir(),'question_types.json')
ver=json.load(open(fmt)).get('site_format_version','v1')
FAM=Q.family_rules(); MARK=Q.markers_map()
L=['# Site question types (bundled site-format snapshot)','',
 f'Source: reference/site-format/{ver}/question_types.json (static snapshot shipped with this skill; the pipeline does not read the app repo). Payload and answer key rules are the ones the app handler validates. Recognition is how scripts/qtypes.py detects the type in an owner file.','',
 'Live means the type is enabled for grading in the app. Publishable means the publish gate may approve it.','',
 '## Aliases','','| Written as | Canonical |','|---|---|']+[f'| {a} | {b} |' for a,b in aliases.items()]+['',
 '## Types','','| # | Type | Family | Scorer | Enabled | Publishable | Live | Uses options | Payload (handler) | Answer key | How to recognize in a source file |','|---|---|---|---|---|---|---|---|---|---|---|']
for i,(n,d) in enumerate(types.items(),1):
    fam=d.get('family'); pay,key=FAM.get(fam,('',''))
    live='yes' if d.get('enabled') and d.get('publishable') else 'staging only' if d.get('enabled') else 'no'
    L.append(f"| {i} | `{n}` | {fam} | {d.get('scorer') or 'none'} | {'yes' if d.get('enabled') else 'no'} | {'yes' if d.get('publishable') else 'no'} | {live} | {'yes' if d.get('uses_options') else 'no'} | {pay} | {key} | {MARK.get(n,'')} |")
L+=['',f'Counts: {len(types)} types, {sum(1 for d in types.values() if d.get("enabled") and d.get("publishable"))} enabled and publishable, {sum(1 for d in types.values() if d.get("enabled") and not d.get("publishable"))} enabled but not publishable, {sum(1 for d in types.values() if not d.get("enabled"))} disabled.','',
 'Extra rules from the publish gate: single_choice and image_based_choice need 2 or more options and exactly 1 correct; multiple_select needs 3 or more options, 2 or more correct, not all correct; true_false needs exactly 2 options; hotspot family needs region labels and 4-number normalized coordinates plus an image.']
open(out,'w').write('\n'.join(L)+'\n'); print(len(types),'types')
