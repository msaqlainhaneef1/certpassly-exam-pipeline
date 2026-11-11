#!/usr/bin/env python3
"""Orchestrate the CertPassly exam pipeline.

    python3 run_pipeline.py --exam CODE [--root DIR] [--config FILE] [--stage NAME] [--date YYYY-MM-DD] [--offline] [--sheet FILE] [--zip]

Stages run in order. Use --stage NAME to run one stage, or repeat --stage.
The run is idempotent: vendor and certification pages are skipped when unchanged,
and saved official sources are reused. Failed checks exit with status 1.

The only stage that calls AI is `author` (batched explanations and original page
prose), and this script never calls a model for it: it only checks that the author
files exist. The `intent` and `writing` stages are scripts too: search intent is built
from research facts, and the writing check flags problems so only the flagged parts
go back for a fix. This script never talks to the app repo, GitHub or artisan.
"""
from __future__ import annotations
import argparse, csv, json, os, shutil, subprocess, sys, time
from pathlib import Path

HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths, site_settings, config_load, shared_sections

STAGES=[
    ('catalog','no','Build catalog.csv and review.csv from the owner sheet. Network only to check official exam URLs (skipped when a saved copy exists).'),
    ('intake','no','Inventory Drive folders, download owner files, run provenance, write intake/. Network for Drive only.'),
    ('sources','no','Fetch and hash official vendor pages listed in research JSON. Reuses saved copies.'),
    ('research','parser first','Fill or check research JSON from official pages using the vendor adapter in scripts/adapters (chosen from config/vendors.yaml). AI is allowed only for official facts the adapter lists as gaps, each with a quote and source id. Not the author stage.'),
    ('extract','no','Split the owner PDF, write visual_draft from OCR and marker boxes. No AI.'),
    ('textfix','decide only','Propose spelling, grammar and punctuation fixes for stems and options (scripts/text_fixes.py): lost ligatures, repeated words and stray spaces are fixed by script; a/an and possible typos are decided in the author batch (authoring/text_fixes_decisions.json). Never changes keys or option order; product names on the saved official pages are protected. Applied in the bank stage and logged in text-fixes.json.'),
    ('answer_research','pick only','Items with no answer in the owner file: find candidate OFFICIAL pages (research sources, listed URLs, site-restricted search on official_domains), save them with sha256, rank matching lines. The key is picked by AI in the author batch (authoring/answer_research.json) and re-verified by script: official domain, saved copy, verbatim quote. No evidence: item stays as draft flagged answer_not_found and is excluded from scoring.'),
    ('intent','no','Build research/<vendor>/<CODE>.search-intent.json from research facts only: the main query per page, people-also-ask questions from official facts and recorded gaps, and which page answers each. Competitor notes (research/<vendor>/<CODE>.competitor-notes.json) are read as topic labels only. Runs before author and pages. A person may edit the file.'),
    ('author','YES','THE AI STAGE. Batched only: rewrite explanations, write original page prose (page_prose.json), finish visual_transcription.json where OCR is not enough, and write bank_meta.json. Never invent questions. Never change keys or option order; stems and options change only through text_fixes (spelling, grammar, punctuation). This script does not call a model; it checks the files are present and stops with instructions if they are not.'),
    ('pages','no','Build exam (and shared vendor/cert) pages from research JSON + page_prose.json. Vendor and cert pages are skipped when their inputs have not changed.'),
    ('writing','no','Writing check after pages (scripts/check_writing.py, no AI): banned AI phrases, long sentences, dashes, unsourced numbers, grade and word count, search-intent coverage, competitor overlap. Writes writing-review.json and WRITING-REVIEW.md (failed checks only) and authoring/writing_fix_request.json. Only flagged parts go back for a fix, then pages and writing run again (the second check). Exit 1 on flags unless writing.fail_on_flags is false; open flags stay in REVIEW.md.'),
    ('import','no','Write workbook CSVs, sidecars (including page_meta_extras.csv) and simulator_settings.json from the generated pages.'),
    ('bank','no','Assemble questions.json, question import CSVs, media, CLEANUP-LOG.md and REVIEW.md. Runs after import so page sources.csv is merged, not wiped.'),
    ('validate','no','Refresh MANIFEST.json, then run validate.py and check_bank.py. Exit 1 on any failed check.'),
    ('package','no','Zip the exam package plus shared vendor and certification pages.'),
]

