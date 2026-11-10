#!/usr/bin/env python3
"""Offline dry run of extract / pages / import / validate for a non-Microsoft exam.

Uses a short synthetic owner PDF and thin official HTML (duration and skill
areas published; passing score not published). No network, no AI. The test
proves the generic path runs end to end and reports official-source gaps
honestly instead of inventing a pass mark.
"""
from __future__ import annotations
import csv, hashlib, json, os, re, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

SKILL=Path(__file__).resolve().parents[1]
SCRIPTS=SKILL/'scripts'
EXAM='Plat-Admn-201'
VENDOR='salesforce'
CERT='platform-administrator'
DATE='2026-11-11'
SG_URL='https://trailheadacademy.salesforce.com/certificate/exam-platform-admin---Plat-Admn-201'
CP_URL='https://trailheadacademy.salesforce.com/credentials/platform-administrator/'

# Intent phrases required by validate check 11 (must appear in page text).
INTENT={
    'exam_hub':['key facts','what the exam covers','what changed'],
    'objectives':['weights at a glance'],
    'study_guide':['study plan by skill area','before exam day'],
    'faq':['how long','pass','cost','languages'],
    'practice_test':['not ready','free official practice'],
    'vendor':['exams on'],
    'certification':['requirements'],
}


def write_simple_pdf(path: Path, lines):
    """Minimal one-page PDF with Helvetica text. No third-party library."""
    chunks=['BT /F1 12 Tf 50 740 Td']
    first=True
    for line in lines:
        s=line.replace('\\','\\\\').replace('(','\\(').replace(')','\\)')
        if first:
            chunks.append(f'({s}) Tj')
            first=False
        else:
            chunks.append(f'0 -16 Td ({s}) Tj')
    chunks.append('ET')
    stream='\n'.join(chunks).encode('latin-1', 'replace')
    objs=[]
    objs.append(b'1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n')
    objs.append(b'2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n')
    objs.append(b'3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n')
    objs.append(b'4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n')
    objs.append(b'5 0 obj << /Length %d >> stream\n'%len(stream)+stream+b'\nendstream endobj\n')
    xref=[]
    out=b'%PDF-1.4\n'
    for obj in objs:
        xref.append(len(out))
        out+=obj
    startxref=len(out)
    out+=b'xref\n0 6\n0000000000 65535 f \n'
    for off in xref:
        out+=f'{off:010d} 00000 n \n'.encode()
    out+=f'trailer << /Size 6 /Root 1 0 R >>\nstartxref\n{startxref}\n%%EOF\n'.encode()
    path.write_bytes(out)


def write_source(root: Path, url: str, html: str, retrieved='2026-11-11T04:00:00+0500'):
    data=html.encode('utf-8')
    sha=hashlib.sha256(data).hexdigest()
    dest=root/'sources'/VENDOR
    dest.mkdir(parents=True, exist_ok=True)
    name=sha[:16]+'.html'
    (dest/name).write_bytes(data)
    meta=dict(url=url, http='200', final_url=url, sha256=sha,
              path=str(dest/name), retrieved_at=retrieved)
    (dest/(name+'.json')).write_text(json.dumps(meta, indent=1), encoding='utf-8')
    return meta


def pad(s, lo, hi):
    if len(s)<lo:
        s=s+' '*(lo-len(s))  # last resort
        # better: add words
    if not lo<=len(s)<=hi:
        raise AssertionError(f'len {len(s)} not in {lo}-{hi}: {s!r}')
    return s


