"""
Resolving what a clinician typed to a name a drug database will recognise.

A prescriber writes "Monocef", not "ceftriaxone". openFDA is a UNITED STATES
label database and RxNorm is a US drug vocabulary, so neither has heard of the
brand names used across most of India - and a system that answers "no
information" to a name written on half the prescriptions in the country is not
much use on those prescriptions.

THREE STEPS, WEAKEST CLAIM LAST:

  1. The name as written. If a database knows it, nothing is resolved and nothing
     is claimed.
  2. RxNorm (NLM, keyless). Resolves US brand names to their ingredients from a
     maintained vocabulary - no curation by us, so nothing here can be wrong in a
     way we introduced.
  3. A LOCAL BRAND MAP, curated here, for Indian brands neither database holds.

EVERY RESOLUTION IS SHOWN TO THE CLINICIAN. This is the safety property that
makes step 3 acceptable at all: mapping a brand to the wrong generic would show a
clinician the wrong drug's contraindications, which is worse than showing none.
So a resolution is never silent - the reader is told "Monocef read as
Ceftriaxone", and the person best placed to catch an error is the person who
typed the name.

THE MAP IS DELIBERATELY SMALL. Common hospital antibacterials whose brand-generic
relationship is stable and widely documented. It is not a formulary and does not
try to be: an unmapped brand falls through to the coverage warning, which is the
honest answer, rather than to a guess.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Optional

# Indian brand -> generic. Antibacterials only, and only where the relationship is
# stable and widely published. A brand that is marketed differently in another
# country is a reason to leave it out, not a reason to guess.
INDIAN_BRAND_TO_GENERIC: Dict[str, str] = {
    "monocef": "Ceftriaxone",
    "magnex": "Cefoperazone and Sulbactam",
    "magnexforte": "Cefoperazone and Sulbactam",
    "taximo": "Cefixime",
    "taxim": "Cefotaxime",
    "zifi": "Cefixime",
    "amoxyclav": "Amoxicillin and Clavulanate Potassium",
    "augmentin": "Amoxicillin and Clavulanate Potassium",
    "clavam": "Amoxicillin and Clavulanate Potassium",
    "piptaz": "Piperacillin and Tazobactam",
    "zosyn": "Piperacillin and Tazobactam",
    "tazact": "Piperacillin and Tazobactam",
    "meromac": "Meropenem",
    "meronem": "Meropenem",
    "linospan": "Linezolid",
    "linezolid": "Linezolid",
    "vancomax": "Vancomycin",
    "targocid": "Teicoplanin",
    "cifran": "Ciprofloxacin",
    "ciplox": "Ciprofloxacin",
    "levoflox": "Levofloxacin",
    "azithral": "Azithromycin",
    "azee": "Azithromycin",
    "althrocin": "Erythromycin",
    "metrogyl": "Metronidazole",
    "flagyl": "Metronidazole",
    "doxt": "Doxycycline",
    "nitrofurantoin": "Nitrofurantoin",
    "colistimethate": "Colistimethate Sodium",
    "polymyxin": "Polymyxin B",
}

RXNORM_URL = "https://rxnav.nlm.nih.gov/REST/drugs.json"

_RESOLVE_CACHE: Dict[str, "ResolvedName"] = {}


@dataclass
class ResolvedName:
    """What was typed, what it was read as, and on whose authority."""

    as_written: str
    resolved: str
    method: str          # AS_WRITTEN | RXNORM | LOCAL_BRAND_MAP | COMBINATION_COMPONENT
    source: str          # printed to the clinician

    @property
    def was_resolved(self) -> bool:
        return self.method != "AS_WRITTEN"

    def to_dict(self) -> Dict[str, str]:
        return {
            "as_written": self.as_written,
            "resolved_to": self.resolved,
            "method": self.method,
            "source": self.source,
            # The line the interface must show. Not optional: an unshown
            # resolution is an unchecked one.
            "notice": (
                f"“{self.as_written}” read as {self.resolved} ({self.source}). "
                "Confirm this is the medication intended before relying on the safety "
                "information below."
                if self.was_resolved else ""
            ),
        }


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _rxnorm_generic(name: str) -> Optional[str]:
    """
    The ingredient RxNorm records for a brand, or None.

    NLM's vocabulary, not ours: whatever it returns is attributable to them, which
    is why this is tried before the local map.
    """
    try:
        import httpx

        response = httpx.get(RXNORM_URL, params={"name": name}, timeout=15.0)
        if response.status_code != 200:
            return None
        groups = (response.json().get("drugGroup") or {}).get("conceptGroup") or []
        for group in groups:
            for concept in group.get("conceptProperties") or []:
                label = concept.get("name") or ""
                # "amoxicillin 25 MG/ML / clavulanate ... [Augmentin]" -> ingredients
                head = label.split("[")[0]
                parts = [p.strip() for p in head.split("/")]
                ingredients = []
                for part in parts:
                    word = re.split(r"\s+\d", part)[0].strip()
                    if word and word.lower() not in ingredients:
                        ingredients.append(word)
                if ingredients:
                    return " and ".join(i.title() for i in ingredients[:2])
        return None
    except Exception:
        return None


def resolve(name: str, canonical_from_kb=None) -> ResolvedName:
    """
    Resolve a written medication name to something a drug database will match.

    `canonical_from_kb` returns this system's own canonical name for a drug it
    holds, or None. It is consulted FIRST and it is not a veto -- an earlier
    version treated "the knowledge base knows this name" as "no resolution
    needed", which was wrong in exactly the case that matters: the knowledge base
    holds the brand names Magnex and Piptaz, openFDA holds neither, so the guard
    skipped resolution and the external lookup then found nothing. Knowing a name
    locally says nothing about whether a foreign regulator indexes it.
    """
    written = (name or "").strip()
    if not written:
        return ResolvedName(written, written, "AS_WRITTEN", "as written")

    cache_key = _key(written)
    if cache_key in _RESOLVE_CACHE:
        return _RESOLVE_CACHE[cache_key]

    def _done(result: ResolvedName) -> ResolvedName:
        _RESOLVE_CACHE[cache_key] = result
        return result

    if canonical_from_kb:
        canonical = canonical_from_kb(written)
        if canonical and _key(canonical) != cache_key:
            return _done(ResolvedName(written, canonical, "KNOWLEDGE_BASE",
                                      "this system's own drug record"))
        if canonical:
            return _done(ResolvedName(written, written, "AS_WRITTEN",
                                      "held in the knowledge base"))

    # 2. RxNorm, before the local map: a maintained vocabulary outranks our curation.
    generic = _rxnorm_generic(written)
    if generic and _key(generic) != cache_key:
        return _done(ResolvedName(written, generic, "RXNORM",
                                  "RxNorm, US National Library of Medicine"))

    # 3. Local brand map.
    mapped = INDIAN_BRAND_TO_GENERIC.get(cache_key)
    if mapped and _key(mapped) != cache_key:
        return _done(ResolvedName(written, mapped, "LOCAL_BRAND_MAP",
                                  "brand list curated in this system, not a regulatory source"))

    # 4. A combination written as one token: try the first component.
    if "-" in written or "+" in written:
        first = re.split(r"[-+]", written)[0].strip()
        if len(first) >= 5 and _key(first) != cache_key:
            return _done(ResolvedName(written, first.title(), "COMBINATION_COMPONENT",
                                      "first component of a combination product"))

    return _done(ResolvedName(written, written, "AS_WRITTEN", "as written"))
