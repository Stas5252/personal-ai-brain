"""
RAG Benchmark Runner for Personal AI Brain Knowledge Factory.
Evaluates 54 realistic queries across 9 categories against the pilot corpus.
Computes Top-1/Top-3 accuracy, refusal precision, citation compliance, and latency.
"""
import sys
import json
import time
from pathlib import Path
from typing import List, Dict, Any

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.resolve()))

from src.brain.models.knowledge import KnowledgeLayer
from src.brain.knowledge.factory import KnowledgeIngestionFactory
from src.brain.knowledge.indexing.hybrid_search import HybridSearchEngine


def setup_pilot_corpus(factory: KnowledgeIngestionFactory) -> Dict[str, str]:
    """Ingests all pilot corpus files into Knowledge Factory."""
    corpus_dir = Path("tests/pilot_corpus").resolve()
    files_to_ingest = [
        ("sample_contract.pdf", KnowledgeLayer.BUSINESS, "Contracts"),
        ("sample_scanned_receipt.pdf", KnowledgeLayer.BUSINESS, "Expenses"),
        ("sample_guide.docx", KnowledgeLayer.PROFESSIONAL, "Lighting Guides"),
        ("sample_portfolio.pptx", KnowledgeLayer.PROFESSIONAL, "Portfolios"),
        ("sample_pricing.xlsx", KnowledgeLayer.BUSINESS, "Pricing"),
        ("sample_moodboard.jpg", KnowledgeLayer.PROFESSIONAL, "Visual Moodboards"),
        ("sample_speech_ru.wav", KnowledgeLayer.CLIENT, "Voice Notes"),
        ("sample_lesson_ru.mp4", KnowledgeLayer.GLOBAL, "Educational Lessons")
    ]

    source_map = {}
    print("--- Ingesting Pilot Corpus ---")
    from src.brain.db import get_connection
    for filename, layer, subcategory in files_to_ingest:
        file_path = corpus_dir / filename
        if not file_path.exists():
            print(f"Warning: File {file_path} not found!")
            continue

        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT source_id FROM knowledge_sources WHERE original_filename = ? OR title LIKE ?", (filename, f"%{file_path.stem}%"))
        old_ids = [r[0] for r in c.fetchall()]
        conn.close()
        for oid in old_ids:
            try:
                factory.delete_source(oid, delete_original=False)
            except Exception:
                pass

        meta, chunks = factory.ingest_file(
            file_path=file_path,
            override_layer=layer,
            subcategory=subcategory,
            force=True
        )
        source_map[filename] = meta.source_id
        print(f"Ingested '{filename}': SourceID={meta.source_id[:8]}, Chunks={len(chunks)}, Status={meta.status.value}")

    return source_map


