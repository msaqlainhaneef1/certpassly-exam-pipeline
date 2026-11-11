#!/usr/bin/env python3
"""Structural checks for an owner-question-file-importer package.

Fails the process on any problem. This script does not claim SME accuracy,
rights review, or publish-gate approval.

Usage:
  python3 check_bank.py /path/to/out/<exam-key>
  python3 check_bank.py /path/to/out/<exam-key> --registry /path/to/question_types.json
  (JSON from this skill's reference/site-format/<version>/question_types.json, or a legacy .php snapshot.)
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

EN_DASH = "\u2013"
EM_DASH = "\u2014"

def as_json(obj):
    return json.JSONEncoder(ensure_ascii=False).encode(obj)

FORBIDDEN_STATUS = re.compile(
    r"\b(verified|approved|published|active|gate[_ ]?passed|reviewed)\b",
    re.I,
)
ALLOWED_STATUS = {"draft", "not_checked", "unverified", "", "no", "yes", "true", "false"}
USES_OPTIONS = {
    "single_choice",
    "multiple_select",
    "true_false",
    "image_based_choice",
}
DEFAULT_TYPES = [
    "single_choice",
    "multiple_select",
    "true_false",
    "image_based_choice",
    "scenario_standalone",
    "yes_no_matrix",
    "single_choice_matrix",
    "multi_select_matrix",
    "inline_dropdown",
    "multi_blank_dropdown",
    "text_cloze",
    "ordering",
    "matching",
    "categorization",
    "drag_drop",
    "hotspot_single",
    "hotspot_multi",
    "case_study_group",
    "active_screen",
    "short_text",
    "numeric",
    "multimedia_stimulus",
    "sectioned_delivery",
    "unscored_pretest",
    "adaptive_delivery",
    "simulation_ui",
    "terminal_task",
    "lab_task",
    "code_answer",
    "testlet",
]
DEFAULT_ALIASES = {
    "multiple_choice": "multiple_select",
    "multi_select": "multiple_select",
    "image_question": "image_based_choice",
    "hotspot": "hotspot_single",
    "drag_and_drop": "drag_drop",
    "case_study": "case_study_group",
    "scenario": "scenario_standalone",
    "matrix_single": "single_choice_matrix",
    "matrix_yes_no": "yes_no_matrix",
    "yes_no": "true_false",
}
HOTSPOT_TYPES = {"hotspot_single", "hotspot_multi", "active_screen"}
VISUAL_HINT_TYPES = HOTSPOT_TYPES | {
    "image_based_choice",
    "multimedia_stimulus",
    "simulation_ui",
    "drag_drop",
}
STATUS_FIELDS = {
    "status",
    "publication_state",
    "structural_gate",
    "review_gate",
    "license_status",
    "rights_status",
    "rights_reviewed",
}
REQUIRED_QUESTION_FIELDS = (
    "question_key",
    "question_version_key",
    "question_type",
    "prompt_text",
    "domain_key",
    "topic_key",
    "answer_key",
    "publication_state",
)


def rec(results, name, passed, detail=""):
    results.append({"name": name, "passed": bool(passed), "detail": detail if detail is not None else ""})


def load_json(path: Path):
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def questions_from(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("questions", "items"):
            if isinstance(data.get(key), list):
                return data[key]
    raise SystemExit("questions.json must be a list or an object with a questions array")


def canonicalize(raw, aliases, known):
    key = (raw or "").strip()
    key = aliases.get(key, key)
    return key, key in known


def ws_norm(value):
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n+", " ", text)
    return text.strip()


def flatten_frozen(entry):
    """Map field name -> text from extracted/stems.json or an imported question."""
    out = {}
    if not isinstance(entry, dict):
        return out
    if entry.get("stem") is not None:
        out["stem"] = entry.get("stem")
    elif entry.get("prompt_text") is not None:
        out["stem"] = entry.get("prompt_text")
    options = entry.get("options")
    if isinstance(options, dict):
        for key, val in options.items():
            if isinstance(val, dict):
                out[f"option.{key}"] = val.get("text") or val.get("option_text") or ""
            else:
                out[f"option.{key}"] = val
    elif isinstance(options, list):
        for val in options:
            if not isinstance(val, dict):
                continue
            key = val.get("id") or val.get("option_id") or val.get("option_letter") or val.get("option_key")
            out[f"option.{key}"] = val.get("text") or val.get("option_text") or ""
    other = entry.get("other_frozen_text")
    if isinstance(other, dict):
        for key, val in other.items():
            out[f"other.{key}"] = val
    return out


def frozen_from_question(question):
    entry = {
        "stem": question.get("prompt_text") or "",
        "options": question.get("options") or [],
        "other_frozen_text": {},
    }
    schema = question.get("response_schema") or {}
    content = schema.get("content") if isinstance(schema, dict) else {}
    if not isinstance(content, dict):
        content = {}
    # Schema options may exist even when options[] is empty.
    if not entry["options"] and isinstance(content.get("options"), list):
        entry["options"] = content.get("options")
    for group, prefix in (
        ("rows", "row"),
        ("columns", "column"),
        ("items", "item"),
        ("left", "left"),
        ("right", "right"),
        ("bins", "bin"),
        ("regions", "region"),
    ):
        for item in content.get(group) or []:
            if isinstance(item, dict) and item.get("text") is not None:
                entry["other_frozen_text"][f"{prefix}.{item.get('id', '')}"] = item.get("text")
            elif isinstance(item, dict) and item.get("label") is not None:
                entry["other_frozen_text"][f"{prefix}.{item.get('id', '')}"] = item.get("label")
    for blank in content.get("blanks") or []:
        if not isinstance(blank, dict):
            continue
        for choice in blank.get("choices") or []:
            if isinstance(choice, dict):
                entry["other_frozen_text"][f"blank.{blank.get('id')}.{choice.get('id')}"] = choice.get("text")
    # Child item stems and options
    for child in content.get("child_items") or []:
        if not isinstance(child, dict):
            continue
        cid = child.get("id") or ""
        if child.get("prompt_text"):
            entry["other_frozen_text"][f"child.{cid}.stem"] = child.get("prompt_text")
        for opt in child.get("options") or []:
            if isinstance(opt, dict):
                entry["other_frozen_text"][f"child.{cid}.option.{opt.get('id')}"] = opt.get("text")
    return flatten_frozen(entry)


def texts_of_question(question):
    blobs = [as_json(question)]
    return blobs


def has_typographic_dash(text):
    return EN_DASH in text or EM_DASH in text


def parse_registry(reg_path: Path | None):
    aliases = dict(DEFAULT_ALIASES)
    known = set(DEFAULT_TYPES)
    if not reg_path:
        return known, aliases
    text = reg_path.read_text(encoding="utf-8", errors="replace")
    if reg_path.suffix.lower() == ".json" or text.lstrip().startswith("{"):
        data = json.loads(text)
        types = data.get("types", data)
        if isinstance(types, dict):
            known = set(types)
        elif isinstance(types, list):
            known = set(types)
        aliases.update(data.get("aliases") or {})
        return known, aliases
    alias_block = re.search(r"'aliases'\s*=>\s*\[(.*?)\],", text, re.S)
    if alias_block:
        for src, dst in re.findall(r"'([^']+)'\s*=>\s*'([^']+)'", alias_block.group(1)):
            aliases[src] = dst
    type_block = re.search(r"'types'\s*=>\s*\[", text)
    if type_block:
        for name in re.findall(r"\n\s*'([a-z0-9_]+)'\s*=>\s*\[", text[type_block.start():]):
            known.add(name)
    return known, aliases


def sha256_file(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_csv(path: Path):
    if not path.is_file():
        return [], []
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        return reader.fieldnames or [], rows


def explanation_count(question):
    expl = question.get("explanations")
    if isinstance(expl, dict):
        return len([v for v in expl.values() if str(v).strip()])
    if isinstance(expl, list):
        return len(expl)
    if question.get("core_explanation"):
        return 1
    return 0


def option_ids(question):
    ids = []
    for opt in question.get("options") or []:
        if isinstance(opt, dict):
            ids.append(str(opt.get("option_id") or opt.get("id") or opt.get("option_letter") or "").lower())
    schema = (question.get("response_schema") or {}).get("content") or {}
    if not ids and isinstance(schema, dict):
        for opt in schema.get("options") or []:
            if isinstance(opt, dict):
                ids.append(str(opt.get("id") or "").lower())
    return [i for i in ids if i]


def answer_present(question):
    key = question.get("answer_key")
    if not key:
        return False
    if isinstance(key, dict):
        return any(
            key.get(name)
            for name in (
                "correct_option_ids",
                "rows",
                "slots",
                "accepted",
                "text",
                "order",
                "pairs",
                "zones",
                "region_ids",
                "value",
                "expected_actions",
                "child_items",
            )
        )
    return True


def media_info(question):
    media = question.get("media") or {}
    schema = (question.get("response_schema") or {}).get("content") or {}
    path = None
    alt = ""
    if isinstance(media, dict):
        path = media.get("path") or media.get("image_url")
        alt = media.get("alt") or media.get("alt_text") or media.get("image_alt") or ""
    if not path and isinstance(schema, dict):
        path = schema.get("image_url")
        alt = schema.get("image_alt") or alt
    return path, alt, schema


def regions_ok(content):
    regions = (content or {}).get("regions") or []
    if not regions:
        return False, "no regions"
    for region in regions:
        if not str(region.get("label") or "").strip():
            return False, f"missing label on {region.get('id')}"
        coords = region.get("normalized_coordinates")
        rect = region.get("rect") or {}
        if not (isinstance(coords, list) and len(coords) == 4):
            return False, f"bad coordinates on {region.get('id')}"
        nums = list(coords)
        if all(k in rect for k in ("x", "y", "w", "h")):
            nums = [rect["x"], rect["y"], rect["w"], rect["h"]]
        try:
            x, y, w, h = [float(n) for n in nums]
        except (TypeError, ValueError):
            return False, f"non-numeric coordinates on {region.get('id')}"
        if min(x, y, w, h) < 0 or x > 1 or y > 1 or x + w > 1.0001 or y + h > 1.0001 or w == 0 or h == 0:
            return False, f"out of bounds on {region.get('id')}"
    return True, f"{len(regions)} regions"


def check_status_value(results, label, value):
    text = "" if value is None else str(value).strip()
    if text.lower() in ALLOWED_STATUS or text == "":
        if FORBIDDEN_STATUS.search(text) and text.lower() not in {"draft", "not_checked", "unverified"}:
            rec(results, label, False, text)
            return
        rec(results, label, True, text or "empty")
        return
    if FORBIDDEN_STATUS.search(text):
        rec(results, label, False, text)
        return
    # Other free text (notes, reasons) is fine unless it asserts a forbidden flag as a status.
    rec(results, label, True, text[:80])


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate a draft owner question import package.")
    parser.add_argument("bank_dir", type=Path, help="Package directory that contains questions.json")
    parser.add_argument("--registry", type=Path, default=None, help="Optional path to question_types.json (bundled site-format) or a legacy .php snapshot")
    args = parser.parse_args(argv)

    root = args.bank_dir.resolve()
    results = []
    rec(results, "bank_dir_exists", root.is_dir(), str(root))
    qpath = root / "questions.json"
    rec(results, "questions_json_exists", qpath.is_file(), str(qpath))
    if not qpath.is_file():
        print_report(results)
        return 1

    data = load_json(qpath)
    questions = questions_from(data)
    rec(results, "questions_present", len(questions) > 0, str(len(questions)))

    package_status = data.get("status") if isinstance(data, dict) else None
    rec(results, "package_status_draft", package_status in (None, "draft"), str(package_status))

    known, aliases = parse_registry(args.registry)

    stems_path = root / "extracted" / "stems.json"
    stems = {}
    if stems_path.is_file():
        loaded = load_json(stems_path)
        stems = loaded.get("questions", loaded) if isinstance(loaded, dict) else {}
        rec(results, "extracted_stems_json_exists", True, str(stems_path))
    else:
        rec(results, "extracted_stems_json_exists", False, "required for the exact-text check")

    # Import CSVs if present
    import_dir = root / "import"
    csv_specs = {
        "questions.csv": [
            "question_key",
            "exam_key",
            "exam_version_key",
            "domain_key",
            "topic_key",
            "question_type",
            "question_version_key",
            "prompt_text",
            "publication_state",
        ],
        "answer_options.csv": [
            "option_key",
            "question_version_key",
            "option_text",
            "is_correct",
            "rationale_text",
            "status",
        ],
        "explanations.csv": [
            "question_version_key",
            "core_explanation",
            "status",
        ],
        "question_sources.csv": [
            "question_version_key",
            "source_url",
            "status",
        ],
        "sources.csv": ["evidence_key", "source_url", "status"],
        "domains.csv": ["domain_key", "exam_version_key", "domain_name", "status"],
        "topics.csv": ["topic_key", "domain_key", "topic_name", "status"],
    }
    csv_rows = {}
    if import_dir.is_dir():
        rec(results, "import_dir_exists", True, str(import_dir))
        for name, required_cols in csv_specs.items():
            path = import_dir / name
            if not path.is_file():
                rec(results, f"import_{name}_exists", False, str(path))
                continue
            rec(results, f"import_{name}_exists", True, str(path))
            fields, rows = load_csv(path)
            csv_rows[name] = rows
            missing = [c for c in required_cols if c not in fields]
            rec(results, f"import_{name}_columns", not missing, ",".join(missing) or "ok")
            for i, row in enumerate(rows, start=2):
                for field in STATUS_FIELDS:
                    if field in row:
                        check_status_value(results, f"{name}:{i}:{field}", row.get(field))
    else:
        rec(results, "import_dir_exists", False, "import/ is part of the expected package")

    for question in questions:
        key = question.get("question_key") or question.get("question_version_key") or "unknown"
        for field in REQUIRED_QUESTION_FIELDS:
            if field == "answer_key" and question.get("answer_key_status") == "answer_not_found":
                continue  # no key by design; covered by the answer_not_found check below
            rec(results, f"{key}_has_{field}", bool(str(question.get(field) or "").strip() or question.get(field) == 0), field)
        raw_type = question.get("question_type") or question.get("type") or ""
        typ, known_type = canonicalize(raw_type, aliases, known)
        rec(results, f"{key}_known_type", known_type, typ or raw_type)
        if question.get("answer_key_status") == "answer_not_found":
            # owner rule v1.1.0: kept as a draft, never scored; no key is expected
            rec(results, f"{key}_answer_not_found_excluded", question.get("scoring_excluded") is True, "scoring_excluded")
        else:
            rec(results, f"{key}_has_answer", answer_present(question), "answer_key")
        n_expl = explanation_count(question)
        rec(results, f"{key}_has_explanations", n_expl >= 1, f"{n_expl} explanations")
        source = question.get("source_url") or ""
        if not source:
            sources = question.get("sources") or question.get("question_sources") or []
            if isinstance(sources, list) and sources:
                source = (sources[0] or {}).get("source_url") if isinstance(sources[0], dict) else str(sources[0])
        rec(results, f"{key}_has_source", bool(str(source).strip()), source or "missing")
        try:
            import vendor_reg
            retired=list(vendor_reg.retired_official_hosts() or [])
        except Exception:
            retired=[]
        if source and any(h and h in str(source) for h in retired):
            rec(results, f"{key}_source_host_current", False, "update a retired official host to the current official host")
        rec(results, f"{key}_has_skill_tag", bool(question.get("domain_key") and question.get("topic_key")), f"{question.get('domain_key')} / {question.get('topic_key')}")
        pub = str(question.get("publication_state") or question.get("status") or "")
        rec(results, f"{key}_draft_status", pub == "draft", pub)
        for field in STATUS_FIELDS:
            if field in question:
                check_status_value(results, f"{key}_{field}", question.get(field))

        if typ in USES_OPTIONS or option_ids(question):
            ids = option_ids(question)
            rec(results, f"{key}_min_two_options", len(ids) >= 2, str(len(ids)))
            if typ == "true_false":
                rec(results, f"{key}_true_false_shape", len(ids) == 2, str(len(ids)))
            expl = question.get("explanations")
            if isinstance(expl, dict):
                missing = [i for i in ids if i and i not in {str(k).lower() for k in expl.keys()}]
                # also accept letter keys
                rec(results, f"{key}_per_option_explanations", not missing, ",".join(missing) or "ok")
            elif typ in USES_OPTIONS:
                rec(results, f"{key}_per_option_explanations", n_expl >= len(ids), f"{n_expl} for {len(ids)} options")

        path, alt, content = media_info(question)
        needs_media = typ in VISUAL_HINT_TYPES or bool(path) or typ in HOTSPOT_TYPES
        if needs_media and typ not in {"drag_drop"} or path:
            if typ in HOTSPOT_TYPES or typ in {"image_based_choice", "multimedia_stimulus", "simulation_ui"} or path:
                rec(results, f"{key}_media_present", bool(path), path or "missing")
                rec(results, f"{key}_media_alt", bool(str(alt).strip()), (alt or "")[:80])
                if path:
                    media_path = root / path if not Path(path).is_absolute() else Path(path)
                    if not media_path.is_file():
                        media_path = root / "media" / Path(path).name
                    rec(results, f"{key}_media_exists", media_path.is_file(), str(media_path))
        if typ in HOTSPOT_TYPES and question.get("answer_key_status") != "answer_not_found":
            ok, detail = regions_ok(content)
            rec(results, f"{key}_regions_ok", ok, detail)
            region_ids = [r.get("id") for r in (content.get("regions") or []) if isinstance(r, dict)]
            key_ids = (question.get("answer_key") or {}).get("region_ids") or []
            rec(results, f"{key}_answer_regions_mapped", bool(key_ids) and all(i in region_ids for i in key_ids), str(key_ids))
            rec(
                results,
                f"{key}_human_review_flag_recommended",
                True if question.get("human_review_required") in (True, "yes", "true", 1, "1") else True,
                "visual items should be listed in REVIEW.md; flag missing only when answer came from an image and the flag is absent",
            )
            if typ in HOTSPOT_TYPES and question.get("human_review_required") not in (True, "yes", "true", 1, "1"):
                # Soft: still pass, but if the key is only from an image the skill wants the flag.
                if (question.get("created_source") or "").find("answer-review") >= 0 or question.get("answer_from_image"):
                    rec(results, f"{key}_human_review_required", False, "image-derived key needs human_review_required")

        # Exact text check
        extracted = stems.get(key) or stems.get(question.get("question_version_key")) if isinstance(stems, dict) else None
        if stems:
            rec(results, f"{key}_extracted_stem_present", isinstance(extracted, dict), "missing from extracted/stems.json" if not extracted else "ok")
            if isinstance(extracted, dict):
                imported = frozen_from_question(question)
                extracted_flat = flatten_frozen(extracted)
                # Stem and options must match. Other frozen text matches when present on both sides.
                compare_keys = set(extracted_flat) | {k for k in imported if k == "stem" or k.startswith("option.")}
                for field in sorted(compare_keys):
                    left = ws_norm(imported.get(field, ""))
                    right = ws_norm(extracted_flat.get(field, ""))
                    rec(
                        results,
                        f"{key}_exact_text_{field}",
                        left == right and left != "",
                        "mismatch" if left != right else "match",
                    )

        expl = question.get("explanations")
        prose_bits = [
            question.get("core_explanation"),
            as_json(expl) if expl is not None else "",
            (question.get("media") or {}).get("alt") if isinstance(question.get("media"), dict) else "",
            ((question.get("response_schema") or {}).get("content") or {}).get("image_alt"),
        ]
        for opt in question.get("options") or []:
            if isinstance(opt, dict):
                prose_bits.append(opt.get("rationale_text"))
        prose_blob = "\n".join("" if b is None else str(b) for b in prose_bits)
        rec(results, f"{key}_no_em_or_en_dashes_in_prose", not has_typographic_dash(prose_blob), "dash found in explanation or alt text" if has_typographic_dash(prose_blob) else "clean")

    # Package-wide dash scan of new prose only (reports, explanations, alt text).
    # Owner stems and options may keep typographic dashes if they were in the source file.
    dash_hits = []
    prose_names = {
        "VALIDATION.md",
        "HOW-IT-WAS-DONE.md",
        "REVIEW.md",
        "CLEANUP-LOG.md",
        "QUESTIONS.md",
    }
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".md", ".csv", ".txt"}:
            continue
        if "__pycache__" in path.parts or "extracted" in path.parts:
            continue
        rel = path.relative_to(root)
        if path.suffix.lower() == ".md" or path.name in prose_names or "explanation" in path.name:
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if has_typographic_dash(text):
                dash_hits.append(str(rel))
        if path.name in {"explanations.csv", "answer_options.csv"}:
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            # answer_options: flag dashes only in rationale_text, not option_text
            if path.name == "answer_options.csv":
                fields, rows = load_csv(path)
                for i, row in enumerate(rows, start=2):
                    if has_typographic_dash(row.get("rationale_text") or ""):
                        dash_hits.append(f"{rel}:rationale:{i}")
            elif has_typographic_dash(text):
                dash_hits.append(str(rel))
    rec(results, "no_em_or_en_dashes_in_new_prose", not dash_hits, ",".join(dash_hits) or "clean")

    manifest = import_dir / "MANIFEST.json"
    if not manifest.is_file():
        manifest = root / "MANIFEST.json"
    if manifest.is_file():
        rec(results, "manifest_exists", True, str(manifest))
        try:
            man = load_json(manifest)
        except json.JSONDecodeError as exc:
            rec(results, "manifest_valid_json", False, str(exc))
            man = {}
        else:
            rec(results, "manifest_valid_json", True, "ok")
        rec(results, "manifest_status_draft", man.get("status") in (None, "draft"), str(man.get("status")))
        files = man.get("files") or []
        for item in files:
            rel = item.get("file") or item.get("path")
            expected = (item.get("sha256") or "").lower()
            if not rel:
                rec(results, "manifest_entry_has_path", False, as_json(item)[:80])
                continue
            path = root / rel
            rec(results, f"manifest_{rel}_exists", path.is_file(), str(path))
            if path.is_file() and expected:
                actual = sha256_file(path)
                rec(results, f"manifest_{rel}_sha256", actual == expected, "mismatch" if actual != expected else "ok")
    else:
        rec(results, "manifest_exists", False, "import/MANIFEST.json or MANIFEST.json is required")

    return print_report(results)


def print_report(results):
    passed = [r for r in results if r["passed"]]
    failed = [r for r in results if not r["passed"]]
    for row in results:
        flag = "PASS" if row["passed"] else "FAIL"
        detail = f" ({row['detail']})" if row["detail"] else ""
        print(f"{flag}: {row['name']}{detail}")
    print("")
    print(f"Summary: {len(passed)} passed, {len(failed)} failed, {len(results)} total")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
