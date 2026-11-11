#!/usr/bin/env python3
"""Write draft import files for one exam (+ shared vendor/cert rows) matching the app contract columns, plus sidecars.
Usage: emit_import.py research/<vendor>/<CODE>.json"""
import csv, hashlib, json, os, sys, glob, datetime
sys.path.insert(0, os.path.dirname(__file__)); import site_settings, paths
B=paths.root(); S=site_settings.load(); TODAY=paths.today()
TPL=paths.csv_template_dir()
def cols(name): return next(csv.reader(open(f'{TPL}/{name}',encoding='utf-8-sig')))
def write(d,name,rows,columns=None):
    columns=columns or cols(name); os.makedirs(d,exist_ok=True)
    with open(f'{d}/{name}','w',newline='') as f:
        w=csv.DictWriter(f,columns); w.writeheader()
        for r in rows:
            extra=set(r)-set(columns)
            if extra: raise SystemExit(f'{name}: unknown columns {extra}')
            w.writerow({c:r.get(c,'') for c in columns})
R=json.load(open(sys.argv[1])); code=R['exam_code']; v=R['vendor_slug']; c=R['certification_slug']; e=R['exam_slug']
V=json.load(open(f'{B}/research/vendors/{v}.json')); C=json.load(open(f'{B}/research/certs/{c}.json'))
out=f'{B}/out/{code}'; imp=f'{out}/import'
pages=[json.load(open(p)) for p in sorted(glob.glob(f'{out}/pages/*.json'))]+[json.load(open(f'{B}/out/vendors/{v}/vendor.json')),json.load(open(f'{B}/out/certifications/{c}/certification.json'))]
src={}
for p in pages:
    for s in p['sources']: src[s['url']]=s
ek={u:f'src-{hashlib.sha1(u.encode()).hexdigest()[:10]}' for u in src}
sgu=next(s['url'] for s in R['sources'] if s['id']=='sg'); cpu=next(s['url'] for s in R['sources'] if s['id']=='cp')
F=R['facts']; ver=f'{e}-{R["objectives"]["outline_as_of"]}'
BR='Draft import. Publish gates not attested; sources unverified; human review required.'
hub=next(p for p in pages if p['kind']=='exam_hub'); vend=next(p for p in pages if p['kind']=='vendor'); cert=next(p for p in pages if p['kind']=='certification')
write(imp,'vendors.csv',[dict(vendor_key=v,display_name=V['name'],short_name=V['name'],official_site_url=V['official_site'],official_certification_url=V['official_site'],official_learning_url=V.get('official_learning_url') or V.get('official_site'),
    directory_summary=vend['meta']['meta_description'],overview=vend['body_html'],catalog_enabled='no',official_lifecycle='active',page_copy_status='draft',official_evidence_key=ek[cpu],catalog_gate='not_checked',content_gate='not_checked',blocking_reason=BR+' Logo not included (brand guidelines).')])
write(imp,'certifications.csv',[dict(certification_key=c,vendor_key=v,credential_name=C['name'],official_credential_url=cpu,credential_type='certification',level=C['level']['value'],official_lifecycle='unknown',
    short_description=cert['meta']['meta_description'],skills_summary='; '.join(d['name'] for d in R['objectives']['domains']),audience_summary=F['audience']['value'],validity_period='',renewal_summary='',
    official_version_date=(C.get('last_updated') or {}).get('value'),requirements_verified='no',source_evidence_key=ek[cpu],page_copy_status='draft',catalog_gate='not_checked',content_gate='not_checked',blocking_reason=BR+' Validity and renewal not stated by vendor.')])
write(imp,'cert_exam_links.csv',[dict(relation_key=f'{c}--{e}',certification_key=c,exam_key=e,requirement_type='required',alternative_logic='none',is_current='yes',official_evidence_key=ek[cpu],status='draft',blocking_reason=BR)])
write(imp,'exams.csv',[dict(exam_key=e,vendor_key=v,certification_key=c,exam_code=code,official_exam_name=R['exam_name']['value'],exam_slug=e,official_exam_url=cpu,official_guide_url=sgu,official_lifecycle='unknown',exam_version_key=ver,
    audience_summary=F['audience']['value'],format_description=f"{F['question_formats']['value']}. {F['duration_minutes']['value']} minutes. Pass mark {F['passing_score']['value']}. Question count not published by the vendor.",
    official_duration_minutes=F['duration_minutes']['value'],official_passing_score=F['passing_score']['value'],source_evidence_key=ek[sgu],page_copy_status='draft',catalog_gate='not_checked',content_gate='not_checked',practice_gate='not_checked',commerce_gate='not_checked',blocking_reason=BR+' No practice bank.')])
