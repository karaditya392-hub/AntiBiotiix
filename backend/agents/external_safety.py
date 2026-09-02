"""
Drug evidence with a national-first escalation chain.

THE ORDER IS THE DESIGN, and it is the order the precedence hierarchy already
states rather than a new one invented here:

  1. THE HELD NATIONAL CORPUS FIRST. For every prescribed drug, look for a
     passage carrying antimicrobial authority - ICMR, NCDC, WHO, the local
     antibiogram - that actually names it. If one exists, that is the answer and
     nothing external is consulted. A national guideline does not need
     corroboration from a foreign regulator, and fetching one anyway would put a
     second source beside an answer the hierarchy has already settled.

  2. ONLY WHERE NOTHING IS HELD, escalate outside: the drug's own regulatory
     label, then the web if a search provider is configured - every web result
     judged by the filtration agent before it can be quoted.

WHY THIS MATTERS. COVERAGE-001 fires when a prescribed drug is outside the
validated knowledge base, and what it says is true and useless: "comprehensive
safety checks cannot be evaluated, manual clinician review required." The system
correctly refuses to give an all-clear, and then leaves the clinician with
nothing. A prescriber facing an unfamiliar agent at 2am needs the
contraindication, not a note that we do not have one. This module goes and finds
one - and says exactly where it came from.

The clinician always sees WHICH tier answered: a national guideline with its page
number, or an external source with its name, its retrieval time, and a standing
notice saying it carries no national authority.

WHAT IT IS NOT ALLOWED TO DO, and the distinction is the whole design:

  * It does not create, remove or re-rank a deterministic warning. COVERAGE-001
    still fires, still at its own severity, and the stewardship rollup is computed
    from the rules alone. This layer adds CONTENT to a gap the engine already
    reported; it never changes the verdict. An advisory found here cannot make an
    unassessed drug look assessed.

  * It does not generate clinical text. Findings are VERBATIM excerpts from the
    label section they came from, matched to the patient by explicit rules below.
    No model writes a contraindication.

  * It never presents an external source as national guidance. Every finding
    carries its own origin - "FDA label" or "Web - site" - and its own standing
    notice. US regulatory labels are not ICMR, and the corpus already draws that
    boundary in backend/guidelines/label_evidence.py; this holds the same line for
    labels fetched live.

MATCHING IS DETERMINISTIC. Whether a label section applies to this patient is
decided by the patient's recorded allergy, eGFR, Child-Pugh class, pregnancy
status and home medication list - not by asking a model whether it seems
relevant. The model's only role in this path is Agent 2 judging web results, and
web results are optional.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend import config

OPENFDA_URL = "https://api.fda.gov/drug/label.json"

# Label sections worth reading, and the concern each speaks to. Ordered: a boxed
# warning is the strongest statement a label makes and is read first.
LABEL_SECTIONS = [
    ("boxed_warning", "BOXED WARNING"),
    ("contraindications", "CONTRAINDICATIONS"),
    ("warnings_and_cautions", "WARNINGS AND PRECAUTIONS"),
    ("drug_interactions", "DRUG INTERACTIONS"),
    ("use_in_specific_populations", "USE IN SPECIFIC POPULATIONS"),
    ("dosage_and_administration", "DOSAGE AND ADMINISTRATION"),
]

# Terms that indicate a section is speaking about a given patient factor.
RENAL_TERMS = ("renal impairment", "creatinine clearance", "crcl", "renal function",
               "dialysis", "kidney impairment", "nephrotox")
HEPATIC_TERMS = ("hepatic impairment", "liver impairment", "hepatic function",
                 "child-pugh", "hepatotox", "cirrho")
PREGNANCY_TERMS = ("pregnan", "fetal", "teratogen", "embryo")
LACTATION_TERMS = ("lactation", "breastfeed", "breast-feed", "nursing mother", "human milk")
PAEDIATRIC_TERMS = ("pediatric", "paediatric", "children", "neonat", "infant")

STANDING_NOTICE = (
    "EXTERNAL SOURCE, NOT A DETERMINISTIC RULE FINDING AND NOT NATIONAL GUIDANCE. "
    "The text below is quoted verbatim from the source named beside it and matched to "
    "this patient's recorded details. It does not carry the authority of the ICMR or "
    "NCDC national guidelines, it did not fire any clinical safety rule, and it does "
    "not change the stewardship priority. Where it differs from the national guidance "
    "shown next to it, this system reports the difference and does not resolve it."
)


@dataclass
class ExternalFinding:
    drug: str
    concern: str               # what patient factor triggered this
    section: str               # which label section it came from
    excerpt: str               # verbatim
    source_label: str          # "FDA label - Ceftaroline Fosamil"
    source_kind: str           # FDA_LABEL | WEB
    source_url: str
    matched_on: str            # the patient detail that matched, printed to the reader
    retrieved_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "drug": self.drug,
            "concern": self.concern,
            "section": self.section,
            "excerpt": self.excerpt,
            "source": self.source_label,
            "source_kind": self.source_kind,
            "source_url": self.source_url,
            "matched_on": self.matched_on,
            "retrieved_at": self.retrieved_at,
            "is_deterministic_rule_finding": False,
            "standing": STANDING_NOTICE,
        }


@dataclass
class CoverageResolution:
    drug: str
    resolved: bool = False
    findings: List[ExternalFinding] = field(default_factory=list)
    label_found: bool = False
    label_source: Optional[str] = None
    web_verdicts: List[Dict[str, Any]] = field(default_factory=list)
    note: str = ""
    resolved_name: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "drug": self.drug,
            "resolved": self.resolved,
            "finding_count": len(self.findings),
            "findings": [f.to_dict() for f in self.findings],
            "regulatory_label_found": self.label_found,
            "regulatory_label_source": self.label_source,
            "web_filter_verdicts": self.web_verdicts,
            "note": self.note,
            # Never omitted when a name was resolved: an unshown resolution is an
            # unchecked one, and a wrong brand mapping would otherwise show a
            # clinician a different drug's contraindications without saying so.
            "resolved_name": self.resolved_name,
            "affects_stewardship_priority": False,
        }


def _sentences(text: str) -> List[str]:
    clean = " ".join((text or "").split())
    return [s.strip() for s in re.split(r"(?<=[.;])\s+(?=[A-Z(])", clean) if s.strip()]


# Sentences that mention a substance in order to say it is NOT a problem. A
# lexical match inside one of these means the opposite of a finding, and printing
# it as a concern would invert the label's meaning.
_NEGATION_PATTERNS = (
    "no incompatibility", "not been demonstrated", "no cross-reactivity",
    "no cross reactivity", "has not been reported", "were not observed",
    "no clinically relevant interaction", "no significant interaction",
    "no dosage adjustment", "no adjustment is required", "did not affect",
    "no evidence of", "is not expected",
)


def _is_negated(sentence: str) -> bool:
    return any(pattern in sentence.lower() for pattern in _NEGATION_PATTERNS)


def _excerpt_for(section_text: str, terms, max_sentences: int = 2) -> Optional[str]:
    """
    The sentences in a label section that actually mention the patient factor.

    Returning the whole section would bury the finding; paraphrasing it would put
    words in a regulator's mouth. So: the matching sentences, verbatim, capped.
    """
    hits = [s for s in _sentences(section_text)
            if any(t in s.lower() for t in terms) and not _is_negated(s)]
    if not hits:
        return None
    excerpt = " ".join(hits[:max_sentences])
    return excerpt[:900] + ("..." if len(excerpt) > 900 else "")


_LABEL_CACHE: Dict[str, Optional[Dict[str, Any]]] = {}


ROUTE_TERMS = {
    "IV": ("INTRAVENOUS", "INJECTION", "INFUSION", "PARENTERAL"),
    "IM": ("INTRAMUSCULAR", "INJECTION", "PARENTERAL"),
    "PO": ("ORAL",),
}


def _label_score(label: Dict[str, Any], route: Optional[str]) -> int:
    """
    How well a returned label matches the medication that was actually prescribed.

    THE ROUTE IS THE PART THAT BITES. openFDA holds every marketed formulation of
    a drug, and asking for one gives an arbitrary one: for Clindamycin it returned
    a TOPICAL gel whose sections are 279 characters long and mention neither renal
    nor hepatic use, for a patient prescribed it intravenously. Reporting "nothing
    found" from a topical label, for an IV order, is a false negative about the
    exact domains the coverage warning said were unassessed.

    So candidates are scored: the prescribed route first, then how much of the
    safety content this system reads is actually present. Deterministic, and the
    chosen label's own name is printed to the reader either way.
    """
    score = 0
    routes = [str(r).upper() for r in (label.get("openfda") or {}).get("route") or []]
    if route:
        wanted = ROUTE_TERMS.get(str(route).upper(), ())
        if any(any(w in r for w in wanted) for r in routes):
            score += 6
        elif routes and "TOPICAL" in " ".join(routes):
            score -= 4       # a topical label for a systemic order is the wrong document
    for key, _ in LABEL_SECTIONS:
        if label.get(key):
            score += 1
    # Longer safety text is a proxy for a full prescribing information document
    # rather than an abbreviated one.
    score += min(len(" ".join(label.get("warnings_and_cautions", []))) // 2000, 3)
    return score


def fetch_label(drug_name: str, route: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    The drug's US regulatory label from openFDA, for the formulation prescribed.

    Keyless and public. Returns None on any failure -- a coverage gap that cannot
    be resolved stays a coverage gap, which is the safe outcome and is exactly
    what the deterministic warning already says.
    """
    name = re.sub(r"[^a-zA-Z0-9 \-]", "", (drug_name or "")).strip()
    if not name:
        return None
    # Cached per process, keyed by drug AND route: the same drug prescribed IV and
    # topically are different documents, and caching one under the other is how a
    # topical gel ends up answering a question about an infusion.
    key = f"{name.lower()}|{(route or '').upper()}"
    if key in _LABEL_CACHE:
        return _LABEL_CACHE[key]
    try:
        import httpx

        for field_name in ("openfda.generic_name", "openfda.brand_name", "openfda.substance_name"):
            response = httpx.get(
                OPENFDA_URL,
                params={"search": f'{field_name}:"{name}"', "limit": 10},
                timeout=25.0,
            )
            if response.status_code == 200:
                results = response.json().get("results") or []
                if results:
                    best = max(results, key=lambda r: _label_score(r, route))
                    _LABEL_CACHE[key] = best
                    return best
        _LABEL_CACHE[key] = None
        return None
    except Exception:
        return None


