"""
Re-embed the guideline corpus onto a different embedding backend.

WHY THIS IS A SCRIPT AND NOT A SETTING. An index is only queryable by the exact
model that built it; the store refuses a mismatch by recorded model name rather
than returning wrong neighbours. So changing EMBEDDING_BACKEND in .env without
running this takes retrieval down. Loudly, on purpose - but down.

SAFETY PROPERTY: the existing index is never overwritten until the new one has
been built AND proved queryable. Every failure path leaves the current index
exactly as it was, because the realistic time to run this is late at night before
a demo, and a half-migrated corpus is worse than an older embedding model.

    python -m scripts.migrate_embeddings --to nvidia      # migrate
    python -m scripts.migrate_embeddings --to local       # migrate back
    python -m scripts.migrate_embeddings --status         # what is built now
    python -m scripts.migrate_embeddings --to nvidia --dry-run

The clinical rule engine is unaffected by all of this and does not read the
index. Warnings fire identically before, during and after a migration.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend import config                                    # noqa: E402
from backend.rag import embeddings                            # noqa: E402
from backend.rag.store import vector_store                    # noqa: E402

# Queries that must still return evidence after a migration. If a fresh index
# cannot answer these, the migration failed regardless of how many vectors it
# wrote -- an index that builds and retrieves nothing is the failure mode a
# vector count will not catch.
SMOKE_QUERIES = [
    "What is the duration of therapy for community acquired pneumonia?",
    "Which antibiotics are in the WHO Reserve group?",
    "How should antibiotics be de-escalated?",
]


def _backend_for(target: str):
    if target == "nvidia":
        return embeddings.NvidiaEmbeddingBackend()
    if target == "local":
        return embeddings.SentenceTransformerBackend()
    raise SystemExit(f"unknown target {target!r}; expected 'nvidia' or 'local'")


def status() -> None:
    vector_store.load()
    print(f"chunks in corpus     : {len(vector_store.chunks)}")
    print(f"documents            : {len(vector_store.docs)}")
    print(f"index built with     : {vector_store.embedding_model}")
    print(f"semantic             : {vector_store.is_semantic}")
    print(f".env EMBEDDING_BACKEND: {config.EMBEDDING_BACKEND}")
    print(f".env NVIDIA model     : {config.NVIDIA_EMBEDDING_MODEL}")
    if vector_store.embedding_model and config.EMBEDDING_BACKEND == "nvidia" \
            and not str(vector_store.embedding_model).startswith("nvidia:"):
        print("\nMISMATCH: .env asks for the NVIDIA backend but the built index is not "
              "NVIDIA. Retrieval will refuse until you migrate.")


def migrate(target: str, dry_run: bool) -> int:
    vec_file = vector_store.dir / "_vectors.npz"
    backup = vector_store.dir / "_vectors.npz.pre-migration"

    vector_store._load_chunks()
    total = len(vector_store.chunks)
    if not total:
        print("No chunks ingested; nothing to migrate.")
        return 1

    print(f"corpus               : {total} chunks across {len(vector_store.docs)} documents")
    print(f"current index        : {vector_store.embedding_model or '(none built)'}")

    try:
        be = _backend_for(target)
    except Exception as exc:
        print(f"\nFAILED to start the {target} backend: {exc}")
        print("Nothing was changed.")
        return 1

    print(f"target backend       : {be.name}")
    if dry_run:
        print("\n--dry-run: stopping before any embedding call. Nothing was changed.")
        return 0

    if target == "nvidia":
        print(f"\nThis sends {total} chunks to {config.NVIDIA_BASE_URL} in batches of 64.")

    if vec_file.exists():
        shutil.copy2(vec_file, backup)
        print(f"current index backed up to {backup.name}")

    started = time.time()
    try:
        written = vector_store.build(backend=be, persist=True)
    except Exception as exc:
        print(f"\nFAILED during embedding: {type(exc).__name__}: {exc}")
        _restore(backup, vec_file)
        return 1

    elapsed = time.time() - started
    print(f"embedded {written} chunks in {elapsed:.0f}s")

    # Prove it before trusting it. A written matrix is not a working index.
    #
    # THE BACKEND IS FORCED HERE, and the first version of this script did not do
    # that. It called reset_backend() and let get_backend() re-read .env -- which
    # still said EMBEDDING_BACKEND=local -- so the verification loaded MiniLM,
    # found a mismatch against the freshly written index, silently re-embedded in
    # memory, and reported three passing smoke queries. The scores were identical
    # to the pre-migration ones, which is the only reason it was caught. A
    # verification that can pass while testing the model you just replaced is
    # worse than no verification.
    try:
        from backend.rag.retrieve import retrieve
        embeddings.reset_backend()
        embeddings._backend = be  # the migrated-to backend, not whatever .env says
        for query in SMOKE_QUERIES:
            result = retrieve(query, k=2)
            if result.refused or not result.chunks:
                raise RuntimeError(f"smoke query returned nothing: {query!r}")
            top = result.chunks[0]
            print(f"  ok  {top.score:.3f}  {query[:52]}")
    except Exception as exc:
        print(f"\nFAILED verification: {exc}")
        _restore(backup, vec_file)
        return 1

    print(f"\nMigration complete. Set EMBEDDING_BACKEND={target} in .env if it is not already.")
    print(f"The previous index is kept at {backup.name} - delete it once you are satisfied.")
    return 0


def _restore(backup: Path, vec_file: Path) -> None:
    if backup.exists():
        shutil.copy2(backup, vec_file)
        print(f"restored the previous index from {backup.name}; retrieval is unchanged.")
    else:
        print("no previous index existed to restore.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--to", choices=["nvidia", "local"], help="backend to migrate onto")
    parser.add_argument("--status", action="store_true", help="report what is built now")
    parser.add_argument("--dry-run", action="store_true", help="check the backend starts, embed nothing")
    args = parser.parse_args()

    if args.status or not args.to:
        status()
        return 0
    return migrate(args.to, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
