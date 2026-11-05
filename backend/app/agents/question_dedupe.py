"""Detect identical and near-duplicate interview questions.

Combines lexical signals with concept/learning-objective fingerprints so
paraphrases that test the same idea (different wording) are rejected.
No embedding API — keeps the interviewer loop fast and dependency-free.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Stopwords kept small — enough to reduce "explain/how/what" noise without
# wiping technical terms.
_STOP = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "of",
    "to",
    "in",
    "on",
    "for",
    "with",
    "your",
    "you",
    "how",
    "what",
    "why",
    "when",
    "which",
    "would",
    "could",
    "should",
    "please",
    "explain",
    "describe",
    "discuss",
    "tell",
    "me",
    "about",
    "is",
    "are",
    "do",
    "does",
    "can",
    "terms",
    "behavior",
    "behaviour",
}

# Synonym groups → one canonical token (interview paraphrase collapse).
_SYNONYM_CANON: dict[str, str] = {}
for _group in (
    ("contiguous", "contiguously"),
    ("static", "fixed", "fixedsize"),
    ("dynamic", "resizable", "resize", "resizing", "resized"),
    ("definition", "define", "defined", "meaning", "means"),
    ("compare", "contrast", "difference", "differences", "versus", "vs", "between"),
    ("allocation", "allocate", "allocated", "allocating"),
    ("memory", "memories"),
    ("element", "elements"),
    ("array", "arrays"),
    ("hashmap", "hashmaps", "hashtable", "hashtables", "hash", "hashes"),
    ("collision", "collisions"),
    ("pointer", "pointers"),
    ("window", "windows"),
    ("prefix", "prefixes"),
    ("complexity", "complexities"),
    ("implement", "implementation", "implementing", "implements"),
    ("tradeoff", "tradeoffs", "trade"),
    ("approach", "approaches"),
    ("algorithm", "algorithms"),
    ("sorted", "sorting", "sort"),
    ("search", "searching", "searches"),
    ("subarray", "subarrays"),
    ("duplicate", "duplicates", "duplicated"),
    ("rotate", "rotation", "rotations", "rotated"),
    ("merge", "merging", "merged"),
    ("access", "accessing", "accessed"),
    ("insert", "insertion", "inserting", "inserted"),
    ("delete", "deletion", "deleting", "deleted", "remove", "removal"),
    ("index", "indexing", "indexed", "indices", "indexes"),
):
    canon = _group[0]
    for word in _group:
        _SYNONYM_CANON[word] = canon

# Learning-objective patterns (DSA / interview common). Order matters for
# overlapping phrases — more specific first.
_CONCEPT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"contigu\w*.{0,24}memory|stored\s+contigu\w*|memory\s+layout"),
        "contiguous_storage",
    ),
    (re.compile(r"fixed[\s-]*size|static\s+array"), "static_array"),
    (re.compile(r"dynamic\s+array|resiz\w+|grow\w*\s+capacit"), "dynamic_array"),
    (
        re.compile(
            r"static.{0,40}dynamic|dynamic.{0,40}static|fixed.{0,40}resiz|resiz.{0,40}fixed"
        ),
        "static_vs_dynamic",
    ),
    (
        re.compile(r"defin\w*\s+of\s+an?\s+array|what\s+an?\s+array\s+is|array\s+is\b"),
        "array_definition",
    ),
    (re.compile(r"two[\s-]*pointer"), "two_pointers"),
    (re.compile(r"sliding[\s-]*window"), "sliding_window"),
    (re.compile(r"prefix[\s-]*sum"), "prefix_sum"),
    (re.compile(r"binary[\s-]*search"), "binary_search"),
    (re.compile(r"hash\s*(map|table)|collision"), "hash_maps"),
    (re.compile(r"time\s+complexity|big[\s-]*o|o\s*\(\s*1\s*\)|o\s*\(\s*n"), "time_complexity"),
    (re.compile(r"space\s+complexity"), "space_complexity"),
    (re.compile(r"random\s+access|index\s+access|o\s*\(\s*1\s*\)\s+access"), "random_access"),
    (re.compile(r"kadane|maximum\s+subarray|max\s+subarray"), "max_subarray"),
    (re.compile(r"subarray"), "subarrays"),
    (re.compile(r"rotat\w+\s+array|array\s+rotat"), "array_rotation"),
    (re.compile(r"merge\w*\s+sorted|sorted\s+merge"), "merge_sorted"),
    (re.compile(r"duplicat"), "duplicates"),
    (re.compile(r"2d\s+array|matrix|row[\s-]*major|column[\s-]*major"), "2d_arrays"),
    (re.compile(r"in[\s-]*place"), "in_place"),
    (re.compile(r"edge\s+case"), "edge_cases"),
]


def normalize_question(text: str) -> str:
    return " ".join(_TOKEN_RE.findall((text or "").lower()))


def _raw_tokens(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall((text or "").lower()) if t not in _STOP and len(t) > 1]


def _stem_light(token: str) -> str:
    """Cheap suffix trim so definition/define-ish forms align after synonyms."""
    if token in _SYNONYM_CANON:
        return _SYNONYM_CANON[token]
    for suffix in ("ingly", "edly", "ing", "ied", "ies", "ed", "ly", "es", "s"):
        if len(token) > len(suffix) + 3 and token.endswith(suffix):
            stem = token[: -len(suffix)]
            return _SYNONYM_CANON.get(stem, stem)
    return token


def _tokens(text: str) -> set[str]:
    return {_stem_light(t) for t in _raw_tokens(text)}


def concept_tags(text: str) -> set[str]:
    """Learning-objective tags derived from known interview concept phrases."""
    low = (text or "").lower()
    tags = {tag for pattern, tag in _CONCEPT_PATTERNS if pattern.search(low)}
    # Definition-style asks without the word "definition".
    if re.search(r"\b(what\s+is|define|definition of)\b", low) and "array" in low:
        tags.add("array_definition")
    return tags


def concept_fingerprint(text: str) -> frozenset[str]:
    """Stable concept set: objective tags + canonical content tokens."""
    tags = {f"tag:{t}" for t in concept_tags(text)}
    tokens = {f"tok:{t}" for t in _tokens(text)}
    return frozenset(tags | tokens)


def _set_coverage(a: set[str], b: set[str]) -> float:
    """How much of the smaller set is covered by the intersection."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def _tag_overlap_duplicate(a_tags: set[str], b_tags: set[str]) -> bool:
    """True when learning-objective tags substantially match."""
    if not a_tags or not b_tags:
        return False
    inter = a_tags & b_tags
    if not inter:
        return False
    # Same multi-concept ask (e.g. definition + contiguous + static/dynamic).
    if len(inter) >= 2 and _set_coverage(a_tags, b_tags) >= 0.66:
        return True
    # Single strong objective both focused on (and little else differing).
    if len(inter) >= 1 and a_tags == b_tags and len(a_tags) >= 2:
        return True
    union = a_tags | b_tags
    return len(inter) / len(union) >= 0.75 and len(inter) >= 2


