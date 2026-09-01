import json
from pathlib import Path
from app.llm.llm_client import LLMClient
import logging

from app.storage.models import Incident

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


def select_relevant_memories(messages: list[dict], max_items: int = 5) -> list[str]:
    """用 LLM side-query 选出相关记忆的文件名。失败降级关键词匹配。"""
    files = list_memory_files()
    if not files:
        return []
    # 记忆太少时不值得多调一次 LLM：全量返回（README 常见卡点自查表）
    if len(files) <= 3:
        return [f["_file"] for f in files[:max_items]]
    catalog = "\n".join(f"{f.get('name')} ({f['_file']}): {f.get('description')}" for f in files)
    recent = format_recent_messages(messages[-6:])
    prompt = (
        "根据最近对话，从下面的记忆目录中选出真正有用的记忆。\n"
        "返回 JSON 数组，元素是目录里括号中的文件名（含 .md 后缀，原样返回，不要编造）。\n,示例:{name:文件名.md}"
        "不确定就不要选；都不相关就返回 []。\n\n"
        f"记忆目录:\n{catalog}\n\n最近对话:\n{recent}"
    )
    try:
        resp = LLMClient().chat(messages=[{"role": "user", "content": prompt}]).choices[0].message.content
        picked = json.loads(resp) if resp else None   # 空内容也走降级
    except Exception as e:
        logger.warning(f"选记忆 side-query 失败，降级关键词匹配: {e}")
        picked = None
    if not isinstance(picked, list):
        picked = _keyword_pick(files, recent)
    # 别名表：文件名 / stem / name 三种写法统一小写后映射回真实文件名
    # （LLM 输出不可信：会在 name 与 _file 间摇摆、大小写漂移、甚至拼接出
    #   "MySQL容器名.md" 这种不存在的名字——归一化匹配兜住这些变异）
    alias: dict[str, str] = {}
    for f in files:
        for k in (f["_file"], Path(f["_file"]).stem, str(f.get("name", ""))):
            if k:
                alias[k.lower()] = f["_file"]
    picked_files: list[str] = []
    for n in picked:
        if not isinstance(n, str):
            continue
        key = n.strip().lower()
        target = alias.get(key)
        if target is None and key.endswith(".md"):
            target = alias.get(key[:-3])          # 剥掉后缀按 stem 再查一次
        if target and target not in picked_files:
            picked_files.append(target)
    return picked_files[:max_items]


def _keyword_pick(files: list[dict], recent: str) -> list[str]:
    """降级路径：recent 里出现 name/description 关键词就选。宁可选不准，不能崩。"""
    low = recent.lower()
    picked = []
    for f in files:
        name = str(f.get("name", ""))
        desc = str(f.get("description", ""))
        tokens = [t for t in name.replace("-", " ").lower().split() if len(t) >= 2]
        if (name and name.lower() in low) or (desc and desc.lower() in low) or any(t in low for t in tokens):
            picked.append(f["_file"])
    return picked


def load_memories(messages: list[dict]) -> str:
    """把选中的记忆内容拼成一段文本，注入当前 user turn。"""
    files = select_relevant_memories(messages)
    blocks = [f"【记忆:{Path(f).stem}】\n{read_memory_body(f)}" for f in files]
    return "\n\n".join(blocks)


def load_memories_for_incident(incident) -> str:
    """Investigator 专用加载：query 是单子的 kind/title/detail（不是对话）。只读不写。

    与 load_memories 共用全套选/读逻辑——"相关"的定义不同而已：
    chat 路径的相关由对话定义，调查路径的相关由工单定义。
    """
    query = (
        f"[{incident.kind}] {incident.title} "
        f"{json.dumps(incident.detail, ensure_ascii=False)}"
    )
    return load_memories([{"role": "user", "content": query}])


def consolidate_memories() -> None:
    """文件数 ≥ 阈值时触发：LLM 去重/合并/淘汰，全量替换。"""
    import shutil
    from app.config import ServerSettings          # 与 executor.py 同款取配置

    threshold = ServerSettings().memory_consolidate_threshold
    files = list_memory_files()
    if len(files) < threshold:
        return

    corpus = "\n\n".join(
        f"---\nname: {f.get('name', '')}\ndescription: {f.get('description', '')}\n"
        f"type: {f.get('type', '')}\n---\n\n{read_memory_body(f['_file'])}"
        for f in files
    )
    prompt = (
        "对下面的运维记忆做去重、合并矛盾、淘汰过时。\n"
        "只使用已有内容,不得发明新信息。返回 JSON 数组: [{name, type, description, body}]\n\n"
        f"{corpus}"
    )
    try:
        resp = LLMClient().chat(messages=[{"role": "user", "content": prompt}]).choices[0].message.content
        new_mems = json.loads(resp) if resp else None
    except Exception as e:
        logger.warning(f"记忆整理: LLM/解析失败, 保留原文件: {e}")
        return
    if not isinstance(new_mems, list) or not new_mems:
        logger.warning("记忆整理: 返回非数组或为空, 保留原文件")
        return

    # ── 先写全量到临时目录；这一步任何失败都不碰 MEMORY_DIR ──
    tmp = MEMORY_DIR.parent / ".memory_tmp"
    old_files = [f for f in MEMORY_DIR.glob("*.md") if f.name != "MEMORY.md"]
    try:
        if tmp.exists():
            shutil.rmtree(tmp)
        tmp.mkdir(parents=True)
        for m in new_mems:
            if not isinstance(m, dict):
                raise ValueError(f"整理结果混入非 dict 项: {m!r}")
            name, mem_type = m.get("name"), m.get("type")
            if not isinstance(name, str) or not name or mem_type not in VALID_TYPES:
                raise ValueError(f"整理结果 name/type 非法: {m!r}")
            slug = name.lower().replace(" ", "-")
            desc, body = str(m.get("description", "")), str(m.get("body", ""))
            (tmp / f"{slug}.md").write_text(
                f"---\nname: {name}\ndescription: {desc}\ntype: {mem_type}\n---\n\n{body}\n",
                encoding="utf-8",
            )
    except Exception as e:
        logger.warning(f"记忆整理: 校验/写临时文件失败, 保留原文件: {e}")
        shutil.rmtree(tmp, ignore_errors=True)
        return

    # ── 替换：先把新文件全部就位(同名原子覆盖)，再清理多余的旧文件，最后重建索引 ──
    try:
        new_names = {f.name for f in tmp.glob("*.md")}
        for f in tmp.glob("*.md"):
            shutil.move(str(f), MEMORY_DIR / f.name)
        for old in old_files:
            if old.name not in new_names:
                old.unlink()
        _rebuild_index()
        logger.info("[Memory: consolidated %d -> %d files]", len(files), len(new_names))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

