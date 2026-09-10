"""Multi-format document loader (markdown, plain text, HTML, PDF).

Every file is normalised to plain text in which section headings are kept as
markdown ``#`` lines.  That single convention lets the structure-aware chunker
and the metadata resolver (section heading / page number for any character
offset) work identically for every source format.

Raw files are never modified; processed documents are written to
``data/processed/docs.jsonl`` so the corpus can be re-indexed without re-parsing.
"""
from __future__ import annotations

import html
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

from bs4 import BeautifulSoup
from pypdf import PdfReader

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


def iter_headings(text: str):
    """Yield (char_offset, level, title) for markdown headings, ignoring fenced code blocks
    (a Python comment such as ``# your routes`` inside ``` fences is not a heading)."""
    pos = 0
    in_code = False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            in_code = not in_code
        elif not in_code:
            m = HEADING_RE.match(line)
            if m:
                yield pos, len(m.group(1)), m.group(2).strip()
        pos += len(line) + 1


@dataclass
class LoadedDocument:
    doc_id: str
    collection: str
    source_path: str
    title: str
    format: str
    text: str
    license: str = ""
    source_url: str = ""
    version: str = ""
    # (char_offset_where_page_starts, page_number) — only populated for PDFs
    page_offsets: list[tuple[int, int]] = field(default_factory=list)

    # ---- metadata resolution -------------------------------------------------
    def section_at(self, offset: int) -> str:
        """Nearest heading path preceding ``offset`` (e.g. 'Settings > Logging')."""
        path: list[tuple[int, str]] = []
        for pos, level, title in iter_headings(self.text):
            if pos > offset:
                break
            path = [(lvl, h) for lvl, h in path if lvl < level]
            path.append((level, title))
        return " > ".join(h for _, h in path) if path else self.title

    def page_at(self, offset: int) -> int | None:
        if not self.page_offsets:
            return None
        page = self.page_offsets[0][1]
        for start, number in self.page_offsets:
            if start <= offset:
                page = number
            else:
                break
        return page

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, line: str) -> "LoadedDocument":
        d = json.loads(line)
        d["page_offsets"] = [tuple(x) for x in d.get("page_offsets", [])]
        return cls(**d)


# --------------------------------------------------------------------------------------
# Source manifest: which folders belong to which collection, and their provenance.
# --------------------------------------------------------------------------------------
@dataclass
class SourceSpec:
    collection: str
    root: Path
    glob: str
    license: str
    url_prefix: str
    version: str
    strip_prefix: str = ""


def default_sources(raw_dir: Path) -> list[SourceSpec]:
    """The corpus used in this portfolio: a 'web platform team' documentation set.

    Versions are the pinned git commits recorded in data/raw/MANIFEST.md.
    """
    m = _read_manifest_versions(raw_dir)
    return [
        SourceSpec("fastapi", raw_dir / "_src/fastapi/docs/en/docs", "**/*.md", "MIT",
                   "https://github.com/fastapi/fastapi/blob/{commit}/docs/en/docs/", m.get("fastapi", "")),
        SourceSpec("starlette", raw_dir / "_src/starlette/docs", "**/*.md", "BSD-3-Clause",
                   "https://github.com/encode/starlette/blob/{commit}/docs/", m.get("starlette", "")),
        SourceSpec("uvicorn", raw_dir / "_src/uvicorn/docs", "**/*.md", "BSD-3-Clause",
                   "https://github.com/encode/uvicorn/blob/{commit}/docs/", m.get("uvicorn", "")),
        SourceSpec("rfc", raw_dir / "rfc", "*.*", "IETF Trust Legal Provisions (unmodified redistribution)",
                   "https://www.rfc-editor.org/rfc/", "as published"),
    ]


def _read_manifest_versions(raw_dir: Path) -> dict[str, str]:
    mf = raw_dir / "MANIFEST.md"
    out: dict[str, str] = {}
    if mf.exists():
        for line in mf.read_text().splitlines():
            m = re.match(r"\|\s*(\w+)\s*\|\s*[^|]*\|\s*`?([0-9a-f]{7,40})`?", line)
            if m:
                out[m.group(1)] = m.group(2)
    return out


