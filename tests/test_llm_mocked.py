"""LLM paths exercised with fake models (no network, no Ollama)."""
import json

import pytest

import classifier
import llm
import retrieval


class FakeChunk:
    def __init__(self, c):
        self.content = c


class FakeModel:
    def __init__(self, reply):
        self.reply = reply

    async def ainvoke(self, messages):
        return FakeChunk(self.reply)

    async def astream(self, messages):
        for part in self.reply.split(" "):
            yield FakeChunk(part + " ")


@pytest.fixture
def fake_llm(monkeypatch):
    def install(reply):
        monkeypatch.setattr(llm, "status", lambda force=False: {
            "active": "ollama", "order": ["ollama"], "groq": {"available": False, "reason": "x"},
            "ollama": {"available": True, "model": "fake"}})
        monkeypatch.setattr(llm, "candidates", lambda json_mode=False: iter([("ollama", FakeModel(reply))]))
    return install


def test_qa_uses_llm_and_engine(client, risky_id, fake_llm):
    fake_llm("### Summary\nFive years [Excerpt 1].")
    r = client.post("/query", json={"doc_id": risky_id, "question": "non-compete length?"}).json()
    assert r["engine"] == "ollama" and "Five years" in r["answer"] and r["sources"]
    retrieval.clear_chat_history(risky_id)


def test_enrichment_applies_valid_json_and_keeps_rule_severity(client, fixtures, fake_llm):
    fake_llm(json.dumps({"plain_english": "LLM explanation of this clause.", "concerns": ["a concern"],
                         "suggested_rewrite": "A rewritten clause here.", "negotiation_tip": "A negotiation tip here."}))
    doc = client.post("/upload", files={"file": ("e.txt", (fixtures / "risky.txt").read_bytes())}).json()["doc_id"]
    d = client.get(f"/risks/{doc}?enrich=true").json()
    assert d["engine"] == "rules+llm:ollama"
    top = d["flags"][0]
    assert top["plain_english"] == "LLM explanation of this clause." and top["analysis_source"] == "rules+llm:ollama"
    assert top["severity_score"] == 9  # detection/severity stay deterministic


def test_enrichment_garbage_falls_back_to_rules(client, fixtures, fake_llm):
    fake_llm("this is not json at all")
    doc = client.post("/upload", files={"file": ("g.txt", (fixtures / "risky.txt").read_bytes())}).json()["doc_id"]
    d = client.get(f"/risks/{doc}?enrich=true").json()
    assert d["engine"] == "rules" and d["flags"][0]["analysis_source"] == "rules"


def test_parse_llm_json_variants():
    assert classifier.parse_llm_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert classifier.parse_llm_json('Sure! {"a": 2} done') == {"a": 2}
    assert classifier.parse_llm_json("nope") is None
