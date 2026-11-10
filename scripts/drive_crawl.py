#!/usr/bin/env python3
"""Crawl public Google Drive folders via embeddedfolderview (names, types, dates only).
Resumable: caches each folder page under cache/drive/<id>.html."""
import csv, html, json, os, re, sys, time, subprocess
sys.path.insert(0, os.path.dirname(__file__))
import paths
BASE=paths.root()
CACHE=f'{BASE}/cache/drive'
ENTRY=re.compile(r'<div class="flip-entry" id="entry-([^"]+)".*?<a href="([^"]+)".*?aria-label="([^"]*)".*?<div class="flip-entry-title">([^<]*)</div>.*?<div class="flip-entry-last-modified"><div>([^<]*)</div>',re.S)
def fetch(fid):
    p=f'{CACHE}/{fid}.html'
    if os.path.exists(p) and os.path.getsize(p)>0:
        return open(p,encoding='utf8',errors='ignore').read(), 'cached'
    r=subprocess.run(['curl','-sL','-w','\n__HTTP__%{http_code}','--max-time','40',f'https://drive.google.com/embeddedfolderview?id={fid}'],capture_output=True,text=True)
    out=r.stdout; code=out.rsplit('__HTTP__',1)[-1].strip(); body=out.rsplit('\n__HTTP__',1)[0]
    time.sleep(0.6)
    if code!='200' or 'flip-entries' not in body and 'flip-list' not in body:
        return None, f'http_{code}'
    open(p,'w').write(body); return body,'fetched'
def main():
    roots=json.load(open(f'{BASE}/cache/drive_roots.json'))  # [{id,label,source}]
    rows=[]; status=[]; seen=set()
    queue=[(r['id'],r['label'],r['label'],r['source'],r['id']) for r in roots]
    while queue:
        fid,label,path,src,root=queue.pop(0)
        if fid in seen: continue
        seen.add(fid)
        body,st=fetch(fid)
        title=''
        if body:
            m=re.search(r'<title>([^<]*)</title>',body); title=html.unescape(m.group(1)) if m else ''
        n=0
        if body:
            for eid,href,aria,name,mod in ENTRY.findall(body):
                name=html.unescape(name); n+=1
                isfolder='/drive/folders/' in href
                ext=os.path.splitext(name)[1].lower().lstrip('.') if not isfolder else ''
                rows.append(dict(root_folder_id=root,root_label=label if fid==root else '',parent_folder_id=fid,
                    path=f'{path}/{name}',name=name,kind='folder' if isfolder else 'file',type=('folder' if isfolder else (aria or ext)),
                    extension=ext,size_bytes='',modified=mod,file_id=eid,url=href))
                if isfolder: queue.append((eid,label,f'{path}/{name}',src,root))
        status.append(dict(folder_id=fid,root_folder_id=root,path=path,sheet_label=label,source=src,drive_title=title,status=st if body else st,entries=n))
        print(st,fid,path,n,file=sys.stderr)
    json.dump(dict(rows=rows,status=status),open(f'{BASE}/cache/drive_crawl.json','w'),indent=1)
main()
