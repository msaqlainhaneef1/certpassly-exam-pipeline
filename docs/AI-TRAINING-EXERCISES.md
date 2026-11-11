# AI training exercises

A graded self-training path on the synthetic demo. Each exercise runs the demo, breaks one thing, shows the gate that fails, then fixes it. The expected outputs below are copied from real runs of v1.2.1 (date frozen to 2026-11-11). Your timestamps and paths will differ; the messages and counts must match.

Rules while training:

- Use the synthetic demo only (`tests/demo_kit.py`). Never use real owner files for training.
- Each exercise starts from a fresh copy of the passing demo, so one exercise never affects another.
- Read the failure message before you fix anything. The point is to learn which gate catches which mistake.
- Never print a denylist term. Exercise 5.1 builds the demo seller string in code for that reason.

You pass a level when every exercise in it gives the expected output, both the failure and the fix.

## Level 0: setup

Run from the repo root after `pip install -e .` (see `docs/AI-OPERATOR-GUIDE.md` section 4). These helpers are used by every exercise. Paste them into a bash shell first:

```bash
SKILL=$(pwd)
LAB=${LAB:-/tmp/certpassly-lab}
mkdir -p "$LAB"
fresh() { rm -rf "$LAB/$1"; cp -a "$LAB/ms" "$LAB/$1"; W="$LAB/$1"; O="$W/out/DM-101"; }
R() { certpassly-pipeline --exam DM-101 --root "$W" --offline --date 2026-11-11 "$@"; }
```

Exercise 0.1: list the stages and run the tests.

```bash
certpassly-pipeline --list-stages
python -m unittest discover -s tests
```

Expected: 15 stage rows in this order: catalog, intake, sources, research, extract, textfix, answer_research, intent, author, pages, writing, import, bank, validate, package. Only `author` says `YES` in the AI column (`research` says `parser first`, `textfix` says `decide only`, `answer_research` says `pick only`). The tests end with `OK`.

## Level 1: run the demo end to end

Exercise 1.1: Microsoft-style demo.

```bash
python tests/demo_kit.py microsoft "$LAB/ms"
W="$LAB/ms"; R > "$W/full.log" 2>&1; echo "exit=$?"
grep -E "textfix:|writing DM-101|imported|Summary|package scan" "$W/full.log"
```

Expected:

```
exit=0
textfix: 0 proposals {}; 0 need an author decision; out/DM-101/text-fixes-proposals.json
writing DM-101: round 1, 0 flags
imported 6 held 0 researched 1 answer_not_found 1 flagged 4 {'single_choice': 2, 'multiple_select': 1, 'yes_no_matrix': 1, 'inline_dropdown': 1, 'active_screen': 1}
Summary: 429 passed, 0 failed, 429 total
package scan: 80 members, 75 text files scanned, 5 images skipped, 0 nested archives, 0 denylist hits
```

Then count the gates:

```bash
python -c "import json,sys; d=json.load(open(sys.argv[1])); print('ok', sum(c['passed'] for c in d), 'fail', sum(not c['passed'] for c in d))" "$LAB/ms/out/DM-101/validation.json"
```

Expected: `ok 64 fail 0`.

What to learn: `q006` had no key and was researched from an official page (`researched 1`); `q005` had no evidence and stays a draft (`answer_not_found 1`). Nothing is held. Open `out/DM-101/REVIEW.md` and find both.

Exercise 1.2: a second vendor (proves nothing is hardcoded).

```bash
python tests/demo_kit.py salesforce "$LAB/sf"
certpassly-pipeline --exam Demo-Admn-101 --root "$LAB/sf" --offline --date 2026-11-11 > "$LAB/sf/full.log" 2>&1; echo "exit=$?"
grep -E "imported|Summary|package scan" "$LAB/sf/full.log"
```

Expected: `exit=0`, the same `imported 6 held 0 researched 1 answer_not_found 1 flagged 4` line, `Summary: 429 passed, 0 failed, 429 total` and `0 denylist hits`.

## Level 2: writing gates

Exercise 2.1: banned AI phrase.

```bash
fresh e21
python - "$O" <<'PY'
import json, sys
p = sys.argv[1] + '/authoring/page_prose.json'; d = json.load(open(p, encoding='utf-8'))
d['exam_hub']['body_html'] = d['exam_hub']['body_html'].replace('<h2>What changed</h2><p>', '<h2>What changed</h2><p>Moreover, this exam is a game changer. ', 1)
json.dump(d, open(p, 'w', encoding='utf-8'), indent=1)
PY
R --stage pages --stage writing > "$W/r1.log" 2>&1; echo "exit=$?"
grep -E "writing DM-101|FLAG" "$W/r1.log"
python -c "import json,sys; print(sorted(json.load(open(sys.argv[1]))['parts']))" "$O/authoring/writing_fix_request.json"
```

Expected:

```
exit=1
writing DM-101: round 2, 2 flags
FLAG banned_ai_phrase exam_hub.body_html: banned AI phrase "game changer"
FLAG banned_ai_phrase exam_hub.body_html: banned AI phrase "moreover"
['page_prose:exam_hub']
```