def run_benchmark():
    factory = KnowledgeIngestionFactory()
    source_map = setup_pilot_corpus(factory)

    queries_path = Path("tests/rag_benchmark/queries.json").resolve()
    with open(queries_path, "r", encoding="utf-8") as f:
        queries = json.load(f)

    search_engine = HybridSearchEngine()

    total_queries = len(queries)
    positive_queries = [q for q in queries if q.get("should_match", True)]
    negative_queries = [q for q in queries if not q.get("should_match", True)]

    top1_hits = 0
    top3_hits = 0
    citation_ok = 0
    refusal_correct = 0
    total_latency_ms = 0.0

    category_stats: Dict[str, Dict[str, int]] = {}
    detailed_results = []

    print(f"\n--- Running Benchmark: {total_queries} Queries ---")

    for q in queries:
        qid = q["id"]
        cat = q["category"]
        query_text = q["query"]
        should_match = q.get("should_match", True)
        expected_src = q.get("expected_source")
        expected_kws = [k.lower() for k in q.get("expected_keywords", [])]

        if cat not in category_stats:
            category_stats[cat] = {"total": 0, "correct": 0}
        category_stats[cat]["total"] += 1

        t0 = time.perf_counter()
        hits = search_engine.search(query=query_text, top_k=3, min_score=0.20)
        t1 = time.perf_counter()
        latency_ms = (t1 - t0) * 1000.0
        total_latency_ms += latency_ms

        status = "FAIL"

        if not should_match:
            # Negative query: must return 0 hits
            if len(hits) == 0:
                refusal_correct += 1
                category_stats[cat]["correct"] += 1
                status = "PASS"
            else:
                status = f"FAIL (Returned {len(hits)} false positives)"
        else:
            # Positive query
            matched_top1 = False
            matched_top3 = False

            if hits:
                clean_src = (expected_src or "").lower().replace("sample_", "").split(".")[0].replace("_", " ")

                # Check top-1
                top1_chunk, top1_score, top1_trace = hits[0]
                content_lower = top1_chunk.content.lower()
                has_kws = any(kw in content_lower for kw in expected_kws) if expected_kws else False
                is_src = (clean_src in (top1_trace.title or "").lower().replace("_", " ")) if clean_src else False

                if has_kws or is_src:
                    top1_hits += 1
                    matched_top1 = True

                # Check top-3 hits
                for chunk, score, trace in hits:
                    c_lower = chunk.content.lower()
                    h_kw = any(kw in c_lower for kw in expected_kws) if expected_kws else False
                    i_src = (clean_src in (trace.title or "").lower().replace("_", " ")) if clean_src else False
                    if h_kw or i_src:
                        matched_top3 = True
                        break

                if matched_top1 or matched_top3:
                    top3_hits += 1

                # Check citation traceability
                if top1_trace.source_id and top1_trace.chunk_id and top1_trace.confidence > 0:
                    citation_ok += 1

            if matched_top1 or matched_top3:
                category_stats[cat]["correct"] += 1
                status = "PASS (Top-1)" if matched_top1 else "PASS (Top-3)"

        detailed_results.append({
            "id": qid,
            "category": cat,
            "query": query_text,
            "status": status,
            "hits_count": len(hits),
            "latency_ms": round(latency_ms, 2),
            "top1_score": round(hits[0][1], 4) if hits else 0.0,
            "top1_snippet": hits[0][0].content[:80] if hits else ""
        })

    # Summary metrics
    avg_latency = total_latency_ms / max(total_queries, 1)
    top1_acc = (top1_hits / max(len(positive_queries), 1)) * 100.0
    top3_acc = (top3_hits / max(len(positive_queries), 1)) * 100.0
    refusal_prec = (refusal_correct / max(len(negative_queries), 1)) * 100.0
    citation_compliance = (citation_ok / max(len(positive_queries), 1)) * 100.0

    print("\n=======================================================")
    print("           RAG BENCHMARK EVALUATION RESULTS            ")
    print("=======================================================")
    print(f"Total Queries Evaluated:    {total_queries}")
    print(f"Positive Queries:           {len(positive_queries)}")
    print(f"Negative Refusal Queries:   {len(negative_queries)}")
    print(f"Top-1 Retrieval Accuracy:   {top1_acc:.1f}% ({top1_hits}/{len(positive_queries)})")
    print(f"Top-3 Retrieval Accuracy:   {top3_acc:.1f}% ({top3_hits}/{len(positive_queries)})")
    print(f"Negative Refusal Precision: {refusal_prec:.1f}% ({refusal_correct}/{len(negative_queries)})")
    print(f"Citation Traceability:      {citation_compliance:.1f}% ({citation_ok}/{len(positive_queries)})")
    print(f"Average Retrieval Latency:  {avg_latency:.2f} ms")
    print("-------------------------------------------------------")
    print("Category Breakdown:")
    for cat, stats in category_stats.items():
        pct = (stats["correct"] / stats["total"]) * 100.0
        print(f"  - {cat:22s}: {stats['correct']}/{stats['total']} ({pct:.1f}%)")
    print("=======================================================\n")

    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_queries": total_queries,
        "metrics": {
            "top1_accuracy_pct": round(top1_acc, 2),
            "top3_accuracy_pct": round(top3_acc, 2),
            "refusal_precision_pct": round(refusal_prec, 2),
            "citation_traceability_pct": round(citation_compliance, 2),
            "average_latency_ms": round(avg_latency, 2)
        },
        "category_breakdown": category_stats,
        "results": detailed_results
    }

    report_path = Path("tests/rag_benchmark/benchmark_report.json").resolve()
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"Detailed benchmark report saved to {report_path}")

    # Return success flag
    return top1_acc >= 85.0 and refusal_prec >= 90.0


if __name__ == "__main__":
    success = run_benchmark()
    if not success:
        sys.exit(1)
