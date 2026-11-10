#!/usr/bin/env python3
"""Always-on checks: grep gate, skill layout, shared seeds, entry point module."""
from __future__ import annotations
import os, re, unittest
from pathlib import Path

SKILL=Path(__file__).resolve().parents[1]
FORBIDDEN_LITERALS=('AB-730', 'ab-730', 'Microsoft', 'ai-business-professional')
FORBIDDEN_PATHS=(
    '/home/box/certpassly',
    'wt-ci-double-build',
    'msaqlainhaneef1/CertPassly',
    'github.com/msaqlain',
    '/workspace/certpassly',
)

class TestSkillGates(unittest.TestCase):
    def test_grep_scripts_have_no_hardcoded_exam_or_vendor(self):
        hits=[]
        for p in (SKILL/'scripts').rglob('*.py'):
            rel=str(p.relative_to(SKILL)).replace('\\','/')
            text=p.read_text(encoding='utf-8', errors='replace')
            if rel!='scripts/adapters/microsoft.py':
                for bad in FORBIDDEN_LITERALS:
                    for i,line in enumerate(text.splitlines(),1):
                        if bad in line:
                            hits.append(f'{rel}:{i}: {bad}')
            for bad in FORBIDDEN_PATHS:
                for i,line in enumerate(text.splitlines(),1):
                    if bad in line and not re.search(r'\b(never|not|without|ignored|does not|do not|no app repo)\b', line, re.I):
                        hits.append(f'{rel}:{i}: {bad}')
        self.assertEqual(hits, [], 'scripts still contain forbidden literals or repo paths:\n'+'\n'.join(hits))

    def test_skill_md_frontmatter_and_install_files(self):
        text=(SKILL/'SKILL.md').read_text(encoding='utf-8')
        self.assertTrue(text.startswith('---\n'))
        self.assertIn('name: certpassly-exam-pipeline', text)
        self.assertIn('description:', text)
        for name in ('pyproject.toml','requirements.txt','install.sh','install.ps1',
                     '.gitignore','.env.example','README.md','CHANGELOG.md',
                     'SKILL_BODY.md','DESCRIPTION.txt'):
            self.assertTrue((SKILL/name).is_file(), name)
        py=(SKILL/'pyproject.toml').read_text(encoding='utf-8')
        self.assertIn('certpassly-pipeline', py)
        self.assertIn('certpassly_pipeline.run_pipeline:main', py)

    def test_skill_root_finds_this_checkout(self):
        import sys
        sys.path.insert(0, str(SKILL/'scripts'))
        import paths
        # reset env
        os.environ.pop('CERTPASSLY_SKILL_ROOT', None)
        # paths may already be imported; call the function
        root=paths.skill_root()
        self.assertTrue((Path(root)/'SKILL.md').is_file())
        self.assertTrue((Path(root)/'reference'/'site-format'/'v1').is_dir())

    def test_shared_seeds_exist_and_have_no_dashes(self):
        import sys
        sys.path.insert(0, str(SKILL/'scripts'))
        os.environ['CERTPASSLY_SKILL_ROOT']=str(SKILL)
        import paths, shared_sections
        blocks=list(shared_sections.iter_blocks())
        site=[b for b in blocks if b.get('level')=='site' or '/site/' in (b.get('_rel') or '')]
        qtypes=[b for b in blocks if 'question-type' in (b.get('_rel') or '') or b.get('level')=='question-type']
        self.assertGreaterEqual(len(site), 6)
        self.assertGreaterEqual(len(qtypes), 30)
        dash=[]
        for b in blocks:
            raw=(b.get('body_html') or '')+' '+(b.get('body') or '')
            if re.search('[\u2013\u2014]', raw):
                dash.append(b.get('_rel') or b.get('key'))
        self.assertEqual(dash, [])

    def test_gitignore_excludes_owner_data(self):
        g=(SKILL/'.gitignore').read_text(encoding='utf-8')
        for needle in ('out/','sources/','run.log','.env','__pycache__','secrets/'):
            self.assertIn(needle, g, needle)

if __name__=='__main__':
    unittest.main(verbosity=2)
