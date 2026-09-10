"""Sanity-check eval/questions.json: unique ids, valid types/splits, and every evidence quote
actually appears verbatim (whitespace-normalised) in the named processed document."""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hybrid_rag.config import settings  # noqa: E402
from hybrid_rag.loaders import read_processed  # noqa: E402


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def main() -> int:
    data = json.loads((settings.data_dir.parent / "eval" / "questions.json").read_text())
    qs = data["questions"]
    docs = {d.doc_id: norm(d.text) for d in read_processed(settings.processed_dir / "docs.jsonl")}
    ids = [q["id"] for q in qs]
    assert len(ids) == len(set(ids)), "duplicate ids"
    bad = 0
    for q in qs:
        assert q["type"] in data["types"] and q["split"] in data["splits"], q["id"]
        for ev in q["evidence"]:
            if ev["doc_id"] not in docs:
                print(f"{q['id']}: unknown doc {ev['doc_id']}"); bad += 1
            elif norm(ev["quote"]) not in docs[ev["doc_id"]]:
                print(f"{q['id']}: quote not found in {ev['doc_id']}: {ev['quote'][:70]!r}"); bad += 1
    print(f"{len(qs)} questions | types {dict(Counter(q['type'] for q in qs))} | splits {dict(Counter(q['split'] for q in qs))}")
    print(f"verification status: {dict(Counter(q['verification']['status'] for q in qs))}")
    print("all evidence quotes found" if not bad else f"{bad} problems")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