Fix only the flagged part, then run the second check:

```bash
python - "$O" <<'PY'
import json, sys
p = sys.argv[1] + '/authoring/page_prose.json'; d = json.load(open(p, encoding='utf-8'))
d['exam_hub']['body_html'] = d['exam_hub']['body_html'].replace('Moreover, this exam is a game changer. ', '', 1)
json.dump(d, open(p, 'w', encoding='utf-8'), indent=1)
PY
R --stage pages --stage writing > "$W/r2.log" 2>&1; echo "exit=$?"
grep -E "writing DM-101" "$W/r2.log"
```

Expected: `exit=0` and `writing DM-101: round 3, 0 flags`.

Exercise 2.2: typographic dash. The script writes the dash with a Python escape so this doc stays dash free.

```bash
fresh e22
python - "$O" <<'PY'
import json, sys
p = sys.argv[1] + '/authoring/page_prose.json'; d = json.load(open(p, encoding='utf-8'))
d['faq']['body_html'] = d['faq']['body_html'].replace('These answers are short on purpose.', 'These answers are short \u2014 on purpose.', 1)
json.dump(d, open(p, 'w', encoding='utf-8'), indent=1)
PY
R --stage pages --stage writing > "$W/r1.log" 2>&1; echo "exit=$?"
grep -E "FLAG" "$W/r1.log"
```

Expected: `exit=1` and `FLAG typographic_dash faq.body_html: em dash or en dash; use a comma, a colon, a hyphen, or "to"`. Fix: replace the dash with a comma, rerun `--stage pages --stage writing`, expect 0 flags.

## Level 3: author files

Exercise 3.1: a missing explanation.

```bash
fresh e31
python - "$O" <<'PY'
import json, sys
p = sys.argv[1] + '/authoring/explanations_text.json'; d = json.load(open(p, encoding='utf-8')); d.pop('q001')
json.dump(d, open(p, 'w', encoding='utf-8'), indent=1)
PY
R --stage bank > "$W/r1.log" 2>&1; echo "exit=$?"
grep -E "author stage" "$W/r1.log"
```

Expected: `exit=1` and `author stage: no explanation for q001 in authoring/explanations_text.json or explanations_visual.json`. Fix: write the q001 entry back (one `c`, one `o` per option, `s`, `a`) and rerun `--stage bank`.

Exercise 3.2: a missing author file.

```bash
fresh e32
rm "$O/authoring/page_prose.json"
R --stage author > "$W/r1.log" 2>&1; echo "exit=$?"
grep -E "Files still needed|  - " "$W/r1.log"
```

Expected: `exit=1`, then `AUTHOR STAGE (the only AI stage). Files still needed:` and `  - page_prose.json`. Fix: write `page_prose.json` (guide section 7.3) and rerun `--stage author`; expect `author: required files present`.

## Level 4: types, keys and text fixes

Exercise 4.1: a DRAG DROP item typed as a drop-down.

```bash
fresh e41
python - "$O" <<'PY'
import json, sys
p = sys.argv[1] + '/extracted/split.json'; d = json.load(open(p, encoding='utf-8'))
d['q004']['stem'] = 'DRAG DROP - Match the schedule to the task. Select and Place:'
json.dump(d, open(p, 'w', encoding='utf-8'), indent=1)
PY
R --stage bank --stage validate > "$W/r1.log" 2>&1; echo "exit=$?"
grep -E "^FAIL" "$W/r1.log"
```

Expected:

```
exit=1
FAIL 12f source markers agree with assigned type (marker-agreement check) :: [('q004', ['DRAG DROP marker but type is inline_dropdown; transcribe tiles and targets as drag_drop'])]
```

Fix: transcribe the item as tiles and targets. The explanation shape (one list per target, one rationale per tile) already fits.

```bash
python - "$O" <<'PY'
import json, sys
p = sys.argv[1] + '/extracted/visual_transcription.json'; v = json.load(open(p, encoding='utf-8'))
v['q004'] = {'tiles': ['daily', 'weekly', 'monthly'], 'targets': ['Backups run'], 'key': [0]}
json.dump(v, open(p, 'w', encoding='utf-8'), indent=1)
PY
R --stage bank --stage validate > "$W/r2.log" 2>&1; echo "exit=$?"
grep -E "imported|12f" "$W/r2.log"
```

Expected: `exit=0`, the type counts now show `'drag_drop': 1`, and `ok   12f source markers agree with assigned type`.

Exercise 4.2: a lost ligature is fixed and logged.

```bash
fresh e42
python - "$O" <<'PY'
import json, sys
p = sys.argv[1] + '/extracted/split.json'; d = json.load(open(p, encoding='utf-8'))
d['q001']['stem'] = d['q001']['stem'].rstrip('?') + ' with unied settings?'
json.dump(d, open(p, 'w', encoding='utf-8'), indent=1)
PY
R --stage textfix --stage bank --stage validate > "$W/r1.log" 2>&1; echo "exit=$?"
grep -E "textfix:|12n" "$W/r1.log"
```