write(imp,'exam_versions.csv',[dict(exam_version_key=ver,exam_key=e,official_version_code=f"Skills measured as of {R['objectives']['outline_as_of']}",effective_date=R['objectives']['outline_as_of'],is_current='yes',official_source_key=ek[sgu],
    blueprint_summary='; '.join(f"{d['name']} ({d['weight_min_pct']} to {d['weight_max_pct']} percent)" for d in R['objectives']['domains']),status='draft')])
dr=[];tr=[]
for d in R['objectives']['domains']:
    dk=f'{ver}-d{d["code"]}'
    dr.append(dict(domain_key=dk,exam_version_key=ver,domain_code=d['code'],domain_name=d['name'],weight_min_pct=d['weight_min_pct'],weight_max_pct=d['weight_max_pct'],official_source_key=ek[sgu],source_section='Skills at a glance',status='draft'))
    for t in d['topics']: tr.append(dict(topic_key=f'{dk}-t{t["code"]}',domain_key=dk,topic_code=t['code'],topic_name=t['name'],official_source_key=ek[sgu],description='; '.join(t['subtopics']),is_scaffold='no',status='draft'))
write(imp,'domains.csv',dr); write(imp,'topics.csv',tr)
prev_sources=f'{imp}/sources.csv'
existing_qsrc=[r for r in csv.DictReader(open(prev_sources))] if os.path.exists(prev_sources) else []
existing_qsrc=[r for r in existing_qsrc if r.get('evidence_key','').startswith('qsrc-')]
sr=[]
for u,s in src.items(): sr.append(dict(evidence_key=ek[u],entity_type='exam' if u==sgu else 'certification',entity_key=e if u==sgu else c,claim_or_field='official facts and skills outline' if u==sgu else 'credential facts, duration, languages',source_type='official_vendor_page',
    document_title=(next((s.get('title') or C['name'] for s in R['sources'] if s['url']==u), C['name'])),source_url=u,official='yes',retrieved_at=s['retrieved_at'],rights_reviewed='not_checked',review_notes=f"sha256 {s['sha256']}",status='unverified'))
write(imp,'sources.csv',sr+existing_qsrc)
pc=[]
for p in pages:
    ent={'vendor':('vendor',v),'certification':('certification',c)}.get(p['kind'],('exam',e))
    for fk,val in [('h1',p['meta']['h1']),('body_html',p['body_html'])]:
        pc.append(dict(copy_key=f"{p['kind']}-{ent[1]}-{fk}",entity_type=ent[0],entity_key=ent[1],page_route_pattern=p['meta']['path'],section_key=p['kind'],field_key=fk,locale='en',draft_text=val,status='draft',source_evidence_key=';'.join(ek[s['url']] for s in p['sources']),blocking_reason=BR))
write(imp,'page_copy.csv',pc)
BANK=os.path.exists(os.path.join(os.path.dirname(imp),'questions.json'))  # build_bank.py owns question files when a bank exists
for n in (['reviews.csv','products.csv','launch_checklist.csv'] if BANK else ['questions.csv','answer_options.csv','explanations.csv','question_sources.csv','reviews.csv','products.csv','launch_checklist.csv']): write(imp,n,[])
# sidecars mapped to app tables
write(imp,'seo_metadatas.csv',[dict(page_key=f"{p['kind']}:{p['entity']}",seo_title=p['meta']['title'],meta_description=p['meta']['meta_description'],canonical_url=p['meta']['canonical_url'],robots=p['meta']['robots'],og_title=p['meta']['og']['og:title'],og_description=p['meta']['og']['og:description'],og_image_url='',h1_heading=p['meta']['h1']) for p in pages],
      ['page_key','seo_title','meta_description','canonical_url','robots','og_title','og_description','og_image_url','h1_heading'])
