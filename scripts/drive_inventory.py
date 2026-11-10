#!/usr/bin/env python3
"""Drive inventory from public embeddedfolderview pages (cached under cache/drive/).
BFS from cache/drive_roots.json, fetches any folder not cached, writes drive_inventory.csv + drive_folders.csv.
Optional --sizes: HEAD-style probe of each file for byte size (one small request per file)."""
import csv, html, json, os, re, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
import paths
B=paths.root(); C=f'{B}/cache/drive'
CACHE_ONLY='--cache-only' in sys.argv
def get(fid):
    p=f'{C}/{fid}.html'
    if os.path.exists(p) and os.path.getsize(p): return open(p,encoding='utf8',errors='ignore').read(),'ok'
    if CACHE_ONLY: return None,'not_crawled_yet'
    r=subprocess.run(['curl','-sL','--max-time','40','-w','\n__HTTP__%{http_code}',f'https://drive.google.com/embeddedfolderview?id={fid}'],capture_output=True,text=True)
    body,_,code=r.stdout.rpartition('\n__HTTP__'); time.sleep(0.6)
    if code.strip()!='200' or 'flip-entries' not in body: return None,f'http_{code.strip()}'
    open(p,'w').write(body); return body,'ok'
def entries(body):
    for chunk in body.split('<div class="flip-entry" id="entry-')[1:]:
        eid=chunk.split('"',1)[0]
        href=re.search(r'<a href="([^"]+)"',chunk).group(1)
        name=html.unescape(re.search(r'<div class="flip-entry-title">([^<]*)',chunk).group(1))
        mod=(re.search(r'flip-entry-last-modified"><div>([^<]*)',chunk) or [None,''])[1]
        mime=(re.search(r'/type/([^"]+)"',chunk) or [None,''])[1]
        yield eid,href,name,mod,mime
def size_of(fid):
    r=subprocess.run(['curl','-sI','-L','--max-time','30',f'https://drive.usercontent.google.com/download?id={fid}&export=download'],capture_output=True,text=True)
    m=re.findall(r'(?i)content-length:\s*(\d+)',r.stdout); ct=re.findall(r'(?i)content-type:\s*([^\r\n;]+)',r.stdout)
    time.sleep(0.5)
    if ct and 'text/html' in ct[-1]: return ''  # virus-scan interstitial (large file) or blocked
    return m[-1] if m else ''
def main(sizes=False):
    roots=json.load(open(f'{B}/cache/drive_roots.json'))
    files=[]; folders=[]; seen=set()
    q=[(r['id'],r['id'],r['label'],r['source'],r['label']) for r in roots]
    while q:
        fid,root,label,src,path=q.pop(0)
        if fid in seen: continue
        seen.add(fid); body,st=get(fid)
        title=html.unescape(re.search(r'<title>([^<]*)',body).group(1)) if body and '<title>' in body else ''
        n=0
        for eid,href,name,mod,mime in (entries(body) if body else []):
            n+=1
            if '/drive/folders/' in href: q.append((eid,root,label,src,f'{path}/{name}')); continue
            ext=os.path.splitext(name)[1].lower().lstrip('.')
            files.append(dict(root_label=label,root_source=src,root_folder_id=root,parent_folder_id=fid,path=f'{path}/{name}',name=name,extension=ext,mime=mime,size_bytes='',modified=mod,file_id=eid,url=href))
        folders.append(dict(folder_id=fid,root_folder_id=root,sheet_label=label,source=src,path=path,drive_title=title,status=st,entries=n,is_root=fid==root))
    if sizes:
        for f in files: f['size_bytes']=size_of(f['file_id'])
    for name,rows in (('drive_inventory.csv',files),('drive_folders.csv',folders)):
        with open(f'{B}/{name}','w',newline='') as fh:
            w=csv.DictWriter(fh,list(rows[0])); w.writeheader(); w.writerows(rows)
    import collections
    print('folders',len(folders),'unreachable',sum(f['status']!='ok' for f in folders),'files',len(files))
    print(collections.Counter(f['extension'] or f['mime'] for f in files).most_common(20))
    print('empty roots',[f['sheet_label'] for f in folders if f['is_root'] and f['entries']==0])
if __name__=='__main__': main('--sizes' in sys.argv)
