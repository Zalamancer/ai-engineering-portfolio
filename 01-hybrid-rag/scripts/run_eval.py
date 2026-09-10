"""Evaluation runner.

  uv run python scripts/run_eval.py retrieval            # all 18 retrieval configs, no LLM needed
  uv run python scripts/run_eval.py sweep                # RRF weight + abstention threshold sweep (dev split only)
  uv run python scripts/run_eval.py answers --strategy recursive --mode hybrid [--no-rerank] [--split all]
                                                         # full pipeline + LLM judges; one run dir per config
"""
from __future__ import annotations

import argparse
import itertools
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hybrid_rag.chunking import STRATEGIES  # noqa: E402
from hybrid_rag.config import settings  # noqa: E402
from hybrid_rag.evaluation import (citation_accuracy, evidence_hits, judge_correctness, judge_faithfulness,  # noqa: E402
                                   load_questions, retrieval_metrics, status_expectation)
from hybrid_rag.llm import FakeLLM  # noqa: E402
from hybrid_rag.pipeline import RAGPipeline  # noqa: E402
from hybrid_rag.retrieval import MODES  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS = ROOT / "eval" / "questions.json"
RESULTS = ROOT / "eval" / "results"
BASELINE = {"strategy": "fixed", "mode": "dense", "rerank": False}


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.mean(xs), 4) if xs else None


def dataset_meta() -> dict:
    d = json.loads(QUESTIONS.read_text())
    from collections import Counter
    return {"dataset_version": d["dataset_version"], "n_questions": len(d["questions"]),
            "verification": dict(Counter(q["verification"]["status"] for q in d["questions"]))}


# ---------------------------------------------------------------------------------------
def cmd_retrieval(args) -> None:
    p = RAGPipeline(llm=FakeLLM())
    qs = [q for q in load_questions(QUESTIONS, "all") if q.get("evidence")]
    configs = [dict(strategy=s, mode=m, rerank=r) for s, m, r in itertools.product(STRATEGIES, MODES, (False, True))]
    rows = []
    t0 = time.time()
    for cfg in configs:
        per_q = []
        for q in qs:
            rr = p.retrieve(q["question"], cfg["strategy"], cfg["mode"], cfg["rerank"], top_k=5)
            ranks = evidence_hits(q, [(h.chunk.doc_id, h.chunk.text) for h in rr.hits])
            m = retrieval_metrics(ranks)
            per_q.append({"id": q["id"], "type": q["type"], "split": q["split"], "ranks": ranks, **m,
                          "confidence": rr.confidence, "top_doc": rr.hits[0].chunk.doc_id if rr.hits else None})
        summary = {}
        for split in ("dev", "heldout", "all"):
            sub = [x for x in per_q if split == "all" or x["split"] == split]
            summary[split] = {"n": len(sub), "hit@5": _mean([x["hit"] for x in sub]),
                              "evidence_recall@5": _mean([x["evidence_recall"] for x in sub]),
                              "mrr@5": _mean([x["mrr"] for x in sub]),
                              "multi_hop_all_found@5": _mean([x["all_found"] for x in sub if x["type"] == "multi_hop"])}
        rows.append({"config": cfg, "is_baseline": cfg == BASELINE, "summary": summary, "per_question": per_q})
        s = summary["all"]
        print(f"{cfg['strategy']:>9} {cfg['mode']:>6} rerank={str(cfg['rerank']):5} hit@5={s['hit@5']:.3f} "
              f"recall={s['evidence_recall@5']:.3f} mrr={s['mrr@5']:.3f} multihop_all={s['multi_hop_all_found@5']}")
    out = RESULTS / "retrieval_eval.json"
    out.write_text(json.dumps({"run_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "seconds": round(time.time() - t0, 1),
                               "dataset": dataset_meta(), "embedding_model": settings.embedding_model,
                               "reranker_model": settings.reranker_model, "top_k": 5,
                               "settings": {k: v for k, v in settings.model_dump().items() if k.startswith(("dense_", "sparse_", "rrf_", "rerank_", "final_"))},
                               "configs": rows}, indent=1, default=str))
    print("wrote", out)


