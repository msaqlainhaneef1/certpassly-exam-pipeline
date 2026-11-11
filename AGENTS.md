# AGENTS.md

You are working in the CertPassly exam pipeline skill (`certpassly-exam-pipeline`, command `certpassly-pipeline`). This file is the entry point for every AI agent and coding tool. Read it fully, then read the files in "Where to go next" before you run or change anything.

## What this repo does

It turns official vendor pages plus an owner's question PDF into draft, site-ready exam pages and question import files for CertPassly. Scripts do the work. One stage, `author`, is written by an AI in a single batched pass. The runner never calls a model.

## Hard rules (never break these)

1. Official vendor brands, product names, certification titles and exam codes are required and must stay exact. CertPassly is the only site brand.
2. Never output a seller or competitor brand (including the seller brand printed in owner PDFs), social links, phone numbers, emails or free-update lines. The denylist is `brand_denylist` and `contact_patterns` in `config/pipeline.example.yaml` (copied to the workspace as `config/pipeline.yaml`).
3. Never invent a question, an answer key or a fact. Questions come only from owner PDFs. Facts come only from saved official pages with URL, sha256 and a verbatim quote. If the vendor does not publish a value, write "not published by the vendor".
4. Never change an owner key. Keys that current official docs contradict are flagged (`key_wrong`, `key_outdated`, `key_arguable`) with a note.
5. Items with no answer are never held or dropped: `answer_research` gives `researched_unverified` (official quote) or `answer_not_found` (draft, excluded from scoring).
6. Stems and options get spelling, grammar and punctuation fixes only. Never change meaning, the correct answer, or option order. Official vendor product names stay exact. Every change is logged in `text-fixes.json` and gated by the key and option-order identity check (validate 12n).
7. Plain English at grade 8 to 9, short sentences, no em or en dashes, no banned AI phrases (`config/banned_ai_phrases.txt`).
8. Max scripts, min AI. `author` is the only AI stage. Fix only the parts a check flagged, then run the check again.
9. No hardcoded exam codes, vendor names or counts in scripts. Use config and adapters.
10. Never claim a result without proof: commit SHAs, exit codes, counts and sha256.
11. Only one pipeline run may write `out/<CODE>/` at a time.
12. Never print, store or commit a token. Never force-push. Never rewrite a tag.

## Where to go next

1. [docs/AI-OPERATOR-GUIDE.md](docs/AI-OPERATOR-GUIDE.md): the full manual. Every rule, every stage in order (inputs, outputs, command, success, failures), the author pass, runbooks, the release flow, the done checklist and the report template.
2. [docs/AI-TRAINING-EXERCISES.md](docs/AI-TRAINING-EXERCISES.md): graded exercises on the synthetic demo with expected outputs. Do them once before your first real run.
3. [reference/lessons-learned.md](reference/lessons-learned.md): read before every run.
4. [reference/writing-brief.md](reference/writing-brief.md): read before the author pass.
5. [SKILL.md](SKILL.md) and [HANDOVER.md](HANDOVER.md): skill summary and the current state of the project.

## Quick commands

```
pip install -e .
certpassly-pipeline --list-stages
python -m unittest discover -s tests -v
```

## For every AI tool

This file is the single source of truth for any AI: ChatGPT, Claude, Gemini, Copilot, Cursor, Codex, Windsurf, Cline, Aider, Continue, Amazon Q, Junie, or any other. Tool-specific files (CLAUDE.md, GEMINI.md, CONVENTIONS.md, .cursorrules, .windsurfrules, .clinerules, llms.txt and others) only point here. If you are a chat AI without file access, ask the user to paste AGENTS.md and docs/AI-OPERATOR-GUIDE.md.
