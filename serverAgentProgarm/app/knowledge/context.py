"""Fair full-corpus context provider used by the B evaluation baseline."""

from dataclasses import dataclass

from app.knowledge.models import IndexDocument


@dataclass(frozen=True)
class FullContextResult:
    status: str
    text: str
    available_ids: list[str]


class FullCaseContextProvider:
    def __init__(self, max_chars: int = 6000):
        self.max_chars = max_chars

    def prepare(
        self,
        documents: list[IndexDocument],
        corpus_version: str,
    ) -> FullContextResult:
        blocks: list[str] = []
        ids: list[str] = []
        for document in sorted(documents, key=lambda item: item.case_id):
            citation_id = f"KC_{corpus_version}_{document.case_id}"
            blocks.append(
                f"[{citation_id}] origin={document.origin} service={document.service}\n"
                f"{document.text}"
            )
            ids.append(citation_id)
        text = "\n\n".join(blocks)
        if len(text) > self.max_chars:
            return FullContextResult(status="over_budget", text="", available_ids=[])
        return FullContextResult(status="ready", text=text, available_ids=ids)
