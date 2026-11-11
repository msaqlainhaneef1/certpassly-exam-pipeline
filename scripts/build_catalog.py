#!/usr/bin/env python3
"""Step 1: sheet -> catalog.csv/json + review.csv. Verifies official URLs (HTTP 200 + code/name on page)."""
import csv, json, re, os, sys, hashlib, subprocess, time, html, argparse
sys.path.insert(0, os.path.dirname(__file__))
from lookup import VENDORS, EXAMS, LABEL_FIX, CODE_VENDOR, EXTRA_VENDORS
import paths, site_settings, config_load, vendor_reg
from adapters import parse_catalog_page
B=paths.root(); SRC=f'{B}/sources'
def compact(s): return re.sub(r'[^a-z0-9]','',s.lower())
def fetch(url):
    key=hashlib.sha1(url.encode()).hexdigest()[:16]; p=f'{SRC}/{key}.html'; meta=p+'.json'
    if os.path.exists(meta): return json.load(open(meta)), (open(p,encoding='utf8',errors='ignore').read() if os.path.exists(p) else '')
    os.makedirs(SRC,exist_ok=True)
    r=subprocess.run(['curl','-sL','-A','Mozilla/5.0','--max-time','30','-o',p,'-w','%{http_code} %{url_effective}',url],capture_output=True,text=True)
    code,_,final=r.stdout.partition(' '); time.sleep(1)
    body=open(p,encoding='utf8',errors='ignore').read() if os.path.exists(p) else ''
    m={'url':url,'http':code,'final_url':final,'sha256':hashlib.sha256(body.encode()).hexdigest(),'path':p,'retrieved_at':time.strftime('%Y-%m-%dT%H:%M:%S%z')}
    json.dump(m,open(meta,'w')); return m, body
def text(body): return html.unescape(re.sub(r'\s+',' ',re.sub(r'<[^>]+>',' ',body)))
ap=argparse.ArgumentParser(description='Build catalog.csv from the owner sheet.')
ap.add_argument('--sheet', default=os.environ.get('CERTPASSLY_SHEET') or '')
ap.add_argument('--root', default=None)
args, _=ap.parse_known_args()
if args.root: paths.set_root(args.root); B=paths.root(); SRC=f'{B}/sources'
cfg=site_settings.load()
sheet=args.sheet or (cfg.get('raw') or {}).get('paths',{}).get('sheet') or os.path.join(B,'sheet.csv')
if not os.path.exists(sheet):
    raise SystemExit('Sheet not found: %s (pass --sheet)'%sheet)
rows=list(csv.reader(open(sheet,encoding='utf-8-sig')))
OV=vendor_reg.catalog_overrides()
def _lab_match(rule,lab):
    return lab.upper()==rule['label'].upper() if rule.get('match')=='upper' else lab==rule['label']
