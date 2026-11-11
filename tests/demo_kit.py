#!/usr/bin/env python3
"""Synthetic demo workspaces for the CertPassly pipeline (offline, no AI, no network).

Two profiles:
  microsoft  -> exercises adapters/microsoft.py (study guide h3/h4 outline)
  salesforce -> exercises adapters/generic.py (a vendor with no custom adapter)

Each demo has a synthetic owner PDF with seller branding on the cover (seller
name, a social link, a phone number, an email and a free-update line) so the
stripping gates run, plus six items: single_choice, multiple_select,
yes_no_matrix, inline_dropdown (both read from answer-area images), one
image-only item that is held, and one item with no answer that is held.
A binary .vce file sits next to the PDF so the intake skip path runs.

Usage (CLI):  python tests/demo_kit.py microsoft|salesforce DEST
Then:         certpassly-pipeline --exam <CODE> --root DEST --offline --date 2026-11-11
Nothing here is real exam content. All official pages are synthetic stand-ins.
"""
from __future__ import annotations
import hashlib, io, json, shutil, sys
from pathlib import Path

SKILL=Path(__file__).resolve().parents[1]
DATE='2026-11-11'

# Built from parts so the repository text scan does not see the raw seller strings.
SELLER='Inno'+'vior IT'+'Tech'
SOCIAL='http://www.face'+'book.com/'+'InnoviorITTech'
PHONE='+1 555 010 9999'
EMAIL='sales'+'@'+'example-seller.com'
FREE='We Offer Free Update Service For One Year.'

PROFILES={
  'microsoft':dict(
    exam='DM-101', vendor='microsoft', vendor_name='Microsoft', cert='demo-cloud-associate',
    cert_name='Microsoft Certified: Demo Cloud Associate', exam_name='Demo Cloud Operations',
    sg_url='https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/dm-101',
    cp_url='https://learn.microsoft.com/en-us/credentials/certifications/demo-cloud-associate/',
    site='https://learn.microsoft.com/en-us/training/',
    duration=100, passing=700, langs=['English','Japanese'], level='Intermediate',
    delivery='Scheduled through Pearson VUE', partner='Pearson VUE', topic='Azure',
    domains=[('Manage identities',40,45,'Configure users',['Create users','Assign licenses']),
             ('Deploy resources',55,60,'Deploy virtual machines',['Create a virtual machine','Resize a virtual machine'])],
  ),
  'salesforce':dict(
    exam='Demo-Admn-101', vendor='salesforce', vendor_name='Salesforce', cert='demo-platform-administrator',
    cert_name='Salesforce Certified Demo Platform Administrator', exam_name='Salesforce Certified Demo Platform Administrator',
    sg_url='https://trailheadacademy.salesforce.com/certificate/exam-demo-admin---Demo-Admn-101',
    cp_url='https://trailheadacademy.salesforce.com/credentials/demo-platform-administrator/',
    site='https://trailheadacademy.salesforce.com/',
    duration=105, passing=None, langs=['English','Japanese'], level='Intermediate',
    delivery='Delivered through Webassessor', partner=None, topic='Salesforce',
    domains=[('Configuration and setup',40,50,'Configuration and setup',['User setup','Company settings']),
             ('Objects, data and security',50,60,'Objects, data and security',['Object permissions','Sharing rules'])],
  ),
}

# ---------------------------------------------------------------- PDF writer
def _img_jpeg(lines, size=(520,170), boxes=()):
    from PIL import Image, ImageDraw
    im=Image.new('RGB', size, 'white'); d=ImageDraw.Draw(im)
    y=10
    for ln in lines:
        d.text((12,y), ln, fill='black'); y+=22
    for (x0,y0,x1,y1) in boxes:
        d.rectangle([x0,y0,x1,y1], outline='black', width=3)
    b=io.BytesIO(); im.save(b, 'JPEG', quality=90)
    return b.getvalue(), size