# ---------------------------------------------------------------------------------------
def cmd_sweep(args) -> None:
    """Tune on DEV only: RRF dense/sparse weight, and the abstention threshold."""
    p = RAGPipeline(llm=FakeLLM())
    dev = load_questions(QUESTIONS, "dev")
    with_ev = [q for q in dev if q.get("evidence") and q["type"] in ("lookup", "multi_hop")]
    weight_rows = []
    # NOTE: with 10 dense + 10 sparse candidates and a reranker over the top 20, every candidate is
    # reranked whatever the weights are, so the weights only matter when reranking is off (or when
    # the candidate pool is smaller than dense_top_k + sparse_top_k). Both variants are measured.
    for rerank in (False, True):
        for w in (0.3, 0.5, 0.6, 0.7, 0.8, 0.9):
            hits = []
            for q in with_ev:
                rr = p.retrieve(q["question"], args.strategy, "hybrid", rerank, top_k=5, dense_weight=w, sparse_weight=round(1 - w, 2))
                hits.append(retrieval_metrics(evidence_hits(q, [(h.chunk.doc_id, h.chunk.text) for h in rr.hits])))
            weight_rows.append({"rerank": rerank, "dense_weight": w, "sparse_weight": round(1 - w, 2), "hit@5": _mean([h["hit"] for h in hits]),
                                "evidence_recall@5": _mean([h["evidence_recall"] for h in hits]), "mrr@5": _mean([h["mrr"] for h in hits])})
            print("weights", weight_rows[-1])
    # abstention threshold: separate no_answer questions from answerable ones by retrieval confidence
    confs = []
    for q in dev:
        if q["type"] in ("lookup", "multi_hop", "no_answer"):
            rr = p.retrieve(q["question"], args.strategy, "hybrid", True, top_k=5)
            confs.append({"id": q["id"], "type": q["type"], "confidence": rr.confidence})
    thr_rows = []
    for thr in [x / 100 for x in range(5, 96, 5)]:
        ans = [c for c in confs if c["type"] != "no_answer"]
        noa = [c for c in confs if c["type"] == "no_answer"]
        keep = sum(1 for c in ans if c["confidence"] >= thr) / len(ans)
        abstain = sum(1 for c in noa if c["confidence"] < thr) / len(noa) if noa else None
        thr_rows.append({"threshold": thr, "answerable_kept": round(keep, 3), "no_answer_abstained": abstain,
                         "balanced": round((keep + (abstain or 0)) / 2, 3)})
    best = max(thr_rows, key=lambda r: r["balanced"])
    print("threshold sweep best:", best)
    out = RESULTS / "threshold_sweep.json"
    out.write_text(json.dumps({"run_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "split": "dev", "strategy": args.strategy,
                               "dataset": dataset_meta(), "rrf_weight_sweep": weight_rows, "confidences": confs,
                               "threshold_sweep": thr_rows, "recommended_threshold": best["threshold"]}, indent=1))
    print("wrote", out)