write(imp,'page_meta_extras.csv',[dict(page_key=f"{p['kind']}:{p['entity']}",slug=p['meta']['slug'],twitter_card=p['meta']['twitter']['twitter:card'],twitter_title=p['meta']['twitter']['twitter:title'],twitter_description=p['meta']['twitter']['twitter:description'],og_type=p['meta']['og']['og:type'],og_url=p['meta']['og']['og:url'],og_site_name=p['meta']['og']['og:site_name'],last_updated=p['meta']['last_updated'],last_checked=p['meta']['last_checked'],jsonld_types='|'.join(j['@type'] for j in p['jsonld']),note='No app column yet; needs column and template support') for p in pages],
      ['page_key','slug','twitter_card','twitter_title','twitter_description','og_type','og_url','og_site_name','last_updated','last_checked','jsonld_types','note'])
facts=[]
for k,f in F.items():
    if f.get('value') not in (None,'') and f.get('source_id'):
        facts.append(dict(exam_key=e,fact_key=k,value=json.dumps(f['value']) if isinstance(f['value'],list) else f['value'],source_url=sgu if f['source_id']=='sg' else cpu,verified_on='',notes=f"quote: {f.get('quote','')}"))
    else: facts.append(dict(exam_key=e,fact_key=k,value='',source_url='',verified_on='',notes=f"empty: {f.get('reason','')}"))
write(imp,'exam_official_facts.csv',facts,['exam_key','fact_key','value','source_url','verified_on','notes'])
faqp=next(p for p in pages if p['kind']=='faq')
import re,html as H
qa=re.findall(r'<h2>(.*?)</h2><p>(.*?)</p>',faqp['body_html'])
write(imp,'exam_faqs.csv',[dict(exam_key=e,locale='en',question=H.unescape(q),answer=H.unescape(re.sub(r'<[^>]+>','',a)),category='exam_facts',sort_order=i+1,is_published='false',reviewed_at='') for i,(q,a) in enumerate(qa)],
      ['exam_key','locale','question','answer','category','sort_order','is_published','reviewed_at'])
# simulator settings
doms=R['objectives']['domains']; mids=[(d['weight_min_pct']+d['weight_max_pct'])/2 for d in doms]
sim=dict(exam_key=e,status='draft',time_limit_minutes=dict(value=F['duration_minutes']['value'],basis='official',source=cpu),passing_score=dict(value=F['passing_score']['value'],basis='official',source=sgu),
    question_count=(dict(value=F['question_count']['value'],basis='official',source=F['question_count'].get('url') or sgu,note=F['question_count'].get('quote') or 'Published by the vendor.')
                   if (F.get('question_count') or {}).get('value') not in (None,'',[])
                   else dict(value=None,basis='site_choice',note='Not published by the vendor. Owner sets this when a reviewed bank exists.')),
    domain_mix=[dict(domain_code=d['code'],domain_name=d['name'],official_range=[d['weight_min_pct'],d['weight_max_pct']],planned_share_pct=round(m*100/sum(mids),1),basis='midpoint of official range, normalized') for d,m in zip(doms,mids)],
    rules=dict(allow_back_navigation=dict(value=True,basis='site_choice'),allow_flagging=dict(value=True,basis='site_choice'),show_review_screen=dict(value=True,basis='site_choice'),
      delivered_question_types=dict(value=[],basis='site_choice',note='Set when the bank exists. Must use types that are enabled and publishable in config/question_types.php.')),
    sections=[],sections_note='The vendor does not publish sections for this exam; single section.',bank_status='not_ready')
json.dump(sim,open(f'{out}/simulator_settings.json','w'),indent=1)
write(imp,'exam_simulation_rules.csv',[dict(exam_key=e,allow_back_navigation='1',allow_flagging='1',show_review_screen='1',delivered_question_types='[]',official_source_url=cpu,notes=('Draft. Navigation flags are site choices. Question count follows the official page. Bank not ready.' if (F.get('question_count') or {}).get('value') not in (None,'',[]) else 'Draft. Navigation flags are site choices. Question count is a site choice (not published). Bank not ready.'))],
      ['exam_key','allow_back_navigation','allow_flagging','show_review_screen','delivered_question_types','official_source_url','notes'])
print('import files',len(os.listdir(imp)))
