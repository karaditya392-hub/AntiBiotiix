"""
Re-measure the retrieval relevance floor for whatever backend is built.

WHY THIS HAS TO BE RUN AFTER EVERY EMBEDDING MIGRATION. The floor in
backend/rag/retrieve.py is not a universal constant; it is a measurement of one
model's score distribution. A different embedding model scores everything
differently, so a floor carried across a migration is a number that no longer
means what its comment says it means -- and it fails in the direction that
matters, either admitting off-domain text or refusing legitimate clinical
questions.

The method is the one recorded in retrieve.py: score legitimate clinical queries
and off-domain queries, and report the gap between the lowest legitimate score
and the highest off-domain one. Only queries that survive unknown_entities() are
counted, because the rest never reach the floor.

    python -m scripts.calibrate_relevance_floor

Reports the measured separation and what the floor should be. It does not edit
the constant: moving a clinical safety threshold is a decision with a name on it,
not something a script does while nobody is looking.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.rag.embeddings import get_backend            # noqa: E402
from backend.rag.retrieve import active_floor, unknown_entities  # noqa: E402
from backend.rag.store import vector_store                # noqa: E402

# Clinical questions the corpus genuinely answers. Extended from the six in
# tests/test_rag_retrieval.py: a floor measured on six queries is a floor with
# six chances to be wrong.
LEGITIMATE = [
    "first line treatment for uncomplicated cystitis",
    "nitrofurantoin renal impairment",
    "WHO Reserve group antibiotics",
    "duration of therapy community acquired pneumonia",
    "treatment of typhoid fever",
    "septic shock empiric therapy",
    "empirical therapy for acute bacterial meningitis in adults",
    "how should antibiotics be de-escalated",
    "WHO AWaRe access watch reserve classification",
    "empirical antibiotic for hospital acquired pneumonia",
    "management of scrub typhus",
    "antibiotic prophylaxis for surgical site infection",
    "treatment of acute pyelonephritis",
    "carbapenem resistant enterobacteriaceae treatment options",
    "dosing of vancomycin in renal impairment",
    "management of febrile neutropenia",
    "antimicrobial stewardship programme components",
    "treatment of leptospirosis",
    "empirical therapy for intra-abdominal infection",
    "duration of antibiotic therapy for bacteraemia",
    "management of clostridioides difficile infection",
    "azithromycin resistance in enteric fever",
    "antibiotic choice in pregnancy",
    "paediatric dosing of amoxicillin",
    "treatment of cellulitis and skin abscess",
    "colistin use in multidrug resistant infection",
    "blood culture collection before antibiotics",
    "switching intravenous antibiotics to oral",
    "treatment of acute otitis media in children",
    "management of catheter associated urinary tract infection",
]

# Questions the corpus must refuse. Ordinary English, no clinical content.
OFF_DOMAIN = [
    "how do I fix a leaking kitchen tap",
    "best pizza recipe in Naples",
    "what is the capital of France",
    "how to train a puppy",
    "how do I change a bicycle tyre",
    "cheapest flights to Singapore in December",
    "how to write a cover letter for a job",
    "what time does the football match start",
    "best budget smartphone camera comparison",
    "how to grow tomatoes on a balcony",
    "rules of the card game bridge",
    "how do I reset a wifi router",
    "history of the Roman aqueducts",
    "how to tie a bow tie",
    "best hiking trails near Manali",
]


def best_score(query: str) -> float | None:
    """Top cosine similarity for a query, or None if it never reaches the floor."""
    if unknown_entities(query):
        return None
    chunks = vector_store.search(query, k=1)
    return float(chunks[0].score) if chunks else None


def main() -> int:
    vector_store.load()
    backend = get_backend()
    print(f"index built with : {vector_store.embedding_model}")
    print(f"backend loaded   : {backend.name}")
    print(f"current floor    : {active_floor()}")
    print(f"corpus           : {len(vector_store.chunks)} chunks")
    if backend.name != vector_store.embedding_model:
        print("\nBACKEND MISMATCH - migrate before calibrating.")
        return 1

    print("\nscoring legitimate clinical queries...")
    legit = []
    for q in LEGITIMATE:
        s = best_score(q)
        if s is None:
            print(f"  (skipped, unknown entity) {q}")
            continue
        legit.append((s, q))

    print("scoring off-domain queries...")
    off = []
    for q in OFF_DOMAIN:
        s = best_score(q)
        if s is None:
            print(f"  (skipped, unknown entity) {q}")
            continue
        off.append((s, q))

    legit.sort()
    off.sort(reverse=True)
    lowest_legit, lowest_q = legit[0]
    highest_off, highest_q = off[0]
    margin = lowest_legit - highest_off

    print()
    print(f"lowest legitimate  {lowest_legit:.4f}  {lowest_q}")
    print(f"highest off-domain {highest_off:.4f}  {highest_q}")
    print(f"MARGIN             {margin:.4f}")
    print()
    if margin <= 0:
        print("NO FLOOR SEPARATES THESE SETS. A single threshold cannot both admit every")
        print("legitimate query and reject every off-domain one on this model. Retrieval")
        print("needs a second signal, not a different number.")
        return 1

    suggested = round(highest_off + margin / 2, 3)
    print(f"SUGGESTED FLOOR    {suggested}  (midway; rejects no legitimate query, admits no off-domain one)")
    print()
    print(f"current floor {active_floor()} would:")
    print(f"  refuse {sum(1 for s, _ in legit if s < active_floor())} of {len(legit)} legitimate queries")
    print(f"  admit  {sum(1 for s, _ in off if s >= active_floor())} of {len(off)} off-domain queries")
    print()
    print("Set RELEVANCE_FLOOR in backend/rag/retrieve.py deliberately, recording this")
    print("measurement in the comment beside it. This script does not edit the constant.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
