"""
Shared driver for the guideline-batch ingestion scripts.

The batch scripts (scripts/ingest_mohfw_stg.py, scripts/ingest_national_guidelines.py)
exist to be provenance records: the source PDFs are not committed, only the corpus
JSON derived from them, so the manifest in each script is the only surviving statement
of what was ingested and what was claimed about it. This module holds the mechanical
part they have in common so those files stay manifests rather than programs.

Nothing here decides anything about a document. It copies the manifest through to
backend.rag.ingest and refuses to proceed when a source file is missing or when the
index would be persisted in a weaker form than the one already committed.
"""
from __future__ import annotations

import argparse
import json
import pathlib
from dataclasses import asdict
from typing import Any, Dict, List

from backend.rag.ingest import ingest_pdf

OUT_DIR = pathlib.Path("backend/guidelines/data/rag")


def run_batch(manifests: List[Dict[str, Any]], common: Dict[str, Any],
              default_pdf_dir: str, description: str) -> int:
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--pdf-dir", type=pathlib.Path, default=pathlib.Path(default_pdf_dir))
    p.add_argument("--out", type=pathlib.Path, default=OUT_DIR)
    p.add_argument("--rebuild-index", action="store_true",
                   help="Re-embed the whole corpus after ingesting (required before serving)")
    args = p.parse_args()

    missing = [m["source_file"] for m in manifests
               if not (args.pdf_dir / m["source_file"]).exists()]
    if missing:
        print(f"REFUSING: {len(missing)} source PDF(s) not found in {args.pdf_dir}:")
        for name in missing:
            print(f"  {name}")
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    total = 0
    for meta in manifests:
        pdf = args.pdf_dir / meta["source_file"]
        print(meta["document_id"])
        # Manifest wins over the batch defaults: a document that does not belong at
        # the batch's precedence rank has to be able to say so.
        doc, chunks = ingest_pdf(pdf, {**common, **meta})
        payload = {"document": asdict(doc), "chunks": [asdict(c) for c in chunks]}
        out = args.out / f"{doc.document_id}.json"
        out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        print(f"  {doc.page_count} pages -> {len(chunks)} chunks -> {out}")
        total += len(chunks)
    print(f"\n{len(manifests)} documents, {total} chunks")

    if args.rebuild_index:
        return rebuild_index(args.out)
    print("\nIndex NOT rebuilt. Retrieval stays disabled until this is re-run with "
          "--rebuild-index.")
    return 0


def rebuild_index(out_dir: pathlib.Path) -> int:
    """
    Re-embed the whole corpus.

    The committed .npz is keyed to the chunk count, so adding documents without
    re-embedding leaves store.load() refusing a misaligned index -- which silently
    disables retrieval for the whole corpus, not just the new files.
    """
    from backend.rag.embeddings import get_backend
    from backend.rag.store import GuidelineVectorStore

    be = get_backend()
    if not be.is_semantic:
        print(f"REFUSING to persist an index built with {be.name}: the committed index is "
              f"semantic, and overwriting it lexically would silently degrade retrieval on "
              f"every machine that CAN load the model. Install sentence-transformers, cache "
              f"all-MiniLM-L6-v2, and re-run.")
        return 1
    store = GuidelineVectorStore(out_dir)
    n = store.build(backend=be, persist=True)
    print(f"re-embedded {n} chunks with {be.name}")
    return 0
