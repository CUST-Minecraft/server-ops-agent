from app.knowledge.context import FullCaseContextProvider
from app.knowledge.models import IndexDocument


def test_full_case_context_uses_stable_citations():
    provider = FullCaseContextProvider(max_chars=500)
    documents = [IndexDocument("case-b", (2,), "real", "sig-b", "nginx", "b text"),
                 IndexDocument("case-a", (1,), "real", "sig-a", "nginx", "a text")]

    result = provider.prepare(documents, corpus_version="v1")

    assert result.status == "ready"
    assert result.available_ids == ["KC_v1_case-a", "KC_v1_case-b"]
    assert "KC_v1_case-a" in result.text


def test_full_case_context_never_returns_partial_corpus():
    provider = FullCaseContextProvider(max_chars=10)
    documents = [IndexDocument("case-a", (1,), "real", "sig-a", "nginx", "long text")]

    result = provider.prepare(documents, corpus_version="v1")

    assert result.status == "over_budget"
    assert result.text == ""
    assert result.available_ids == []