def _label_source(label: Dict[str, Any], drug: str) -> str:
    openfda = label.get("openfda") or {}
    brand = (openfda.get("brand_name") or [""])[0]
    manufacturer = (openfda.get("manufacturer_name") or [""])[0]
    named = brand or drug
    return f"FDA label - {named}" + (f" ({manufacturer})" if manufacturer else "")


def findings_from_label(patient, item, label: Dict[str, Any],
                        co_prescribed: Optional[List[str]] = None) -> List[ExternalFinding]:
    """
    Match label sections against this patient's recorded details.

    Deterministic throughout: each branch fires on a value the clinician entered,
    and the reader is told which value it was.

    `co_prescribed` is the other medications on the SAME order. Home medications
    were being checked and these were not, which is the wrong half to miss: two
    agents started together are the interaction a prescriber can still prevent.
    """
    drug = item.medication_name
    source = _label_source(label, drug)
    url = f"https://api.fda.gov/drug/label.json?search=openfda.generic_name:%22{drug}%22"
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out: List[ExternalFinding] = []

    def add(concern, section_label, excerpt, matched_on):
        out.append(ExternalFinding(drug, concern, section_label, excerpt, source,
                                   "FDA_LABEL", url, matched_on, stamp))

    sections = {key: " ".join(label.get(key, [])) for key, _ in LABEL_SECTIONS if label.get(key)}

    # A boxed warning is reported whether or not it matches a patient factor: it is
    # the strongest statement a regulator makes about a drug and withholding it
    # because no recorded detail matched would be the wrong call.
    if "boxed_warning" in sections:
        text = " ".join(_sentences(sections["boxed_warning"])[:3])[:900]
        if text:
            add("Boxed warning", "BOXED WARNING", text, "applies to all patients")

    # --- documented allergies -------------------------------------------------
    for allergy in (patient.allergies or []):
        token = re.sub(r"[^a-z]", "", (allergy or "").lower())
        if len(token) < 4:
            continue
        stem = token[:6]
        # ONLY THE SECTIONS THAT CARRY HYPERSENSITIVITY STATEMENTS. A dosing
        # section listing drugs a solution is physically compatible with is not a
        # statement about this patient's allergy: matching "cephalothin" there
        # reported a cephalosporin cross-reactivity out of a sentence that said no
        # incompatibility had been demonstrated.
        for key, section_label in LABEL_SECTIONS:
            if key not in sections or key not in ("contraindications", "warnings_and_cautions"):
                continue
            # THE ALLERGY ITSELF MUST APPEAR IN THE SENTENCE. An earlier version
            # accepted any excerpt containing "hypersensitivity", which is a false
            # positive generator: almost every contraindications section carries
            # that word about the drug's OWN hypersensitivity, so every patient
            # with any allergy would be told of a cross-reactivity that the label
            # never claimed. Vancomycin was reported as cross-reacting with a
            # cephalosporin allergy on exactly that basis.
            #
            # So the excerpt must name the substance the patient reacted to. A
            # generic hypersensitivity statement about a different drug is not a
            # finding about this patient, and a finding this system cannot support
            # is one it must not print.
            excerpt = _excerpt_for(sections[key], (stem,))
            if excerpt and stem in excerpt.lower():
                add(f"Possible cross-reactivity with documented allergy: {allergy}",
                    section_label, excerpt, f"allergy: {allergy}")
                break

    # --- renal ----------------------------------------------------------------
    egfr = getattr(patient, "egfr_ml_min", None)
    if egfr is not None and egfr < 60:
        for key, section_label in LABEL_SECTIONS:
            if key not in sections:
                continue
            excerpt = _excerpt_for(sections[key], RENAL_TERMS)
            if excerpt:
                add(f"Renal impairment (eGFR {egfr:g} mL/min)", section_label, excerpt,
                    f"eGFR {egfr:g} mL/min")
                break

    # --- hepatic --------------------------------------------------------------
    child_pugh = getattr(patient, "child_pugh_class", None)
    if child_pugh:
        for key, section_label in LABEL_SECTIONS:
            if key not in sections:
                continue
            excerpt = _excerpt_for(sections[key], HEPATIC_TERMS)
            if excerpt:
                add(f"Hepatic impairment ({child_pugh})", section_label, excerpt, str(child_pugh))
                break

    # --- pregnancy and lactation ---------------------------------------------
    pregnancy = str(getattr(patient, "pregnancy_status", "") or "")
    if "PREGNANT_TRIMESTER" in pregnancy:
        for key, section_label in LABEL_SECTIONS:
            if key not in sections:
                continue
            excerpt = _excerpt_for(sections[key], PREGNANCY_TERMS)
            if excerpt:
                add("Pregnancy", section_label, excerpt, pregnancy.replace("_", " ").title())
                break
    if str(getattr(patient, "lactation_status", "") or "") == "LACTATING":
        for key, section_label in LABEL_SECTIONS:
            if key not in sections:
                continue
            excerpt = _excerpt_for(sections[key], LACTATION_TERMS)
            if excerpt:
                add("Lactation", section_label, excerpt, "documented as lactating")
                break

    # --- paediatric -----------------------------------------------------------
    age = getattr(patient, "age", None)
    if age is not None and age < 18:
        for key, section_label in LABEL_SECTIONS:
            if key not in sections:
                continue
            excerpt = _excerpt_for(sections[key], PAEDIATRIC_TERMS)
            if excerpt:
                add(f"Paediatric patient (age {age})", section_label, excerpt, f"age {age}")
                break

    # --- interactions: home medications AND drugs on this same order ----------
    #
    # Searched across every section rather than only DRUG INTERACTIONS: labels put
    # interaction language in warnings and in dosing text too, and a real
    # interaction described in the wrong section is still a real interaction.
    for source_list, kind in ((patient.active_medications or [], "home medication"),
                              (co_prescribed or [], "co-prescribed medication")):
        for med in source_list:
            name = re.split(r"[\s0-9]", (med or "").strip())[0].lower()
            if len(name) < 5 or name == drug.lower()[:len(name)]:
                continue
            for key, section_label in LABEL_SECTIONS:
                if key not in sections or key == "boxed_warning":
                    continue
                excerpt = _excerpt_for(sections[key], (name,))
                if excerpt and name in excerpt.lower():
                    add(f"Interaction with {kind}: {med}", section_label, excerpt,
                        f"{kind}: {med}")
                    break

    return out


