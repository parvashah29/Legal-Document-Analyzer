"""LLM backend selection: Groq (if key works) -> local Ollama -> none (rule-based / no Q&A generation)."""
import logging
import time

import httpx

import config

log = logging.getLogger("legal.llm")

_CACHE_TTL = 30.0
_status_cache: dict = {"at": 0.0, "value": None}


def _probe_groq() -> dict:
    if not config.GROQ_API_KEY:
        return {"available": False, "reason": "GROQ_API_KEY not set"}
    try:
        r = httpx.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"}, timeout=6,
        )
        if r.status_code == 200:
            return {"available": True, "model": config.GROQ_MODEL}
        return {"available": False, "reason": f"Groq rejected the key (HTTP {r.status_code})"}
    except Exception as e:  # noqa: BLE001
        return {"available": False, "reason": f"Groq unreachable ({type(e).__name__})"}


def _probe_ollama() -> dict:
    try:
        r = httpx.get(f"{config.OLLAMA_HOST}/api/tags", timeout=3)
        r.raise_for_status()
        names = [m.get("name", "") for m in r.json().get("models", [])]
        want = config.OLLAMA_MODEL
        match = next((n for n in names if n == want or n.split(":")[0] == want.split(":")[0]), None)
        if match:
            return {"available": True, "model": match}
        return {"available": False, "reason": f"model '{want}' not pulled (run: ollama pull {want})"}
    except Exception as e:  # noqa: BLE001
        return {"available": False, "reason": f"Ollama not reachable at {config.OLLAMA_HOST} ({type(e).__name__})"}


def status(force: bool = False) -> dict:
    now = time.time()
    if not force and _status_cache["value"] and now - _status_cache["at"] < _CACHE_TTL:
        return _status_cache["value"]
    prov = config.LLM_PROVIDER
    groq = _probe_groq() if prov in ("auto", "groq") else {"available": False, "reason": "disabled by LLM_PROVIDER"}
    ollama = _probe_ollama() if prov in ("auto", "ollama") else {"available": False, "reason": "disabled by LLM_PROVIDER"}
    order = [n for n, s in (("groq", groq), ("ollama", ollama)) if s["available"]]
    value = {
        "active": order[0] if order else "none",
        "order": order,
        "groq": groq,
        "ollama": ollama,
    }
    _status_cache.update(at=now, value=value)
    return value


def reset_cache():
    _status_cache.update(at=0.0, value=None)


def build_model(name: str, json_mode: bool = False):
    st = status()[name]
    if name == "groq":
        from langchain_groq import ChatGroq
        kw = {"model_kwargs": {"response_format": {"type": "json_object"}}} if json_mode else {}
        return ChatGroq(api_key=config.GROQ_API_KEY, model=st["model"], temperature=0.1,
                        timeout=config.LLM_TIMEOUT_S, max_retries=1, **kw)
    from langchain_ollama import ChatOllama
    kw = {"format": "json"} if json_mode else {}
    return ChatOllama(base_url=config.OLLAMA_HOST, model=st["model"], temperature=0.1,
                      client_kwargs={"timeout": config.LLM_TIMEOUT_S}, **kw)


def candidates(json_mode: bool = False):
    """Yield (name, model) for each available provider, preferred first."""
    for name in status()["order"]:
        try:
            yield name, build_model(name, json_mode)
        except Exception as e:  # noqa: BLE001
            log.warning("Could not init %s: %s", name, type(e).__name__)


async def ainvoke(messages, json_mode: bool = False):
    """Invoke the first working provider. Returns (provider_name, text) or (None, None)."""
    for name, model in candidates(json_mode):
        try:
            resp = await model.ainvoke(messages)
            return name, resp.content
        except Exception as e:  # noqa: BLE001
            log.warning("%s call failed (%s); trying next provider", name, type(e).__name__)
            reset_cache()
    return None, None


async def astream(messages):
    """Yield (provider_name, token). Falls through to next provider only if nothing was emitted."""
    for name, model in candidates():
        emitted = False
        try:
            async for chunk in model.astream(messages):
                tok = chunk.content if isinstance(chunk.content, str) else ""
                if tok:
                    emitted = True
                    yield name, tok
            return
        except Exception as e:  # noqa: BLE001
            log.warning("%s stream failed (%s)", name, type(e).__name__)
            reset_cache()
            if emitted:
                return
