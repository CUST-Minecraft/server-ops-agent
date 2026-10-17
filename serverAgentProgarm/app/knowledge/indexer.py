"""Synchronize database recovery cases into the derived local index."""

from pathlib import Path

from sqlalchemy.orm import sessionmaker

from app.knowledge.case_service import RecoveryCaseService
from app.knowledge.embeddings import EmbeddingProvider
from app.knowledge.retriever import RecoveryIndex
from app.storage.models import RecoveryCaseRecord
from datetime import datetime, timezone


class RecoveryIndexer:
    def __init__(
        self,
        session_factory: sessionmaker,
        path: str | Path,
        embedding_provider: EmbeddingProvider,
        origin: str = "real",
    ):
        self.case_service = RecoveryCaseService(session_factory, origin=origin)
        self.index = RecoveryIndex(path, embedding_provider)

    def sync(self) -> int:
        self.case_service.reconcile()
        documents = self.case_service.index_documents()
        try:
            self.index.build(documents)
        except Exception:
            with self.case_service.session_factory() as session:
                rows = session.query(RecoveryCaseRecord).filter(
                    RecoveryCaseRecord.record_status == "active",
                    RecoveryCaseRecord.outcome == "verified",
                    RecoveryCaseRecord.index_status.in_(("pending", "failed")),
                ).all()
                for row in rows:
                    row.index_status = "failed"
                session.commit()
            raise
        with self.case_service.session_factory() as session:
            rows = session.query(RecoveryCaseRecord).filter(
                RecoveryCaseRecord.record_status == "active",
                RecoveryCaseRecord.outcome == "verified",
            ).all()
            now = datetime.now(timezone.utc)
            for row in rows:
                row.index_status = "indexed"
                row.indexed_at = now
                row.aggregate_dirty = False
            session.commit()
        return len(documents)
