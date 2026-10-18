"""Turns the model's JSON answers for the disagreement map and the verdict into validated records.

The model proposes; this code decides what is kept. Claim ids must exist, perspectives must be real, statuses are
computed here, and limits that the evidence imposes (no sources, missing perspectives) are applied by code so the
moderator cannot talk its way past them."""
import json  # parses JSON text
import re  # regular expressions (pattern matching on text)
from collections.abc import Callable  # type for "a function we can call"

from .schemas import CRITERIA, PERSONAS, clip  # the criteria names, the five analysts, and the text trimmer

# Reply shapes: group name -> id prefix. Items in the first three groups need claims from two or more analysts.
GROUPS = {"agreements": "A", "interpretations": "I", "conflicts": "C", "unresolved": "U", "evidence_needed": "E"}
NEEDS_TWO_PERSPECTIVES = ("agreements", "interpretations", "conflicts")
MAX_ITEMS_PER_GROUP = 4

# Keys whose values are text shown to readers (screened by the content filter), and keys holding lists of text.
TEXT_KEYS = {
    "position_summary", "strongest_argument", "counterargument", "text", "summary", "central_question", "argument",
    "evidence_supports", "strongest_counterargument", "conflicting_or_insufficient_evidence", "reasoning",
    "conclusion", "assessment",
}
LIST_KEYS = {"assumptions", "uncertainties", "unresolved_questions", "could_change_conclusion"}


# Pulls the first JSON object out of a model reply (it may wrap it in words or a code fence). None if there is none.
def extract_json(raw: str) -> dict | None:
    match = re.search(r"\{.*\}", raw or "", re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


# Calls visit(text) for every reader-facing text in a record, in a fixed order, replacing each with its result.
def walk_texts(node: object, visit: Callable[[str], str]) -> None:
    """Used twice: first to collect the texts for the content filter, then to put the filtered texts back."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in TEXT_KEYS and isinstance(value, str):
                node[key] = visit(value)
            elif key in LIST_KEYS and isinstance(value, list):
                node[key] = [visit(item) if isinstance(item, str) else item for item in value]
            else:
                walk_texts(value, visit)
    elif isinstance(node, list):
        for item in node:
            walk_texts(item, visit)


# Validates the disagreement map. claim_persona maps every real claim id to the analyst who wrote it.
def build_map(data: dict, claim_persona: dict[str, str]) -> dict:
    """Keeps only items that point at real claims; agreements/interpretations/conflicts must span 2+ analysts."""
    result: dict = {"central_question": clip(data.get("central_question"), 300)}
    for group, prefix in GROUPS.items():
        items: list[dict] = []
        raw = data.get(group)
        for entry in raw if isinstance(raw, list) else []:
            if not isinstance(entry, dict):
                continue
            summary = clip(entry.get("summary"), 300)
            ids: list[str] = []
            listed = entry.get("claim_ids")
            for claim_id in listed if isinstance(listed, list) else []:
                if isinstance(claim_id, str) and claim_id in claim_persona and claim_id not in ids:
                    ids.append(claim_id)
            # Grouping claims from a single analyst says nothing about agreement or disagreement between analysts.
            if not summary or (group in NEEDS_TWO_PERSPECTIVES and len({claim_persona[i] for i in ids}) < 2):
                continue
            items.append({"id": f"{prefix}{len(items) + 1}", "summary": summary, "claim_ids": ids[:8]})
            if len(items) >= MAX_ITEMS_PER_GROUP:
                break
        result[group] = items
    return result


# True when the validated map holds nothing at all.
def map_is_empty(disagreements: dict) -> bool:
    return not disagreements.get("central_question") and not any(disagreements.get(group) for group in GROUPS)


# Marks factual claims that sit in a "conflicts" item as disputed (and undoes earlier marks). Returns the analysts
# whose stored perspective changed. Opinions and assumptions keep their label; they are not facts to dispute.
def apply_disputes(perspectives: dict[str, dict], disagreements: dict) -> set[str]:
    in_conflict = {claim_id for item in disagreements.get("conflicts", []) for claim_id in item["claim_ids"]}
    changed: set[str] = set()
    for persona, state in perspectives.items():
        for claim in (state.get("content") or {}).get("claims", []):
            if claim["type"] != "factual":
                continue
            wanted = "disputed" if claim["id"] in in_conflict else "unverified"
            if claim["status"] != wanted:
                claim["status"] = wanted
                changed.add(persona)
    return changed


# Validates the moderator's verdict. None if the reply is unusable (no summary).
def build_verdict(data: dict, completed: list[str], source_count: int) -> dict | None:
    summary = clip(data.get("summary"), 600)
    if not summary:
        return None
    # One strongest argument per real, completed analyst, in display order.
    by_persona: dict[str, str] = {}
    arguments = data.get("strongest_arguments")
    for entry in arguments if isinstance(arguments, list) else []:
        if isinstance(entry, dict) and entry.get("perspective") in completed and entry["perspective"] not in by_persona:
            argument = clip(entry.get("argument"), 500)
            if argument:
                by_persona[entry["perspective"]] = argument
    strongest = [{"perspective": p, "argument": by_persona[p]} for p in PERSONAS if p in by_persona]
    # The five criteria, matched by name and shown in our order; criteria the model skipped are left out.
    criteria_raw = data.get("criteria")
    given = {
        str(entry.get("name", "")).strip().lower(): clip(entry.get("assessment"), 400)
        for entry in (criteria_raw if isinstance(criteria_raw, list) else [])
        if isinstance(entry, dict)
    }
    criteria = [{"name": name, "assessment": given[name.lower()]} for name in CRITERIA if given.get(name.lower())]

    def texts(key: str) -> list[str]:
        value = data.get(key)
        cleaned = [clip(item, 300) for item in value] if isinstance(value, list) else []
        return [item for item in cleaned if item][:5]

    # No fact-checking step exists, so the app never calls the evidence "sufficient". The model may say
    # "insufficient"; with no sources at all it is always "insufficient".
    asked = str(data.get("evidence_sufficiency", "")).strip().lower()
    sufficiency = "insufficient" if source_count == 0 or asked == "insufficient" else "limited"
    # Limitations that the code knows for certain, stated plainly alongside the model's own text.
    limitations = ["Claims were not independently fact-checked."]
    if source_count == 0:
        limitations.insert(0, "No external sources were retrieved; the verdict reflects the arguments' reasoning only.")
    if len(completed) < len(PERSONAS):
        limitations.append(f"Based on {len(completed)} of {len(PERSONAS)} perspectives; the others did not complete.")
    return {
        "summary": summary,
        "strongest_arguments": strongest,
        "evidence_supports": clip(data.get("evidence_supports"), 700),
        "strongest_counterargument": clip(data.get("strongest_counterargument"), 600),
        "conflicting_or_insufficient_evidence": clip(data.get("conflicting_or_insufficient_evidence"), 600),
        "unresolved_questions": texts("unresolved_questions"),
        "criteria": criteria,
        "reasoning": clip(data.get("reasoning"), 900),
        "conclusion": clip(data.get("conclusion"), 500),
        "evidence_sufficiency": sufficiency,
        "could_change_conclusion": texts("could_change_conclusion"),
        "limitations": limitations,
        "based_on": {"perspectives": len(completed), "of": len(PERSONAS), "sources": source_count},
    }


# Plain-text summary of a verdict, stored in the legacy "verdict" field (used by archive cards and old clients).
def verdict_text(verdict: dict) -> str:
    return " ".join(part for part in (verdict.get("summary"), verdict.get("conclusion")) if part)[:700]
