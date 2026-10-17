"""Offline retrieval ablation for the Verified Recovery index."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path

from app.config import ServerSettings
from app.knowledge.embeddings import (HashEmbeddingProvider,
                                      build_embedding_provider)
from app.knowledge.context import FullCaseContextProvider
from app.knowledge.models import IndexDocument
from app.knowledge.retriever import RecoveryIndex


@dataclass(frozen=True)
class EvalCase:
    query: str
    service: str
    expected_case_id: str


def load_corpus(path: Path) -> tuple[list[IndexDocument], list[EvalCase]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    documents = [
        IndexDocument(
            case_id=item["case_id"],
            source_incident_ids=tuple(item["source_incident_ids"]),
            origin=item["origin"],
            signature=item["signature"],
            service=item.get("service"),
            text=item["text"],
        )
        for item in payload["documents"]
    ]
    cases = [EvalCase(**item) for item in payload["cases"]]
    return documents, cases


def demo_documents() -> list[IndexDocument]:
    return load_corpus(Path("scripts/recovery_eval_corpus.json"))[0]


def eval_cases() -> list[EvalCase]:
    return load_corpus(Path("scripts/recovery_eval_corpus.json"))[1]


def score_group(documents: list[IndexDocument], cases: list[EvalCase], mode: str,
                embedding_provider) -> dict:
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        index = RecoveryIndex(
            Path(directory) / "recovery.sqlite",
            embedding_provider=embedding_provider,
        )
        index.build(documents)
        hits = 0
        reciprocal_rank = 0.0
        no_data = 0
        false_positive_no_data = 0
        latencies = []
        for case in cases:
            started = time.perf_counter()
            if mode == "none":
                returned = []
                status = "no_data"
            elif mode == "full":
                full = FullCaseContextProvider(max_chars=6000).prepare(documents, "demo")
                returned = [document.case_id for document in documents
                            if document.service == case.service] if full.status == "ready" else []
                status = "success" if returned else "no_data"
            else:
                result = index.search(case.query, service=case.service, mode=mode)
                returned = [hit.case_id for hit in result.hits]
                status = result.status
            latencies.append((time.perf_counter() - started) * 1000)
            if status == "no_data":
                no_data += 1
                if case.expected_case_id == "missing":
                    false_positive_no_data += 1
            if case.expected_case_id in returned:
                hits += 1
                reciprocal_rank += 1 / (returned.index(case.expected_case_id) + 1)
        total = len(cases)
        return {
            "mode": mode,
            "cases": total,
            "hit_rate": hits / total if total else 0.0,
            "mrr": reciprocal_rank / total if total else 0.0,
            "no_data": no_data,
            "negative_cases": sum(case.expected_case_id == "missing" for case in cases),
            "negative_no_data": false_positive_no_data,
            "avg_latency_ms": sum(latencies) / len(latencies) if latencies else 0.0,
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--corpus", type=Path,
                        default=Path("scripts/recovery_eval_corpus_50.json"))
    parser.add_argument("--embedding-provider", choices=("hash", "ollama"),
                        default="hash")
    args = parser.parse_args()
    documents, cases = load_corpus(args.corpus)
    embedding_provider = (
        HashEmbeddingProvider(dimensions=64)
        if args.embedding_provider == "hash"
        else build_embedding_provider(ServerSettings())
    )
    results = [
        score_group(documents, cases, mode, embedding_provider)
        for mode in ("none", "full", "sparse", "dense", "hybrid")
    ]
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return
    for result in results:
        print(
            f"{result['mode']:>6} hit={result['hit_rate']:.2f} "
            f"mrr={result['mrr']:.2f} no_data={result['no_data']} "
            f"negative_no_data={result['negative_no_data']}/{result['negative_cases']} "
            f"avg_ms={result['avg_latency_ms']:.2f}"
        )


if __name__ == "__main__":
    main()
