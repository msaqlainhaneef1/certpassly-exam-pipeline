"""Question-type registry from the bundled site-format snapshot, plus source-marker rules.

This module never reads the app repo or a PHP file.
"""
from __future__ import annotations
import json, os, re, sys
sys.path.insert(0, os.path.dirname(__file__))
import paths

def _data(version=None):
    p=os.path.join(paths.site_format_dir(version),'question_types.json')
    return json.load(open(p,encoding='utf-8'))

def registry(version=None):
    d=_data(version)
    types=d['types']; aliases=dict(d.get('aliases') or {})
    return types, aliases

def family_rules(version=None):
    d=_data(version).get('family_rules') or {}
    # restore tuple shape used by gen_site_question_types
    return {k:(v.get('payload',''), v.get('answer_key','')) for k,v in d.items()}

FAMILY_RULES=None  # filled lazily; gen_site_question_types calls family_rules()

MARKERS=None
def markers_map(version=None):
    return dict(_data(version).get('markers') or {})

RX={'yes_no':re.compile(r'select Yes if the statement is true',re.I),
    'dropdown':re.compile(r'completes the sentence|drop-down|options in the answer area',re.I),
    'multi':re.compile(r'\b(which|choose|select) (two|three|four)\b|Each correct answer presents',re.I),
    'exhibit':re.compile(r'shown in the following exhibit|refer to the exhibit',re.I),
    'hotspot':re.compile(r'^HOTSPOT\b'),'dragdrop':re.compile(r'DRAG DROP',re.I)}

def markers(stem):
    return sorted(k for k,r in RX.items() if r.search(stem))

def classify(item, visual=None):
    """item: split.json record. visual: transcription record for image-keyed items. Returns (type, reason)."""
    m=markers(item['stem'])
    if item['options']:
        letters=re.sub(r'[^A-H]','',item['answer_raw'].upper())
        vals={v.strip().lower().rstrip('.') for v in item['options'].values()}
        if len(item['options'])==2 and vals in ({'true','false'},{'yes','no'}): return 'true_false','two True/False options'
        if 'exhibit' in m and item['question_images']: return ('multiple_select' if len(letters)>1 else 'image_based_choice'),'lettered options with exhibit image'
        if len(letters)>1: return 'multiple_select',f'{len(letters)} letters keyed'
        return 'single_choice','one letter keyed'
    if visual is None: return 'needs_review','visual item without transcription'
    if 'yes_no' in m and visual.get('rows'): return 'yes_no_matrix','Yes/No statement grid'
    if visual.get('blanks'):
        return ('inline_dropdown' if len(visual['blanks'])==1 else 'multi_blank_dropdown'),f"{len(visual['blanks'])} drop-down(s) in answer area"
    if visual.get('type')=='active_screen': return 'active_screen','boxed controls on a mock screen'
    return 'needs_review','no rule matched'

def agree(qtype, stem, n_correct=None, n_blanks=None, has_exhibit=False):
    """Marker-agreement check: source markers must agree with the assigned type. Returns list of problems."""
    m=markers(stem); p=[]
    if 'yes_no' in m and qtype!='yes_no_matrix': p.append('Yes/No statement marker but type is '+qtype)
    if qtype=='yes_no_matrix' and 'yes_no' not in m: p.append('yes_no_matrix without Yes/No marker')
    if 'multi' in m and qtype!='multiple_select': p.append('choose-N marker but type is '+qtype)
    if qtype=='multiple_select':
        w=re.search(r'\b(?:which|choose|select|what are) (two|three|four)\b',stem,re.I); want={'two':2,'three':3,'four':4}.get(w.group(1).lower()) if w else None
        if want and n_correct!=want: p.append(f'stem asks for {want} but key has {n_correct}')
    if qtype in ('inline_dropdown','multi_blank_dropdown') and not ('dropdown' in m or 'hotspot' in m): p.append('drop-down type without answer-area marker')
    if qtype=='inline_dropdown' and n_blanks!=1: p.append('inline_dropdown must have 1 blank')
    if qtype=='multi_blank_dropdown' and (n_blanks or 0)<2: p.append('multi_blank_dropdown needs 2+ blanks')
    if 'hotspot' in m and qtype in ('single_choice','multiple_select','true_false'): p.append('HOTSPOT marker flattened to a plain choice type')
    if 'exhibit' in m and not has_exhibit: p.append('exhibit marker but no exhibit attached')
    if qtype=='image_based_choice' and not has_exhibit: p.append('image_based_choice without image')
    return p