vhead={'C':None,'E':None}; cat={}; review=[]
def rv(reason,label,link,cell,vendor,note): review.append(dict(reason=reason,raw_label=label,drive_link=link,sheet_cell=cell,context_vendor=vendor or '',note=note))
for i,r in enumerate(rows,1):
    r=(r+['']*5)[:5]
    for col,(lab,link,stat) in (('A',(r[0],r[2],r[1])),('D',(r[3],r[4],''))):
        lab=lab.strip(); side='C' if col=='A' else 'E'
        if not lab: continue
        cell=f'{col}{i}'; c=compact(lab)
        if c in VENDORS:
            vhead[side]=VENDORS[c][0]
            if link: rv('vendor_only_folder',lab,link,cell,VENDORS[c][0],'Vendor header with a Drive folder but no exam code. Ask which exams this folder holds.')
            for h in OV.get('header_notes') or []:
                if compact(h['header'])==c: rv(h['reason'],lab,'',cell,'',h['note'])
            continue
        key=re.sub(r'\s+','',lab).upper()
        code=LABEL_FIX.get(key)
        if not code:
            for k in EXAMS:
                if re.sub(r'\s+','',k).upper()==key: code=k
        sk=next((x for x in OV.get('skip_labels') or [] if _lab_match(x,lab)),None)
        if sk:
            rv(sk['reason'],lab,link,cell,vhead[side] if sk.get('vendor_context')=='@header' else sk.get('vendor_context',''),sk['note']); continue
        mg=next((x for x in OV.get('label_merges') or [] if _lab_match(x,lab)),None)
        if mg:
            if mg.get('review')=='before': rv(mg['reason'],lab,link,cell,mg.get('vendor_context',''),mg['note'])
            code=mg['code']
        if not code: rv('unknown_label',lab,link,cell,vhead[side],'Label not in lookup tables. Not guessed.'); continue
        v=EXAMS[code]['vendor']
        if vhead[side] and vhead[side]!=v and code not in CODE_VENDOR:
            rv('vendor_header_mismatch',lab,link,cell,vhead[side],f'Code belongs to {v} by code lookup but sits under header {vhead[side]}.')
        for cn in OV.get('code_notes') or []:
            if code in cn['codes']: rv(cn['reason'],lab,link,cell,cn.get('vendor_context',''),cn['note'])
        e=cat.setdefault(code,dict(code=code,vendor=v,labels=[],cells=[],statuses=[],folders=[]))
        if e['labels'] and not mg: rv('duplicate_row',lab,link,cell,v,f'Same exam already listed at {e["cells"][0]}. Merged.')
        if mg and mg.get('review')=='after': rv(mg['reason'],lab,link,cell,mg.get('vendor_context',''),mg['note'])
        e['labels'].append(lab); e['cells'].append(cell); e['statuses'].append(stat.strip()); 
        if link: e['folders'].append(link.strip())
# shared folder check
seen={}
for e in cat.values():
    for f in e['folders']:
        fid=re.search(r'/(?:folders|d)/([\w-]+)',f).group(1); seen.setdefault(fid,[]).append(e['code'])
for fid,codes in seen.items():
    if len(codes)>1: rv('shared_folder_link','/'.join(codes),f'https://drive.google.com/drive/folders/{fid}','',cat[codes[0]]['vendor'],'The same Drive folder is linked for different exams. One link is probably wrong.')
out=[]
for code,e in cat.items():
    L=EXAMS[code]; vend=next((x for x in list(VENDORS.values())+list(EXTRA_VENDORS.values()) if x[0]==e['vendor']),(e['vendor'],e['vendor'],''))
    rec=dict(vendor=vend[1],vendor_slug=vend[0],certification='',exam_code=code,exam_name='',sheet_label=' | '.join(e['labels']),sheet_status=' | '.join(s for s in e['statuses'] if s) ,
             drive_folder_url=' | '.join(e['folders']),sheet_cell=' | '.join(e['cells']),official_exam_url='',url_http='',url_sha256='',source_path='',page_names_exam='',empty_reason='')
    if not L.get('urls'): rec['empty_reason']='Official exam page not located in this phase (no confirmed URL pattern; not guessed).'
    for u in L.get('urls',[]):
        m,body=fetch(u); t=text(body)
        rec.update(official_exam_url=m['final_url'] or u,url_http=m['http'],url_sha256=m['sha256'],source_path=m['path'])
        if m['http']!='200': rec['empty_reason']=f'Official URL returned HTTP {m["http"]} to the script (bot block or moved); names left empty until checked in a browser.'; continue
        tl=t.lower(); has_code=code.lower() in tl or code.replace('/','').lower() in tl
        parsed=parse_catalog_page(e['vendor'], code, u, body, t)
        rec['exam_name']=parsed.get('exam_name') or rec['exam_name']
        rec['certification']=parsed.get('certification') or rec['certification']
        rec['empty_reason']=parsed.get('empty_reason') or ''
        nm=L.get('name',''); ct=L.get('cert','')
        N=lambda x: re.sub(r'\s+',' ',re.sub(r'[\u2013\u2014:\-]',' ',x.lower())).strip()
        nt=N(t)
        if not rec['exam_name'] and nm and N(nm) in nt: rec['exam_name']=nm
        if not rec['certification'] and ct and N(ct) in nt: rec['certification']=ct
        if not rec['exam_name']:
            if len(t)<3000:
                rec['empty_reason']='Page resolves (HTTP 200) but content is rendered by JavaScript, so the script could not read names. Recheck in a browser.'
            elif not rec['empty_reason']:
                rec['empty_reason']='Page resolves but the expected name was not found in page text; left empty.'
        else:
            rec['empty_reason']=''
        rec['page_names_exam']='yes' if (has_code or rec['exam_name']) else 'no'
        if rec['url_http']=='200': break
    out.append(rec)
