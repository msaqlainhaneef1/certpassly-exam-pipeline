#!/usr/bin/env python3
"""Assemble the draft question bank from extracted items + visual transcription + authored explanations.
Scripted: classification, skill mapping, payloads, CSVs, media, logs. Usage: build_bank.py research/<vendor>/<CODE>.json"""
import csv, hashlib, json, os, re, shutil, sys, glob, datetime
sys.path.insert(0, os.path.dirname(__file__)); import qtypes as Q, paths
B=paths.root(); R=json.load(open(sys.argv[1])); code=R['exam_code']; OUT=f'{B}/out/{code}'; EX=f'{OUT}/extracted'
TPL=paths.csv_template_dir()
def cols(n): return next(csv.reader(open(f'{TPL}/{n}',encoding='utf-8-sig')))
def write(name,rows,columns):
    with open(f'{OUT}/import/{name}','w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=columns,extrasaction='raise'); w.writeheader(); [w.writerow({c:r.get(c,'') for c in columns}) for r in rows]
def sha(p): return hashlib.sha256(open(p,'rb').read()).hexdigest()
def _loadj(path, default):
    return json.load(open(path,encoding='utf-8')) if os.path.exists(path) else default
S=json.load(open(f'{EX}/split.json'))
VT=_loadj(f'{EX}/visual_transcription.json', {})
VD=_loadj(f'{EX}/visual_draft.json', {})
EXP={**_loadj(f'{OUT}/authoring/explanations_text.json', {}), **_loadj(f'{OUT}/authoring/explanations_visual.json', {})}
_bs=f'{B}/research/{R["vendor_slug"]}/{code}-bank-sources.json'
BS={s['id']:s for s in _loadj(_bs, {'sources':[]}).get('sources') or []}
src_meta={json.load(open(m))['url']:json.load(open(m)) for m in glob.glob(f'{B}/sources/{R["vendor_slug"]}/*.json')}
types,_=Q.registry(); src_pdf=next(f for f in json.load(open(f'{OUT}/intake/files.json'))['files'] if f.get('use')=='extracted' or str(f.get('name','')).lower().endswith('.pdf'))
exam_key=code.lower(); ver=f'{exam_key}-{R["objectives"]["outline_as_of"]}'
dom_key=lambda d:f'{ver}-d{d}'; top_key=lambda t:f'{ver}-d{t.split(".")[0]}-t{t}'
META_PATH=f'{OUT}/authoring/bank_meta.json'
if not os.path.exists(META_PATH):
    raise SystemExit('missing authoring/bank_meta.json (skill map, skipped files, cover-fact notes). Add it in the author or extract stage.')
META=json.load(open(META_PATH))
def skill(text):
    t=text.lower() if not any(r.get('flags')=='' for r in META.get('skill_rules') or []) else text
    for rule in META.get('skill_rules') or []:
        flags=re.I if 'i' in (rule.get('flags') or 'i') else 0
        if re.search(rule['pattern'], text if flags==0 else t, flags):
            return rule['topic']
    return META.get('default_topic') or '1.1'
_off=META.get('off_syllabus') or {}
OFF_SYL=re.compile(_off['pattern'], re.I) if _off.get('pattern') else None
os.makedirs(f'{OUT}/media',exist_ok=True); os.makedirs(f'{OUT}/import',exist_ok=True)
qs=[]; stems={}; review=[]; held=[]; media_rows=[]; qma=[]; cleanups=json.load(open(f'{EX}/cleanups.json'))
for k,it in S.items():
    vt=VT.get(k); qtype,reason=Q.classify(it,vt)
    if vt and vt.get('held'):
        held.append(dict(question_key=k,type='active_screen',reason=vt['reason'],stem=it['stem'],regions=vt.get('candidate_regions'))); continue
    if it['options'] and not re.sub(r'[^A-H]','',it['answer_raw'].upper()):
        held.append(dict(question_key=k,type=qtype,reason='no answer in the owner file; key not invented',stem=it['stem'],regions=[])); continue
    if k not in EXP:
        raise SystemExit(f'author stage: no explanation for {k} in authoring/explanations_text.json or explanations_visual.json')
    e=EXP[k]; t=types[qtype]; text=it['stem']+' '+' '.join(it['options'].values())+' '+' '.join((vt or {}).get('rows',[]))+' '+(vt or {}).get('template','')
    sk=skill(text); flags=[]; hr=False
    content={'prompt':it['stem']}; key={}; expl={'core':e['c']}; frozen={}; opts=[]
    if qtype in ('single_choice','multiple_select','image_based_choice','true_false'):
        letters=list(re.sub(r'[^A-H]','',it['answer_raw'].upper().replace(' ','')))
        for i,(lt,tx) in enumerate(it['options'].items()):
            opts.append(dict(id=lt,option_letter=lt.upper(),text=tx,is_correct=lt.upper() in letters,rationale_text=e['o'][i])); expl[lt]=e['o'][i]
        content['options']=[dict(id=o['id'],text=o['text']) for o in opts]; key={'correct_option_ids':[l.lower() for l in letters]}
        if qtype=='multiple_select': content['constraints']={'min_choices':len(letters),'max_choices':len(letters)}
    elif qtype=='yes_no_matrix':
        content.update(rows=[dict(id=f'r{i+1}',text=r) for i,r in enumerate(vt['rows'])],columns=[dict(id='yes',text='Yes'),dict(id='no',text='No')])
        key={'rows':{f'r{i+1}':v for i,v in enumerate(vt['key'])}}
        for i,r in enumerate(vt['rows']): frozen[f'row.r{i+1}']=r; expl[f'r{i+1}']=e['o'][i]
    else:
        blanks=[]; 
        for bi,ch in enumerate(vt['blanks']):
            bid=f'blank{bi+1}'; lab=vt['labels'][bi] if vt.get('labels') else None
            blanks.append(dict(id=bid,label=lab or f'Answer box {bi+1}',choices=[dict(id=f'c{ci+1}',text=c) for ci,c in enumerate(ch)]))
            for ci,c in enumerate(ch): frozen[f'blank.{bid}.c{ci+1}']=c; expl[f'{bid}.c{ci+1}']=e['o'][bi][ci]
        tpl=vt.get('template') or '\n'.join(f'{l} {{{{blank{i+1}}}}}' for i,l in enumerate(vt['labels']))
        content.update(prompt_template=tpl.replace('{{blank','{{blank'),blanks=blanks); key={'slots':{f'blank{i+1}':f'c{j+1}' for i,j in enumerate(vt['key'])}}
    # media
    exh=[]; 
    if it['question_images'] and (qtype=='image_based_choice' or (vt and vt.get('exhibit'))):
        f=it['question_images'][0]; ext=f.rsplit('.',1)[1]; dst=f'media/{k}-exhibit.{ext}'; shutil.copy(f'{OUT}/media/src/{f}',f'{OUT}/{dst}')
        alts=(META.get('exhibit_alts') or {}); alt=alts.get(k) or alts.get('default') or 'Exhibit image from the source question.'
        content['image_url']=dst; content['image_alt']=alt; exh.append((dst,'exhibit','candidate',alt))
    if vt:
        for f in it['question_images'][-1:]:
            if content.get('image_url','').endswith(f): continue
            ext=f.rsplit('.',1)[1]; dst=f'media/{k}-answer-area.{ext}'; shutil.copy(f'{OUT}/media/src/{f}',f'{OUT}/{dst}'); exh.append((dst,'diagram','reviewer_only','Source answer area image used to transcribe the interactive item.'))
        for n,f in enumerate(it['answer_images'],1):
            ext=f.rsplit('.',1)[1]; dst=f'media/{k}-answer-review{"-"+str(n) if len(it["answer_images"])>1 else ""}.{ext}'; shutil.copy(f'{OUT}/media/src/{f}',f'{OUT}/{dst}'); exh.append((dst,'answer_image_review_only','reviewer_only','Marked answer image from the source file, reviewer only.'))
        hr=True; flags.append('text and key read from images: human confirmation required')
        sk_rows=VD.get(k,{}).get('key',{})
        if qtype=='yes_no_matrix':
            sc=[sk_rows.get(f'r{i+1}') for i in range(len(vt['rows']))]
            if None in sc: flags.append('marker-box script could not confirm every row; key read visually')
            elif sc!=vt['key']: flags.append('SCRIPT/VISUAL KEY MISMATCH')
        if vt.get('note'): flags.append(vt['note'])
    from PIL import Image
    for dst,kind,vis,alt in exh:
        im=Image.open(f'{OUT}/{dst}'); h=sha(f'{OUT}/{dst}')
        media_rows.append(dict(filename=os.path.basename(dst),original_name=dst,filepath=dst,mime_type='image/png' if dst.endswith('png') else 'image/jpeg',file_size_bytes=os.path.getsize(f'{OUT}/{dst}'),width=im.width,height=im.height,alt_text=alt,category='question_image',uploaded_by='',usage_count=0))
        qma.append(dict(question_version_key=f'{k}-v1',path=dst,kind=kind,mime_type=media_rows[-1]['mime_type'],sha256=h,width=im.width,height=im.height,alt_text=alt,rights_status='unverified',visibility=vis,license_evidence_ref='intake/rights-confirmation.md',long_description='',human_review_required='yes' if kind!='exhibit' or hr else 'no'))
    prob=Q.agree(qtype,it['stem'],n_correct=len(key.get('correct_option_ids',[])) or None,n_blanks=len(content.get('blanks',[])) or None,has_exhibit=bool(content.get('image_url')))
    if prob: flags+=['MARKER: '+p for p in prob]
    if e['a']!='key_matches_current_docs' and e['a']!='key_could_not_be_checked': flags.append(f"accuracy: {e['a']}: {e.get('n','')}")
    elif e.get('n'): flags.append('note: '+e['n'])
    if OFF_SYL and OFF_SYL.search(text) and sk==(_off.get('when_topic') or sk): flags.append(_off.get('flag') or 'possibly off-syllabus')
    srcs=[dict(source_url=BS[s]['url'],title=BS[s]['title'],evidence_key=f'qsrc-{s.lower()}') for s in e['s']]
    q=dict(question_key=k,question_version_key=f'{k}-v1',exam_key=exam_key,exam_version_key=ver,domain_key=dom_key(sk.split('.')[0]),topic_key=top_key(sk),
           question_type=qtype,type_reason=reason,source_markers=Q.markers(it['stem']),type_status='assigned',prompt_text=it['stem'],options=[dict(id=o['id'],option_letter=o['option_letter'],text=o['text']) for o in opts],
           response_schema={'type':qtype,'content':content},answer_key=key,answer_key_status='flagged_for_owner' if e['a'] in ('key_wrong','key_outdated','key_arguable') else 'as_in_source_file',
           accuracy_status=e['a'],core_explanation=e['c'],explanations=expl,source_url=srcs[0]['source_url'],sources=srcs,
           media={'path':content['image_url'],'alt':content['image_alt']} if content.get('image_url') else {},
           human_review_required=hr or bool(flags and any(f.startswith(('accuracy','MARKER','SCRIPT')) for f in flags)),publication_state='draft',structural_gate='not_checked',review_gate='not_checked',
           license_status='not_checked',rights_status='asserted_by_owner',created_source=f'owner_file sha256:{src_pdf["sha256"][:16]} {it["marker"]} pages {it["pages"]}',
           live_status='live' if types[qtype].get('enabled') and types[qtype].get('publishable') else 'staging only',flags=flags,difficulty='')
    qs.append(q)
    stems[k]=dict(stem=it['stem'],options={o['id']:o['text'] for o in opts},other_frozen_text=frozen,source=dict(file=src_pdf['name'],pages=it['pages'],marker=it['marker']))
    if flags: review.append((k,qtype,flags))
json.dump(dict(status='draft',exam_key=exam_key,questions=qs,held_for_review=held),open(f'{OUT}/questions.json','w'),indent=1,ensure_ascii=False)
json.dump(stems,open(f'{EX}/stems.json','w'),indent=1,ensure_ascii=False)
# CSVs
write('questions.csv',[dict(question_key=q['question_key'],exam_key=exam_key,exam_version_key=ver,domain_key=q['domain_key'],topic_key=q['topic_key'],question_type=q['question_type'],difficulty='',
    question_version_key=q['question_version_key'],prompt_text=q['prompt_text'],free_preview_requested='no',author_key='owner',created_source=q['created_source'],license_status='not_checked',
    editor_notes='; '.join(q['flags'])[:900],structural_gate='not_checked',review_gate='not_checked',publication_state='draft',blocking_reason='Draft import. Publish gates not attested; SME, source verification and rights review pending.') for q in qs],cols('questions.csv'))
ao=[]
for q in qs:
    for i,o in enumerate(q['options']):
        ao.append(dict(option_key=f"{q['question_key']}-{o['id']}",question_version_key=q['question_version_key'],option_letter=o['option_letter'],display_order=i+1,option_text=o['text'],
                       is_correct='yes' if o['id'] in q['answer_key'].get('correct_option_ids',[]) else 'no',rationale_text=q['explanations'][o['id']],checked_by='',checked_at='',status='draft'))
write('answer_options.csv',ao,cols('answer_options.csv'))
def wc(q): return ' '.join(v for kk,v in q['explanations'].items() if kk!='core' and (kk in q['answer_key'].get('correct_option_ids',[]) or q['answer_key'].get('rows',{}).get(kk)=='yes' or kk in [f'{b}.{c}' for b,c in q['answer_key'].get('slots',{}).items()]))
write('explanations.csv',[dict(question_version_key=q['question_version_key'],core_explanation=q['core_explanation'],why_correct=wc(q) or q['core_explanation'],
    why_incorrect=' '.join(f"{kk}: {v}" for kk,v in q['explanations'].items() if kk!='core'),architectural_takeaway='',common_mistake='',reviewer='',reviewed_at='',status='draft') for q in qs],cols('explanations.csv'))
write('question_sources.csv',[dict(question_version_key=q['question_version_key'],evidence_key=s['evidence_key'],source_url=s['source_url'],relevant_section=s['title'],supports_claim='core explanation',rights_status='unverified',reviewer='',verified_at='',status='unverified') for q in qs for s in q['sources']],cols('question_sources.csv'))
sc=cols('sources.csv'); sp=f'{OUT}/import/sources.csv'; old=[r for r in csv.DictReader(open(sp))] if os.path.exists(sp) else []; old=[r for r in old if not r['evidence_key'].startswith('qsrc-')]
used={s['evidence_key']:s for q in qs for s in q['sources']}
for ek,s in sorted(used.items()):
    m=src_meta[s['source_url']]
    old.append(dict(evidence_key=ek,entity_type='question_bank',entity_key=exam_key,claim_or_field='question explanations',source_type='official_documentation',document_title=s['title'],source_url=s['source_url'],official='yes',
                    source_section='',retrieved_at=m['retrieved_at'],verified_by='',verified_at='',rights_reviewed='not_checked',rights_notes='',review_notes=f"saved copy sha256 {m['sha256']}",status='unverified'))
write('sources.csv',old,sc)
write('media_assets.csv',media_rows,['uuid','filename','original_name','filepath','mime_type','file_size_bytes','width','height','alt_text','category','uploaded_by','usage_count'])
write('question_media_assets.csv',qma,['question_version_key','path','kind','mime_type','sha256','width','height','alt_text','rights_status','visibility','license_evidence_ref','long_description','human_review_required'])
# logs
import site_settings; SS=site_settings.load()
def mask(t):
    hit=any(re.search(r'\b'+re.escape(d)+r'\b',t,re.I) for d in SS['brand_denylist']) or any(re.search(rx,t,re.I) for n,rx in SS['policy']['contact_patterns'].items() if n!='phone')
    return f"[seller branding or contact line, {len(t)} chars, sha256 {hashlib.sha256(t.encode()).hexdigest()[:12]}]" if hit else t
for c in cleanups: c['before']=mask(c['before'])
L=['# CLEANUP LOG','','Every removal or repair between the raw PDF text layer and the imported text. Removals of seller branding, contact links, update offers and cover facts are owner-authorized (see intake/rights-confirmation.md).','',
   '| # | Question | Field | Before | After | Reason |','|---|---|---|---|---|---|']+[f"| {i} | {c['question_key']} | {c['field']} | {c['before'].replace('|','/')[:120]} | {c['after'] or '(removed)'} | {c['reason']} |" for i,c in enumerate(cleanups,1)]
L+=['','## Image text','','Text inside answer-area images was read by Tesseract OCR (scripts/vision_util.py) as a draft and then transcribed from the image into extracted/visual_transcription.json. Those items are marked human_review_required. Lone periods that sit after a drop-down box in the image are kept in the template.']
open(f'{OUT}/CLEANUP-LOG.md','w').write('\n'.join(L)+'\n')
from collections import Counter
cnt=Counter(q['question_type'] for q in qs)
RV=['# REVIEW','',f'{len(S)} items in the file. {len(qs)} imported as drafts, {len(held)} held. {len(review)} imported items carry flags. '+(f'All {sum(1 for k in S if VT.get(k) and not VT[k].get("held"))} image-based items need human confirmation of text and key.' if any(VT.get(k) and not VT[k].get('held') for k in S) else 'No image-based items.'),'',
    '## Held (not importable without owner input)','']+[f"* {h['question_key']}: {h['reason']}. Type would be {h['type']}. Visible clickable areas: {', '.join(h.get('regions') or []) or 'none'}." for h in held]
RV+=['','## Flagged items','','| Question | Type | Flags |','|---|---|---|']+[f"| {k} | {t} | {'; '.join(f).replace('|','/')} |" for k,t,f in review]
RV+=['','## Accuracy review summary','']+[f'* {a}: {n}' for a,n in Counter(q['accuracy_status'] for q in qs).most_common()]
RV+=['','Accuracy statuses come from a check against the saved official pages listed in import/sources.csv. "key_could_not_be_checked" means the saved pages did not settle it in this pass; an SME must check those.']
cover=META.get('cover_facts_conflict'); skipped=list(META.get('skipped_files') or [])
# Files the intake stage skipped (VCE and other binaries) are listed even if bank_meta forgot them.
for f in json.load(open(f'{OUT}/intake/files.json')).get('files') or []:
    if str(f.get('use','')).startswith('skipped') and not any(f.get('name','') in x for x in skipped):
        skipped.append(f"{f.get('name')} (sha256 {str(f.get('sha256',''))[:16]}): {f.get('use')}")
if cover:
    cover=[cover] if isinstance(cover,str) else [str(c) for c in cover]
    RV+=['','## Cover facts in the file that differ from the official page','']+['* '+c for c in cover]
if skipped:
    RV+=['','## VCE file skipped' if any('.vce' in s.lower() for s in skipped) else '## Skipped source files','']+[f'* {s}' for s in skipped]
open(f'{OUT}/REVIEW.md','w').write('\n'.join(RV)+'\n')
print('imported',len(qs),'held',len(held),'flagged',len(review),dict(cnt))
