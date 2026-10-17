"""Read-only knowledge tools for historical recovery cases."""

from app.knowledge.retriever import RecoveryIndex
from app.tools.base import Tool, ToolResult
from app.tools.builtin import validate_service_name


def build_knowledge_tools(
    index: RecoveryIndex,
    top_k: int = 5,
    max_context_chars: int = 6000,
) -> list[Tool]:
    def search_recovery_cases(args: dict) -> ToolResult:
        query = args.get("query", "")
        if not isinstance(query, str) or not query.strip() or len(query) > 500:
            return ToolResult(status="error", error="query 必须是 1-500 字符")
        service = args.get("service")
        if service is not None:
            try:
                service = validate_service_name(service)
            except ValueError as exc:
                return ToolResult(status="error", error=str(exc))
        result = index.search(query.strip(), service=service, top_k=top_k)
        filtered_hits = [
            hit for hit in result.hits
            if service is None or hit.service == service
        ]
        remaining = max_context_chars
        truncated = False
        hits = []
        for hit in filtered_hits:
            excerpt = hit.excerpt
            if len(excerpt) > remaining:
                excerpt = excerpt[:max(remaining, 0)]
                truncated = True
            if not excerpt:
                truncated = True
                break
            remaining -= len(excerpt)
            hits.append({
                "citation_id": hit.citation_id,
                "case_id": hit.case_id,
                "parent_case_id": hit.parent_case_id,
                "source_incident_ids": list(hit.source_incident_ids),
                "origin": hit.origin,
                "signature": hit.signature,
                "service": hit.service,
                "excerpt": excerpt,
                "score": hit.score,
                "passed_count": hit.passed_count,
                "failed_count": hit.failed_count,
                "section": hit.section,
                "outcome_scope": "postconditions_recovered_not_root_cause_proven",
            })
        data = {
            "corpus_version": result.corpus_version,
            "degraded": result.degraded,
            "stale": result.stale,
            "truncated": truncated,
            "hits": hits,
        }
        status = "no_data" if result.status == "success" and not hits else result.status
        return ToolResult(status=status, data=data, error=result.error)

    return [Tool(
        name="search_recovery_cases",
        description=(
            "检索历史已验证修复案例。结果是历史参考，不是当前事实，"
            "不会执行命令或授予修复权限。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 500},
                "service": {"type": "string", "pattern": r"^[a-zA-Z0-9_.-]+$"},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        handler=search_recovery_cases,
    )]
