from app.config import ServerSettings


def test_recovery_rag_defaults_to_vector_enabled(monkeypatch):
    monkeypatch.delenv("RECOVERY_RAG_ENABLED", raising=False)

    settings = ServerSettings()

    assert settings.recovery_rag_enabled is True