def resolve_coverage_gap(patient, item, diagnosis: Optional[str] = None,
                         include_web: bool = True,
                         co_prescribed: Optional[List[str]] = None) -> CoverageResolution:
    """
    Everything findable about one uncovered drug, for this patient.

    Never raises. A resolution that finds nothing reports that it found nothing,
    which leaves the deterministic coverage warning standing on its own -- the
    behaviour before this module existed.
    """
    result = CoverageResolution(drug=item.medication_name)

    # fetch_label already swallows its own network errors, but the guard is here
    # too because this function PROMISES not to raise, and a promise that depends
    # on another function keeping its own is not a guarantee. A prescription
    # analysis must not fail because a drug label endpoint had a bad morning.
    # What the clinician typed may not be a name any drug database holds -- a
    # brand, a combination written as one token. Resolved first, and the
    # resolution travels on the result so the reader is told what it was read as.
    try:
        from backend.agents.drug_names import resolve as _resolve_name
        from backend.guidelines.knowledge_base import knowledge_base as _kb

        def _canonical(written: str):
            info = _kb.get_drug_info(_kb.normalize_drug_name(written)) or {}
            return info.get("name")

        resolved = _resolve_name(item.medication_name, canonical_from_kb=_canonical)
    except Exception:
        from backend.agents.drug_names import ResolvedName
        resolved = ResolvedName(item.medication_name, item.medication_name,
                                "AS_WRITTEN", "as written")
    result.resolved_name = resolved.to_dict()

    # CANDIDATES, TRIED IN ORDER, because resolving a name must never LOSE a label
    # that the written name would have found. "Augmentin" is indexed by openFDA;
    # this system's canonical record calls it "Amoxicillin-Clavulanate", which is
    # not - so resolving it and stopping there turned two findings into none.
    # A combination's first component is tried last: a label for one ingredient is
    # weaker evidence than one for the product, and is only worth having when
    # nothing better exists.
    route = getattr(item, "route", None)
    candidates: List[str] = []
    for candidate in (resolved.resolved, item.medication_name,
                      re.split(r"[-+]", resolved.resolved)[0].strip(),
                      re.split(r"[-+]", item.medication_name)[0].strip()):
        if candidate and len(candidate) >= 4 and candidate not in candidates:
            candidates.append(candidate)

    label = None
    for candidate in candidates:
        try:
            label = fetch_label(candidate, route)
        except Exception:
            label = None
        if label:
            if candidate != resolved.resolved:
                # The reader is told which name actually produced the document.
                result.resolved_name = dict(
                    result.resolved_name,
                    resolved_to=candidate,
                    notice=(f"“{item.medication_name}” looked up as {candidate}. "
                            "Confirm this is the medication intended before relying on "
                            "the safety information below."),
                )
            break

    if label:
        result.label_found = True
        result.label_source = _label_source(label, item.medication_name)
        try:
            result.findings.extend(findings_from_label(patient, item, label, co_prescribed))
        except Exception:
            pass

    if include_web:
        try:
            from backend.agents import web_search
            from backend.agents.filtration import filter_web_results

            if web_search.available():
                query = (f"{item.medication_name} contraindications warnings "
                         f"{diagnosis or ''}").strip()
                filtered = filter_web_results(web_search.search(query), query)
                result.web_verdicts = filtered.to_dict()["verdicts"]
                stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
                for citation in filtered.accepted:
                    result.findings.append(ExternalFinding(
                        drug=item.medication_name,
                        concern="Web-sourced safety context",
                        section="WEB PAGE",
                        excerpt=citation.get("verbatim_passage", "")[:900],
                        source_label=f"Web - {citation.get('source_site')}",
                        source_kind="WEB",
                        source_url=citation.get("source_url", ""),
                        matched_on=f"drug outside knowledge base: {item.medication_name}",
                        retrieved_at=citation.get("retrieved_at", stamp),
                    ))
        except Exception:
            pass

    result.resolved = bool(result.findings)
    if result.resolved:
        result.note = (
            f"{len(result.findings)} external finding(s) for {item.medication_name}, which no "
            "clinical safety rule could assess. Each is quoted verbatim from the source named "
            "beside it and matched to a detail recorded for this patient."
        )
    elif result.label_found:
        result.note = (
            f"A regulatory label was found for {item.medication_name}, but nothing in it matched "
            "this patient's recorded allergies, renal or hepatic status, pregnancy status or home "
            "medications. That is an absence of a match, not a finding of safety."
        )
    else:
        result.note = (
            f"No regulatory label and no admissible web source was found for "
            f"{item.medication_name}. The coverage warning stands unresolved and clinician review "
            "of this medication is required."
        )
    return result


