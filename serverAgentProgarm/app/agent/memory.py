import json
from pathlib import Path
from app.llm.llm_client import LLMClient
import logging

logger = logging.getLogger(__name__)



MEMORY_DIR = Path(".memory")    # 项目根下的 .memory/（demo 与 CLI 的工作目录都是项目根）

VALID_TYPES = {"operator", "server", "incident_lesson", "runbook_hint"}

def write_memory_file(name: str, mem_type: str, description: str, body: str) -> None:
    """写一个记忆文件并重建索引。"""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)   # 首次写入前 .memory/ 并不存在
    slug = name.lower().replace(" ", "-")
    path = MEMORY_DIR / f"{slug}.md"
    path.write_text(
        f"---\nname: {name}\ndescription: {description}\ntype: {mem_type}\n---\n\n{body}\n",
        encoding="utf-8",
    )
    _rebuild_index()

def _read_frontmatter(path: Path) -> dict:
    """解析 .md 顶部 --- 与 --- 之间的键值对（只认单行 key: value）。
    不引 pyyaml：我们的 frontmatter 只有单行字符串字段，手写解析足够。"""
    fm: dict = {}
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}                                  # 没有 frontmatter：返回空
    for line in lines[1:]:
        if line.strip() == "---":                  # 结束分隔符，停止
            break
        key, sep, val = line.partition(":")
        if sep:                                    # 只认 key: value 行，其余忽略
            fm[key.strip()] = val.strip()
    return fm

def list_memory_files() -> list[dict]:
    """列出全部记忆的元数据（frontmatter dict，附带 _file=文件名）。
    步骤 3 防重与步骤 4 side-query 都用它。"""
    if not MEMORY_DIR.exists():
        return []
    out = []
    for f in sorted(MEMORY_DIR.glob("*.md")):
        if f.name == "MEMORY.md":
            continue
        fm = _read_frontmatter(f)
        if fm:
            fm["_file"] = f.name          # 记下文件名：side-query 选完要按它读正文
            out.append(fm)
    return out

def read_memory_body(filename: str) -> str:
    """读记忆正文（跳过 frontmatter，返回第二个 --- 之后的内容）。步骤 4 注入时用。"""
    lines = (MEMORY_DIR / filename).read_text(encoding="utf-8").splitlines()
    if lines and lines[0].strip() == "---":
        try:
            end = lines.index("---", 1)            # 第二个 --- 是 frontmatter 结束
            return "\n".join(lines[end + 1:]).strip()
        except ValueError:                         # 没有结束分隔符：整个文件当正文
            return "\n".join(lines[1:]).strip()
    return "\n".join(lines)                        # 没有 frontmatter：整个文件都是正文

def _rebuild_index() -> None:
    """扫描全部 .md（排除 MEMORY.md），重建索引文件。"""
    lines = []
    for f in sorted(MEMORY_DIR.glob("*.md")):
        if f.name == "MEMORY.md":
            continue
        fm = _read_frontmatter(f)      # 解析 frontmatter
        if not fm:
            continue                   # 无 frontmatter 的文件跳过（一行坏文件不崩整个重建）
        lines.append(f"- [{fm.get('name', f.stem)}]({f.name}) — {fm.get('description', '')}")
    (MEMORY_DIR / "MEMORY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def format_recent_messages(messages: list[dict]) -> str:
    """把消息列表拼成纯文本对话（提取/选记忆的 prompt 用；步骤 4 也复用）。"""
    return "\n".join(f"{m['role']}: {m['content']}" for m in messages)

def extract_memories(messages: list[dict]) -> int:
    """从最近对话提取新记忆，返回写入条数。LLM 失败返回 0，不阻塞主流程。"""
    dialogue = format_recent_messages(messages[-10:])
    existing = "\n".join(f"- {m.get('name')}: {m.get('description')}" for m in list_memory_files())
    prompt = (
        "从对话中提取值得长期记住的运维信息。\n"
        "类型: operator(值班人偏好)/server(服务器特性)/incident_lesson(故障经验)/runbook_hint(排查线索)\n"
        "返回 JSON 数组: [{name, type, description, body}]。没有新信息或已覆盖则返回 []。\n\n"
        f"已有记忆:\n{existing}\n\n对话:\n{dialogue[:4000]}"
    )
    # TODO(你来实现)：
    #   1) 调 LLM 拿 JSON（复用 llm_client 或直接 openai SDK）
    #   2) json.loads 失败 / 非数组 -> 记 warning 返回 0
    #   3) 逐条校验: name/type 非空、type 在 VALID_TYPES、已有记忆没覆盖（防重）
    #   4) write_memory_file(...) 并计数；logger.info("[Memory: extracted N new memories]")
    try:
        llm = LLMClient()
        response = llm.chat(messages=[{"role": "user", "content": prompt}]).choices[0].message.content
    except Exception as e:
        logger.warning(f"llm调用出现错误,{e}")
        return 0

    try:
        results : list[dict] = json.loads(response)
    except json.JSONDecodeError as e:
        logger.warning(f"记忆反序列化失败,{e},总结失败,返回null")
        results = []
        return 0

    memory_len = 0
    if not isinstance(results, list):
        logger.warning("返回结果非数组,解析错误")
        return 0

    if not response:  # None / 空串直接走失败分支
        logger.warning("LLM 返回空内容,跳过记忆提取")
        return 0

    for result in results:
        if not isinstance(result, dict):
            continue
        if result.get("name") is None:
            continue
        if result.get("type") not in VALID_TYPES:
            continue
        name = result.get("name")
        # 万一llm抽风,防御性措施
        if not isinstance(name, str) or not name:
            continue

        slug = name.lower().replace(" ", "-")
        if (MEMORY_DIR / f"{slug}.md").exists():
            continue
        write_memory_file(name=result.get("name"),mem_type=result.get("type"),description=result.get("description",""),body=result.get("body",""))
        memory_len += 1
    logger.info("[Memory: extracted %d new memories]",memory_len)
    return memory_len









