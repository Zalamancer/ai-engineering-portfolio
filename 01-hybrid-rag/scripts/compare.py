"""Aggregate every eval run into eval/results/RESULTS.md (tables) and FAILURES.md (saved failure examples)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "eval" / "results"


def fmt(x, pct=True):
    if x is None:
        return "–"
    return f"{100 * x:.0f}%" if pct else f"{x}"


def retrieval_table() -> str:
    f = RESULTS / "retrieval_eval.json"
    if not f.exists():
        return "_retrieval eval not run_\n"
    d = json.loads(f.read_text())
    lines = [f"Retrieval-only comparison (no LLM). {d['dataset']['n_questions']} questions in the file, "
             f"{d['configs'][0]['summary']['all']['n']} with gold evidence; top-5 after fusion/rerank. "
             f"Embeddings `{d['embedding_model']}`, reranker `{d['reranker_model']}`. Run {d['run_at']}.", "",
             "| chunking | mode | rerank | hit@5 (all) | evidence recall@5 | MRR@5 | multi-hop all found | hit@5 dev | hit@5 held-out |",
             "|---|---|---|---|---|---|---|---|---|"]
    for c in sorted(d["configs"], key=lambda c: -(c["summary"]["all"]["hit@5"] or 0)):
        cfg, s, dv, ho = c["config"], c["summary"]["all"], c["summary"]["dev"], c["summary"]["heldout"]
        tag = " **(baseline)**" if c["is_baseline"] else ""
        lines.append(f"| {cfg['strategy']}{tag} | {cfg['mode']} | {'yes' if cfg['rerank'] else 'no'} | {fmt(s['hit@5'])} | "
                     f"{fmt(s['evidence_recall@5'])} | {s['mrr@5']:.2f} | {fmt(s['multi_hop_all_found@5'])} | {fmt(dv['hit@5'])} | {fmt(ho['hit@5'])} |")
    return "\n".join(lines) + "\n"


def sweep_section() -> str:
    f = RESULTS / "threshold_sweep.json"
    if not f.exists():
        return ""
    d = json.loads(f.read_text())
    lines = [f"### Tuning on the dev split only ({d['strategy']}, hybrid + rerank)", "",
             "RRF dense/sparse weight sweep (with the reranker on, all 20 fused candidates are reranked, so the "
             "weights can only change results when reranking is off):", "",
             "| rerank | dense w | sparse w | hit@5 | evidence recall@5 | MRR@5 |", "|---|---|---|---|---|---|"]
    for r in d["rrf_weight_sweep"]:
        lines.append(f"| {'yes' if r.get('rerank') else 'no'} | {r['dense_weight']} | {r['sparse_weight']} | {fmt(r['hit@5'])} | {fmt(r['evidence_recall@5'])} | {r['mrr@5']:.2f} |")
    lines += ["", f"Abstention threshold sweep (retrieval confidence): recommended **{d['recommended_threshold']}** "
              "(maximises the mean of answerable-kept and no-answer-abstained on dev).", "",
              "| threshold | answerable kept | no-answer abstained |", "|---|---|---|"]
    for r in d["threshold_sweep"]:
        lines.append(f"| {r['threshold']:.2f} | {fmt(r['answerable_kept'])} | {fmt(r['no_answer_abstained'])} |")
    return "\n".join(lines) + "\n"


def answer_runs() -> list[dict]:
    runs = []
    for s in sorted((RESULTS / "runs").glob("*/summary.json")) if (RESULTS / "runs").exists() else []:
        runs.append(json.loads(s.read_text()))
    return runs


def answers_table(runs: list[dict]) -> str:
    if not runs:
        return "_no answer-quality runs yet_\n"
    lines = [f"End-to-end answer quality. Generator and judge: `{runs[0]['llm_model']}` (local). "
             "Correctness/faithfulness/citation verdicts are **LLM judgments, not human judgments**. "
             f"Dataset {runs[0]['dataset']['dataset_version']} — verification: {runs[0]['dataset']['verification']}.", "",
             "| run | chunking | mode | rerank | n | correct (judge ≥4/5) | mean score | wrongly abstained | faithfulness | citation precision | no-answer abstained | ambiguity handled | retrieval hit@5 | median s/q |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in runs:
        c, s = r["config"], r["summary"]["all"]
        tag = " **(baseline)**" if r.get("is_baseline") else ""
        lines.append(f"| {r['run_id'][:15]} | {c['strategy']}{tag} | {c['mode']} | {'yes' if c['rerank'] else 'no'} | {s['n']} | "
                     f"{fmt(s['answer_correct_rate'])} | {s['answer_score_mean_1_5'] or '–'} | {fmt(s['wrongly_abstained_rate'])} | "
                     f"{fmt(s['faithfulness'])} | {fmt(s['citation_precision'])} | {fmt(s['no_answer_abstain_rate'])} | "
                     f"{fmt(s['ambiguity_handled_rate'])} | {fmt(s['retrieval_hit@5'])} | {s['median_wall_s']} |")
    lines += ["", "Held-out split only (never used for tuning):", "",
              "| run | chunking | mode | rerank | n | correct | faithfulness | citation precision | no-answer abstained |", "|---|---|---|---|---|---|---|---|---|"]
    for r in runs:
        c, s = r["config"], r["summary"]["heldout"]
        lines.append(f"| {r['run_id'][:15]} | {c['strategy']} | {c['mode']} | {'yes' if c['rerank'] else 'no'} | {s['n']} | "
                     f"{fmt(s['answer_correct_rate'])} | {fmt(s['faithfulness'])} | {fmt(s['citation_precision'])} | {fmt(s['no_answer_abstain_rate'])} |")
    return "\n".join(lines) + "\n"


def failures(runs: list[dict]) -> str:
    out = ["# Saved failure examples", "", "Pulled automatically from the latest run of each configuration. "
           "Judgments are by the local LLM judge; a human may disagree.", ""]
    latest: dict[str, dict] = {}
    for r in runs:
        key = f"{r['config']['strategy']}/{r['config']['mode']}/{'rerank' if r['config']['rerank'] else 'norerank'}"
        latest[key] = r
    for key, r in latest.items():
        rows = [json.loads(l) for l in (RESULTS / "runs" / r["run_id"] / "answers.jsonl").open()]
        out.append(f"## {key} ({r['run_id']})")
        buckets = {
            "Wrong or partial answers (judge ≤3)": [x for x in rows if x["correctness"] and (x["correctness"]["score_1_5"] or 0) <= 3],
            "Answered a question the corpus cannot answer (should have abstained)": [x for x in rows if x["type"] == "no_answer" and not x["status"]["status_ok"]],
            "Abstained on an answerable question": [x for x in rows if x["status"].get("wrongly_abstained")],
            "Citations judged NOT_SUPPORTED": [x for x in rows if any(v == "NOT_SUPPORTED" for c in x["answer"]["claims"] for v in c["verdicts"].values())],
            "Ambiguity not surfaced": [x for x in rows if x["type"] == "ambiguous" and not x["status"]["status_ok"]],
            "Gold evidence not retrieved (retrieval miss)": [x for x in rows if x["retrieval_metrics"] and x["retrieval_metrics"]["hit"] == 0],
        }
        for title, items in buckets.items():
            out.append(f"### {title}: {len(items)}")
            for x in items[:4]:
                a = x["answer"]
                out += [f"- **{x['id']}** ({x['type']}, {x['split']}): {x['question']}",
                        f"  - gold: {x['gold_answer'][:220]}",
                        f"  - system [{a['status']}]: {a['answer'][:300].replace(chr(10), ' ')}",
                        f"  - cited: {[(c['n'], c['doc_id']) for c in a['citations']]} · flags: {a['flags'][:3]} · "
                        f"top retrieved: {[h['doc_id'] for h in a['retrieval']['hits'][:3]]}"]
            out.append("")
    return "\n".join(out) + "\n"


def main() -> None:
    runs = answer_runs()
    md = ["# Results", "", "Generated by `scripts/compare.py`. Numbers are measured on this Mac with the local models named below; "
          "they are portfolio-workload measurements, not customer impact.", "",
          "## 1. Retrieval configurations vs the plain baseline", "", retrieval_table(), "",
          sweep_section(), "", "## 2. Answer quality (generation + citation verification)", "", answers_table(runs)]
    (RESULTS / "RESULTS.md").write_text("\n".join(md))
    (RESULTS / "FAILURES.md").write_text(failures(runs))
    print("wrote", RESULTS / "RESULTS.md", "and FAILURES.md")


if __name__ == "__main__":
    main()