def _coverage_gaps(drug: str) -> List[str]:
    """
    The safety domains the knowledge base holds nothing on for this drug.

    Read from the drug record rather than inferred: a PARTIAL entry names its own
    gaps, and those names are what the clinician is told went unassessed.
    """
    try:
        from backend.guidelines.knowledge_base import knowledge_base

        info = knowledge_base.get_drug_info(knowledge_base.normalize_drug_name(drug)) or {}
        if info.get("knowledge_coverage") == "PARTIAL":
            return list(info.get("coverage_gaps") or [])
        return []
    except Exception:
        return []


def _gap_text(gaps: List[str]) -> str:
    return ", ".join(g.replace("_", " ") for g in gaps)


def national_evidence_for(drug: str, diagnosis: Optional[str], k: int = 3) -> List[Dict[str, Any]]:
    """
    What the HELD corpus says about this drug: ICMR, NCDC, WHO, the antibiogram.

    The left-hand column of the side-by-side. Retrieved per drug rather than per
    diagnosis, because a clinician comparing sources on piperacillin-tazobactam
    needs the passages about that agent, not the ones about the syndrome.

    Restricted to passages carrying antimicrobial authority. A cancer consensus
    document that mentions the drug in passing is not the national position on it,
    and placing one opposite a regulatory label would invite exactly the
    comparison it cannot support.
    """
    try:
        from backend.agents.provenance import mark_held
        from backend.rag.retrieve import retrieve

        query = f"{drug} {diagnosis or ''} dose contraindications".strip()
        result = retrieve(query, k=k + 3)
        if result.refused:
            return []
        out = []
        for chunk in result.chunks:
            if not chunk.carries_antimicrobial_authority:
                continue
            if drug.split("-")[0].lower()[:6] not in chunk.text.lower():
                continue
            out.append(mark_held(chunk.to_citation()))
            if len(out) >= k:
                break
        return out
    except Exception:
        return []


