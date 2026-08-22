"""
PDF text repair for guideline ingestion.

Two defects appear in the source PDFs and both corrupt retrieved passages that
are shown verbatim to clinicians:

  1. LIGATURE CONTROL BYTES. The documents encode fi/fl/ff ligatures as
     font-specific control bytes, so "confirmed" extracts as "con\\x81rmed" and
     "fluoroquinolone" as "\\x95uoroquinolone". The byte->ligature mapping is
     FONT-dependent: \\x7f means "fi" in one font and "fl" in another, so a fixed
     substitution table would silently corrupt text.

  2. KERNING-SPLIT WORDS. Wide letter spacing extracts as "hyg iene",
     "tr eatment", "sev er e".

Both are repaired by the same conservative rule: a change is applied ONLY when
it produces a word that already occurs, uncorrupted, elsewhere in the same
corpus. Where no candidate resolves, or several do ambiguously, the text is left
alone. Digits, dosages and units are never joined or altered.

This is spelling repair on extraction artifacts. It does not paraphrase, reorder
or summarise: retrieved passages remain verbatim source text.
"""
from __future__ import annotations

import collections
import re
from typing import Counter as CounterT, Dict, Iterable, List, Tuple

# Ligatures that appear in these documents, longest first so "ffi" is tried
# before "ff".
LIGATURE_CANDIDATES: Tuple[str, ...] = ("ffi", "ffl", "fi", "fl", "ff")

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
_WORD = re.compile(r"[A-Za-z]{3,}")

# Minimum clean occurrences before a word is trusted as a repair target. Guards
# against "repairing" one artifact into another artifact.
MIN_CLEAN_FREQ = 2


def build_dictionary(texts: Iterable[str]) -> CounterT[str]:
    """Words that extracted cleanly, i.e. contain no control bytes."""
    vocab: CounterT[str] = collections.Counter()
    for t in texts:
        for line in t.split("\n"):
            if _CONTROL.search(line):
                # Skip whole lines containing artifacts; their words are suspect.
                continue
            for w in _WORD.findall(line):
                vocab[w.lower()] += 1
    return vocab


def _resolve_token(token: str, vocab: CounterT[str]) -> str:
    """
    Replace control bytes in one token by testing each ligature candidate and
    keeping the substitution that yields a known clean word.
    """
    positions = [i for i, ch in enumerate(token) if _CONTROL.match(ch)]
    if not positions:
        return token

    # Single control byte covers essentially every real case here.
    if len(positions) == 1:
        i = positions[0]
        matches = []
        for lig in LIGATURE_CANDIDATES:
            cand = token[:i] + lig + token[i + 1:]
            if vocab.get(cand.lower(), 0) >= MIN_CLEAN_FREQ:
                matches.append((vocab[cand.lower()], cand))
        if matches:
            # Most frequent clean form wins; ties are resolved deterministically.
            matches.sort(key=lambda kv: (-kv[0], kv[1]))
            return matches[0][1]
        return token

    # Multiple control bytes: try the most common ligature pair combination.
    cand = token
    for lig in ("fi", "fl"):
        trial = _CONTROL.sub(lig, token)
        if vocab.get(trial.lower(), 0) >= MIN_CLEAN_FREQ:
            return trial
    return cand


# An alphabetic run interrupted by control bytes, e.g. "con\x81rmed" inside
# "con\x81rmed/suspected". Matching the word rather than the whitespace-delimited
# token means attached punctuation cannot defeat the dictionary lookup.
_BROKEN_WORD = re.compile(r"[A-Za-z]*[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f][A-Za-z]*")


def repair_ligatures(text: str, vocab: CounterT[str]) -> Tuple[str, int]:
    """Repair control-byte ligatures. Returns (text, repairs_applied)."""
    if not _CONTROL.search(text):
        return text, 0
    repairs = 0

    def _sub(m: "re.Match[str]") -> str:
        nonlocal repairs
        token = m.group()
        fixed = _resolve_token(token, vocab)
        if fixed != token:
            repairs += 1
        return fixed

    result = _BROKEN_WORD.sub(_sub, text)
    # Any control byte the dictionary could not resolve is dropped rather than
    # shown to a clinician as mojibake.
    result = _CONTROL.sub("", result)
    return result, repairs


