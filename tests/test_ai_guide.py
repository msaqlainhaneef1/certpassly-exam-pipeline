#!/usr/bin/env python3
"""v1.2.1: the AI guidance docs must match the code.

Parses AGENTS.md, docs/AI-OPERATOR-GUIDE.md, docs/AI-TRAINING-EXERCISES.md and HANDOVER.md and checks:
the stage order equals run_pipeline.STAGES (what --list-stages prints), every stage heading and
--stage value is a real stage, every repo path and relative link exists, every certpassly-pipeline
command uses only real flags, every python scripts/... or tests/... file exists, the docs have no
typographic dashes, no denylist terms and no contact lines, and the agent pointer files point to
AGENTS.md. No network, no AI.
"""
from __future__ import annotations
import re, sys, unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / 'scripts'))
import run_pipeline, site_settings, package_guard as PG

GUIDE = SKILL / 'docs' / 'AI-OPERATOR-GUIDE.md'
EXERCISES = SKILL / 'docs' / 'AI-TRAINING-EXERCISES.md'
AGENTS = SKILL / 'AGENTS.md'
HANDOVER = SKILL / 'HANDOVER.md'
POINTERS = [SKILL / 'CLAUDE.md', SKILL / '.cursor' / 'rules' / 'certpassly.mdc', SKILL / '.github' / 'copilot-instructions.md']
DOCS = [AGENTS, GUIDE, EXERCISES, HANDOVER] + POINTERS
STAGES = [s[0] for s in run_pipeline.STAGES]
REPO_PREFIXES = ('scripts/', 'config/', 'reference/', 'tests/', 'docs/', 'shared/', 'schema/', '.github/', '.cursor/')
# Files that live in the operator's workspace, not in the repo.
WORKSPACE_ONLY = {'config/pipeline.yaml', 'config/vendors.yaml'}
WORKSPACE_ROOT_FILES = {'REVIEW.md', 'CLEANUP-LOG.md', 'WRITING-REVIEW.md', 'VALIDATION.md', 'SITE-QUESTION-TYPES.md'}
ROOT_EXT = ('.md', '.toml', '.sh', '.ps1', '.mdc', '.txt')


def read(p):
    return p.read_text(encoding='utf-8')


def code_blocks(text):
    return re.findall(r'```[a-z]*\n(.*?)```', text, re.S)


def backticked(text):
    out = []
    for t in re.findall(r'`([^`\n]+)`', re.sub(r'```.*?```', '', text, flags=re.S)):
        out.append(t.strip())
    return out


def parser_flags():
    src = read(SKILL / 'scripts' / 'run_pipeline.py')
    return set(re.findall(r"add_argument\('(--[a-z][a-z-]*)'", src)) | {'--help'}


class DocsExist(unittest.TestCase):
    def test_all_docs_exist(self):
        for p in DOCS:
            self.assertTrue(p.exists(), p)

    def test_pointer_files_point_to_agents_md(self):
        for p in POINTERS:
            self.assertIn('AGENTS.md', read(p), p)
        self.assertIn('alwaysApply: true', read(POINTERS[1]))

    def test_readme_and_skill_point_to_guide(self):
        for p in (SKILL / 'README.md', SKILL / 'SKILL.md', SKILL / 'SKILL_BODY.md', AGENTS):
            self.assertIn('docs/AI-OPERATOR-GUIDE.md', read(p), p)

    def test_handover_names_current_version(self):
        ver = re.search(r'^version\s*=\s*"([^"]+)"', read(SKILL / 'pyproject.toml'), re.M).group(1)
        self.assertIn('v' + ver, read(HANDOVER))


