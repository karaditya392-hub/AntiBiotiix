"""
Re-measure the cross-source relevance gates for the built embedding model.

Companion to scripts/calibrate_relevance_floor.py, and needed for the same
reason: MIN_SCORE_ABSOLUTE and MIN_SCORE_RELATIVE in
backend/guidelines/cross_source.py are measurements of one model's score
distribution, not constants. The comment beside them records that the absolute
bar was set to 0.50 to sit above the 0.45 retrieval floor; when the floor moves
because the embedding model changed, that relationship has to be re-established
or national guidelines get gated out of syndromes their own chapters cover.

Method is the one recorded in that comment: over a set of syndrome topics, count
how often NCDC-NTG-AMR-2016 -- a national antimicrobial guideline with a
syndromic therapy chapter -- is shown, and how many off-scope documents are
admitted. A gate that buys NCDC coverage by admitting an oncology or
hypertension document has bought nothing.

    python -m scripts.calibrate_cross_source_gates

Retrieval runs once per topic; thresholds are then evaluated offline against
those scores, so the sweep costs 11 queries rather than 11 x settings.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.config import ANTIMICROBIAL_CONTENT_DOCUMENT_IDS  # noqa: E402
from backend.guidelines.cross_source import (                  # noqa: E402
    MIN_SCORE_ABSOLUTE, MIN_SCORE_RELATIVE,
)
from backend.rag.store import vector_store                     # noqa: E402

TOPICS = [
    "community acquired pneumonia",
    "urinary tract infection",
    "enteric fever",
    "infective endocarditis",
    "acute bacterial meningitis",
    "skin and soft tissue infection",
    "intra-abdominal infection",
    "febrile neutropenia",
    "acute gastroenteritis",
    "surgical prophylaxis",
    "hospital acquired pneumonia",
]

NCDC = "NCDC-NTG-AMR-2016"

# Documents that must never be admitted to an infection topic. If a gate lets one
# of these in, the gate is wrong however good its NCDC coverage looks.
OFF_SCOPE_MARKERS = (
    "CANCER", "ONCOLOGY", "BREAST", "CERVIX", "GALLBLADDER", "GASTRIC",
    "COLORECTAL", "MYELOMA", "OVARIAN", "DIABETES", "T1DM", "AYURVED",
    "ETHIC", "BSL3", "BIOREPOSITORY", "STEM-CELL",
)

SETTINGS = [
    (0.50, 0.80),   # current
    (0.40, 0.80),
    (0.35, 0.80),
    (0.33, 0.80),
    (0.33, 0.82),
    (0.33, 0.78),
    (0.30, 0.80),
]


def is_off_scope(document_id: str) -> bool:
    up = document_id.upper()
    return (any(m in up for m in OFF_SCOPE_MARKERS)
            and document_id not in ANTIMICROBIAL_CONTENT_DOCUMENT_IDS)


def main() -> int:
    vector_store.load()
    print(f"index built with : {vector_store.embedding_model}")
    print(f"current gates    : absolute {MIN_SCORE_ABSOLUTE}  relative {MIN_SCORE_RELATIVE}")
    print(f"topics           : {len(TOPICS)}")
    print()

    # One retrieval per topic; best score per document.
    per_topic = {}
    for topic in TOPICS:
        best = defaultdict(float)
        for hit in vector_store.search(topic, k=60):
            if hit.score > best[hit.document_id]:
                best[hit.document_id] = float(hit.score)
        per_topic[topic] = dict(best)
        top = max(best.values()) if best else 0.0
        ncdc = best.get(NCDC)
        print(f"  {topic:<34} best {top:.4f}   NCDC {ncdc:.4f}" if ncdc
              else f"  {topic:<34} best {top:.4f}   NCDC not retrieved")

    print()
    print(f"{'absolute':>9} {'relative':>9} {'NCDC shown':>12} {'avg shown':>10} {'off-scope':>10}")
    for absolute, relative in SETTINGS:
        ncdc_shown, shown_counts, off_scope = 0, [], 0
        for topic, best in per_topic.items():
            if not best:
                continue
            threshold = max(absolute, max(best.values()) * relative)
            passing = [d for d, s in best.items() if s >= threshold]
            shown_counts.append(len(passing))
            ncdc_shown += NCDC in passing
            off_scope += sum(1 for d in passing if is_off_scope(d))
        avg = sum(shown_counts) / len(shown_counts) if shown_counts else 0
        flag = "  <-- current" if (absolute, relative) == (MIN_SCORE_ABSOLUTE, MIN_SCORE_RELATIVE) else ""
        print(f"{absolute:>9.2f} {relative:>9.2f} {ncdc_shown:>8}/{len(per_topic):<3} "
              f"{avg:>10.1f} {off_scope:>10}{flag}")

    print()
    print("Choose the setting that buys NCDC coverage with zero off-scope admissions,")
    print("and record the measurement in the comment beside the constants. This script")
    print("does not edit them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
