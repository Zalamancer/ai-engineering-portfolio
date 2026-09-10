"""Creates data/demo_analytics.sqlite from the project-1 documentation corpus so the analysis
specialist has real, read-only data to query (tables: docs, sections)."""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agentops.config import settings  # noqa: E402

out = settings.data_dir / "demo_analytics.sqlite"
out.parent.mkdir(parents=True, exist_ok=True)
out.unlink(missing_ok=True)
c = sqlite3.connect(out)
c.executescript("""
CREATE TABLE docs (doc_id TEXT PRIMARY KEY, collection TEXT, title TEXT, format TEXT, chars INTEGER, source_url TEXT, license TEXT);
CREATE TABLE sections (id INTEGER PRIMARY KEY, doc_id TEXT, heading TEXT, level INTEGER, chars INTEGER, mentions_https INTEGER, mentions_proxy INTEGER, mentions_websocket INTEGER);
""")
n = 0
if settings.docs_corpus_path.exists():
    for line in settings.docs_corpus_path.open():
        d = json.loads(line)
        c.execute("INSERT INTO docs VALUES (?,?,?,?,?,?,?)", (d["doc_id"], d["collection"], d.get("title"), d["format"], len(d["text"]), d.get("source_url"), d.get("license")))
        for sec in re.split(r"\n(?=#{1,6} )", d["text"]):
            m = re.match(r"^(#{1,6}) (.*)", sec)
            heading, level = (m.group(2)[:120], len(m.group(1))) if m else ("(intro)", 0)
            low = sec.lower()
            c.execute("INSERT INTO sections (doc_id, heading, level, chars, mentions_https, mentions_proxy, mentions_websocket) VALUES (?,?,?,?,?,?,?)",
                      (d["doc_id"], heading, level, len(sec), int("https" in low), int("proxy" in low), int("websocket" in low)))
            n += 1
c.commit()
print(f"wrote {out}: {c.execute('select count(*) from docs').fetchone()[0]} docs, {n} sections")
