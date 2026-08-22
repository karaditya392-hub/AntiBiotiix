"""
DailyMed (FDA Structured Product Label) ingester.

Fetches FDA drug labels for the antimicrobials in the project formulary and
extracts the safety-relevant sections into citable source files.

Why this exists
---------------
The ICMR guideline portal is organised by infection syndrome and contains no
cross-cutting sections on allergy cross-reactivity, renal/hepatic dose
adjustment, or drug interactions. Those are exactly what the ALLERGY-*, RENAL-*,
HEPATIC-*, DDI-* and VULN-* rules assert. FDA SPLs carry that content as legally
mandated label sections, are public domain, and expose stable per-label
identifiers (setid + spl_version + published_date).

Provenance honesty
------------------
These are UNITED STATES regulatory product labels, not Indian national guidance
and not clinical practice guidelines. Indian CDSCO labelling may differ. Every
file written here records source_type: fda_structured_product_label so a citation
generated from it can never be presented as ICMR or WHO guidance.

Usage
-----
    python scripts/ingest_dailymed.py --all
    python scripts/ingest_dailymed.py --drug nitrofurantoin
    python scripts/ingest_dailymed.py --report
    python scripts/ingest_dailymed.py --all --offline    # use cached XML only
"""
from __future__ import annotations

import argparse
import datetime
import html
import json
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.request

API = "https://dailymed.nlm.nih.gov/dailymed/services/v2"
HUMAN_URL = "https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={setid}"

SOURCES = pathlib.Path("backend/guidelines/data/sources/dailymed")
CACHE = pathlib.Path(".cache/dailymed")

# Maps the project's KB keys to the DailyMed generic name to search for.
FORMULARY = {
    "amoxicillin": "amoxicillin",
    "amoxicillin_clavulanate": "amoxicillin and clavulanate potassium",
    "ciprofloxacin": "ciprofloxacin",
    "levofloxacin": "levofloxacin",
    "azithromycin": "azithromycin",
    "clarithromycin": "clarithromycin",
    "metronidazole": "metronidazole",
    "ceftriaxone": "ceftriaxone",
    "piperacillin_tazobactam": "piperacillin and tazobactam",
    "meropenem": "meropenem",
    "vancomycin": "vancomycin hydrochloride",
    "doxycycline": "doxycycline hyclate",
    "nitrofurantoin": "nitrofurantoin",
    "linezolid": "linezolid",
    "gentamicin": "gentamicin sulfate",
}

# LOINC section codes, verified against a live legacy-format label
# (nitrofurantoin) and a live PLR-format label (linezolid).
WANTED = {
    "34070-3": "Contraindications",
    "34071-1": "Warnings",                      # legacy format
    "43685-7": "Warnings and Precautions",      # PLR format
    "42232-9": "Precautions",                   # legacy format
    "34073-7": "Drug Interactions",             # PLR only
    "43684-0": "Use in Specific Populations",   # PLR only
    "42228-7": "Pregnancy",
    "77290-5": "Lactation",
    "34081-0": "Pediatric Use",
    "34082-8": "Geriatric Use",
    "34068-7": "Dosage and Administration",     # renal adjustment often lives here
    "34066-1": "Boxed Warning",
}

# Which rule families each section can support. Recorded in front-matter so the
# corpus can be audited against the rule catalog.
SECTION_RULE_HINTS = {
    "Contraindications": ["ALLERGY", "RENAL", "HEPATIC", "VULNERABLE_POPULATION"],
    "Warnings": ["ALLERGY", "RENAL", "HEPATIC", "DRUG_INTERACTION"],
    "Warnings and Precautions": ["ALLERGY", "RENAL", "HEPATIC", "DRUG_INTERACTION"],
    "Precautions": ["DRUG_INTERACTION", "VULNERABLE_POPULATION"],
    "Drug Interactions": ["DRUG_INTERACTION"],
    "Use in Specific Populations": ["VULNERABLE_POPULATION", "RENAL", "HEPATIC"],
    "Pregnancy": ["VULNERABLE_POPULATION"],
    "Lactation": ["VULNERABLE_POPULATION"],
    "Pediatric Use": ["VULNERABLE_POPULATION"],
    "Geriatric Use": ["VULNERABLE_POPULATION"],
    "Dosage and Administration": ["RENAL", "HEPATIC"],
    "Boxed Warning": ["ALLERGY", "DRUG_INTERACTION", "VULNERABLE_POPULATION"],
}