out.sort(key=lambda r:(r['vendor'],r['exam_code']))
# Drive-only Salesforce folders (from owner's Salesforce folder) not in sheet -> review
dc={'rows':[]}
if os.path.exists(f'{B}/drive_folders.csv'):
    for d in csv.DictReader(open(f'{B}/drive_folders.csv')):
        parts=d['path'].split('/')
        extra_roots=list((cfg.get('catalog') or {}).get('extra_drive_roots') or [])
        extra_ids={r['id']:r for r in extra_roots if r.get('id')}
        if d['root_folder_id'] in extra_ids and len(parts)==2:
            dc['rows'].append(dict(parent_folder_id=d['root_folder_id'],kind='folder',name=parts[1],url='https://drive.google.com/drive/folders/'+d['folder_id'],vendor_slug=extra_ids[d['root_folder_id']].get('vendor_slug','')))
sheetlabels={compact(x) for r in out for x in r['sheet_label'].split(' | ')}|{compact(r['exam_code']) for r in out}
for d in dc['rows']:
    if d['parent_folder_id'] in {r['id'] for r in extra_roots} and d['kind']=='folder' and compact(d['name']) not in sheetlabels:
        vslug=d.get('vendor_slug') or extra_ids.get(d['parent_folder_id'],{}).get('vendor_slug','')
        note=f"Folder in the owner {vslug or 'extra'} Drive folder but not in the sheet. Not added to the catalog. Owner to confirm scope."
        if re.search(r'\(\d+ Questions\)',d['name']): note+=' Name carries a question count label, which is not an official figure.'
        if re.search(r'\((SU|SP)\d\d\)',d['name']): note+=' Name carries an old release tag (likely a retired version).'
        rv('drive_only_folder',d['name'],d['url'],'drive',vslug,note)
F=['vendor','vendor_slug','certification','exam_code','exam_name','sheet_status','drive_folder_url','sheet_cell','sheet_label','official_exam_url','url_http','page_names_exam','url_sha256','source_path','empty_reason']
with open(f'{B}/catalog.csv','w',newline='') as f: w=csv.DictWriter(f,F); w.writeheader(); w.writerows(out)
json.dump(dict(generated=time.strftime('%Y-%m-%d %H:%M %Z'),status='draft',exams=out),open(f'{B}/catalog.json','w'),indent=1)
REVIEW_COLS=['reason','raw_label','drive_link','sheet_cell','context_vendor','note']
with open(f'{B}/review.csv','w',newline='') as f: w=csv.DictWriter(f,REVIEW_COLS); w.writeheader(); w.writerows(review)  # header even when nothing needs review
print('exams',len(out),'vendors',len({r['vendor'] for r in out}),'review',len(review))
import collections; print(collections.Counter(r['reason'] for r in review))
print('url200',sum(r['url_http']=='200' for r in out),'cert',sum(bool(r['certification']) for r in out),'name',sum(bool(r['exam_name']) for r in out))
