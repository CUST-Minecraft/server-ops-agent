from types import SimpleNamespace

import app.agent.memory as memory


def fake_llm_response(content):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def test_write_list_read_and_rebuild_index(memory_dir):
    memory.write_memory_file("SSH Port", "server", "SSH listener", "Port is 22.")

    assert memory.list_memory_files() == [{
        "name": "SSH Port",
        "description": "SSH listener",
        "type": "server",
        "_file": "ssh-port.md",
    }]
    assert memory.read_memory_body("ssh-port.md") == "Port is 22."
    assert (memory_dir / "MEMORY.md").read_text(encoding="utf-8") == "- [SSH Port](ssh-port.md) — SSH listener\n"


def test_memory_listing_ignores_index_file(memory_dir):
    memory_dir.mkdir()
    (memory_dir / "MEMORY.md").write_text("index", encoding="utf-8")

    assert memory.list_memory_files() == []


def test_extract_memories_writes_only_valid_new_types(memory_dir, monkeypatch):
    payload = (
        '[{"name":"SSH Port","type":"server","description":"SSH listener","body":"Port is 22."},'
        '{"name":"Bad","type":"unknown","description":"x","body":"x"}]'
    )
    monkeypatch.setattr(memory, "LLMClient", lambda: SimpleNamespace(chat=lambda **_kwargs: fake_llm_response(payload)))

    assert memory.extract_memories([{"role": "user", "content": "SSH 是 22 端口"}]) == 1
    assert memory.extract_memories([{"role": "user", "content": "SSH 是 22 端口"}]) == 0
    assert memory.read_memory_body("ssh-port.md") == "Port is 22."


def test_consolidation_does_not_call_llm_below_threshold(memory_dir, monkeypatch):
    memory.write_memory_file("SSH Port", "server", "SSH listener", "Port is 22.")
    monkeypatch.setattr("app.config.ServerSettings", lambda: SimpleNamespace(memory_consolidate_threshold=2))
    monkeypatch.setattr(memory, "LLMClient", lambda: (_ for _ in ()).throw(AssertionError("should not call LLM")))

    memory.consolidate_memories()

    assert [item["_file"] for item in memory.list_memory_files()] == ["ssh-port.md"]