# ---------------------------------------------------------------------------------------
def cmd_answers(args) -> None:
    p = RAGPipeline()
    if not p.llm.is_available():
        sys.exit("LLM endpoint not available — start scripts/serve_llm.sh")
    qs = load_questions(QUESTIONS, args.split)
    if args.limit:
        qs = qs[: args.limit]
    run_id = f"{time.strftime('%Y%m%d-%H%M%S')}_{args.strategy}_{args.mode}_{'rerank' if args.rerank else 'norerank'}"
    run_dir = RESULTS / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    t_start = time.time()
    with (run_dir / "answers.jsonl").open("w") as fh:
        for i, q in enumerate(qs, 1):
            t0 = time.time()
            ans = p.ask(q["question"], args.strategy, args.mode, args.rerank, verify=True, threshold=args.threshold)
            hits = p.retrieve(q["question"], args.strategy, args.mode, args.rerank).hits  # same deterministic hits, for judges
            ranks = evidence_hits(q, [(h["doc_id"], h["text"]) for h in ans.retrieval["hits"]])
            row = {"id": q["id"], "type": q["type"], "split": q["split"], "question": q["question"], "gold_answer": q["gold_answer"],
                   "answer": ans.to_dict(), "retrieval_metrics": retrieval_metrics(ranks) if q.get("evidence") else None,
                   "status": status_expectation(q, ans), "citations": citation_accuracy(ans), "wall_s": None}
            judge_calls = 0
            if q["type"] in ("lookup", "multi_hop") and ans.status != "insufficient":
                score, raw = judge_correctness(p.llm, q["question"], q["gold_answer"], ans.answer)
                judge_calls += 1
                row["correctness"] = {"score_1_5": score, "correct": (score or 0) >= 4, "raw": raw, "judge": p.s.llm_model}
            else:
                row["correctness"] = None
            if ans.claims:
                f = judge_faithfulness(p.llm, ans, hits)
                judge_calls += sum(1 for j in f["judged"] if not j["verdict"].endswith("(cited)"))
                row["faithfulness"] = f
            else:
                row["faithfulness"] = {"faithfulness": None, "n_claims": 0, "judged": []}
            row["judge_llm_calls"] = judge_calls
            row["wall_s"] = round(time.time() - t0, 1)
            rows.append(row)
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            c = row["correctness"]
            print(f"[{i}/{len(qs)}] {q['id']} {q['type']:<9} status={ans.status:<12} ok={row['status']['status_ok']!s:<5} "
                  f"correct={c['score_1_5'] if c else '-'} faith={row['faithfulness']['faithfulness']} "
                  f"cit_prec={row['citations']['citation_precision']} {row['wall_s']}s", flush=True)
    summary = summarize(rows)
    meta = {"run_id": run_id, "config": {"strategy": args.strategy, "mode": args.mode, "rerank": args.rerank,
                                         "threshold": args.threshold if args.threshold is not None else settings.retrieval_confidence_threshold,
                                         "top_k": settings.final_top_k},
            "is_baseline": {"strategy": args.strategy, "mode": args.mode, "rerank": args.rerank} == BASELINE,
            "llm_model": p.s.llm_model, "judge_model": p.s.llm_model, "embedding_model": p.s.embedding_model,
            "reranker_model": p.s.reranker_model, "dataset": dataset_meta(), "split": args.split, "n": len(rows),
            "run_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "total_seconds": round(time.time() - t_start, 1),
            "note": "correctness/faithfulness/citation verdicts are LLM judgments by the model named in judge_model, not human judgments",
            "summary": summary}
    (run_dir / "summary.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps(summary, indent=1))
    print("wrote", run_dir)


def summarize(rows: list[dict]) -> dict:
    out = {}
    for split in ("dev", "heldout", "all"):
        sub = [r for r in rows if split == "all" or r["split"] == split]
        answerable = [r for r in sub if r["type"] in ("lookup", "multi_hop")]
        noans = [r for r in sub if r["type"] == "no_answer"]
        amb = [r for r in sub if r["type"] == "ambiguous"]
        out[split] = {
            "n": len(sub),
            "answer_correct_rate": _mean([1.0 if (r["correctness"] and r["correctness"]["correct"]) else 0.0 for r in answerable]),
            "answer_score_mean_1_5": _mean([r["correctness"]["score_1_5"] for r in answerable if r["correctness"]]),
            "wrongly_abstained_rate": _mean([1.0 if r["status"].get("wrongly_abstained") else 0.0 for r in answerable]),
            "faithfulness": _mean([r["faithfulness"]["faithfulness"] for r in sub]),
            "citation_precision": _mean([r["citations"]["citation_precision"] for r in sub]),
            "citation_partial_rate": _mean([r["citations"]["partial_rate"] for r in sub]),
            "retrieval_hit@5": _mean([r["retrieval_metrics"]["hit"] for r in sub if r["retrieval_metrics"]]),
            "no_answer_abstain_rate": _mean([1.0 if r["status"]["status_ok"] else 0.0 for r in noans]),
            "ambiguity_handled_rate": _mean([1.0 if r["status"]["status_ok"] else 0.0 for r in amb]),
            "median_wall_s": round(statistics.median([r["wall_s"] for r in sub]), 1) if sub else None,
            "mean_llm_calls": _mean([r["answer"]["usage"]["llm_calls"] for r in sub]),
            "mean_prompt_tokens": _mean([r["answer"]["usage"]["prompt_tokens"] for r in sub]),
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("retrieval")
    s = sub.add_parser("sweep"); s.add_argument("--strategy", default="recursive", choices=STRATEGIES)
    a = sub.add_parser("answers")
    a.add_argument("--strategy", default=settings.default_strategy, choices=STRATEGIES)
    a.add_argument("--mode", default="hybrid", choices=MODES)
    a.add_argument("--rerank", dest="rerank", action="store_true", default=True)
    a.add_argument("--no-rerank", dest="rerank", action="store_false")
    a.add_argument("--split", default="all", choices=("dev", "heldout", "all"))
    a.add_argument("--threshold", type=float, default=None)
    a.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)
    {"retrieval": cmd_retrieval, "sweep": cmd_sweep, "answers": cmd_answers}[args.cmd](args)


if __name__ == "__main__":
    main()