Expected: `exit=0`, `textfix: 1 proposals {'lost_ligature': 1}; 0 need an author decision`, and `ok   12n text fixes keep keys and option order ... 1 text fixes {'lost_ligature': 1}`. Open `out/DM-101/text-fixes.json`: the fix "unied" to "unified" is logged, and `key_identity.identical` is true. REVIEW.md shows the key identity line.

Exercise 4.3: a fix that touches a protected word is rejected.

```bash
fresh e43
python - "$O" <<'PY'
import json, sys
o = sys.argv[1]; s = json.load(open(o + '/extracted/split.json', encoding='utf-8'))
k, v = next(iter(s['q001']['options'].items()))
w = [t for t in v.split() if t[:1].isupper()][0]
fix = {'item': 'q001', 'field': 'option.' + k, 'before': w, 'after': w.lower(), 'kind': 'spelling', 'reason': 'exercise'}
json.dump({'decisions': {}, 'extra': [fix]}, open(o + '/authoring/text_fixes_decisions.json', 'w', encoding='utf-8'), indent=1)
PY
R --stage bank > "$W/r1.log" 2>&1; echo "exit=$?"
grep -E "text_fixes" "$W/r1.log"
```

Expected: `exit=1` and `text_fixes: author fixes rejected by the guard: [('q001', 'option.a', 'changes protected words: Secret')]`. The fix lowercased a capitalized product word. Fix: delete the `extra` entry and rerun `--stage bank`.

Exercise 4.4: a key or option order change is caught.

```bash
fresh e44
python - "$O" <<'PY'
import json, sys
p = sys.argv[1] + '/questions.json'; d = json.load(open(p, encoding='utf-8'))
q = d['questions'][0]; q['options'] = list(reversed(q['options']))
json.dump(d, open(p, 'w', encoding='utf-8'), indent=1)
PY
R --stage validate > "$W/r1.log" 2>&1; echo "exit=$?"
grep -E "^FAIL" "$W/r1.log"
```

Expected:

```
exit=1
FAIL 12n text fixes keep keys and option order (key letters + option ids + count per item, split.json vs questions.json) :: ['q001']
```

Fix: never edit `questions.json` by hand. Rebuild it with `R --stage bank --stage validate`; expect `exit=0`.

## Level 5: shipping safety

Exercise 5.1: a seller brand leaks into the package. The seller string is built in code (`tests/demo_kit.py` `SELLER`), never typed.

```bash
fresh e51
python -c "import sys; sys.path.insert(0, 'tests'); import demo_kit; print('Thanks ' + demo_kit.SELLER.replace(' ', ''))" >> "$O/REVIEW.md"
R --stage package > "$W/r1.log" 2>&1; echo "exit=$?"
grep -E "package scan|package removed" "$W/r1.log"
ls "$W/DM-101-package.zip"
```

Expected: `exit=1`, `package scan: ... 2 denylist hits`, log lines `DENYLIST HIT DM-101-package/DM-101/REVIEW.md: denylist term #0` and `#1` (the console line also shows the term; never copy it into a report), `package removed: it must not ship with denylist hits`, and `ls` reports that the zip does not exist. Fix: rebuild REVIEW.md from scripts with `R --stage bank`, then `R --stage package`; expect `0 denylist hits` and `package written`.

Exercise 5.2: offline without the link-check cache.

```bash
fresh e52
rm "$W/cache/linkcheck.json"
R --stage validate > "$W/r1.log" 2>&1; echo "exit=$?"
grep -E "^FAIL" "$W/r1.log"
```

Expected: `exit=1` and `FAIL 09c external links resolve (HTTP 200) :: offline; cached 0; missing [...]`. Fix: run validate once online to rebuild the cache, or restore the file from the passing copy: `cp "$LAB/ms/cache/linkcheck.json" "$W/cache/"`, then rerun; expect `exit=0`.

Exercise 5.3: a direct script call without the workspace set.

```bash
W="$LAB/ms"
CERTPASSLY_ROOT="$W" PYTHONUTF8=1 python scripts/validate.py "$W/research/microsoft/DM-101.json" --offline > "$LAB/direct.log" 2>&1; echo "exit=$?"
```

Expected: `exit=0`. Without `CERTPASSLY_ROOT` the script looks in the wrong folder and stops with `FileNotFoundError`. Lesson: prefer `certpassly-pipeline --stage validate`, which sets the root and UTF-8 mode for you.

## Level 6: report

Exercise 6.1: fill the report template from `docs/AI-OPERATOR-GUIDE.md` section 13 for the Level 1 demo run. Use real values: `git rev-parse HEAD`, the exit codes, the bank line, `ok 64 fail 0`, the check_bank summary, and the package size and sha256:

```bash
ls -l "$LAB/ms/DM-101-package.zip"
sha256sum "$LAB/ms/DM-101-package.zip"
```

Then tick every line of section 12. You are trained when you can do Levels 0 to 6 without reading the expected outputs first.
