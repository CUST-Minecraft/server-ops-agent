from pathlib import Path

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