def evidence_for_items(patient, items, warnings, diagnosis: Optional[str] = None,
                       include_web: bool = True) -> List[Dict[str, Any]]:
    """
    Evidence for every prescribed drug, ESCALATING ONLY WHEN IT HAS TO.

    The order is the point, and it is the same order the precedence hierarchy
    already states:

        1. THE HELD NATIONAL CORPUS FIRST. ICMR, NCDC, WHO, the antibiogram. If a
           passage carrying antimicrobial authority names this drug, that is the
           answer, and nothing external is consulted at all. A national guideline
           does not need corroboration from a foreign regulator, and fetching one
           anyway invites a reader to weigh two sources the hierarchy has already
           ranked.

        2. ONLY IF NOTHING IS HELD, go outside: the drug's regulatory label, and
           the web where a provider is configured -- every web result judged by
           the filtration agent before it can be quoted.

    So a drug the national guidelines cover is answered by the national
    guidelines. A drug they do not cover -- a new agent, an unusual indication --
    is answered by whatever external source can be found and cited, clearly marked
    as external. The clinician always sees WHICH tier answered.

    `in_knowledge_base` is still read from the ENGINE'S OWN OUTPUT rather than by
    re-checking the knowledge base here. Two components answering "was this drug
    assessed?" independently is two components that can disagree, and the answer
    the clinician acts on has to be the one the rules actually used.
    """
    uncovered = {
        w.prescribed_drug for w in warnings
        if getattr(w, "rule_id", None) == "COVERAGE-001"
    }

    out: List[Dict[str, Any]] = []
    all_names = [i.medication_name for i in items]

    for item in items:
        drug = item.medication_name
        others = [n for n in all_names if n != drug]
        national = national_evidence_for(drug, diagnosis)
        gaps = _coverage_gaps(drug)

        # SAFETY CHECKS RUN FOR EVERY DRUG. Allergy cross-reactivity and drug
        # interactions are looked up whether or not the national corpus names the
        # agent, because a contraindication does not stop applying to this patient
        # because a guideline mentions the drug. The national-first ordering below
        # governs GUIDANCE - what to prescribe and how to dose it - which is a
        # different question from whether this particular patient can take it.
        resolution = resolve_coverage_gap(patient, item, diagnosis, include_web, others).to_dict()

        # ...and the guidance tier is reported separately from those findings.
        answered_nationally = bool(national) and drug not in uncovered and not gaps
        resolution.update({
            "source_tier": "NATIONAL_GUIDELINE" if answered_nationally else "EXTERNAL_FALLBACK",
            "escalated_to_external": not answered_nationally,
            "national_evidence": national,
            "coverage_gaps": gaps,
            "in_knowledge_base": drug not in uncovered,
        })

        if answered_nationally:
            resolution["note"] = (
                f"Guidance: answered by the held national corpus, {len(national)} passage(s) naming "
                f"{drug} with antimicrobial authority, and every safety domain assessed by the "
                "rules. " + (
                    f"Safety: {resolution['finding_count']} additional finding(s) from the "
                    "regulatory label matched this patient."
                    if resolution["finding_count"] else
                    "Safety: nothing in the regulatory label matched this patient's recorded details."
                )
            )
        elif gaps:
            resolution["note"] = (
                f"The rules could not assess {drug} on: {_gap_text(gaps)}. The national passages "
                f"naming it ({len(national)} held) do not cover those domains, so external sources "
                "were consulted. " + resolution["note"]
            )
        else:
            resolution["note"] = (
                f"No held national passage names {drug}, so external sources were consulted. "
                + resolution["note"]
            )

        resolution["comparison_note"] = (
            "Assessed by the deterministic rules."
            if resolution["in_knowledge_base"] else
            "NOT assessed by any deterministic rule - this drug is outside the validated "
            "knowledge base, and the coverage warning stands."
        )
        out.append(resolution)
    return out


# Retained under the original name: the endpoint and tests written against the
# coverage-gap-only behaviour keep working, and callers that want every drug ask
# for it explicitly above.
def resolve_uncovered_items(patient, items, warnings, diagnosis: Optional[str] = None,
                            include_web: bool = True) -> List[Dict[str, Any]]:
    """Only the drugs the deterministic engine reported as uncovered."""
    uncovered = {
        w.prescribed_drug for w in warnings
        if getattr(w, "rule_id", None) == "COVERAGE-001"
    }
    if not uncovered:
        return []
    return [
        resolve_coverage_gap(patient, item, diagnosis, include_web).to_dict()
        for item in items if item.medication_name in uncovered
    ]