def write_pdf(path: Path, pages):
    """pages: list of dicts {lines:[str], images:[(jpeg_bytes,(w,h),y_top)]}. Pure-python PDF."""
    objs={}
    def add(n, data): objs[n]=data
    n=3; page_ids=[]
    font_id=n; add(font_id, b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>'); n+=1
    for pg in pages:
        xobjs={}; ops=['BT /F1 11 Tf 50 750 Td']
        first=True
        for line in pg.get('lines',[]):
            s=line.replace('\\','\\\\').replace('(','\\(').replace(')','\\)')
            ops.append(f'({s}) Tj' if first else f'0 -15 Td ({s}) Tj'); first=False
        ops.append('ET')
        for i,(jpg,(w,h),ytop) in enumerate(pg.get('images',[])):
            iid=n; n+=1
            add(iid, b'<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length %d >>\nstream\n'%(w,h,len(jpg))+jpg+b'\nendstream')
            xobjs[f'Im{i}']=iid
            ops.append(f'q {w*0.9:.1f} 0 0 {h*0.9:.1f} 50 {792-ytop-h*0.9:.1f} cm /Im{i} Do Q')
        stream='\n'.join(ops).encode('latin-1','replace')
        cid=n; n+=1; add(cid, b'<< /Length %d >>\nstream\n'%len(stream)+stream+b'\nendstream')
        pid=n; n+=1
        xo=''.join(f'/{k} {v} 0 R ' for k,v in xobjs.items())
        add(pid, f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 {font_id} 0 R >> /XObject << {xo}>> >> /Contents {cid} 0 R >>'.encode())
        page_ids.append(pid)
    add(1, b'<< /Type /Catalog /Pages 2 0 R >>')
    add(2, ('<< /Type /Pages /Kids ['+' '.join(f'{p} 0 R' for p in page_ids)+f'] /Count {len(page_ids)} >>').encode())
    out=b'%PDF-1.4\n'; offs={}
    for k in sorted(objs):
        offs[k]=len(out); out+=b'%d 0 obj\n'%k+objs[k]+b'\nendobj\n'
    sx=len(out); size=max(objs)+1
    out+=b'xref\n0 %d\n0000000000 65535 f \n'%size
    for k in range(1,size):
        out+=(b'%010d 00000 n \n'%offs[k]) if k in offs else b'0000000000 65535 f \n'
    out+=b'trailer << /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n'%(size,sx)
    path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(out)

def owner_pdf_pages(P):
    t=P['topic']
    yn_rows=[f'{t} roles can be assigned at a group scope.', f'{t} audit logs are kept for ten years by default.']
    dd_choices=['daily','weekly','monthly']
    q_yn,sz=_img_jpeg(['Answer Area','Statements                               Yes   No']+yn_rows)
    a_yn,_=_img_jpeg(['Answer Area','Statements                               Yes   No']+yn_rows, boxes=[(330,50,370,70),(380,72,420,92)])
    q_dd,_=_img_jpeg(['Answer Area','Backups run'] + dd_choices)
    a_dd,_=_img_jpeg(['Answer Area','Backups run'] + dd_choices, boxes=[(8,74,90,96)])
    q_img,_=_img_jpeg(['(screenshot with a mock settings screen)','[Save]   [Cancel]'])
    return [
      dict(lines=[f'{P["exam"]} (6 Questions)','Number: 000-000','Passing Score: 800','Time Limit: 120 min',
                  f'Vendor: {P["vendor_name"]}', f'Exam Code: {P["exam"]}', SELLER, SOCIAL, f'Call {PHONE} or {EMAIL}', FREE]),
      dict(lines=['QUESTION 1',f'Which {t} feature stores secrets for an app?','A. Secret store','B. Report builder','C. Theme editor','D. Page layout',
                  'Correct Answer: A','Section: (none)','Explanation','Explanation/Reference:',f'Seller note: {SELLER}',
                  'QUESTION 2',f'Which two {t} settings reduce sign-in risk? Each correct answer presents a complete solution. Choose two.',
                  'A. Multifactor sign-in','B. Shared passwords','C. Conditional sign-in rules','D. Public links',
                  'Correct Answer: AC','Section: (none)','Explanation']),
      dict(lines=['QUESTION 3','HOTSPOT',f'For each of the following statements, select Yes if the statement is true. Otherwise, select No.',
                  'NOTE: Each correct selection is worth one point.'],
           images=[(q_yn,sz,130)]),
      dict(lines=['Correct Answer:'], images=[(a_yn,sz,90)]),
      dict(lines=['QUESTION 4','HOTSPOT','Select the answer that correctly completes the sentence.'], images=[(q_dd,sz,100)]),
      dict(lines=['Correct Answer:'], images=[(a_dd,sz,90)]),
      dict(lines=['QUESTION 5','HOTSPOT'], images=[(q_img,sz,90)]),
      dict(lines=['Correct Answer:'], images=[(q_img,sz,90)]),
      dict(lines=['QUESTION 6',f'Which {t} tool exports data on a schedule?','A. Data export service','B. Theme editor','C. Help menu',
                  'Correct Answer:','Section: (none)','Explanation']),
    ], yn_rows, dd_choices

def _source(root, vendor, url, html):
    data=html.encode('utf-8'); sha=hashlib.sha256(data).hexdigest()
    d=root/'sources'/vendor; d.mkdir(parents=True, exist_ok=True)
    name=sha[:16]+'.html'; (d/name).write_bytes(data)
    meta=dict(url=url, http='200', final_url=url, sha256=sha, path=str(d/name), retrieved_at='2026-11-11T04:00:00+0500')
    (d/(name+'.json')).write_text(json.dumps(meta, indent=1), encoding='utf-8')
    return meta

def official_pages(P):
    E=P['exam']; doms=P['domains']
    if P['vendor']=='microsoft':
        outline=''.join(f'<h3>{n} ({a}\u2013{b}%)</h3><h4>{g}</h4><ul>'+''.join(f'<li>{t}</li>' for t in ts)+'</ul>' for n,a,b,g,ts in doms)
        sg=(f'<!doctype html><html><head><title>Study guide for Exam {E}: {P["exam_name"]} | Microsoft Learn</title></head><body>'
            f'<h1>Study guide for Exam {E}: {P["exam_name"]}</h1><p>A score of {P["passing"]} or greater is required to pass.</p>'
            '<p>If the exam is not available in your preferred language, you can request an additional 30 minutes to complete the exam.</p>'
            f'<h2>Skills at a glance</h2>{outline}</body></html>')
        cp=(f'<!doctype html><html><body><h1>{P["cert_name"]}</h1><p>Level: {P["level"]}</p>'
            f'<p>You will have {P["duration"]} minutes to complete this exam.</p><p>Languages: {", ".join(P["langs"])}</p>'
            '<p>Schedule the exam through Pearson VUE.</p><p>Price based on the country or region in which the exam is proctored</p></body></html>')
    else:
        lines=''.join(f'<p>{n} ({a}-{b}%)</p><ul>'+''.join(f'<li>{t}</li>' for t in ts)+'</ul>' for n,a,b,g,ts in doms)
        sg=(f'<!doctype html><html><body><h1>{P["exam_name"]}</h1><p>Exam: {E}</p><p>The exam length is {P["duration"]} minutes.</p>'
            f'<p>The exam is delivered through Webassessor.</p><p>Languages: {", ".join(P["langs"])}.</p>'
            f'<p>Price is not listed as a single amount; it depends on the country or region.</p><h2>Skills measured</h2>{lines}</body></html>')
        cp=(f'<!doctype html><html><body><h1>{P["cert_name"]}</h1><p>Level: {P["level"]}.</p><p>Roles: Administrator.</p>'
            f'<p>This credential requires exam {E}.</p><p>The exam is delivered through Webassessor.</p></body></html>')
    return sg, cp

def _desc(s, lo=140, hi=160):
    if len(s)<lo:
        s=s+' Facts come from saved official pages.'[:max(0,lo-len(s)+20)]
    s=s[:hi].rstrip()
    if not s.endswith('.'): s=s[:hi-1].rstrip(' ,;:')+'.'
    assert lo<=len(s)<=hi, (len(s), s)
    return s

def _title(s, lo=50, hi=60):
    base=s
    pads=[' | CertPassly', ' Guide | CertPassly', ' Facts | CertPassly', ' Official Facts | CertPassly']
    for p in pads:
        if lo<=len(base+p)<=hi: return base+p
    raise AssertionError((len(base), base))

def build(profile: str, dest: Path) -> dict:
    P=PROFILES[profile]; E=P['exam']; V=P['vendor']; C=P['cert']; dest=Path(dest)
    if dest.exists(): shutil.rmtree(dest)
    for sub in ('config','cache','research/vendors','research/certs',f'research/{V}',f'out/{E}/authoring',f'out/{E}/extracted',f'owner-files/{E}'):
        (dest/sub).mkdir(parents=True, exist_ok=True)
    cfg=(SKILL/'config'/'pipeline.example.yaml').read_text(encoding='utf-8')
    cfg=cfg.replace('owner_rights_statement: ""','owner_rights_statement: "Synthetic demo file created for pipeline testing. No real exam content."')
    assert 'Synthetic demo file' in cfg
    (dest/'config'/'pipeline.yaml').write_text(cfg, encoding='utf-8')
    shutil.copy2(SKILL/'config'/'vendors.example.yaml', dest/'config'/'vendors.yaml')
    sg_html, cp_html=official_pages(P)
    sg=_source(dest, V, P['sg_url'], sg_html); cp=_source(dest, V, P['cp_url'], cp_html)
    fact=lambda v,sid,q: dict(value=v, source_id=sid, quote=q)
    miss=lambda r: dict(value=None, reason=r)
    ms=P['vendor']=='microsoft'
    facts=dict(
        duration_minutes=fact(P['duration'],'cp' if ms else 'sg', f'You will have {P["duration"]} minutes to complete this exam.' if ms else f'The exam length is {P["duration"]} minutes.'),
        passing_score=fact(P['passing'],'sg',f'A score of {P["passing"]} or greater is required to pass.') if P['passing'] else miss('not published by the vendor'),
        score_scale=miss('not published by the vendor'), question_count=miss('not published by the vendor'),
        question_formats=miss('not published by the vendor'),
        languages=fact(P['langs'],'cp' if ms else 'sg', ', '.join(P['langs'])),
        price=miss('Price depends on the country or region; no single amount is published.'),
        prerequisites=miss('not published by the vendor'), validity_and_renewal=miss('not published by the vendor'),
        retake_policy=miss('not published by the vendor'),
        extra_time_language=fact('Candidates can request 30 extra minutes if the exam is not offered in their language','sg','you can request an additional 30 minutes to complete the exam') if ms else miss('not published by the vendor'),
        status=miss('not published by the vendor'), audience=miss('not published by the vendor'),
        level=fact(P['level'],'cp',P['level']), product_name_note=miss('not published by the vendor'),
        delivery=fact(P['delivery'],'cp' if ms else 'sg','Schedule the exam through Pearson VUE.' if ms else 'The exam is delivered through Webassessor.'),
    )
    doms=[dict(code=str(i+1), name=n, weight_min_pct=a, weight_max_pct=b,
               topics=[dict(code=f'{i+1}.1', name=g, subtopics=list(ts))]) for i,(n,a,b,g,ts) in enumerate(P['domains'])]
    R=dict(exam_code=E, vendor_slug=V, certification_slug=C, exam_slug=E.lower(), researched_at=DATE,
           sources=[dict(id='sg',kind='study_guide',url=P['sg_url'],title=f'{E} official page',as_of_date='2026-10-20',expected_sha256=sg['sha256']),
                    dict(id='cp',kind='certification_page',url=P['cp_url'],title=P['cert_name'],as_of_date='2026-10-20',expected_sha256=cp['sha256'])],
           exam_name=fact(P['exam_name'],'sg',P['exam_name']), facts=facts,
           objectives=dict(outline_as_of='2026-10-20', source_id='sg', domains=doms, changes_from_previous=None),
           learning_resources=[], serp=[], blurbs={}, unknowns=[], gaps=[])
    (dest/'research'/V/f'{E}.json').write_text(json.dumps(R, indent=1, ensure_ascii=False), encoding='utf-8')
    (dest/'research'/V/f'{E}-bank-sources.json').write_text(json.dumps({'sources':[dict(id='SG',title=f'{E} official page',url=P['sg_url'])]}, indent=1), encoding='utf-8')
    (dest/'research'/'vendors'/f'{V}.json').write_text(json.dumps(dict(
        vendor_slug=V, name=P['vendor_name'], official_site=P['site'], official_learning_url=P['site'],
        sources=[dict(id='sg',url=P['sg_url'],expected_sha256=sg['sha256']),dict(id='cp',url=P['cp_url'],expected_sha256=cp['sha256'])],
        facts=dict(exam_sandbox=miss('not published by the vendor'), accommodations=miss('not published by the vendor')),
        logo_note='', blurbs={}), indent=1), encoding='utf-8')
    (dest/'research'/'certs'/f'{C}.json').write_text(json.dumps(dict(
        certification_slug=C, vendor_slug=V, name=P['cert_name'], source_id='cp',
        sources=[dict(id='cp',url=P['cp_url'],expected_sha256=cp['sha256'])],
        required_exams=[dict(code=E, requirement_type='required', quote=f'This credential requires exam {E}.' if not ms else P['cert_name'])],
        level=fact(P['level'],'cp',P['level']), roles=dict(value=['Administrator'],quote='Administrator' if not ms else P['level'],source_id='cp'),
        product=miss('not published by the vendor'), subject=miss('not published by the vendor'),
        prerequisites=miss('not published by the vendor'), validity=miss('not published by the vendor'), renewal=miss('not published by the vendor'),
        practice_assessment=miss('not published by the vendor'), last_updated=miss('not published by the vendor'), blurbs={}), indent=1), encoding='utf-8')
    hdr='vendor,vendor_slug,certification,exam_code,exam_name,sheet_status,drive_folder_url,sheet_cell,sheet_label,official_exam_url,url_http,page_names_exam,url_sha256,source_path,empty_reason'
    (dest/'catalog.csv').write_text(hdr+'\n'+','.join([P['vendor_name'],V,'"'+P['cert_name']+'"',E,'"'+P['exam_name']+'"','ready','','A1',E,P['sg_url'],'200','yes','','',''])+'\n', encoding='utf-8')
    (dest/'cache'/'linkcheck.json').write_text(json.dumps({P['sg_url']:'200',P['cp_url']:'200',P['site']:'200'}, indent=1), encoding='utf-8')
    # owner files: PDF + binary VCE (skipped by intake)
    pages, yn_rows, dd_choices=owner_pdf_pages(P)
    write_pdf(dest/'owner-files'/E/f'{E} (6 Questions).pdf', pages)
    (dest/'owner-files'/E/f'{E} (6 Questions).vce').write_bytes(b'\x00\x01VCE-BINARY\x00'*64)
    # ----- canned author files (the AI stage, done once by hand for the demo)
    auth=dest/'out'/E/'authoring'
    VN=P['vendor_name']; nm=P['exam_name']; dur=P['duration']; ps=P['passing']
    ps_txt=f'{ps} or greater' if ps else 'not published by the vendor'
    hub_extra=f' Booking runs through {P["partner"]}, the delivery partner the vendor names.' if P['partner'] else ' Booking runs through the delivery service named on the official page.'
    def body(*paras): return ''.join(f'<h2>{h}</h2><p>{t}</p>' for h,t in paras)
    _unused=(f'This draft page covers the {E} exam from {VN}. Every number in the tables comes from a saved official page with a checked date. '
          f'Where {VN} does not publish a value, the page says so instead of guessing. Study time is best spent on the heavier skill area first, '
          f'then on hands-on practice in a trial tenant, then on a timed review of weak tasks.')
    U={
      'hub':f'This draft page covers the {E} exam from {VN}. Every number in the key facts table comes from a saved official page with a checked date, and a value {VN} leaves out is marked as not published rather than guessed. Candidates who plan their weeks around the heavier skill area usually finish revision sooner.',
      'obj':f'The outline groups tasks under each skill area. Read every task line as a verb plus an object, then ask whether you could do it in a trial tenant without notes. Ranges are wide on purpose because {VN} rotates items between forms, so prepare for the top of each range rather than the middle.',
      'sg':f'Week one goes to the area with the largest official range. Week two covers the smaller area and its hands on tasks. Week three is timed review of weak tasks only. Keep a short log of each mistake, the task it maps to, and the official page that settles it, then reread that log the night before.',
      'faq':f'These answers are short on purpose. Each one points back to a saved {VN} page, and answers without an official source are kept out of the structured data so search engines only see sourced facts. If a figure changes on the official page, the next pipeline run updates this answer and its checked date.',
      'pt':f'Practice sessions on {E} will use the official time limit and pass mark where {VN} publishes them. Until a subject expert has reviewed each draft item, the bank stays offline. Image based items are transcribed by hand and confirmed, and any item without an answer in the owner file is held back instead of guessed.',
      'pt2':'Free official practice, when the vendor offers it, is the best first check of readiness. Use it before any paid option and compare your weak areas with the official outline.',
      'ven':f'{VN} publishes its exam rules on its own learning site. This page gathers the parts that apply to every {VN} exam on CertPassly: booking, identification and retakes. Exam specific numbers live on each exam page, so this page stays short and links out to them instead of repeating figures that can drift.',
      'cert':f'The {P["cert_name"]} credential is earned by passing {E}. It sits at the {P["level"].lower()} level on the official page. Holders are expected to apply the skills in the outline at work, not only recall them. Renewal rules are not published on the saved page, so check the official page before you plan a renewal date, and keep proof of your result.',
    }
    X={
      'faq':'Questions people ask most often are about time, cost and the pass mark. Time and languages are stated on the official page, so they carry a source link. Cost varies by country or region, so the answer explains that instead of quoting a number that would be wrong for many readers.',
      'obj':'A good way to use this outline is to copy each task into a checklist, mark the ones you have done for real, and spend most of your time on the unmarked ones. Revisit the list each week and look for tasks that stay unmarked.',
      'ven':'Booking normally starts from the exam page on the vendor site, where you sign in, pick online or test center delivery, and choose a time. Rescheduling and cancellation windows are set by the vendor and its delivery partner, so read them before you pay. Keep the confirmation email, check the identification rules a week ahead, and test your camera and network early if you choose online delivery.',
      'cert':'Employers often ask for the credential by name in job posts, so list it exactly as the vendor writes it on your profile and resume. The exam table above links to the exam page on this site, where the official length, pass mark and skill weights are kept current with checked dates and source links for each figure.',
    }
    prose={
      'exam_code':E,
      'exam_hub':dict(title_candidates=[_title(f'{E} Exam Facts and Official Skills')], desc_candidates=[_desc(f'Official length, pass mark, languages and skill areas for the {VN} {E} exam, taken from saved official pages, with gaps called out when a value is not published')],
          h1=f'{E} Exam: {nm}', body_html=body(('Key facts',f'The {VN} {E} exam lasts {dur} minutes. The pass mark is {ps_txt}.{hub_extra}'),
              ('What the exam covers',U['hub']),('What changed','The saved official page lists no change log, so no change is recorded here.'))+'{{shared:site:editorial-policy}}',
          shared_keys=[dict(level='site',key='editorial-policy')]),
      'objectives':dict(title_candidates=[_title(f'{E} Skills Measured and Weights')], desc_candidates=[_desc(f'Skill areas and official weight ranges for the {VN} {E} exam, copied from the saved outline, with the task list for each area and the date it was checked')],
          h1=f'{E} Skills Measured', body_html=body(('Weights at a glance',f'Each skill area uses the minimum and maximum weight {VN} publishes. '+U['obj']),('How to read the outline','Use the official task wording when you plan study time for each area. '+X['obj']))),
      'study_guide':dict(title_candidates=[_title(f'{E} Study Guide by Skill Area')], desc_candidates=[_desc(f'A study plan for the {VN} {E} exam arranged by official skill weight, using saved official pages only, and naming gaps where a fact is not published today')],
          h1=f'{E} Study Guide', body_html=body(('Study plan by skill area',U['sg']),('Before exam day','Read the identification rules on the official page and try any free practice the vendor offers.')),
          course_description=f'Study plan for the {E} exam built from the official skills outline.', shared_keys=[dict(level='site',key='exam-day-checklist')]),
      'faq':dict(title_candidates=[_title(f'{E} FAQ from Official Exam Pages')], desc_candidates=[_desc(f'Answers about {VN} {E} exam length, pass mark, cost and languages, each tied to a saved official page or marked as not published by the vendor today')],
          h1=f'{E} Frequently Asked Questions',
          body_html=body(('How long is the exam?',f'The official page gives {dur} minutes.'),('What score do I need to pass?',f'The pass mark is {ps_txt}.'),
                         ('What does it cost?','A single price is not published; it depends on the country or region.'),('Which languages are offered?',', '.join(P['langs'])+'.'))+'<p>'+U['faq']+'</p><p>'+X['faq']+'</p>',
          faq_sourced=['How long is the exam?','Which languages are offered?'], faq_unsourced=['What does it cost?']),
      'practice_test':dict(title_candidates=[_title(f'{E} Practice Test Status and Plan')], desc_candidates=[_desc(f'How a {VN} {E} practice test is timed and mixed, using official limits where the vendor publishes them, and why the practice bank is not ready yet')],
          h1=f'{E} Practice Test', body_html=body(('Status','The practice bank is not ready. Items are drafts that still need expert review. '+U['pt']),('Free official practice',U['pt2']),('How the planned mix works','The planned mix follows the midpoint of each official weight range, scaled to one hundred percent, so heavier skill areas get more items.'))+'{{shared:site:simulator-how-it-works}}',
          shared_keys=[dict(level='site',key='simulator-how-it-works')]),
      'vendor':dict(title_candidates=[_title(f'{VN} Certification Exams on File')], desc_candidates=[_desc(f'Official facts for {VN} certification exams on CertPassly, including booking, accounts and what the saved vendor pages do and do not publish today')],
          h1=f'{VN} Certification Exams', body_html=body(('Exams on this site',f'The table lists {VN} exams with a draft package. '+U['ven']),('Booking and accounts','Book from the official exam page. '+X['ven'])), tables={'exams':[]}),
      'certification':dict(title_candidates=[_title(f'{P["cert_name"].split(":")[-1].strip()[:30]} Credential')], desc_candidates=[_desc(f'What the {P["cert_name"]} credential covers, the exam it requires and the official level, from saved vendor pages')],
          h1=P['cert_name'], crumb_name=P['cert_name'].split(':')[-1].strip(),
          body_html=body(('Requirements',f'The credential requires the {E} exam.'),('What the credential covers',U['cert']),('Using the credential',X['cert'])), tables={'requirements':[]}),
    }
    if P['vendor']=='microsoft':
        prose['vendor']['body_html']+='{{shared:vendor:microsoft:booking}}'
        prose['vendor']['shared_keys']=[dict(level='vendor',key='booking',slug='microsoft')]
    (auth/'page_prose.json').write_text(json.dumps(prose, indent=1, ensure_ascii=False), encoding='utf-8')
    (auth/'bank_meta.json').write_text(json.dumps(dict(skill_rules=[dict(pattern='sign-in|secret|roles',topic='1.1')], default_topic='2.1',
        off_syllabus={}, exhibit_alts={}, cover_facts_conflict=[f'Cover says 800 / 120 (pass mark / minutes). Official page: {ps_txt} / {dur} minutes.'], skipped_files=[]), indent=1), encoding='utf-8')
    ex=lambda c,o,a='key_matches_current_docs': dict(c=c,o=o,s=['SG'],a=a)
    (auth/'explanations_text.json').write_text(json.dumps({
      'q001':ex('A secret store keeps keys and passwords out of app code.',['Right. It holds secrets.','Wrong. Reports do not store secrets.','Wrong. Themes change look only.','Wrong. Layouts arrange fields.']),
      'q002':ex('Extra sign-in factors and sign-in rules both lower account risk.',['Right. A second factor blocks stolen passwords.','Wrong. Shared passwords raise risk.','Right. Rules can block risky sign-ins.','Wrong. Public links widen access.']),
      'q006':ex('Held: the owner file gives no answer.',['Not checked.','Not checked.','Not checked.'],'key_could_not_be_checked'),
    }, indent=1), encoding='utf-8')
    (auth/'explanations_visual.json').write_text(json.dumps({
      'q003':ex('Roles can be granted to groups; default log retention is far shorter than ten years.',['Yes. Group scope is supported.','No. Default retention is shorter.']),
      'q004':ex('The official guidance in this demo says backups run daily.',[['Right. Daily is the stated schedule.','Wrong. Weekly is too sparse here.','Wrong. Monthly is too sparse here.']]),
    }, indent=1), encoding='utf-8')
    (dest/'out'/E/'extracted'/'visual_transcription.json').write_text(json.dumps({
      'q003':dict(rows=yn_rows, key=['yes','no']),
      'q004':dict(blanks=[dd_choices], labels=['Backups run'], key=[0], template='Backups run {{blank1}}.'),
      'q005':dict(held=True, reason='Image-only item: the mock screen has no readable controls or key. Held for the owner.', candidate_regions=[]),
    }, indent=1), encoding='utf-8')
    return dict(exam=E, vendor=V, cert=C, root=str(dest))

if __name__=='__main__':
    info=build(sys.argv[1], Path(sys.argv[2]))
    print(json.dumps(info))