def question_similarity(a: str, b: str) -> float:
    """Return 0..1 similarity. 1.0 means effectively the same question."""
    na, nb = normalize_question(a), normalize_question(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
        if len(shorter) >= 12 and len(shorter) / max(len(longer), 1) >= 0.55:
            return 0.92

    ta, tb = _tokens(a), _tokens(b)
    jaccard = (len(ta & tb) / len(ta | tb)) if ta and tb else 0.0
    coverage = _set_coverage(ta, tb)
    seq = SequenceMatcher(None, na, nb).ratio()
    tags_a, tags_b = concept_tags(a), concept_tags(b)
    tag_score = 0.0
    if tags_a and tags_b:
        tag_score = len(tags_a & tags_b) / len(tags_a | tags_b)
        if _tag_overlap_duplicate(tags_a, tags_b):
            tag_score = max(tag_score, 0.9)
    return max(jaccard, coverage * 0.95, seq, tag_score)


def is_near_duplicate(a: str, b: str, *, threshold: float = 0.72) -> bool:
    """True when questions test the same ask (exact, paraphrase, or same concepts)."""
    na, nb = normalize_question(a), normalize_question(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    # Contained paraphrase (short vs long wording of the same ask).
    if na in nb or nb in na:
        shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
        if len(shorter) >= 12 and len(shorter) / max(len(longer), 1) >= 0.55:
            return True

    tags_a, tags_b = concept_tags(a), concept_tags(b)
    if _tag_overlap_duplicate(tags_a, tags_b):
        return True

    seq = SequenceMatcher(None, na, nb).ratio()
    if seq >= 0.88:
        return True

    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    inter = ta & tb
    jaccard = len(inter) / len(ta | tb)
    coverage = _set_coverage(ta, tb)

    # Soft containment: most content words of the shorter ask appear in the other.
    if coverage >= 0.72 and len(inter) >= 4:
        return True
    # Reordered paraphrase: almost the same content words.
    if jaccard >= 0.78 and len(inter) >= 3:
        return True
    # Soft match: need both token overlap and string similarity so template
    # families with different topics are not collapsed.
    if jaccard >= threshold and seq >= max(0.68, threshold - 0.08):
        return True
    # Concept tags + strong lexical coverage (synonym-aware).
    # noqa below: a direct `return <expr>` could return an empty set instead
    # of False; keep the explicit boolean contract.
    if tags_a and tags_b and coverage >= 0.55 and len(tags_a & tags_b) >= 2:  # noqa: SIM103
        return True
    return False


def is_duplicate_question(
    candidate: str,
    asked: list[str],
    *,
    threshold: float = 0.72,
) -> bool:
    """True if candidate matches any prior question exactly or near-exactly."""
    if not candidate or not candidate.strip():
        return False
    return any(is_near_duplicate(candidate, prev, threshold=threshold) for prev in asked if prev)


def duplicate_of(candidate: str, asked: list[str], *, threshold: float = 0.72) -> str | None:
    """Return the prior question that collides, if any."""
    for prev in asked:
        if prev and is_near_duplicate(candidate, prev, threshold=threshold):
            return prev
    return None