# --------------------------------------------------------------------------------------
# Format-specific normalisers
# --------------------------------------------------------------------------------------
_MD_INCLUDE_RE = re.compile(r"^\s*\{[\*!].*?[\*!]\}\s*$", re.M)          # {* ../../docs_src/x.py *}  {!x!}
_MD_ADMON_OPEN_RE = re.compile(r"^///\s*(\w[\w-]*)(?:\s*\|\s*(.*))?$", re.M)  # /// tip | Title
_MD_ADMON_CLOSE_RE = re.compile(r"^///\s*$", re.M)
_MD_HTML_TAG_RE = re.compile(r"<[^>\n]+>")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MD_IMG_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
_MD_STYLE_RE = re.compile(r"\{[.:][^}]*\}")   # { .external-link target=_blank }
_MULTI_BLANK_RE = re.compile(r"\n{3,}")


def normalize_markdown(text: str) -> str:
    text = text.replace("\r\n", "\n")
    text = _MD_IMG_RE.sub("", text)
    text = _MD_INCLUDE_RE.sub("", text)
    text = _MD_ADMON_OPEN_RE.sub(lambda m: f"{m.group(1).capitalize()}: {m.group(2) or ''}".rstrip(), text)
    text = _MD_ADMON_CLOSE_RE.sub("", text)
    text = _MD_STYLE_RE.sub("", text)
    text = _MD_LINK_RE.sub(r"\1", text)
    # strip raw HTML tags, but never inside code fences / inline code (``<module>:<attribute>`` is content)
    parts = re.split(r"(```.*?```|`[^`\n]*`)", text, flags=re.S)
    text = "".join(part if part.startswith("`") else _MD_HTML_TAG_RE.sub("", part) for part in parts)
    # strip yaml front matter
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            text = text[end + 5:]
    text = re.sub(r"\s*\{\s*#[^}]*\}", "", text)  # heading anchors: { #first-steps }
    text = html.unescape(text)
    text = _MULTI_BLANK_RE.sub("\n\n", text)
    return text.strip() + "\n"


