"""Retrieval-augmented Q&A over a single document."""
import asyncio
import json
import logging

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

import llm
import store

log = logging.getLogger("legal.retrieval")

SYSTEM = """You are a careful contract analyst. Answer using ONLY the numbered contract excerpts below.
Cite the excerpts you rely on like [Excerpt 2]. If the excerpts do not contain the answer, say exactly:
"This information is not present in the uploaded contract." Never invent terms, numbers or parties.
You are not a lawyer; do not give legal advice.

Format:
### Summary
A concise answer.

### Key Points
- Findings, each with an [Excerpt N] citation.

### Risks & Concerns
- Risky, one-sided or ambiguous language relevant to the question (or "None identified in the retrieved excerpts.").

Contract excerpts:
{context}"""

NO_LLM_MARKER = "[NO-LLM MODE]"

conversation_store: dict[str, list] = {}


def clear_chat_history(doc_id: str) -> None:
    conversation_store.pop(doc_id, None)


def _history(chat_history, doc_id):
    src = chat_history if chat_history else None
    if src:
        out = []
        for m in src[-10:]:
            if m["role"] == "user":
                out.append(HumanMessage(content=m["content"]))
            elif m["role"] == "assistant":
                out.append(AIMessage(content=m["content"]))
        return out
    return list(conversation_store.get(doc_id, []))


def _save(doc_id, q, a):
    h = conversation_store.setdefault(doc_id, [])
    h += [HumanMessage(content=q), AIMessage(content=a)]
    conversation_store[doc_id] = h[-10:]


def _build_messages(question, sources, history):
    context = "\n\n".join(f"[Excerpt {i + 1}] (chunk #{s['chunk_index'] + 1})\n{s['text']}" for i, s in enumerate(sources))
    return [SystemMessage(content=SYSTEM.format(context=context)), *history, HumanMessage(content=question)]


def no_llm_answer(sources: list[dict], reason: str) -> str:
    bullets = "\n".join(f"- **Excerpt {i + 1} (chunk #{s['chunk_index'] + 1})**: {s['text'].strip()[:500]}" for i, s in enumerate(sources))
    return (
        f"### Summary\n{NO_LLM_MARKER} No language model is available ({reason}), so no written answer can be generated. "
        f"Below are the {len(sources)} passages of your contract most relevant to the question, found by semantic search. "
        "Start Ollama (`ollama serve`) or set GROQ_API_KEY to enable generated answers.\n\n"
        f"### Key Points\n{bullets or '- No matching passages found.'}\n"
    )


def _no_llm_reason() -> str:
    st = llm.status()
    return f"Groq: {st['groq'].get('reason', 'unavailable')}; Ollama: {st['ollama'].get('reason', 'unavailable')}"


def retrieve(doc_id: str, question: str, limit: int = 5) -> list[dict]:
    return store.search(doc_id, question, limit)


async def query_rag(doc_id: str, question: str, chat_history=None) -> dict:
    sources = await asyncio.to_thread(retrieve, doc_id, question)
    if not sources:
        return {"answer": "This information is not present in the uploaded contract.", "sources": [], "engine": "none"}
    history = _history(chat_history, doc_id)
    name, answer = await llm.ainvoke(_build_messages(question, sources, history))
    if not name or not answer:
        answer, name = no_llm_answer(sources, _no_llm_reason()), "none"
    _save(doc_id, question, answer)
    return {"answer": answer, "sources": sources, "engine": name}


async def query_rag_stream(doc_id: str, question: str, chat_history=None):
    """Yields newline-delimited JSON events: {token, done:false}... then {done:true, sources, engine}."""
    try:
        sources = await asyncio.to_thread(retrieve, doc_id, question)
    except Exception as e:  # noqa: BLE001
        log.exception("retrieval failed")
        yield json.dumps({"token": "", "done": True, "error": f"Search failed: {type(e).__name__}", "sources": []}) + "\n"
        return
    if not sources:
        msg = "This information is not present in the uploaded contract."
        yield json.dumps({"token": msg, "done": False}) + "\n"
        yield json.dumps({"token": "", "done": True, "sources": [], "engine": "none"}) + "\n"
        return
    history = _history(chat_history, doc_id)
    full, engine = "", "none"
    async for name, tok in llm.astream(_build_messages(question, sources, history)):
        engine = name
        full += tok
        yield json.dumps({"token": tok, "done": False}) + "\n"
    if not full:
        full = no_llm_answer(sources, _no_llm_reason())
        for i in range(0, len(full), 40):
            yield json.dumps({"token": full[i:i + 40], "done": False}) + "\n"
    _save(doc_id, question, full)
    yield json.dumps({"token": "", "done": True, "sources": sources, "engine": engine}) + "\n"
