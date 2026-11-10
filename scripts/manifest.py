#!/usr/bin/env python3
"""Write out/<CODE>/import/MANIFEST.json: sha256 of every generated file plus inputs. Usage: manifest.py research/<vendor>/<CODE>.json"""
import glob,hashlib,json,os,sys,datetime
sys.path.insert(0, os.path.dirname(__file__))
import paths
B=paths.root(); R=json.load(open(sys.argv[1])); code=R['exam_code']; OUT=f'{B}/out/{code}'
fs=sorted(f for f in glob.glob(f'{OUT}/**/*',recursive=True)+glob.glob(f'{B}/out/vendors/{R["vendor_slug"]}/*')+glob.glob(f'{B}/out/certifications/{R["certification_slug"]}/*')
          +[os.path.abspath(sys.argv[1]),f'{B}/research/vendors/{R["vendor_slug"]}.json',f'{B}/research/certs/{R["certification_slug"]}.json']+glob.glob(f'{B}/sources/{R["vendor_slug"]}/*')
          if os.path.isfile(f) and not f.endswith(('MANIFEST.json','VALIDATION.md','validation.json')))
role=lambda f:'import' if '/import/' in f else 'page' if '/out/' in f and f.endswith(('.html','.json')) and 'simulator' not in f else 'source' if '/sources/' in f else 'research' if '/research/' in f else 'other'
M={'exam_code':code,'status':'draft','generated_at':paths.now_label(),
   'files':[{'path':f,'role':role(f),'bytes':os.path.getsize(f),'sha256':hashlib.sha256(open(f,'rb').read()).hexdigest()} for f in fs]}
json.dump(M,open(f'{OUT}/import/MANIFEST.json','w'),indent=1); print(len(fs),'files in manifest')
