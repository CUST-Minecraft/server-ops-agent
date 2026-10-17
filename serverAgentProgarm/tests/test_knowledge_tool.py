import json

from app.knowledge.embeddings import HashEmbeddingProvider
from app.knowledge.models import IndexDocument, SearchHit, SearchResult
from app.knowledge.retriever import RecoveryIndex
from app.tools.knowledge import build_knowledge_tools


def test_search_recovery_cases_is_read_only_and_structured(tmp_path):
    index = RecoveryIndex(tmp_path / "recovery.sqlite", HashEmbeddingProvider(32))
    index.build([
        IndexDocument(
            case_id="case-1",
            source_incident_ids=(1,),
            origin="chaos_lab",
            signature="sig-1",
            service="nginx",
            text="nginx inactive OOM port 80 restored",
        )
    ])
    tool = build_knowledge_tools(index)[0]

    result = tool.handler({"query": "nginx OOM port 80", "service": "nginx"})

    assert result.status == "success"
    assert result.data["hits"][0]["citation_id"].startswith("KC_")
    assert result.data["hits"][0]["source_incident_ids"] == [1]


def test_search_recovery_cases_rejects_unsafe_service(tmp_path):
    index = RecoveryIndex(tmp_path / "recovery.sqlite", HashEmbeddingProvider(32))
    tool = build_knowledge_tools(index)[0]

    result = tool.handler({"query": "nginx", "service": "nginx; reboot"})

    assert result.status == "error"
    assert "服务名" in result.error


def test_knowledge_tool_respects_context_budget(tmp_path):
    index = RecoveryIndex(tmp_path / "recovery.sqlite", HashEmbeddingProvider(32))
    index.build([
        IndexDocument(
            case_id="case-1",
            source_incident_ids=(1,),
            origin="chaos_lab",
            signature="sig-1",
            service="nginx",
            text="nginx OOM " + "evidence " * 100,
        )
    ])
    tool = build_knowledge_tools(index, max_context_chars=80)[0]

    result = tool.handler({"query": "nginx OOM", "service": "nginx"})

    assert result.status == "success"
    assert result.data["truncated"] is True
    assert len(result.data["hits"][0]["excerpt"]) <= 80


def test_search_recovery_cases_filters_cross_service_hits():
    class FakeIndex:
        def search(self, _query, service=None, top_k=5):
            return SearchResult(
                status="success",
                hits=[
                    SearchHit(
                        citation_id="KC_docker",
                        case_id="case-docker",
                        source_incident_ids=(2,),
                        origin="synthetic_eval",
                        signature="sig-docker",
                        service="docker",
                        excerpt="docker daemon inactive",
                        score=0.4,
                        passed_count=1,
                        failed_count=0,
                    ),
                    SearchHit(
                        citation_id="KC_nginx",
                        case_id="case-nginx",
                        source_incident_ids=(1,),
                        origin="synthetic_eval",
                        signature="sig-nginx",
                        service="nginx",
                        excerpt="nginx inactive",
                        score=0.3,
                        passed_count=1,
                        failed_count=0,
                    ),
                ],
            )

    tool = build_knowledge_tools(FakeIndex())[0]

    result = tool.handler({"query": "service down", "service": "nginx"})

    assert result.status == "success"
    assert [hit["service"] for hit in result.data["hits"]] == ["nginx"]