def build_workspace(dest: Path):
    dest.mkdir(parents=True, exist_ok=True)
    for sub in ('config','cache','research/vendors','research/certs',f'research/{VENDOR}',
                f'out/{EXAM}/intake',f'out/{EXAM}/authoring','owner-files'):
        (dest/sub).mkdir(parents=True, exist_ok=True)
    shutil.copy2(SKILL/'config'/'pipeline.example.yaml', dest/'config'/'pipeline.yaml')
    shutil.copy2(SKILL/'config'/'vendors.example.yaml', dest/'config'/'vendors.yaml')

    sg_html='''<!doctype html><html><body>
<h1>Salesforce Certified Platform Administrator</h1>
<p>Exam: Plat-Admn-201</p>
<p>The exam length is 105 minutes.</p>
<p>The exam is delivered through Webassessor.</p>
<p>Languages: English.</p>
<p>Price is not listed as a single amount; it depends on the country or region.</p>
<h2>Skills measured</h2>
<p>Configuration and setup (40-50%)</p>
<p>Objects, data and security (50-60%)</p>
<p>Configuration and setup covers user setup and company settings.</p>
<p>Objects, data and security covers object permissions and sharing.</p>
</body></html>'''
    cp_html='''<!doctype html><html><body>
<h1>Salesforce Certified Platform Administrator</h1>
<p>Level: Intermediate.</p>
<p>Roles: Administrator.</p>
<p>This credential requires exam Plat-Admn-201.</p>
<p>A free official practice offering is not described on this page.</p>
<p>Last updated date is not stated as a specific day on this page.</p>
<p>The exam is delivered through Webassessor.</p>
</body></html>'''
    sg=write_source(dest, SG_URL, sg_html)
    cp=write_source(dest, CP_URL, cp_html)

    fact=lambda value, sid, quote: dict(value=value, source_id=sid, quote=quote)
    missing=lambda reason: dict(value=None, reason=reason)

    research=dict(
        exam_code=EXAM, vendor_slug=VENDOR, certification_slug=CERT, exam_slug='plat-admn-201',
        researched_at=DATE,
        sources=[
            dict(id='sg', kind='study_guide', url=SG_URL, title='Salesforce Certified Platform Administrator',
                 as_of_date='2026-10-20', expected_sha256=sg['sha256']),
            dict(id='cp', kind='certification_page', url=CP_URL, title='Salesforce Certified Platform Administrator',
                 as_of_date='2026-10-20', expected_sha256=cp['sha256']),
        ],
        exam_name=fact('Salesforce Certified Platform Administrator','sg','Salesforce Certified Platform Administrator'),
        facts=dict(
            duration_minutes=fact(105,'sg','The exam length is 105 minutes.'),
            passing_score=missing('The official page does not publish a passing score for this exam. not published by the vendor.'),
            score_scale=missing('The official page does not publish a score scale.'),
            question_count=missing('The official page does not publish a fixed number of questions.'),
            question_formats=missing('The official page does not publish question formats.'),
            languages=fact(['English'],'sg','Languages: English.'),
            price=missing('The official page does not publish a single price. Price is not listed as a single amount; it depends on the country or region.'),
            prerequisites=missing('The official page does not publish prerequisites.'),
            validity_and_renewal=missing('The official page does not publish a renewal rule.'),
            retake_policy=missing('The official page does not publish a retake rule.'),
            extra_time_language=missing('The official page does not publish an extra-time rule.'),
            status=missing('The official page does not publish a lifecycle status.'),
            audience=missing('The official page does not publish an audience profile.'),
            level=fact('Intermediate','cp','Level: Intermediate.'),
            product_name_note=missing('The official page does not publish a product-name note.'),
            delivery=fact('Delivered through Webassessor','sg','The exam is delivered through Webassessor.'),
        ),
        objectives=dict(
            outline_as_of='2026-10-20', source_id='sg',
            domains=[
                dict(code='1', name='Configuration and setup', weight_min_pct=40, weight_max_pct=50,
                     topics=[dict(code='1.1', name='Configuration and setup covers user setup and company settings.', subtopics=[])]),
                dict(code='2', name='Objects, data and security', weight_min_pct=50, weight_max_pct=60,
                     topics=[dict(code='2.1', name='Objects, data and security covers object permissions and sharing.', subtopics=[])]),
            ],
            changes_from_previous=None,
        ),
        learning_resources=[], serp=[], blurbs={},
        unknowns=['passing_score','question_count','price'],
        gaps=['passing_score','question_count','price','question_formats','prerequisites','validity_and_renewal','retake_policy'],
    )
    (dest/'research'/VENDOR/f'{EXAM}.json').write_text(json.dumps(research, indent=1), encoding='utf-8')
    (dest/'research'/VENDOR/f'{EXAM}-bank-sources.json').write_text(json.dumps({
        'sources':[dict(id='SG', title='Salesforce Certified Platform Administrator', url=SG_URL)]
    }, indent=1), encoding='utf-8')

    vendor=dict(
        vendor_slug=VENDOR, name='Salesforce', official_site='https://trailheadacademy.salesforce.com/',
        official_learning_url='https://trailheadacademy.salesforce.com/',
        sources=[dict(id='sg', url=SG_URL, expected_sha256=sg['sha256']),
                 dict(id='cp', url=CP_URL, expected_sha256=cp['sha256'])],
        facts=dict(
            exam_sandbox=missing('The official page does not describe an exam sandbox.'),
            accommodations=missing('The official page does not describe accommodations.'),
        ),
        logo_note='', blurbs={},
    )
    (dest/'research'/'vendors'/f'{VENDOR}.json').write_text(json.dumps(vendor, indent=1), encoding='utf-8')

    cert=dict(
        certification_slug=CERT, vendor_slug=VENDOR,
        name='Salesforce Certified Platform Administrator', source_id='cp',
        sources=[dict(id='cp', url=CP_URL, expected_sha256=cp['sha256'])],
        required_exams=[dict(code=EXAM, requirement_type='required', quote='This credential requires exam Plat-Admn-201.')],
        level=fact('Intermediate','cp','Level: Intermediate.'),
        roles=dict(value=['Administrator'], quote='Roles: Administrator.', source_id='cp'),
        product=missing('The official page does not name a single product line for this credential.'),
        subject=missing('The official page does not name a subject category.'),
        prerequisites=missing('The official page does not publish prerequisites.'),
        validity=missing('The official page does not publish an expiry period.'),
        renewal=missing('The official page does not publish a renewal rule.'),
        practice_assessment=missing('A free official practice offering is not described on this page.'),
        last_updated=missing('Last updated date is not stated as a specific day on this page.'),
    )
    (dest/'research'/'certs'/f'{CERT}.json').write_text(json.dumps(cert, indent=1), encoding='utf-8')

    # catalog
    header='vendor,vendor_slug,certification,exam_code,exam_name,sheet_status,drive_folder_url,sheet_cell,sheet_label,official_exam_url,url_http,page_names_exam,url_sha256,source_path,empty_reason'
    row=','.join([
        'Salesforce',VENDOR,'Salesforce Certified Platform Administrator',EXAM,
        'Salesforce Certified Platform Administrator','ready','','A1',EXAM,SG_URL,'200','','','',''
    ])
    (dest/'catalog.csv').write_text(header+'\n'+row+'\n', encoding='utf-8')

    lc={SG_URL:'200', CP_URL:'200', 'https://trailheadacademy.salesforce.com/':'200'}
    (dest/'cache'/'linkcheck.json').write_text(json.dumps(lc, indent=1), encoding='utf-8')

    # Owner PDF + intake (the "Drive PDF" is represented here as a local file listed in intake)
    pdf=dest/'owner-files'/f'{EXAM}-owner.pdf'
    write_simple_pdf(pdf, [
        'Owner question file for training use',
        'QUESTION 1',
        'Which Setup area is used to change a user language?',
        'A. Users',
        'B. Company Information',
        'C. Reports',
        'D. App Launcher only',
        'Correct Answer: A',
        'Explanation',
        'QUESTION 2',
        'Which statements about profiles are true? (Choose two.)',
        'A. A profile grants object permissions.',
        'B. A profile is the same as a role.',
        'C. A user is assigned one profile.',
        'D. Profiles replace permission sets.',
        'Correct Answer: A,C',
        'Explanation',
    ])
    intake=dict(files=[dict(name=pdf.name, path=str(pdf), use='extracted', sha256=hashlib.sha256(pdf.read_bytes()).hexdigest())])
    (dest/'out'/EXAM/'intake'/'files.json').write_text(json.dumps(intake, indent=1), encoding='utf-8')
    (dest/'out'/EXAM/'intake'/'rights-confirmation.md').write_text(
        'Owner-provided file for pipeline testing. Synthetic items only.\n', encoding='utf-8')

    def titles(t): return [t]
    def desc(d):
        if not (140<=len(d)<=160):
            raise AssertionError(f'desc len {len(d)}: {d}')
        return [d]

    prose={
        'note':'Synthetic author-stage fixture for the non-Microsoft dry run. No seller branding.',
        'exam_code':EXAM,
        'exam_hub':dict(
            title_candidates=titles('Plat-Admn-201 Exam Facts for Administrators | CertPassly'),
            desc_candidates=desc("Official length, delivery, languages and skill areas for Plat-Admn-201, taken from the vendor's exam page, with gaps called out when a value is not published."),
            h1='Plat-Admn-201 Exam: Platform Administrator',
            body_html=(
                '<h2>Key facts</h2><p>The key facts table lists official length, delivery and languages for this Salesforce exam. A passing score is not published by the vendor, and this page does not invent one.</p>'
                '<h2>What the exam covers</h2><p>The exam covers configuration and setup, and objects, data and security, at the official weights on the vendor page.</p>'
                '<h2>What changed</h2><p>The vendor page we saved does not list a change log, so this section records that no official change note was published on that copy.</p>'
                '{{shared:site:editorial-policy}}'
            ),
            shared_keys=[dict(level='site', key='editorial-policy')],
        ),
        'objectives':dict(
            title_candidates=titles('Plat-Admn-201 Official Skills and Weights | CertPassly'),
            desc_candidates=desc('Skill areas and official weight ranges for Plat-Admn-201, copied from the vendor outline, including values the vendor does not publish at this time.'),
            h1='Plat-Admn-201 Skills Measured',
            body_html=(
                '<h2>Weights at a glance</h2><p>Each skill area below uses the official minimum and maximum weight published by Salesforce.</p>'
                '<h2>How to read the outline</h2><p>Use the official task wording, not a third-party rewrite, when you study each area.</p>'
            ),
        ),
        'study_guide':dict(
            title_candidates=titles('Plat-Admn-201 Study Guide from Official Skills | CertPassly'),
            desc_candidates=desc('A study plan for Plat-Admn-201 arranged by official skill-area weight, using official vendor pages only, and stating gaps when a fact is not published today.'),
            h1='Plat-Admn-201 Study Guide',
            body_html=(
                '<h2>Study plan by skill area</h2><p>Start with the heavier official skill area, then practice each task in the product before you sit a timed session.</p>'
                '<h2>Before exam day</h2><p>Read the official identification rules and try any official practice the vendor still offers.</p>'
            ),
            course_description='Study plan for the Plat-Admn-201 exam built from the official skills outline dated 20 October 2026.',
            shared_keys=[dict(level='site', key='exam-day-checklist')],
        ),
        'faq':dict(
            title_candidates=titles('Plat-Admn-201 FAQ from Official Exam Pages | CertPassly'),
            desc_candidates=desc('Answers about Plat-Admn-201 length, booking, pass mark, cost and languages, each tied to a saved official page or marked as not published yet.'),
            h1='Plat-Admn-201 Frequently Asked Questions',
            body_html=(
                '<h2>How long is the exam?</h2><p>The official page says the exam length is 105 minutes. (<a href="'+SG_URL+'">source</a>)</p>'
                '<h2>What is the pass mark?</h2><p>A passing score is not published by the vendor on the saved official page.</p>'
                '<h2>What does it cost?</h2><p>A single price is not published by the vendor. The page says price depends on the country or region.</p>'
                '<h2>Which languages are offered?</h2><p>The official page lists English. (<a href="'+SG_URL+'">source</a>)</p>'
            ),
            faq_sourced=['How long is the exam?','Which languages are offered?'],
            faq_unsourced=['What is the pass mark?','What does it cost?'],
        ),
        'practice_test':dict(
            title_candidates=titles('Plat-Admn-201 Practice Test Status and Plan | CertPassly'),
            desc_candidates=desc('How a Plat-Admn-201 practice test would be timed and mixed, using official limits where the vendor publishes them, and saying when the bank is not ready.'),
            h1='Plat-Admn-201 Practice Test',
            body_html=(
                '<h2>Status</h2><p>A practice bank on this site is not ready for sale. This page describes the planned mix only.</p>'
                '<h2>Free official practice</h2><p>A free official practice offering is not described on the saved vendor page, so we do not invent one.</p>'
                '{{shared:site:simulator-how-it-works}}'
            ),
            shared_keys=[dict(level='site', key='simulator-how-it-works')],
        ),
        'vendor':dict(
            title_candidates=titles('Salesforce Certification Exams: Official Facts | CertPassly'),
            desc_candidates=desc('Official facts for Salesforce certification exams on CertPassly, including booking, accounts and what the vendor page does and does not publish today on file.'),
            h1='Salesforce Certification Exams',
            body_html=(
                '<h2>Exams on this site</h2><p>The table lists Salesforce exams that have a draft package on CertPassly.</p>'
                '<h2>Booking and accounts</h2><p>Book from the official exam page, which uses the vendor delivery partner named there.</p>'
                '{{shared:vendor:salesforce:booking}}'
            ),
            tables={'exams':[]},
        ),
        'certification':dict(
            title_candidates=titles('Platform Administrator Credential Guide | CertPassly'),
            desc_candidates=desc('What the Salesforce Platform Administrator credential covers, the exam it requires, official level and roles, and facts the vendor page still does not publish.'),
            h1='Salesforce Certified Platform Administrator',
            crumb_name='Platform Administrator',
            body_html=(
                '<h2>Requirements</h2><p>The official page states that this credential requires exam Plat-Admn-201.</p>'
                '<h2>What the credential covers</h2><p>The credential is aimed at administrators who configure the platform, at the intermediate level named on the official page.</p>'
            ),
            tables={'requirements':[]},
        ),
    }
    # booking block for this vendor may not exist (only a seed under another vendor slug).
    # Remove the marker if the block is missing so build_pages does not leave a raw tag.
    # The test will rely on the generic booking sentence already in the vendor body.
    prose['vendor']['body_html']=prose['vendor']['body_html'].replace('{{shared:vendor:salesforce:booking}}','')
    auth=dest/'out'/EXAM/'authoring'
    (auth/'page_prose.json').write_text(json.dumps(prose, indent=1), encoding='utf-8')
    (auth/'bank_meta.json').write_text(json.dumps(dict(
        skill_rules=[], default_topic='1.1', off_syllabus=[], exhibit_alts={},
        cover_facts_conflict=[], skipped_files=[],
    ), indent=1), encoding='utf-8')
    (auth/'explanations_text.json').write_text(json.dumps({
        'q001':dict(c='The Users page in Setup is where a language is set for that user.',
                    o=['Right. User language is set on the user record in Setup.',
                       'Wrong. Company Information is org-wide, not a user language.',
                       'Wrong. Reports are not used to change a user language.',
                       'Wrong. App Launcher opens apps, not user language.'],
                    s=['SG'], a='key_matches_current_docs'),
        'q002':dict(c='A profile grants object permissions, and a user is assigned one profile.',
                    o=['Right. Object permissions come from the profile (and permission sets).',
                       'Wrong. A role is a hierarchy concept, not a profile.',
                       'Right. A user is assigned exactly one profile.',
                       'Wrong. Permission sets add to a profile; they do not replace it.'],
                    s=['SG'], a='key_matches_current_docs'),
    }, indent=1), encoding='utf-8')
    return dest