def _get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "S11-CDSS-ingester/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def find_label(generic: str, offline: bool = False) -> dict | None:
    """Return metadata for the most recently published label for a generic name."""
    cache = CACHE / f"{generic.replace(' ', '_')}.search.json"
    if cache.exists() and offline:
        return json.loads(cache.read_text(encoding="utf-8"))
    if offline:
        return None
    url = f"{API}/spls.json?drug_name={urllib.parse.quote(generic)}&pagesize=25"
    data = json.loads(_get(url, timeout=45))
    rows = data.get("data") or []
    if not rows:
        return None

    def pub(row):
        try:
            return datetime.datetime.strptime(row["published_date"], "%b %d, %Y")
        except Exception:
            return datetime.datetime.min

    best = max(rows, key=pub)
    best["total_labels_available"] = data.get("metadata", {}).get("total_elements")
    CACHE.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(best, indent=1), encoding="utf-8")
    return best


def fetch_xml(setid: str, offline: bool = False) -> str | None:
    cache = CACHE / f"{setid}.xml"
    if cache.exists():
        return cache.read_text(encoding="utf-8", errors="ignore")
    if offline:
        return None
    xml = _get(f"{API}/spls/{setid}.xml", timeout=90).decode("utf-8", "ignore")
    CACHE.mkdir(parents=True, exist_ok=True)
    cache.write_text(xml, encoding="utf-8")
    return xml