class StageNames(unittest.TestCase):
    def test_guide_stage_order_matches_list_stages(self):
        sec = read(GUIDE).split('## 5. Stage order', 1)[1].split('\n## ', 1)[0]
        listed = re.findall(r'^\d+\.\s+`([a-z_]+)`\s*$', sec, re.M)
        self.assertEqual(listed, STAGES)

    def test_guide_has_one_section_per_stage_in_order(self):
        heads = re.findall(r'^### Stage (\d+): `([a-z_]+)`', read(GUIDE), re.M)
        self.assertEqual([n for _, n in heads], STAGES)
        self.assertEqual([int(i) for i, _ in heads], list(range(1, len(STAGES) + 1)))

    def test_handover_stage_order_matches(self):
        line = [l for l in read(HANDOVER).splitlines() if l.startswith('Stage order')][0]
        self.assertEqual(re.findall(r'`([a-z_]+)`', line.split('. ', 1)[0]), STAGES)

    def test_exercise_stage_order_matches(self):
        m = re.search(r'15 stage rows in this order: ([a-z_, ]+)\.', read(EXERCISES))
        self.assertEqual([s.strip() for s in m.group(1).split(',')], STAGES)

    def test_only_author_is_ai_yes(self):
        self.assertEqual([s[0] for s in run_pipeline.STAGES if s[1] == 'YES'], ['author'])
        self.assertIn('`author` is the only AI stage', read(GUIDE))

    def test_every_stage_flag_value_is_real(self):
        for p in DOCS:
            for v in re.findall(r'--stage\s+([A-Za-z_]+)', read(p)):
                if v in ('NAME', 'S'):
                    continue
                self.assertIn(v, STAGES, f'{p.name}: --stage {v}')


class CommandsAndPaths(unittest.TestCase):
    def test_pipeline_commands_use_real_flags(self):
        flags = parser_flags()
        self.assertIn('--list-stages', flags)
        for p in DOCS:
            for block in code_blocks(read(p)):
                for line in block.splitlines():
                    if 'certpassly-pipeline' not in line:
                        continue
                    for f in re.findall(r'(?<![\w-])(--[a-z][a-z-]*)', line.split('certpassly-pipeline', 1)[1]):
                        self.assertIn(f, flags, f'{p.name}: {line.strip()}')

    def test_python_script_commands_point_to_real_files(self):
        for p in DOCS:
            for block in code_blocks(read(p)):
                for rel in re.findall(r'python\s+((?:scripts|tests)/[\w/]+\.py)', block):
                    self.assertTrue((SKILL / rel).exists(), f'{p.name}: {rel}')

    def test_repo_paths_exist(self):
        for p in DOCS:
            for t in backticked(read(p)):
                if any(c in t for c in '<>* ') or t in WORKSPACE_ONLY:
                    continue
                path = t.rstrip('/')
                if t.startswith(REPO_PREFIXES):
                    self.assertTrue((SKILL / path).exists(), f'{p.name}: {t}')
                elif '/' not in t and t.endswith(ROOT_EXT) and t not in WORKSPACE_ROOT_FILES and t[:1].isupper():
                    self.assertTrue((SKILL / path).exists(), f'{p.name}: {t}')

    def test_relative_links_exist(self):
        for p in DOCS:
            for link in re.findall(r'\]\(([^)#]+)(?:#[^)]*)?\)', read(p)):
                if link.startswith(('http://', 'https://')):
                    continue
                self.assertTrue((p.parent / link).resolve().exists(), f'{p.name}: {link}')

    def test_named_scripts_exist(self):
        for p in DOCS:
            for name in re.findall(r'scripts/([\w/]+\.py)', read(p)):
                self.assertTrue((SKILL / 'scripts' / name).exists(), f'{p.name}: scripts/{name}')


class CleanText(unittest.TestCase):
    def test_no_typographic_dashes(self):
        for p in DOCS:
            self.assertIsNone(re.search('[\u2013\u2014]', read(p)), p)

    def test_no_denylist_terms_or_contact_lines(self):
        S = site_settings.load(str(SKILL / 'config' / 'pipeline.example.yaml'))
        R = PG.rules(S)
        self.assertTrue(any(l.startswith('denylist') for l, _, _ in R))
        for p in DOCS:
            hits = PG.text_hits(read(p), R)
            self.assertEqual([l for l, _ in hits], [], f'{p.name}: {[l for l, _ in hits]}')

    def test_cited_gate_ids_exist_in_validate(self):
        ids = set(re.findall(r"chk\(f?['\"](\d{2}[a-z]?) ", read(SKILL / 'scripts' / 'validate.py')))
        self.assertGreater(len(ids), 50)
        self.assertIn(f'{len(ids)} checks', read(GUIDE))
        self.assertIn(f'ok {len(ids)} fail 0', read(EXERCISES))
        for p in (AGENTS, GUIDE, EXERCISES, HANDOVER):
            for g in re.findall(r'(?:gate|gates|validate|FAIL|check)\s+(\d{2}[a-z]?)\b(?!\s+(?:of|checks))', read(p)):
                self.assertIn(g, ids, f'{p.name}: gate {g}')

if __name__ == '__main__':
    unittest.main(verbosity=2)
