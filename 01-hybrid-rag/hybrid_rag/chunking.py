"""Three switchable chunking strategies (guide Phase 1.2).

* ``fixed``     — fixed-size character windows with overlap (the baseline).
* ``recursive`` — structure-aware: split on markdown headings first, then
                  recursively by paragraph/line/word inside oversized sections.
* ``semantic``  — paragraph embeddings; a new chunk starts wherever the cosine
                  distance between neighbouring paragraphs exceeds a percentile.

Every chunk records its character span in the source document, so section
heading and page number are resolved from the document, not guessed.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from typing import Callable, Sequence

import numpy as np
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .loaders import HEADING_RE, LoadedDocument, iter_headings

STRATEGIES = ("fixed", "recursive", "semantic")


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    collection: str
    source_path: str
    source_url: str
    title: str
    section: str
    page: int | None
    strategy: str
    chunk_index: int
    start: int
    end: int
    char_count: int
    text: str

    def metadata(self) -> dict:
        d = asdict(self)
        d.pop("text")
        d["page"] = -1 if self.page is None else self.page  # Chroma cannot store None
        return d


def _make_chunk(doc: LoadedDocument, strategy: str, idx: int, start: int, end: int, text: str) -> Chunk:
    key = f"{strategy}|{doc.doc_id}|{start}|{end}"
    cid = hashlib.sha1(key.encode()).hexdigest()[:16]
    return Chunk(
        chunk_id=cid, doc_id=doc.doc_id, collection=doc.collection, source_path=doc.source_path,
        source_url=doc.source_url, title=doc.title, section=doc.section_at(start), page=doc.page_at(start),
        strategy=strategy, chunk_index=idx, start=start, end=end, char_count=len(text), text=text,
    )


# --------------------------------------------------------------------------------------
# 1. fixed-size with overlap
# --------------------------------------------------------------------------------------
def chunk_fixed(doc: LoadedDocument, size: int = 800, overlap: int = 120) -> list[Chunk]:
    text = doc.text
    chunks: list[Chunk] = []
    start = 0
    idx = 0
    n = len(text)
    while start < n:
        end = min(n, start + size)
        if end < n:  # snap to a whitespace boundary so words are not cut
            ws = text.rfind(" ", start + size // 2, end)
            nl = text.rfind("\n", start + size // 2, end)
            snap = max(ws, nl)
            if snap > start:
                end = snap
        piece = text[start:end]
        if piece.strip():
            chunks.append(_make_chunk(doc, "fixed", idx, start, end, piece.strip()))
            idx += 1
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return chunks


# --------------------------------------------------------------------------------------
# 2. structure-aware recursive
# --------------------------------------------------------------------------------------
def _sections(text: str) -> list[tuple[int, int]]:
    """Character spans of heading-delimited sections (heading line included)."""
    bounds = [pos for pos, _, _ in iter_headings(text)]
    if not bounds or bounds[0] != 0:
        bounds.insert(0, 0)
    spans = []
    for i, b in enumerate(bounds):
        e = bounds[i + 1] if i + 1 < len(bounds) else len(text)
        if text[b:e].strip():
            spans.append((b, e))
    return spans


def chunk_recursive(doc: LoadedDocument, size: int = 900, overlap: int = 100, min_section: int = 200) -> list[Chunk]:
    text = doc.text
    spans = _sections(text)
    # merge tiny sections (e.g. a heading with one line) into the following one
    merged: list[tuple[int, int]] = []
    for s, e in spans:
        if merged and (merged[-1][1] - merged[-1][0]) < min_section:
            merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=size, chunk_overlap=overlap, add_start_index=True,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks: list[Chunk] = []
    idx = 0
    for s, e in merged:
        section_text = text[s:e]
        heading_line = section_text.split("\n", 1)[0] if HEADING_RE.match(section_text.split("\n", 1)[0]) else ""
        if len(section_text) <= size:
            pieces = [(0, section_text)]
        else:
            pieces = [(d.metadata["start_index"], d.page_content) for d in splitter.create_documents([section_text])]
        # merge fragments that are too small to stand alone (a bare heading, a stray line)
        pieces = _merge_small(pieces, min_chars=80)
        for off, piece in pieces:
            if not piece.strip():
                continue
            body = piece
            # keep the section heading on continuation pieces so each chunk stays self-describing
            if off > 0 and heading_line and not body.startswith(heading_line):
                body = f"{heading_line}\n{body}"
            chunks.append(_make_chunk(doc, "recursive", idx, s + off, s + off + len(piece), body.strip()))
            idx += 1
    return chunks


def _merge_small(pieces: list[tuple[int, str]], min_chars: int) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for off, piece in pieces:
        if out and len(out[-1][1].strip()) < min_chars:
            prev_off, prev = out[-1]
            gap_end = off + len(piece)
            out[-1] = (prev_off, prev + ("\n" if not prev.endswith("\n") else "") + piece) if off >= prev_off + len(prev) - 200 else (prev_off, prev + "\n" + piece)
            continue
        out.append((off, piece))
    if len(out) > 1 and len(out[-1][1].strip()) < min_chars:
        off, piece = out.pop()
        prev_off, prev = out[-1]
        out[-1] = (prev_off, prev + "\n" + piece)
    return out


# --------------------------------------------------------------------------------------
# 3. semantic (embedding-similarity breakpoints)
# --------------------------------------------------------------------------------------
_PARA_RE = re.compile(r"\n\s*\n")


def _paragraph_spans(text: str) -> list[tuple[int, int]]:
    spans, pos = [], 0
    in_code = False
    buf_start = 0
    lines = text.split("\n")
    # keep fenced code blocks intact, otherwise split on blank lines
    out: list[tuple[int, int]] = []
    cur_start = 0
    cur_has_text = False
    for line in lines:
        line_start = pos
        pos += len(line) + 1
        if line.strip().startswith("```"):
            in_code = not in_code
            cur_has_text = True
            continue
        if not in_code and not line.strip():
            if cur_has_text:
                out.append((cur_start, line_start))
            cur_start = pos
            cur_has_text = False
        else:
            cur_has_text = True
    if cur_has_text:
        out.append((cur_start, len(text)))
    return [(s, e) for s, e in out if text[s:e].strip()]


def chunk_semantic(
    doc: LoadedDocument,
    embed: Callable[[Sequence[str]], np.ndarray],
    breakpoint_percentile: float = 80.0,
    min_chars: int = 250,
    max_chars: int = 1400,
) -> list[Chunk]:
    text = doc.text
    paras = _paragraph_spans(text)
    if not paras:
        return []
    # group paragraphs into units of at least ~min_chars/2 so single lines don't dominate distances
    units: list[tuple[int, int]] = []
    for s, e in paras:
        if units and (units[-1][1] - units[-1][0]) < min_chars // 2:
            units[-1] = (units[-1][0], e)
        else:
            units.append((s, e))
    if len(units) == 1:
        groups = [units[0]]
    else:
        vecs = embed([text[s:e] for s, e in units])
        vecs = vecs / np.clip(np.linalg.norm(vecs, axis=1, keepdims=True), 1e-9, None)
        dists = 1.0 - np.sum(vecs[:-1] * vecs[1:], axis=1)
        threshold = float(np.percentile(dists, breakpoint_percentile))
        groups = []
        gs = units[0][0]
        for i, d in enumerate(dists):
            if d > threshold:
                groups.append((gs, units[i][1]))
                gs = units[i + 1][0]
        groups.append((gs, units[-1][1]))
    # enforce size bounds: merge small groups, split oversized ones
    bounded: list[tuple[int, int]] = []
    for s, e in groups:
        if bounded and (bounded[-1][1] - bounded[-1][0]) < min_chars:
            bounded[-1] = (bounded[-1][0], e)
        else:
            bounded.append((s, e))
    splitter = RecursiveCharacterTextSplitter(chunk_size=max_chars, chunk_overlap=80, add_start_index=True,
                                              separators=["\n\n", "\n", ". ", " ", ""])
    chunks: list[Chunk] = []
    idx = 0
    for s, e in bounded:
        seg = text[s:e]
        if len(seg) <= max_chars:
            pieces = [(0, seg)]
        else:
            pieces = [(d.metadata["start_index"], d.page_content) for d in splitter.create_documents([seg])]
        for off, piece in _merge_small(pieces, min_chars=80):
            if piece.strip():
                chunks.append(_make_chunk(doc, "semantic", idx, s + off, s + off + len(piece), piece.strip()))
                idx += 1
    return chunks


def chunk_document(doc: LoadedDocument, strategy: str, settings, embed=None) -> list[Chunk]:
    if strategy == "fixed":
        return chunk_fixed(doc, settings.fixed_chunk_size, settings.fixed_chunk_overlap)
    if strategy == "recursive":
        return chunk_recursive(doc, settings.recursive_chunk_size, settings.recursive_chunk_overlap)
    if strategy == "semantic":
        if embed is None:
            raise ValueError("semantic chunking needs an embedding function")
        return chunk_semantic(doc, embed, settings.semantic_breakpoint_percentile,
                              settings.semantic_min_chars, settings.semantic_max_chars)
    raise ValueError(f"unknown strategy {strategy!r}; choose from {STRATEGIES}")
