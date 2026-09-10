from pathlib import Path

from hybrid_rag.config import settings
from hybrid_rag.loaders import LoadedDocument, normalize_html, normalize_markdown, normalize_rfc_text
from hybrid_rag.chunking import chunk_fixed, chunk_recursive, chunk_semantic


def test_markdown_normalisation_keeps_code_spans_and_strips_html():
    md = "# Title { #title }\n\n<abbr title='x'>API</abbr> in `<module>:<attr>` form.\n\n{* ../../docs_src/a.py *}\n\n/// tip | Hi\nTip body\n///\n"
    out = normalize_markdown(md)
    assert out.startswith("# Title\n")
    assert "`<module>:<attr>`" in out and "<abbr" not in out
    assert "docs_src" not in out and "Tip: Hi" in out and "Tip body" in out


def test_rfc_text_headings_and_title():
    raw = ("Internet Engineering Task Force (IETF)      A. Person\nRequest for Comments: 9999\nCategory: Standards Track\n\n"
           "   Fancy Protocol\n\nAbstract\n\n   Body.\n\nFielding, et al.  Standards Track  [Page 1]\n\f\n"
           "1.  Introduction\n\n   Intro text.\n\n1.1.  Scope\n\n   Scope text.\n")
    out = normalize_rfc_text(raw)
    assert out.startswith("# Fancy Protocol")
    assert "## 1. Introduction" in out and "### 1.1. Scope" in out
    assert "[Page 1]" not in out


def test_html_headings_become_markdown():
    html = "<html><body><h1>Doc</h1><p>Para one.</p><h2>Sub</h2><pre>code\nblock</pre><ul><li>item</li></ul></body></html>"
    out = normalize_html(html)
    assert "# Doc" in out and "## Sub" in out and "```\ncode\nblock\n```" in out and "item" in out


def _doc(text: str, pages=None) -> LoadedDocument:
    return LoadedDocument("t/doc.md", "t", "/x/doc.md", "Doc", "markdown", text, page_offsets=pages or [])


def test_section_and_page_resolution():
    text = "# A\n\npara a\n\n## B\n\npara b\n\n# C\n\npara c\n"
    d = _doc(text, pages=[(0, 1), (text.index("# C"), 2)])
    assert d.section_at(text.index("para b")) == "A > B"
    assert d.section_at(text.index("para c")) == "C"
    assert d.page_at(text.index("para c")) == 2 and d.page_at(0) == 1


def test_fixed_chunks_cover_document_with_overlap():
    text = ("word " * 600).strip()
    d = _doc(text)
    chunks = chunk_fixed(d, size=200, overlap=40)
    assert chunks[0].start == 0 and chunks[-1].end == len(text)
    assert all(c.char_count <= 200 for c in chunks)
    assert chunks[1].start < chunks[0].end  # overlap
    assert all(c.strategy == "fixed" for c in chunks)
    assert len({c.chunk_id for c in chunks}) == len(chunks)


def test_recursive_chunks_follow_headings_and_keep_heading_on_continuations():
    body = "sentence. " * 120
    text = f"# Alpha\n\n{body}\n\n# Beta\n\nshort beta section.\n"
    d = _doc(text)
    chunks = chunk_recursive(d, size=400, overlap=50)
    assert {c.section for c in chunks} >= {"Alpha", "Beta"}
    alpha = [c for c in chunks if c.section == "Alpha"]
    assert len(alpha) > 1 and all(c.text.startswith("# Alpha") for c in alpha)


def test_semantic_chunker_breaks_on_topic_change():
    import numpy as np

    def fake_embed(texts):
        # topic A → vector (1,0), topic B → (0,1)
        return np.array([[1.0, 0.0] if "cats" in t else [0.0, 1.0] for t in texts], dtype=np.float32)

    paras = ["cats purr softly " * 10] * 3 + ["servers bind ports " * 10] * 3
    text = "\n\n".join(paras)
    chunks = chunk_semantic(_doc(text), fake_embed, breakpoint_percentile=80, min_chars=50, max_chars=5000)
    assert len(chunks) == 2
    assert "cats" in chunks[0].text and "servers" in chunks[1].text and "cats" not in chunks[1].text


def test_processed_corpus_exists_and_has_all_formats():
    p = settings.processed_dir / "docs.jsonl"
    if not p.exists():
        import pytest
        pytest.skip("corpus not ingested")
    from hybrid_rag.loaders import read_processed
    docs = read_processed(p)
    assert {d.format for d in docs} >= {"markdown", "text", "html", "pdf"}
    pdf = next(d for d in docs if d.format == "pdf")
    assert pdf.page_at(len(pdf.text) - 10) and pdf.page_at(len(pdf.text) - 10) > 100
