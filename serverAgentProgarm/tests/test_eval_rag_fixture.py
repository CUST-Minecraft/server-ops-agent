from pathlib import Path

from scripts.eval_rag import load_corpus


def test_synthetic_recovery_corpus_has_labeled_positive_and_negative_cases() -> None:
    documents, cases = load_corpus(
        Path("scripts/recovery_eval_corpus.json")
    )

    assert len(documents) >= 8
    assert len(cases) >= 10
    assert all(document.origin == "synthetic_eval" for document in documents)
    assert any(case.expected_case_id == "missing" for case in cases)


def test_large_synthetic_recovery_corpus_is_available() -> None:
    documents, cases = load_corpus(
        Path("scripts/recovery_eval_corpus_50.json")
    )

    assert len(documents) >= 50
    assert len(cases) >= 60
    assert sum(case.expected_case_id == "missing" for case in cases) >= 10