def _damaged_forms(vocab: CounterT[str]) -> set:
    """
    Dictionary entries that are themselves probably ligature damage.

    A word is suspect when deleting a ligature from a longer, well-attested
    dictionary word produces it exactly -- "fluoroquinolone" minus "fl" gives
    "uoroquinolone". Such tokens recur often enough to look legitimate, so they
    must be excluded before the dictionary is trusted.
    """
    suspect = set()
    for word, freq in vocab.items():
        if freq < MIN_CLEAN_FREQ or len(word) < 7:
            continue
        for lig in ("fi", "fl", "ff"):
            idx = word.find(lig)
            while idx != -1:
                stripped = word[:idx] + word[idx + len(lig):]
                if len(stripped) >= 5 and stripped != word:
                    suspect.add(stripped)
                idx = word.find(lig, idx + 1)
    # Never treat a well-attested word as damage if it is far more common than
    # any repaired form would be.
    return {w for w in suspect if vocab.get(w, 0) < vocab_max_source(vocab, w) * 4}


def vocab_max_source(vocab: CounterT[str], stripped: str) -> int:
    """Highest frequency among dictionary words that could have produced `stripped`."""
    best = 0
    for lig in ("fi", "fl", "ff"):
        for i in range(len(stripped) + 1):
            cand = stripped[:i] + lig + stripped[i:]
            best = max(best, vocab.get(cand, 0))
    return best or 1


def repair_dropped_ligatures(text: str, vocab: CounterT[str]) -> Tuple[str, int]:
    """
    Repair ligatures the extractor dropped outright, leaving no control byte:
    "uoroquinolone" -> "fluoroquinolone", "signicant" -> "significant".

    Unlike repair_ligatures there is no marker to key on, so the rule is
    deliberately strict: the word must be unknown to the dictionary, and exactly
    ONE insertion position and ligature must yield a known clean word. Ambiguous
    cases are left untouched.
    """
    repairs = 0

    suspect = _damaged_forms(vocab)

    def _sub(m: "re.Match[str]") -> str:
        nonlocal repairs
        word = m.group()
        lower = word.lower()
        # A dropped ligature leaves a plausible-looking token that occurs often
        # enough to enter the dictionary ("uoroquinolone" appears 37 times). So
        # membership in the dictionary is NOT evidence the word is real: it is
        # only trusted if it is not also reachable by deleting a ligature from a
        # longer dictionary word.
        if len(word) < 5:
            return word
        if vocab.get(lower, 0) >= 1 and lower not in suspect:
            return word
        found = set()
        for lig in ("fi", "fl", "ff"):
            for i in range(1, len(word)):
                cand = word[:i] + lig + word[i:]
                if vocab.get(cand.lower(), 0) >= MIN_CLEAN_FREQ:
                    found.add(cand)
            cand = lig + word
            if vocab.get(cand.lower(), 0) >= MIN_CLEAN_FREQ:
                found.add(cand)
        if len(found) == 1:
            repairs += 1
            return found.pop()
        return word

    result = re.sub(r"[A-Za-z]{5,}", _sub, text)
    return result, repairs


def repair_spacing(text: str, vocab: CounterT[str]) -> Tuple[str, int]:
    """
    Rejoin kerning-split words: "hyg iene" -> "hygiene".

    Only joins when the concatenation is a known clean word AND at least one
    fragment is not itself a word, so genuine word pairs are never merged.
    Fragments containing digits are never joined, protecting dosages.
    """
    joins = 0
    tokens = text.split(" ")
    out: List[str] = []
    i = 0
    while i < len(tokens):
        a = tokens[i]
        b = tokens[i + 1] if i + 1 < len(tokens) else ""
        if (
            a and b
            and a.isalpha() and b.isalpha()
            and len(a) + len(b) >= 4
            and (len(a) <= 4 or len(b) <= 4)          # at least one short fragment
            and vocab.get((a + b).lower(), 0) >= MIN_CLEAN_FREQ
            and not (vocab.get(a.lower(), 0) >= MIN_CLEAN_FREQ
                     and vocab.get(b.lower(), 0) >= MIN_CLEAN_FREQ)
        ):
            out.append(a + b)
            joins += 1
            i += 2
            continue
        out.append(a)
        i += 1
    return " ".join(out), joins


def repair(text: str, vocab: CounterT[str]) -> Tuple[str, Dict[str, int]]:
    text, lig = repair_ligatures(text, vocab)
    text, dropped = repair_dropped_ligatures(text, vocab)
    text, sp = repair_spacing(text, vocab)
    return text, {"ligatures": lig, "dropped": dropped, "spacing": sp}
