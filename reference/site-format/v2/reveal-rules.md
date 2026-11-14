# Reveal rules (question format v2)

These rules are part of the v2 contract. They apply to any importer, API, or client that uses this format. Do not put reveal policy in hard-coded per-exam branches. Use this file and the schema as the source of truth (owner rule 21).

## Learner payload versus answer block

The author and import document has three top-level blocks:

- `learner`: stem, media, interaction config, and authored constraints. This is the only block a candidate may receive before an authorized reveal.
- `answer`: `answer_key`, `explanation`, and `partial_credit`. Never copy this block into a learner payload, a service-worker cache, or an offline store.
- `meta`: status, sources, and scoring flags. Meta may be trimmed for the learner (do not send research quotes or reviewer notes that the candidate should not see).

`QuestionCandidateSerializer` / `public_view` is the site shape that should carry the learner block only. A re-import updates the record by `question_key` plus integer `version`. It must not create a duplicate key.

Partial credit lives in `answer.partial_credit` (mode and points). It is defined per type in `question.schema.json`. It is not defined in scoring code. Session totals should use points when a mode other than `all_or_nothing` is set.

## Practice mode and exam mode

- Practice mode may reveal the answer and explanation after the learner submits that question, and only if `canRevealAnswerKeys()` is true and the access-policy mode allows it.
- Exam (simulator) mode reveals answers only after the attempt is submitted or times out, on the sealed results page. Mid-exam evaluate calls must not return keys, explanations, or `correct_option_ids`.
- Instant feedback is a practice-only behavior. It is not an exam behavior.

## Offline and service-worker caching (owner rule 143)

Offline support and the service worker must never store answers, explanations, or any answer-key field.

Store only a candidate-safe learner payload (the public view), if you store anything at all. Grade on the server when the client is back online. Never grade from a client-held key. Do not precache attempt payloads.

The current site service worker already lists `/api`, `/practice/`, `/exam/`, `/simulator`, `/student`, `/app`, and `/storage/` in `NEVER_CACHE_PREFIXES`. Keep that rule when HTML and SVG stems are added.

## Free trial (owner rule 216)

The owner rule is: 1 week, 10 questions, and 2 simulator uses.

The site worktree reviewed on 14 Nov 2026 still used a code default of 3 free questions (`EntitlementService::FREE_PREVIEW_QUESTIONS_LIMIT`), overridable by platform settings, and no complete enforcement of the 1-week and 2-use caps was found. Configure and enforce rule 216 in the site before HTML or SVG items go to trial users. This format does not encode those caps in the question JSON (they are entitlement rules, not per-question fields).

## No hardcoding (owner rule 21)

- The type enum comes from `config/question_types.php`, parsed into `question_types.json`. Do not hand-edit a second list of types.
- `max_choices` / `choose_n` must be authored in `learner.constraints` or `learner.interaction`. Never derive them from the count of correct options.
- Reveal behavior is this file plus `canRevealAnswerKeys()` and attempt mode. Do not special-case an exam code.

## Three known site security bugs, and how v2 stays compatible

These bugs were found in a read-only review of worktree `wt-merge-1114-fixes2`. This skill does not change site code. The format stays compatible by refusing to rely on the buggy behavior.

1. **`max_choices` leaks before answering.** In `SchemaDrivenHandler.php` (around line 238), `max_choices` for `multiple_select` is set from `$version->options->where('is_correct', true)->count()`. A learner who can read the public schema can learn how many options are keyed before they answer. v2 fix: author `choose_n` / `max_choices` explicitly. The schema forbids deriving that number from the answer block. Importers must not compute it from `answer.answer_key`. If the stem does not say "choose N", omit the field.

2. **`POST /api/questions/{id}/evaluate` can return keys without checking attempt mode.** `PracticeSessionService::evaluateTypedResponse` and the typed API evaluate path can return `correct_option_ids` and explanations. The path is not fully gated on practice-versus-exam attempt mode or on `canRevealAnswerKeys()`. v2 fix: the evaluate response is not the author document. Never send the `answer` block unless reveal is authorized. Exam attempts wait until submit. Clients that implement v2 must ignore any unexpected key fields and must not store them.

3. **`filterExplanationPayload` does not strip `correct_option_ids`.** `ContentAccessPolicyService::filterExplanationPayload` withholds explanation text in `locked` / `truncated` / `sample_only` modes, but it does not remove `correct_option_ids` or other typed answer maps. v2 fix: treat `correct_option_ids`, `answer_key`, pair maps, slot keys, and region ids as answer fields. They belong only in the `answer` block. A filter that hides explanations must also drop those fields. The schema keeps them out of `learner`.

Until the site fixes these three bugs, keep scoring on the server, keep keys out of `public_view`, and do not ship v2 HTML/SVG items to production.

## Compatibility notes

- Existing `public_view` fields (`question_type`, `schema_version`, `stimulus`, `response_schema`, `renderer`) can be filled from the v2 `learner` block plus the type registry.
- Encrypted `question_answer_keys` on the server remains the store for `answer.answer_key`.
- Draft-only `meta.record_status` stays `draft`. This pipeline never sets verified, reviewed, approved, published, or active flags.