def normalize_html(raw: str) -> str:
    soup = BeautifulSoup(raw, "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    # rfc-editor.org HTML for older RFCs is one big <pre> with <span class="hN"> headings.
    pres = soup.find_all("pre")
    if pres and "Request for Comments:" in pres[0].get_text()[:2000]:
        for pre in pres:  # one <pre> per printed page
            for span in pre.find_all("span", class_=re.compile(r"^h[1-6]$")):
                span.replace_with("\n" + span.get_text() + "\n")
        return normalize_rfc_text("\n".join(pre.get_text() for pre in pres))
    lines: list[str] = []
    body = soup.body or soup
    for el in body.descendants:
        if not getattr(el, "name", None):
            continue
        name = el.name.lower()
        if name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            txt = " ".join(el.get_text(" ", strip=True).split())
            if txt:
                lines.append(f"\n{'#' * int(name[1])} {txt}\n")
        elif name == "pre":
            code = el.get_text("\n", strip=False).strip("\n")
            if code:
                lines.append(f"\n```\n{code}\n```\n")
        elif name in {"p", "li", "dd", "dt", "td", "th", "blockquote"}:
            if el.find_parent("pre"):
                continue
            txt = " ".join(el.get_text(" ", strip=True).split())
            if txt and not el.find(["p", "li", "pre", "table"]):
                lines.append(txt + ("\n" if name != "li" else ""))
    text = "\n".join(lines)
    text = re.sub(r"\[Page \d+\]", "", text)
    return _MULTI_BLANK_RE.sub("\n\n", text).strip() + "\n"


_RFC_PAGE_FOOTER_RE = re.compile(r"^.*(?:\[Page \d+\]|Standards Track Page \d+|Informational Page \d+)\s*$", re.M)
_RFC_PAGE_HEADER_RE = re.compile(r"^RFC \d+\s+.*\s+(?:January|February|March|April|May|June|July|August|September|October|November|December) \d{4}\s*$", re.M)
_LIGATURES = {"\ufb01": "fi", "\ufb02": "fl", "\ufb00": "ff", "\ufb03": "ffi", "\ufb04": "ffl"}


def _rfc_title(text: str) -> str | None:
    """Title = last non-empty line before 'Abstract' that is not part of the header block."""
    lines = text.split("\n")
    for i, line in enumerate(lines[:80]):
        if line.strip() == "Abstract":
            for prev in reversed(lines[:i]):
                p = prev.strip()
                if p and "  " not in p and not re.match(r"^(RFC \d+|Request for Comments|Category|ISSN|Obsoletes|Updates|STD)", p):
                    return p
    return None
_RFC_SECTION_RE = re.compile(r"^(?:(\d+(?:\.\d+)*)\.|(Appendix [A-Z](?:\.\d+)*)\.)\s+(\S.*)$")


def normalize_rfc_text(raw: str) -> str:
    """Plain-text RFCs: drop page headers/footers and form feeds, turn numbered
    section titles into markdown headings so structure is preserved."""
    text = raw.lstrip("﻿").replace("\r\n", "\n").replace("\f", "\n")
    text = _RFC_PAGE_FOOTER_RE.sub("", text)
    text = _RFC_PAGE_HEADER_RE.sub("", text)
    title = _rfc_title(text)
    out: list[str] = [f"# {title}\n"] if title else []
    out.extend(_convert_rfc_sections(text.split("\n"), indented_body=True))
    text = "\n".join(out)
    text = _MULTI_BLANK_RE.sub("\n\n", text)
    return text.strip() + "\n"


def _convert_rfc_sections(lines: list[str], indented_body: bool) -> list[str]:
    """Turn numbered section titles into markdown headings while skipping the Table of
    Contents: ToC lines look like headings too, so heading conversion only starts once a
    section number seen in the ToC appears a second time (i.e. the body begins)."""
    out: list[str] = []
    in_toc = False
    toc_numbers: set[str] = set()
    for line in lines:
        stripped = line.rstrip()
        core = stripped.strip()
        if core == "Table of Contents":
            in_toc = True
            out.append("## Table of Contents")
            continue
        m = _RFC_SECTION_RE.match(core) if len(core) < 100 else None
        is_title_line = m is not None and (not indented_body or not stripped.startswith(" "))
        if in_toc:
            if m is not None:
                number = m.group(1) or m.group(2)
                if number in toc_numbers and is_title_line:
                    in_toc = False  # body begins here — fall through to heading conversion
                else:
                    toc_numbers.add(number)
                    continue
            else:
                continue  # ToC continuation lines (page numbers, dotted leaders)
        if is_title_line:
            number = m.group(1) or m.group(2)
            level = number.count(".") + 2 if m.group(1) else 2
            out.append(f"\n{'#' * min(6, level)} {number}. {m.group(3).strip()}\n")
            continue
        if indented_body:
            out.append(core if stripped.startswith("   ") else stripped)
        else:
            out.append(stripped)
    return out


def normalize_plaintext(raw: str) -> str:
    if re.search(r"^RFC \d+", raw.lstrip("﻿"), re.M) or re.search(r"Request for Comments:", raw):
        return normalize_rfc_text(raw)
    return _MULTI_BLANK_RE.sub("\n\n", raw.lstrip("﻿").replace("\r\n", "\n")).strip() + "\n"


def load_pdf(path: Path) -> tuple[str, list[tuple[int, int]]]:
    """Returns normalised text plus (char_offset, page_number) markers."""
    reader = PdfReader(str(path))
    parts: list[str] = []
    offsets: list[tuple[int, int]] = []
    pos = 0
    is_rfc = False
    for i, page in enumerate(reader.pages, start=1):
        raw = page.extract_text() or ""
        for lig, rep in _LIGATURES.items():
            raw = raw.replace(lig, rep)
        if i == 1 and ("Request for Comments" in raw or raw.startswith("RFC ")):
            is_rfc = True
            first = [ln.strip() for ln in raw.split("\n") if ln.strip()]
            if len(first) >= 2 and first[0].startswith("RFC ") and first[1] != "Abstract":
                raw = raw.replace(first[1], f"# {first[1]}", 1)
        if is_rfc:
            raw = _RFC_PAGE_FOOTER_RE.sub("", raw)
            raw = _RFC_PAGE_HEADER_RE.sub("", raw)
        raw = _MULTI_BLANK_RE.sub("\n\n", raw).strip()
        parts.append(raw + "\n\n")
    if is_rfc:
        # convert section titles with ToC awareness across the whole document, page by page
        parts = _convert_rfc_sections_keep_pages(parts)
    for i, chunk in enumerate(parts, start=1):
        offsets.append((pos, i))
        pos += len(chunk)
    return "".join(parts), offsets


def _convert_rfc_sections_keep_pages(pages: list[str]) -> list[str]:
    """Run _convert_rfc_sections over all pages at once but return per-page strings so page
    offsets stay exact. Uses a sentinel line to mark page boundaries."""
    sentinel = "\x00PAGEBREAK\x00"
    lines: list[str] = []
    for p in pages:
        lines.extend(p.split("\n"))
        lines.append(sentinel)
    out_lines = _convert_rfc_sections(lines, indented_body=False)
    out_pages: list[str] = []
    cur: list[str] = []
    for ln in out_lines:
        if ln == sentinel:
            out_pages.append(_MULTI_BLANK_RE.sub("\n\n", "\n".join(cur)).strip() + "\n\n")
            cur = []
        else:
            cur.append(ln)
    if cur:
        out_pages.append("\n".join(cur))
    return out_pages


def _title_from_text(text: str, fallback: str) -> str:
    for _, _, title in iter_headings(text):
        return title
    return fallback


def load_file(path: Path, spec: SourceSpec) -> LoadedDocument | None:
    suffix = path.suffix.lower()
    rel = path.relative_to(spec.root).as_posix()
    doc_id = f"{spec.collection}/{rel}"
    page_offsets: list[tuple[int, int]] = []
    if suffix in {".md", ".markdown"}:
        fmt, text = "markdown", normalize_markdown(path.read_text(encoding="utf-8", errors="replace"))
    elif suffix in {".txt", ".text"}:
        fmt, text = "text", normalize_plaintext(path.read_text(encoding="utf-8", errors="replace"))
    elif suffix in {".html", ".htm"}:
        fmt, text = "html", normalize_html(path.read_text(encoding="utf-8", errors="replace"))
    elif suffix == ".pdf":
        fmt = "pdf"
        text, page_offsets = load_pdf(path)
    else:
        return None
    if len(text.strip()) < 40:
        return None
    url = spec.url_prefix.replace("{commit}", spec.version or "main") + rel
    return LoadedDocument(
        doc_id=doc_id,
        collection=spec.collection,
        source_path=str(path),
        title=_title_from_text(text, path.stem),
        format=fmt,
        text=text,
        license=spec.license,
        source_url=url,
        version=spec.version,
        page_offsets=page_offsets,
    )


def load_sources(specs: Iterable[SourceSpec]) -> Iterator[LoadedDocument]:
    for spec in specs:
        if not spec.root.exists():
            continue
        for path in sorted(spec.root.glob(spec.glob)):
            if not path.is_file():
                continue
            doc = load_file(path, spec)
            if doc is not None:
                yield doc


def write_processed(docs: Iterable[LoadedDocument], out_path: Path) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with out_path.open("w", encoding="utf-8") as fh:
        for d in docs:
            fh.write(d.to_json() + "\n")
            n += 1
    return n


def read_processed(path: Path) -> list[LoadedDocument]:
    with path.open(encoding="utf-8") as fh:
        return [LoadedDocument.from_json(line) for line in fh if line.strip()]
