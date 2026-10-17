from app.knowledge.embeddings import HashEmbeddingProvider
from app.knowledge.embeddings import OllamaEmbeddingProvider
from app.knowledge.models import IndexDocument
from app.knowledge.normalization import build_occurrence_signature, redact_text, search_tokens
from app.knowledge.retriever import RecoveryIndex
from app.knowledge.indexer import RecoveryIndexer


def _docs():
    return [
        IndexDocument(
            case_id="case-nginx-1",
            source_incident_ids=(1,),
            origin="chaos_lab",
            signature="sig-nginx",
            service="nginx",
            text="nginx inactive OOM killed process port 80 restored",
            passed_count=1,
            failed_count=0,
        ),
        IndexDocument(
            case_id="case-db-1",
            source_incident_ids=(2,),
            origin="real",
            signature="sig-mysql",
            service="docker",
            text="docker daemon inactive MySQL connection refused port 3306 restored",
            passed_count=1,
            failed_count=0,
        ),
    ]


def test_redact_text_removes_secrets_but_keeps_diagnostic_tokens():
    text = "OOM on nginx token=abc123 port 3306 Authorization: Bearer secret"

    redacted = redact_text(text)

    assert "abc123" not in redacted
    assert "secret" not in redacted
    assert "OOM" in redacted
    assert "3306" in redacted


def test_occurrence_signature_is_stable_for_canonical_fields():
    first = build_occurrence_signature({"service": "nginx", "port": 80, "state": "inactive"})
    second = build_occurrence_signature({"state": "inactive", "port": 80, "service": "nginx"})

    assert first == second


def test_hybrid_search_returns_exact_and_semantic_candidates(tmp_path):
    index = RecoveryIndex(
        tmp_path / "recovery.sqlite",
        embedding_provider=HashEmbeddingProvider(dimensions=32),
    )
    index.build(_docs())

    result = index.search("nginx OOM port 80", service="nginx", top_k=5)

    assert result.status == "success"
    assert result.hits[0].case_id == "case-nginx-1"
    assert result.hits[0].origin == "chaos_lab"


def test_sparse_and_dense_modes_are_individually_callable(tmp_path):
    index = RecoveryIndex(
        tmp_path / "recovery.sqlite",
        embedding_provider=HashEmbeddingProvider(dimensions=32),
    )
    index.build(_docs())

    sparse = index.search("nginx OOM port 80", service="nginx", mode="sparse")
    dense = index.search("nginx OOM port 80", service="nginx", mode="dense")

    assert sparse.status == "success"
    assert dense.status == "success"
    assert sparse.hits[0].case_id == "case-nginx-1"
    assert dense.hits[0].case_id == "case-nginx-1"


def test_no_data_does_not_return_nearest_unrelated_case(tmp_path):
    index = RecoveryIndex(
        tmp_path / "recovery.sqlite",
        embedding_provider=HashEmbeddingProvider(dimensions=32),
    )
    index.build(_docs())

    result = index.search("kafka rebalance partition", service="kafka", top_k=5)

    assert result.status == "no_data"
    assert result.hits == []


def test_dense_failure_degrades_to_sparse_results(tmp_path):
    class FailingEmbedding:
        model_id = "failing"

        def embed(self, texts):
            raise RuntimeError("embedding unavailable")

    index = RecoveryIndex(tmp_path / "recovery.sqlite", embedding_provider=FailingEmbedding())
    index.build(_docs(), build_embeddings=False)

    result = index.search("nginx OOM port 80", service="nginx", top_k=5)

    assert result.status == "success"
    assert result.degraded is True
    assert result.hits[0].case_id == "case-nginx-1"


def test_indexer_syncs_verified_cases_from_database(db, tmp_path):
    from tests.test_recovery_cases import _seed_verified

    _seed_verified(db)
    indexer = RecoveryIndexer(
        db,
        tmp_path / "recovery.sqlite",
        embedding_provider=HashEmbeddingProvider(32),
        origin="chaos_lab",
    )

    assert indexer.sync() == 2
    result = indexer.index.search("nginx OOM", service="nginx")
    assert result.status == "success"
    assert result.hits[0].source_incident_ids


def test_ollama_embedding_provider_uses_local_model(monkeypatch):
    calls = []

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"embeddings": [[0.1, 0.2]]}

    def fake_post(url, json, timeout):
        calls.append((url, json, timeout))
        return Response()

    monkeypatch.setattr("app.knowledge.embeddings.requests.post", fake_post)
    provider = OllamaEmbeddingProvider(model="qwen3-embedding:0.6b")

    assert provider.embed(["nginx OOM"]) == [[0.1, 0.2]]
    assert calls[0][0] == "http://127.0.0.1:11434/api/embed"
    assert calls[0][1]["model"] == "qwen3-embedding:0.6b"


def test_embedding_build_failure_keeps_sparse_index_available(tmp_path):
    class FailingEmbedding:
        model_id = "failing"

        def embed(self, texts):
            raise RuntimeError("ollama offline")

    index = RecoveryIndex(tmp_path / "recovery.sqlite", FailingEmbedding())

    index.build(_docs())
    result = index.search("nginx OOM port 80", service="nginx", mode="hybrid")

    assert result.status == "success"
    assert result.degraded is True
    assert result.hits[0].case_id == "case-nginx-1"

    no_match = index.search("kafka rebalance", service="kafka", mode="hybrid")
    assert no_match.status == "no_data"
    assert no_match.degraded is True


def test_chinese_query_uses_cjk_bigrams_for_sparse_match(tmp_path):
    assert "数据" in search_tokens("数据库连接失败")
    index = RecoveryIndex(tmp_path / "recovery.sqlite", HashEmbeddingProvider(32))
    index.build([
        IndexDocument(
            case_id="case-mysql-cn",
            source_incident_ids=(3,),
            origin="chaos_lab",
            signature="sig-mysql-cn",
            service="docker",
            text="数据库连接失败 MySQL connection refused port 3306",
        )
    ])

    result = index.search("数据库连接失败", service="docker", mode="sparse")

    assert result.status == "success"
    assert result.hits[0].case_id == "case-mysql-cn"


def test_sparse_results_are_ranked_by_bm25(tmp_path):
    index = RecoveryIndex(tmp_path / "recovery.sqlite", HashEmbeddingProvider(32))
    index.build([
        IndexDocument("case-broad", (1,), "real", "broad", "nginx", "nginx inactive port 80"),
        IndexDocument("case-exact", (2,), "real", "exact", "nginx", "nginx OOM port 80"),
    ])

    result = index.search("nginx OOM port 80", service="nginx", mode="sparse")

    assert result.hits[0].case_id == "case-exact"