def _clean(fragment: str) -> str:
    """SPL XHTML fragment -> readable text, preserving list and paragraph breaks."""
    t = re.sub(r"<(?:br|BR)\s*/?>", "\n", fragment)
    t = re.sub(r"</(?:paragraph|item|td|tr|title)>", "\n", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    t = t.replace("\xa0", " ")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n\s*\n+", "\n\n", t)
    return "\n".join(line.strip() for line in t.split("\n")).strip()


def extract_sections(xml: str) -> list[tuple[str, str]]:
    """Return [(section_name, text)] for the safety sections we care about."""
    out: list[tuple[str, str]] = []
    # Each <component><section> ... </section></component>; match non-greedily on
    # the code attribute then take text up to the next section boundary.
    for m in re.finditer(r'<section[^>]*>(.*?)</section>', xml, flags=re.S):
        block = m.group(1)
        code = re.search(r'<code code="([0-9-]+)"', block)
        if not code or code.group(1) not in WANTED:
            continue
        name = WANTED[code.group(1)]
        # Drop nested subsections' duplicate codes but keep their prose.
        text = _clean(block)
        # Strip a leading repeat of the section title.
        text = re.sub(r"^" + re.escape(name) + r"\s*", "", text, flags=re.I)
        if len(text) < 40:
            continue
        out.append((name, text))
    # De-duplicate by name, keeping the longest capture (outermost section).
    best: dict[str, str] = {}
    for name, text in out:
        if len(text) > len(best.get(name, "")):
            best[name] = text
    order = list(WANTED.values())
    return sorted(best.items(), key=lambda kv: order.index(kv[0]))


def write_source(kb_key: str, generic: str, meta: dict, sections: list[tuple[str, str]]) -> pathlib.Path:
    setid = meta["setid"]
    hints = sorted({h for name, _ in sections for h in SECTION_RULE_HINTS.get(name, [])})
    fm = f"""---
document_id: DAILYMED-{kb_key.upper().replace('_', '-')}
title: "FDA Structured Product Label — {generic}"
label_title: "{meta.get('title', '').replace('"', "'")[:200]}"
kb_drug_key: {kb_key}
issuing_org: "US Food and Drug Administration (label published via NLM DailyMed)"
geographic_scope: "United States (US product labelling)"
setid: {setid}
spl_version: {meta.get('spl_version')}
published_date: "{meta.get('published_date')}"
source_url: "{HUMAN_URL.format(setid=setid)}"
source_type: fda_structured_product_label
retrieved_at: "{datetime.date.today().isoformat()}"
sections_extracted: {json.dumps([n for n, _ in sections])}
supports_rule_categories: {json.dumps(hints)}
provenance_note: >
  Extracted from the FDA Structured Product Label via the NLM DailyMed API.
  This is US regulatory product labelling, NOT Indian national guidance and NOT
  a clinical practice guideline. Indian CDSCO labelling may differ. It sits
  outside the ICMR/WHO precedence hierarchy and must be cited as product
  labelling, never as ICMR or WHO guidance. Content is reproduced verbatim from
  the label; section boundaries are derived from LOINC section codes.
label_selection_note: >
  {meta.get('total_labels_available', 'multiple')} labels exist for this generic
  (different manufacturers). The most recently published one was selected.
  Manufacturer labels for the same generic can differ in wording.
---

"""
    body = []
    for name, text in sections:
        body.append(f"## {name}\n\n{text}\n")
    SOURCES.mkdir(parents=True, exist_ok=True)
    out = SOURCES / f"{kb_key}.md"
    out.write_text(fm + "\n".join(body), encoding="utf-8")
    return out


def ingest(kb_key: str, generic: str, offline: bool = False) -> tuple[bool, str]:
    meta = find_label(generic, offline=offline)
    if not meta:
        return False, "no label found"
    xml = fetch_xml(meta["setid"], offline=offline)
    if not xml:
        return False, "no cached XML (run without --offline)"
    sections = extract_sections(xml)
    if not sections:
        return False, "no target sections in label"
    out = write_source(kb_key, generic, meta, sections)
    names = ", ".join(n for n, _ in sections)
    return True, f"{out.name}: {len(sections)} sections ({names})"


def report() -> None:
    if not SOURCES.exists():
        print("nothing ingested yet")
        return
    files = sorted(SOURCES.glob("*.md"))
    print(f"{'drug':26} {'sections':>8} {'words':>7}  supports")
    print("-" * 78)
    for f in files:
        t = f.read_text(encoding="utf-8")
        secs = len(re.findall(r"^## ", t, flags=re.M))
        sup = re.search(r"^supports_rule_categories: (.+)$", t, flags=re.M)
        cats = ",".join(json.loads(sup.group(1))) if sup else ""
        print(f"{f.stem:26} {secs:>8} {len(t.split()):>7}  {cats}")
    print("-" * 78)
    print(f"{len(files)}/{len(FORMULARY)} formulary drugs ingested")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--all", action="store_true")
    p.add_argument("--drug", help="single KB key, e.g. nitrofurantoin")
    p.add_argument("--offline", action="store_true", help="use cached data only")
    p.add_argument("--report", action="store_true")
    a = p.parse_args()

    if a.report:
        report()
        return 0

    targets = FORMULARY if a.all else ({a.drug: FORMULARY[a.drug]} if a.drug in FORMULARY else {})
    if not targets:
        p.error("use --all, or --drug with one of: " + ", ".join(FORMULARY))

    failures = 0
    for kb_key, generic in targets.items():
        try:
            ok, msg = ingest(kb_key, generic, offline=a.offline)
        except Exception as exc:
            ok, msg = False, f"{type(exc).__name__}: {exc}"
        print(f"  {'OK ' if ok else 'FAIL'} {kb_key:26} {msg}")
        if not ok:
            failures += 1
        if not a.offline:
            time.sleep(0.4)
    print(f"\n{len(targets) - failures}/{len(targets)} ingested")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