def log(fh, msg):
    line=f'{paths.now_label()}  {msg}'
    print(line, flush=True)
    if fh:
        fh.write(line+'\n'); fh.flush()

def run_script(args, logf, extra_env=None):
    env=os.environ.copy()
    if extra_env: env.update(extra_env)
    env['CERTPASSLY_ROOT']=paths.root()
    env['PYTHONUTF8']='1'; env['PYTHONIOENCODING']='utf-8'
    env['PYTHONPATH']=HERE+(os.pathsep+env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
    log(logf, '  $ '+' '.join(args))
    r=subprocess.run(args, cwd=paths.root(), env=env)
    if r.returncode!=0:
        log(logf, f'  FAILED exit {r.returncode}')
        sys.exit(r.returncode)
    return r

def preflight(cfg, exam, logf, stages):
    problems=[]
    fmt=cfg.get('site_format_version') or 'v1'
    try:
        d=paths.site_format_dir(fmt)
        for need in ('question_types.json','csv_templates','url_routes.json','allowed_statuses.json'):
            if not os.path.exists(os.path.join(d,need)):
                problems.append(f'site-format {fmt} missing {need}')
    except SystemExit as e:
        problems.append(str(e))
    if not cfg.get('brand') or not cfg.get('disclaimer'):
        problems.append('config must set brand and disclaimer')
    if not cfg.get('brand_denylist'):
        problems.append('config must set brand_denylist')
    # This pipeline must not depend on an app checkout
    for key in ('CERTPASSLY_APP','APP_REPO','CERTPASSLY_REPO'):
        if os.environ.get(key):
            log(logf, f'note: {key} is set but will be ignored; the skill is self-contained.')
    later={'sources','research','extract','textfix','intent','author','bank','pages','writing','import','validate','package'}
    if later & set(stages) and not exam:
        problems.append('--exam CODE is required for this stage')
    if problems:
        for p in problems: log(logf, 'PREFLIGHT FAIL: '+p)
        sys.exit(2)
    log(logf, f'preflight ok; site_format={fmt}; brand={cfg.get("brand")}; exam={exam or "-"}')

def research_path(root, exam):
    # find research/<vendor>/<CODE>.json (not bank-sources or parsed)
    hits=[]
    rdir=os.path.join(root,'research')
    if not os.path.isdir(rdir): return None
    for dirpath,_,fs in os.walk(rdir):
        if os.path.basename(dirpath) in ('vendors','certs'): continue
        for f in fs:
            if f==f'{exam}.json':
                hits.append(os.path.join(dirpath,f))
    return hits[0] if hits else None

def load_research(root, exam, logf):
    p=research_path(root, exam)
    if not p:
        log(logf, f'research JSON not found for {exam} under research/<vendor>/{exam}.json')
        sys.exit(2)
    return p, json.load(open(p))

def stage_catalog(opts, logf):
    sheet=opts.sheet or os.environ.get('CERTPASSLY_SHEET') or ''
    cfg=config_load.load(os.environ.get('CERTPASSLY_CONFIG'))
    sheet=sheet or ((cfg.get('paths') or {}).get('sheet') or '')
    if not sheet and not os.path.exists(os.path.join(paths.root(),'sheet.csv')):
        if os.path.exists(os.path.join(paths.root(),'catalog.csv')):
            log(logf, 'catalog: no owner sheet given; using the existing catalog.csv (pass --sheet to rebuild it).')
            return
        log(logf, 'catalog: no owner sheet and no catalog.csv. Pass --sheet FILE.'); sys.exit(2)
    cmd=[sys.executable, os.path.join(HERE,'build_catalog.py'), '--root', paths.root()]
    if sheet: cmd+=['--sheet', sheet]
    run_script(cmd, logf)

BINARY_EXT=('.vce','.exe','.bin','.dat','.apkg')

def build_intake_from_folder(exam, folder, out, cfg, logf):
    """Write intake/files.json and rights-confirmation.md from owner files already on disk.

    PDFs are marked use=extracted (first one is the bank source), binary files such
    as VCE are marked skipped and never parsed. Rights text comes from config
    owner_rights_statement; without it the stage stops (rights are the owner's call).
    """
    import hashlib
    files=[]
    for name in sorted(os.listdir(folder)):
        p=os.path.join(folder,name)
        if not os.path.isfile(p) or name.startswith('.') or name.endswith('.part'): continue
        low=name.lower()
        rec=dict(path=os.path.abspath(p), size=os.path.getsize(p), sha256=hashlib.sha256(open(p,'rb').read()).hexdigest(), name=name)
        if low.endswith('.pdf'): rec['use']='extracted'
        elif low.endswith(BINARY_EXT): rec['use']='skipped: binary '+low.rsplit('.',1)[-1].upper()+', not decrypted'
        else: rec['use']='skipped: unsupported file type'
        files.append(rec)
    if not any(f['use']=='extracted' for f in files):
        log(logf, f'intake: no PDF in {folder}'); sys.exit(2)
    stmt=(cfg.get('owner_rights_statement') or '').strip()
    if not stmt:
        log(logf, 'intake: set owner_rights_statement in pipeline.yaml (the owner confirms rights to these files), then rerun.')
        sys.exit(2)
    os.makedirs(out, exist_ok=True)
    json.dump(dict(files=files), open(os.path.join(out,'files.json'),'w',encoding='utf-8'), indent=1, ensure_ascii=False)
    with open(os.path.join(out,'rights-confirmation.md'),'w',encoding='utf-8') as fh:
        fh.write(f'# Rights confirmation for {exam}\n\n{stmt}\n\nrights_status: asserted_by_owner\nlicense_status: not_checked\n\n')
        for f in files: fh.write(f"* {f['name']} sha256 {f['sha256']} use: {f['use']}\n")
    log(logf, f'intake: wrote files.json from {folder} ({len(files)} files; '+', '.join(f["use"] for f in files)+')')

def owner_folder(exam, cfg):
    tmpl=((cfg.get('paths') or {}).get('owner_files') or 'owner-files/{exam}')
    p=tmpl.format(exam=exam)
    return p if os.path.isabs(p) else os.path.join(paths.root(), p)

def stage_intake(opts, logf, exam):
    out=os.path.join(paths.root(),'out',exam,'intake')
    if os.path.exists(os.path.join(out,'files.json')) and not opts.force:
        log(logf, f'intake already present at {out} (idempotent skip). Pass --force to rebuild it.')
        return
    cfg=config_load.load(os.environ.get('CERTPASSLY_CONFIG'))
    folder=owner_folder(exam, cfg)
    has_files=os.path.isdir(folder) and any(not n.startswith('.') for n in os.listdir(folder))
    if not opts.offline and (not has_files or opts.force):
        import drive_fetch
        log(logf, f'intake: downloading owner files for {exam} from its Drive folder in catalog.csv')
        r=drive_fetch.fetch(exam, folder)
        log(logf, f'intake: Drive download done ({len(r["downloaded"])} new, {len(r["skipped"])} already present)')
    elif opts.offline and not has_files:
        log(logf, 'intake: offline, so the Drive download is skipped.')
    if os.path.isdir(folder) and any(not n.startswith('.') for n in os.listdir(folder)):
        return build_intake_from_folder(exam, folder, out, cfg, logf)
    log(logf, f'intake: no owner files. Download the owner files for {exam} into {folder} (PDF plus any VCE), set owner_rights_statement in pipeline.yaml, then rerun.')
    sys.exit(2)

def _generated(rp):
    try: return json.load(open(rp,encoding='utf-8')).get('generated_by')=='research_init'
    except Exception: return False

def stage_sources(opts, logf, exam):
    rp=research_path(paths.root(), exam)
    if not rp or _generated(rp):
        import research_init
        log(logf, 'sources: no hand-written research file; discovering official pages from catalog.csv (render when needed)')
        research_init.discover(exam)
        return
    rpath,R=load_research(paths.root(), exam, logf)
    files=[rpath,
           os.path.join(paths.root(),'research','vendors',R['vendor_slug']+'.json'),
           os.path.join(paths.root(),'research','certs',R['certification_slug']+'.json')]
    files=[f for f in files if os.path.exists(f)]
    env={'CERTPASSLY_OFFLINE':'1'} if opts.offline else None
    if opts.offline:
        # only succeed if every listed source already has a saved copy
        missing=[]
        for f in files:
            for s in json.load(open(f)).get('sources') or []:
                found=False
                v=json.load(open(f)).get('vendor_slug') or R['vendor_slug']
                d=os.path.join(paths.root(),'sources',v)
                if os.path.isdir(d):
                    for n in os.listdir(d):
                        if n.endswith('.json') and json.load(open(os.path.join(d,n))).get('url')==s['url']:
                            found=True
                if not found: missing.append(s['url'])
        if missing:
            log(logf, 'sources missing in offline mode: '+'; '.join(missing))
            sys.exit(2)
        log(logf, 'sources: all official pages already saved (offline)')
        return
    run_script([sys.executable, os.path.join(HERE,'fetch_sources.py'), *files], logf, env)

def stage_research(opts, logf, exam):
    rp=research_path(paths.root(), exam)
    if not rp or _generated(rp):
        import research_init
        research_init.build(exam, force=True)
        log(logf, 'research: research JSON generated from saved official pages (every fact has source id, url, sha256, quote); gaps in research/gaps.json')
    rpath,R=load_research(paths.root(), exam, logf)
    from adapters import parse_official
    out=parse_official(R, paths.root())
    dest=rpath.replace('.json','.parsed.json')
    json.dump(out, open(dest,'w'), indent=1, ensure_ascii=False)
    gaps=out.get('gaps') or []
    agree=out.get('agree')
    if agree:
        log(logf, 'research: adapter compared saved official pages to research JSON: '+json.dumps(agree))
        if not (agree.get('domains') and agree.get('passing_score') and agree.get('tasks')):
            log(logf, 'research: adapter disagrees with research JSON; fix the research file or the saved sources.')
            sys.exit(1)
    else:
        log(logf, f"research: generic adapter fields={list((out.get('fields') or {}).keys())} gaps={gaps}")
    if gaps:
        log(logf, 'research: gaps for the author stage (official quotes only): '+', '.join(gaps))

def stage_extract(opts, logf, exam):
    out=os.path.join(paths.root(),'out',exam)
    split=os.path.join(out,'extracted','split.json')
    if os.path.exists(split) and not opts.force:
        log(logf, 'extract: split.json already present (idempotent skip). Pass --force to redo.')
        return
    intake=os.path.join(out,'intake','files.json')
    if not os.path.exists(intake):
        log(logf, 'extract: missing intake/files.json'); sys.exit(2)
    files=json.load(open(intake)).get('files') or []
    pdfs=[f for f in files if (f.get('use')=='extracted' or str(f.get('name','')).lower().endswith('.pdf'))]
    if not pdfs:
        log(logf, 'extract: no extracted PDF listed in intake/files.json'); sys.exit(2)
    pdf=pdfs[0].get('path') or ''
    if not os.path.exists(pdf):
        log(logf, f'extract: PDF not found: {pdf}'); sys.exit(2)
    run_script([sys.executable, os.path.join(HERE,'extract_owner_pdf.py'), pdf, out], logf)
    run_script([sys.executable, os.path.join(HERE,'analyze_visual.py'), out], logf)

def stage_textfix(opts, logf, exam):
    import text_fixes
    rpath,R=load_research(paths.root(), exam, logf)
    r=text_fixes.propose(os.path.join(paths.root(),'out',exam), R['vendor_slug'], paths.root())
    log(logf, f"textfix: {len(r['proposals'])} proposals {r['counts']}; {len(r['undecided'])} need an author decision; out/{exam}/text-fixes-proposals.json")

def stage_answer_research(opts, logf, exam):
    import answer_research
    out=os.path.join(paths.root(),'out',exam)
    rpath,R=load_research(paths.root(), exam, logf)
    v=R['vendor_slug']
    C=answer_research.discover(out, v, exam, offline=opts.offline)
    if not C:
        log(logf, 'answer_research: every item has an answer in the owner file; nothing to research.')
        return
    Rz=answer_research.verify(out, v, exam)
    from collections import Counter
    log(logf, f'answer_research: {len(C)} no-answer items -> {dict(Counter(r["status"] for r in Rz.values()))}; candidates in out/{exam}/answer_research/candidates.json')

def intent_file(rpath, exam):
    return os.path.join(os.path.dirname(os.path.abspath(rpath)), f'{exam}.search-intent.json')

def stage_intent(opts, logf, exam):
    rpath,_=load_research(paths.root(), exam, logf)
    run_script([sys.executable, os.path.join(HERE,'search_intent.py'), rpath], logf)

def ensure_intent(opts, logf, exam):
    """Pre-step for author and pages: build the search-intent file when it is missing."""
    rpath,_=load_research(paths.root(), exam, logf)
    if not os.path.exists(intent_file(rpath, exam)):
        log(logf, 'search intent: no file yet, building it from research facts first.')
        stage_intent(opts, logf, exam)

def stage_writing(opts, logf, exam, no_fail=False):
    rpath,_=load_research(paths.root(), exam, logf)
    run_script([sys.executable, os.path.join(HERE,'check_writing.py'), rpath]+(['--no-fail'] if no_fail else []), logf)

def stage_author(opts, logf, exam):
    ensure_intent(opts, logf, exam)
    out=os.path.join(paths.root(),'out',exam,'authoring')
    need=['explanations_text.json','page_prose.json','bank_meta.json']
    # explanations_visual.json is optional if there are no visual items
    missing=[n for n in need if not os.path.exists(os.path.join(out,n))]
    vis=os.path.join(paths.root(),'out',exam,'extracted','visual_draft.json')
    trans=os.path.join(paths.root(),'out',exam,'extracted','visual_transcription.json')
    if os.path.exists(vis) and not os.path.exists(trans):
        try:
            draft=json.load(open(vis,encoding='utf-8'))
        except Exception:
            draft={}
        if draft:
            missing.append('extracted/visual_transcription.json')
    arp=os.path.join(paths.root(),'out',exam,'answer_research','result.json')
    if os.path.exists(arp) and not os.path.exists(os.path.join(out,'answer_research.json')):
        try: pend=[k for k,r in json.load(open(arp,encoding='utf-8')).items() if r.get('status')=='pending_ai_pick']
        except Exception: pend=[]
        if pend: missing.append('answer_research.json (pick keys for '+', '.join(pend)+' from answer_research/candidates.json; verbatim quotes only)')
    tfp=os.path.join(paths.root(),'out',exam,'text-fixes-proposals.json')
    if os.path.exists(tfp):
        try:
            und=json.load(open(tfp,encoding='utf-8')).get('undecided') or []
            dec=json.load(open(os.path.join(out,'text_fixes_decisions.json'),encoding='utf-8')).get('decisions') or {} if os.path.exists(os.path.join(out,'text_fixes_decisions.json')) else {}
        except Exception: und,dec=[],{}
        und=[i for i in und if i not in dec]
        if und: missing.append(f'text_fixes_decisions.json (accept or reject {len(und)} proposals from text-fixes-proposals.json: '+', '.join(und[:6])+(' ...' if len(und)>6 else '')+')')
    if missing:
        log(logf, 'AUTHOR STAGE (the only AI stage). Files still needed:')
        for m in missing: log(logf, '  - '+m)
        log(logf, 'Write them in one batched pass: original page prose, rewritten explanations, bank_meta (skill map, skipped files, cover-fact notes), and visual transcription where OCR is not enough. Follow reference/writing-brief.md. Answer the questions research/<vendor>/'+exam+'.search-intent.json assigns to each page. Use competitor notes as topics only, never their wording. Do not invent questions. Do not change keys or option order; stem and option text changes go through authoring/text_fixes_decisions.json only (spelling, grammar, punctuation). Then rerun --stage author (or the remaining stages).')
        sys.exit(2)
    # light presence check: explanations cover split items later in bank/validate
    log(logf, 'author: required files present (explanations, page_prose, bank_meta). AI is not invoked by this script.')
    fixp=os.path.join(out,'writing_fix_request.json')
    if os.path.exists(fixp):
        try: parts=sorted((json.load(open(fixp,encoding='utf-8')).get('parts') or {}).keys())
        except Exception: parts=[]
        if parts:
            log(logf, 'author: writing fixes pending. Fix ONLY these parts (see authoring/writing_fix_request.json), then rerun pages and writing: '+', '.join(parts))
    # Shared blocks listed in page_prose must exist or be written in the same batched pass.
    try:
        prose=json.load(open(os.path.join(out,'page_prose.json'),encoding='utf-8'))
        wanted=[]
        for kind,rec in prose.items():
            if not isinstance(rec, dict): continue
            for item in rec.get('shared_keys') or []:
                wanted.append(item)
        missing=shared_sections.list_missing(wanted)
        if missing:
            log(logf, 'author: shared blocks not on disk yet (write under shared/ then rerun pages): '+json.dumps(missing))
        else:
            log(logf, 'author: shared keys in page_prose already exist or none were listed.')
    except Exception as e:
        log(logf, 'author: could not check shared keys ('+type(e).__name__+')')


def stage_bank(opts, logf, exam):
    rpath,_=load_research(paths.root(), exam, logf)
    run_script([sys.executable, os.path.join(HERE,'build_bank.py'), rpath], logf)

def stage_pages(opts, logf, exam):
    ensure_intent(opts, logf, exam)
    rpath,_=load_research(paths.root(), exam, logf)
    run_script([sys.executable, os.path.join(HERE,'build_pages.py'), rpath], logf)
    if 'writing' not in (getattr(opts,'selected_stages',None) or []):
        # Pages were rebuilt (for example after a flagged fix): the writing check must run again.
        # Here it records flags (writing-review.json, REVIEW.md) without stopping the stages the
        # caller chose; the writing stage itself, or validate check 19, is the gate.
        log(logf, 'pages: running the writing check on the rebuilt pages (second check after a fix; flags are recorded, the writing stage or validate check 19 gates them).')
        stage_writing(opts, logf, exam, no_fail=True)

def stage_import(opts, logf, exam):
    rpath,_=load_research(paths.root(), exam, logf)
    run_script([sys.executable, os.path.join(HERE,'emit_import.py'), rpath], logf)

def stage_validate(opts, logf, exam):
    rpath,_=load_research(paths.root(), exam, logf)
    run_script([sys.executable, os.path.join(HERE,'manifest.py'), rpath], logf)
    out=os.path.join(paths.root(),'out',exam,'SITE-QUESTION-TYPES.md')
    run_script([sys.executable, os.path.join(HERE,'gen_site_question_types.py'), out], logf)
    cmd=[sys.executable, os.path.join(HERE,'validate.py'), rpath]
    if opts.offline: cmd.append('--offline')
    run_script(cmd, logf)
    bank=os.path.join(paths.root(),'out',exam)
    reg=os.path.join(paths.site_format_dir(),'question_types.json')
    run_script([sys.executable, os.path.join(HERE,'check_bank.py'), bank, '--registry', reg], logf)

def stage_package(opts, logf, exam):
    rpath,R=load_research(paths.root(), exam, logf)
    root=paths.root()
    zip_path=opts.zip or os.path.join(root,f'{exam}-package.zip')
    staging=os.path.join(root,'out','.package-staging',exam)
    if os.path.exists(staging): shutil.rmtree(staging)
    dest=os.path.join(staging,f'{exam}-package')
    os.makedirs(dest, exist_ok=True)
    def copytree(src, dst):
        if os.path.exists(src): shutil.copytree(src, dst, dirs_exist_ok=True)
    copytree(os.path.join(root,'out',exam), os.path.join(dest, exam))
    # Owner rule: raw extracts and removed seller lines never ship (workspace copies stay for audit).
    import package_guard as PG
    S=site_settings.load(); cfg=config_load.load(os.environ.get('CERTPASSLY_CONFIG'))
    PG.prepare(os.path.join(dest, exam), S, cfg, log=lambda m: log(logf, m))
    copytree(os.path.join(root,'out','vendors',R['vendor_slug']), os.path.join(dest,'vendors',R['vendor_slug']))
    copytree(os.path.join(root,'out','certifications',R['certification_slug']), os.path.join(dest,'certifications',R['certification_slug']))
    # include run.log if present
    rl=os.path.join(root,'run.log')
    if os.path.exists(rl): shutil.copy2(rl, os.path.join(dest,'run.log'))
    parent=os.path.dirname(os.path.abspath(zip_path)) or '.'
    os.makedirs(parent, exist_ok=True)
    base,ext=os.path.splitext(os.path.abspath(zip_path))
    archive=shutil.make_archive(base,'zip',staging,f'{exam}-package')
    if os.path.abspath(archive)!=os.path.abspath(zip_path) and zip_path.endswith('.zip'):
        shutil.move(archive, zip_path)
        archive=zip_path
    shutil.rmtree(staging, ignore_errors=True)
    # Gate: scan every file in the finished zip against the config denylist.
    res=PG.scan_zip(archive, S); rep=PG.write_report(res, archive+'.scan.json')
    log(logf, f"package scan: {rep['members']} members, {rep['files_scanned']} text files scanned, {rep['images_skipped']} images skipped, {rep['nested_archives']} nested archives, {rep['hit_count']} denylist hits; report {archive}.scan.json")
    if res['hits']:
        for f,label,term in res['hits']:
            log(logf, f'  DENYLIST HIT {f}: {label}')
            print(f'  DENYLIST HIT {f}: {label} ({term})', file=sys.stderr, flush=True)
        os.remove(archive)
        log(logf, f'  package removed: it must not ship with denylist hits')
        sys.exit(1)
    log(logf, f'package written: {archive}')

HANDLERS={
    'catalog': lambda o,l,e: stage_catalog(o,l),
    'intake': stage_intake,
    'sources': stage_sources,
    'research': stage_research,
    'extract': stage_extract,
    'textfix': stage_textfix,
    'answer_research': stage_answer_research,
    'intent': stage_intent,
    'author': stage_author,
    'writing': stage_writing,
    'bank': stage_bank,
    'pages': stage_pages,
    'import': stage_import,
    'validate': stage_validate,
    'package': stage_package,
}

def select_exams(opts):
    """Resolve which exam codes to run from --exam, --vendor, --all, --batch."""
    codes=list(opts.exams or [])
    if opts.vendor or opts.all or opts.batch:
        cat=os.path.join(paths.root(),'catalog.csv')
        if not os.path.exists(cat):
            raise SystemExit('catalog.csv not found in the workspace (run the catalog stage first, or pass --exam).')
        rows=list(csv.DictReader(open(cat)))
        if opts.vendor:
            rows=[r for r in rows if r.get('vendor_slug')==opts.vendor]
            if not rows:
                raise SystemExit(f'No catalog rows for vendor {opts.vendor!r}.')
        codes += [r['exam_code'] for r in rows if r.get('exam_code') and r['exam_code'] not in codes]
    # de-dupe, keep order
    seen=set(); out=[]
    for c in codes:
        if c not in seen:
            seen.add(c); out.append(c)
    return out

def _ensure_utf8():
    """Windows defaults to a legacy code page; saved official pages and owner text are UTF-8.

    Re-run once in Python UTF-8 mode so every open() in this process and its child
    scripts reads UTF-8. A no-op on Linux and macOS with a UTF-8 locale.
    """
    import locale
    if sys.flags.utf8_mode or os.environ.get('CERTPASSLY_UTF8_CHILD'):
        return None
    if (locale.getpreferredencoding(False) or '').lower().replace('-','') in ('utf8',):
        return None
    env=os.environ.copy(); env['PYTHONUTF8']='1'; env['PYTHONIOENCODING']='utf-8'; env['CERTPASSLY_UTF8_CHILD']='1'
    return subprocess.run([sys.executable,'-X','utf8',os.path.abspath(__file__)]+sys.argv[1:], env=env).returncode

def main():
    rc=_ensure_utf8()
    if rc is not None:
        return rc

    names=[s[0] for s in STAGES]
    ap=argparse.ArgumentParser(description='Run the CertPassly exam pipeline (scripts first, one AI stage).')
    ap.add_argument('--exam', action='append', dest='exams', help='Exam code. Repeat to run more than one.')
    ap.add_argument('--root', help='Workspace root (default: CERTPASSLY_ROOT or cwd)')
    ap.add_argument('--config', help='Path to pipeline.yaml')
    ap.add_argument('--stage', action='append', dest='stages', help='Run one stage (repeatable). Default: all.')
    ap.add_argument('--date', help='Freeze the last-updated date (YYYY-MM-DD). Also honors CERTPASSLY_DATE.')
    ap.add_argument('--offline', action='store_true', help='No network. Use saved sources and the link-check cache only.')
    ap.add_argument('--sheet', help='Owner exam sheet (CSV) for the catalog stage.')
    ap.add_argument('--zip', help='Output zip path for the package stage.')
    ap.add_argument('--vendor', help='Run every exam in the catalog for this vendor slug.')
    ap.add_argument('--all', action='store_true', help='Run every exam in the catalog.')
    ap.add_argument('--batch', action='store_true', help='Run exams in catalog (sheet) order. Combine with --vendor or use alone for all exams.')
    ap.add_argument('--force', action='store_true', help='Redo extract even if split.json exists.')
    ap.add_argument('--list-stages', action='store_true', help='Print the stage table and exit.')
    opts=ap.parse_args()
    if opts.list_stages:
        print('stage\tAI?\twhat it does')
        for n,ai,desc in STAGES:
            print(f'{n}\t{ai}\t{desc}')
        return 0
    if opts.root: paths.set_root(opts.root)
    else: paths.set_root(paths.root())
    if opts.date: os.environ['CERTPASSLY_DATE']=opts.date
    if opts.offline: os.environ['CERTPASSLY_OFFLINE']='1'
    if opts.config: os.environ['CERTPASSLY_CONFIG']=os.path.abspath(opts.config)
    cfg=config_load.load(opts.config)
    site_settings.reset(); site_settings.load(opts.config)
    stages=opts.stages or names
    opts.selected_stages=list(stages)
    for s in stages:
        if s not in HANDLERS:
            print('unknown stage:', s, file=sys.stderr); print('known:', ', '.join(names), file=sys.stderr); return 2
    log_path=os.path.join(paths.root(),'run.log')
    fh=open(log_path,'a',encoding='utf-8')
    exams=select_exams(opts)
    later={s for s in stages if s not in ('catalog',)}
    if later and not exams:
        log(fh, 'No exam codes. Pass --exam CODE, --vendor SLUG, --all or --batch.')
        return 2
    log(fh, f'start exams={",".join(exams) or "-"} stages={",".join(stages)} root={paths.root()} offline={opts.offline}')
    preflight(cfg, exams[0] if exams else None, fh, stages)
    t0=time.time()
    failed=[]
    try:
        for exam in (exams or [None]):
            if exam: log(fh, f'######## exam {exam} ########')
            opts.exam=exam
            for s in stages:
                if s=='catalog' and exam and exam!=exams[0]:
                    continue  # catalog once
                log(fh, f'==== stage {s} ({exam or "workspace"}) ====')
                try:
                    HANDLERS[s](opts, fh, exam)
                    log(fh, f'==== stage {s} done ====')
                except SystemExit as e:
                    code=e.code if isinstance(e.code,int) else 1
                    if not isinstance(e.code,int) and e.code: log(fh, f'ERROR: {e.code}')
                    log(fh, f'==== stage {s} failed for {exam} (exit {code}) ====')
                    failed.append((exam,s,code))
                    if code and s=='catalog':
                        raise
                    break
    finally:
        log(fh, f'elapsed {round(time.time()-t0,1)}s; failed={failed!r}; log={log_path}')
        fh.close()
    return 1 if failed else 0

if __name__=='__main__':
    sys.exit(main())
