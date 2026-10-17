"""Persistent hybrid recovery-case index and deterministic retrieval."""

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import tempfile
from pathlib import Path

from app.knowledge.embeddings import EmbeddingProvider
from app.knowledge.models import IndexDocument, SearchHit, SearchResult
from app.knowledge.normalization import fts_query, redact_text, search_tokens, sha256_text


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


class RecoveryIndex:
    def __init__(
        self,
        path: str | Path,
        embedding_provider: EmbeddingProvider,
        dense_min_score: float = 0.5,
        candidate_limit: int = 20,
        rrf_k: int = 60,
    ):
        self.path = Path(path)
        self.embedding_provider = embedding_provider
        self.dense_min_score = dense_min_score
        self.candidate_limit = candidate_limit
        self.rrf_k = rrf_k

    def build(self, documents: list[IndexDocument], build_embeddings: bool = True) -> str:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        corpus_version = sha256_text(
            json.dumps(
                [document.__dict__ for document in documents],
                sort_keys=True,
                ensure_ascii=False,
                default=str,
            )
            + self.embedding_provider.model_id
        )[:16]
        fd, temporary_name = tempfile.mkstemp(
            prefix=f"{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        os.close(fd)
        temporary_path = Path(temporary_name)
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(temporary_path)
            connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            connection.execute(
                """CREATE TABLE documents (
                    case_id TEXT PRIMARY KEY,
                    source_incident_ids TEXT NOT NULL,
                    origin TEXT NOT NULL,
                    signature TEXT NOT NULL,
                    service TEXT,
                    text TEXT NOT NULL,
                    passed_count INTEGER NOT NULL,
                    failed_count INTEGER NOT NULL,
                    parent_case_id TEXT,
                    section TEXT NOT NULL,
                    embedding TEXT
                )"""
            )
            connection.execute(
                "CREATE VIRTUAL TABLE documents_fts USING fts5(case_id UNINDEXED, content)"
            )
            embedding_available = build_embeddings
            if build_embeddings and documents:
                try:
                    embeddings = self.embedding_provider.embed(
                        [redact_text(document.text) for document in documents]
                    )
                except Exception:
                    # Preserve the lexical index when local Ollama is unavailable.
                    embedding_available = False
                    embeddings = [[] for _ in documents]
            else:
                embeddings = [[] for _ in documents]
            for document, embedding in zip(documents, embeddings):
                text = redact_text(document.text)
                lexical_text = f"{text}\n{' '.join(search_tokens(text))}"
                connection.execute(
                    "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        document.case_id,
                        json.dumps(document.source_incident_ids),
                        document.origin,
                        document.signature,
                        document.service,
                        text,
                        document.passed_count,
                        document.failed_count,
                        document.parent_case_id,
                        document.section,
                        json.dumps(embedding),
                    ),
                )
                connection.execute(
                    "INSERT INTO documents_fts(case_id, content) VALUES (?, ?)",
                    (document.case_id, lexical_text),
                )
            connection.execute("INSERT INTO metadata VALUES ('corpus_version', ?)", (corpus_version,))
            connection.execute("INSERT INTO metadata VALUES ('embedding_model', ?)", (self.embedding_provider.model_id,))
            connection.execute("INSERT INTO metadata VALUES ('embedding_available', ?)", (str(embedding_available).lower(),))
            connection.commit()
            connection.close()
            connection = None
            os.replace(temporary_path, self.path)
            return corpus_version
        finally:
            if connection is not None:
                connection.close()
            if temporary_path.exists():
                temporary_path.unlink()

    def search(
        self,
        query: str,
        service: str | None = None,
        top_k: int = 5,
        mode: str = "hybrid",
    ) -> SearchResult:
        if mode not in {"sparse", "dense", "hybrid"}:
            return SearchResult(status="error", error=f"unsupported retrieval mode: {mode}")
        if not self.path.exists():
            return SearchResult(status="error", error="recovery index does not exist")
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        corpus_version = connection.execute(
            "SELECT value FROM metadata WHERE key='corpus_version'"
        ).fetchone()[0]
        metadata = {
            row["key"]: row["value"]
            for row in connection.execute("SELECT key, value FROM metadata").fetchall()
        }
        sparse: list[sqlite3.Row] = []
        dense: list[tuple[sqlite3.Row, float]] = []
        degraded = False
        lexical = fts_query(query)
        if mode in {"sparse", "hybrid"} and lexical:
            if service:
                sparse = connection.execute(
                    """SELECT d.* FROM documents_fts f JOIN documents d ON d.case_id=f.case_id
                       WHERE documents_fts MATCH ? AND d.service=?
                       ORDER BY bm25(documents_fts) LIMIT ?""",
                    (lexical, service, self.candidate_limit),
                ).fetchall()
            else:
                sparse = connection.execute(
                    """SELECT d.* FROM documents_fts f JOIN documents d ON d.case_id=f.case_id
                       WHERE documents_fts MATCH ?
                       ORDER BY bm25(documents_fts) LIMIT ?""",
                    (lexical, self.candidate_limit),
                ).fetchall()
        try:
            if mode == "sparse":
                raise RuntimeError("dense disabled")
            if metadata.get("embedding_available") != "true":
                raise RuntimeError("embedding unavailable when index was built")
            query_vector = self.embedding_provider.embed([query])[0]
            rows = connection.execute(
                "SELECT * FROM documents WHERE service=? OR ? IS NULL",
                (service, service),
            ).fetchall()
            dense = [
                (row, _cosine(query_vector, json.loads(row["embedding"])))
                for row in rows
                if row["embedding"]
            ]
            dense.sort(key=lambda pair: pair[1], reverse=True)
            dense = [pair for pair in dense[:self.candidate_limit] if pair[1] >= self.dense_min_score]
        except Exception:
            degraded = mode in {"dense", "hybrid"}
            if mode == "dense":
                dense = []
        connection.close()
        if not sparse and not dense:
            return SearchResult(
                status="error" if degraded and mode == "dense" else "no_data",
                corpus_version=corpus_version,
                degraded=degraded,
                error="embedding unavailable" if degraded and mode == "dense" else None,
            )
        rankings = []
        if mode in {"sparse", "hybrid"}:
            rankings.append([row["case_id"] for row in sparse])
        if mode in {"dense", "hybrid"}:
            rankings.append([row[0]["case_id"] for row in dense])
        scores: dict[str, float] = {}
        for ranking in rankings:
            for rank, case_id in enumerate(ranking, start=1):
                scores[case_id] = scores.get(case_id, 0.0) + 1 / (self.rrf_k + rank)
        by_id = {row["case_id"]: row for row in sparse}
        by_id.update({row["case_id"]: row for row, _ in dense})
        seen: set[tuple[str, str]] = set()
        hits: list[SearchHit] = []
        for case_id, score in sorted(scores.items(), key=lambda item: item[1], reverse=True):
            row = by_id[case_id]
            grouping_key = (row["signature"], row["origin"])
            if grouping_key in seen:
                continue
            seen.add(grouping_key)
            citation = "KC_" + hashlib.sha256(
                f"{corpus_version}:{case_id}".encode("utf-8")
            ).hexdigest()[:12]
            hits.append(SearchHit(
                citation_id=citation,
                case_id=case_id,
                source_incident_ids=tuple(json.loads(row["source_incident_ids"])),
                origin=row["origin"],
                signature=row["signature"],
                service=row["service"],
                excerpt=row["text"][:1200],
                score=score,
                passed_count=row["passed_count"],
                failed_count=row["failed_count"],
                section=row["section"],
                parent_case_id=row["parent_case_id"],
            ))
            if len(hits) >= top_k:
                break
        return SearchResult(
            status="success" if hits else "no_data",
            hits=hits,
            corpus_version=corpus_version,
            degraded=degraded,
            error="embedding unavailable" if degraded and not sparse else None,
        )
