# Writing brief

Every page and every explanation follows this brief. That covers the author stage (one batched AI pass) and any human writer. The brief is written in the same style it asks for.

## Plain English

- Write plain, friendly English.
- Keep sentences short. Put one idea in each sentence.
- Aim for a reading grade of 8 to 9. The gate fails above grade 11.
- Use no jargon unless the official vendor page uses that term. Then explain it in plain words the first time.
- Use no typographic dashes. No em dash and no en dash. Use a comma, a colon, a hyphen, or the word "to".
- Use the official product name, exam code and credential title exactly as the vendor writes them.

## Write for people first

We follow Google's guidance on helpful, reliable, people-first content. In short:

- Write for the person who searched, not for a search engine.
- Answer what they came to learn. A reader should leave with the answer and the next step.
- Show first-hand use of the official pages. Quote them, link them, and show the date we checked them.
- Be original. Do not copy other sites. Do not rewrite another site's outline or explanations.
- Do not write a page just to rank. Do not stuff keywords. Use the exam code where it reads naturally.
- Be honest about gaps. If the vendor does not publish a fact, say so. Never guess a number.

## Inputs you get

- The research file `research/<vendor>/<CODE>.json`: every official fact, with a source id, a saved page and a quote.
- The search-intent file `research/<vendor>/<CODE>.search-intent.json`: the main query for each page and the questions people ask, with the page that must answer each one. A script builds it from research facts. A person can edit it.
- Competitor notes `research/<vendor>/<CODE>.competitor-notes.json`, when the CertPassly Researcher supplies them. Use them as topics only. Never copy a sentence, a title, an outline or an explanation from them. Cover a topic only when a saved official page supports it. If it does not, skip the topic or say the vendor did not publish it.

## Banned AI phrases

The full list is data in `config/banned_ai_phrases.txt`. The writing check loads it. A workspace can add more lines in its own `config/banned_ai_phrases.txt`. Add a line when a run finds a new stock phrase.

The list is about wording, not about official vendor terms. Official product names, exam codes and quoted vendor sentences are allowed, even when they sound formal. A vendor quote is exempt only when it is found word for word on a saved official page. Do not rewrite a verbatim quote to dodge the list.

Bad and good examples:

1. Bad: "In today's digital world, data is more important than ever."
   Good: "This exam tests how you use Data 360 at work. The official guide lists the skills below."
2. Bad: "Unlock your potential and take your career to the next level."
   Good: "The credential is earned by passing the official exam. The vendor states the requirements on the page we saved."
3. Bad: "This comprehensive guide will delve into everything you need to know."
   Good: "This page covers the official exam facts, the skill outline, and a study plan. Every figure has a source link and a checked date."
4. Bad: "Whether you are a beginner or an expert, this is for you."
   Good: "The official page lists the experience the vendor expects. We quote that wording and do not add our own levels."
5. Bad: "Leverage a robust, seamless, cutting-edge solution to empower your team."
   Good: "Use the official product name and say what the task is, in the same words the vendor uses where you can."
6. Bad: "It is important to note that..." or "Moreover..." or "Furthermore..." or "Additionally, it should be noted..."
   Good: Just state the fact. "The official passing score is 70 percent."
7. Bad: "Dive in" or "Let's dive in" or "Let's get started on this journey."
   Good: "Here is the official outline." or "Start with domain 1."
8. Bad: "The landscape of certification is constantly evolving."
   Good: "The vendor can change the exam. We re-check the official page and show the date we checked."
9. Bad: "In conclusion, ..." as a filler wrap-up.
   Good: Close with the official next step, or with what the reader should do. For example: book the exam only from the vendor, and keep proof of the official result.
10. Bad: "Unlock the power of..." or "This game-changer..." or "Holistic approach."
    Good: Name the concrete skill or task from the outline.

## The check, then fix only what is flagged

1. After the pages stage, the `writing` stage runs `scripts/check_writing.py`. The existing gates still run in `validate`.
2. The writing check looks for banned AI phrases, long sentences, typographic dashes, numbers that are not in the research files, thin pages, a high reading grade, search-intent questions that a page does not answer, and wording copied from competitor notes.
3. It writes `out/<CODE>/writing-review.json` and a short `out/<CODE>/WRITING-REVIEW.md`. Both list only the checks that failed. A clean run writes zero flags.
4. It also writes `out/<CODE>/authoring/writing_fix_request.json`. That file lists only the flagged parts. Fix those parts and nothing else. Do not rewrite a page or an explanation that already passed. The next check flags any unflagged part that changed.
5. Rerun `--stage pages --stage writing`. A second check must run after every fix. With `writing.validate_gate: true` in `pipeline.yaml`, validate fails unless the latest writing check ran on the current files and found zero flags.
6. Unresolved flags stay in `REVIEW.md`. Never mark a record published or verified to clear a flag.

## Self-check before a batch is done

Before an authoring batch is accepted, the writer confirms each line. The script ticks what it can and writes the result to `out/<CODE>/writing-self-check.json`. Lines it cannot tick stay with the writer.

1. Every official number and name matches the research file and a saved page quote. (Script: numbers in prose must appear in the research files. Validate check 02 covers quotes.)
2. Short sentences, plain words, no typographic dashes. (Script.)
3. No phrase from the banned AI list, unless it is inside a vendor quote. (Script.)
4. Each page answers the search-intent questions assigned to it. (Script.)
5. Competitor notes were used as topics only. No copied wording. (Script.)
6. No invented key, no invented fact, no invented question. (Writer. Bank and validate gates keep stems, options and keys as they are in the source.)
7. Grade and word-count gates still pass. (Script.)