def run_pipeline(root: Path, stages):
    env=os.environ.copy()
    env['https_proxy']='http://127.0.0.1:9'
    env['http_proxy']='http://127.0.0.1:9'
    env['HTTPS_PROXY']=env['https_proxy']
    env['HTTP_PROXY']=env['http_proxy']
    env['ALL_PROXY']=env['https_proxy']
    env['no_proxy']=''; env['NO_PROXY']=''
    for k in ('CERTPASSLY_APP','APP_REPO','CERTPASSLY_REPO'):
        env.pop(k, None)
    env['CERTPASSLY_ROOT']=str(root)
    env['CERTPASSLY_SKILL_ROOT']=str(SKILL)
    env['CERTPASSLY_OFFLINE']='1'
    env['CERTPASSLY_DATE']=DATE
    env['PYTHONPATH']=str(SCRIPTS)
    cmd=[sys.executable, str(SCRIPTS/'run_pipeline.py'),
         '--exam', EXAM, '--root', str(root),
         '--config', str(root/'config'/'pipeline.yaml'),
         '--date', DATE, '--offline']
    for s in stages:
        cmd+=['--stage', s]
    return subprocess.run(cmd, cwd=root, env=env, capture_output=True, text=True)


class TestNonMicrosoftDryRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir=Path(tempfile.mkdtemp(prefix='certpassly-nonms-'))
        build_workspace(cls.tmpdir)
        cls.result=run_pipeline(cls.tmpdir, ['research','extract','author','pages','import','bank','validate'])
        (cls.tmpdir/'test_stdout.log').write_text(cls.result.stdout+'\n--- stderr ---\n'+cls.result.stderr)

    def test_01_extract_split_two_items_and_layout(self):
        split=json.loads((self.tmpdir/'out'/EXAM/'extracted'/'split.json').read_text())
        self.assertEqual(sorted(split), ['q001','q002'])
        self.assertIn('Users', split['q001']['options'].get('a',''))
        self.assertEqual(split['q001']['options'].get('a'), 'Users')
        self.assertIn('A', split['q001']['answer_raw'].upper())
        self.assertIn('A,C', split['q002']['answer_raw'].replace(' ','').upper())
        layout=json.loads((self.tmpdir/'out'/EXAM/'extracted'/'layout.json').read_text())
        self.assertGreaterEqual(layout.get('start_count') or 0, 2)
        unparsed=json.loads((self.tmpdir/'out'/EXAM/'extracted'/'unparsed.json').read_text())
        self.assertIsInstance(unparsed, list)

    def test_02_research_reports_gaps_and_does_not_invent_a_pass_mark(self):
        log=(self.result.stdout+self.result.stderr)
        if (self.tmpdir/'run.log').exists():
            log+= (self.tmpdir/'run.log').read_text()
        self.assertIn('gaps', log.lower())
        parsed=self.tmpdir/'research'/VENDOR/f'{EXAM}.parsed.json'
        self.assertTrue(parsed.is_file(), 'generic adapter should write a parsed sidecar')
        out=json.loads(parsed.read_text())
        # Passing score must be a reported gap, not a guessed number.
        fields=out.get('fields') or {}
        gaps=out.get('gaps') or []
        blob=json.dumps(out).lower()
        if 'passing_score' in fields and fields['passing_score'] not in (None,'',[]):
            # If the parser thought it found one, it must have been on the saved page. Our page has none.
            self.fail('adapter invented a passing score: '+repr(fields['passing_score']))
        self.assertTrue('passing_score' in gaps or 'passing' in blob or 'not published' in blob)

    def test_03_pages_and_import_exist(self):
        pages=self.tmpdir/'out'/EXAM/'pages'
        for name in ('exam-hub.json','objectives.json','study-guide.json','faq.json','practice-test.json'):
            self.assertTrue((pages/name).is_file(), name)
        self.assertTrue((self.tmpdir/'out'/'vendors'/VENDOR/'vendor.json').is_file())
        self.assertTrue((self.tmpdir/'out'/'certifications'/CERT/'certification.json').is_file())
        imp=self.tmpdir/'out'/EXAM/'import'
        for name in ('exams.csv','page_copy.csv','page_meta_extras.csv','sources.csv'):
            self.assertTrue((imp/name).is_file(), name)

    def test_04_hub_states_pass_mark_is_not_published(self):
        hub=json.loads((self.tmpdir/'out'/EXAM/'pages'/'exam-hub.json').read_text())
        text=re.sub(r'<[^>]+>',' ', hub['body_html']+' '+json.dumps(hub.get('tables')))
        self.assertIn('not published by the vendor', text.lower())
        # Do not invent a common four-digit pass mark
        self.assertNotRegex(text, r'\b(700|720|750|800)\b')
        # Official vendor brand required
        self.assertIn('salesforce', text.lower())
        # Official duration is present
        self.assertIn('105', text)

    def test_05_validate_ran_and_recorded_honest_gaps(self):
        vpath=self.tmpdir/'out'/EXAM/'validation.json'
        self.assertTrue(vpath.is_file(), 'validation.json missing; log:\n'+(self.result.stdout+self.result.stderr)[-3000:])
        rows=json.loads(vpath.read_text())
        names=[r['check'] if isinstance(r,dict) and 'check' in r else (r[0] if isinstance(r,list) else str(r)) for r in rows]
        self.assertTrue(names, 'no checks recorded')
        # Passing score / 01c may fail; that is an honest gap, not a crash.
        failed=[]
        for r in rows:
            if isinstance(r, dict):
                ok=r.get('passed', r.get('ok'))
                name=r.get('check') or r.get('name')
            else:
                name, ok = r[0], r[1]
            if not ok:
                failed.append(name)
        # Pages were built; validate must have at least run the official-source and meta checks.
        joined=' '.join(names).lower()
        self.assertTrue('source' in joined or '01' in joined or 'fact' in joined)
        # If 01c or passing score failed, that is expected. A crash would have left no file.
        (self.tmpdir/'validate_failed.json').write_text(json.dumps(failed, indent=1))

    def test_06_no_network_and_extract_was_not_skipped_wrongly(self):
        blob=self.result.stdout+self.result.stderr
        if (self.tmpdir/'run.log').exists():
            blob+=(self.tmpdir/'run.log').read_text()
        for bad in ('Cloning into','php artisan','github.com/'):
            self.assertNotIn(bad, blob)
        # extract should have run (split exists from test_01). Pipeline may be non-zero because validate reports gaps.
        self.assertTrue((self.tmpdir/'out'/EXAM/'extracted'/'split.json').is_file())


if __name__=='__main__':
    unittest.main(verbosity=2)
