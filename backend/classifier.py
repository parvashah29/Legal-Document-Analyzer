"""Clause risk classification: deterministic rules (rules.py) + optional LLM enrichment of wording."""
import asyncio
import json
import logging

import config
import llm
import store
from rules import detect, level_for

log = logging.getLogger("legal.classifier")

_cache: dict = {}  # doc_id -> result (documents are immutable once ingested)

ENRICH_PROMPT = """You are a contract attorney helping a non-lawyer. A rule engine flagged this clause as "{clause_type}" (risk: {level}).
Respond ONLY with a JSON object with these keys:
"plain_english": 1-2 sentences explaining what THIS clause means for the signer, based only on the text,
"concerns": array of 2-3 short strings naming specific problems in THIS text,
"suggested_rewrite": a fairer, balanced rewrite of the clause,
"negotiation_tip": one sentence the signer can say to the other party.
Clause text:
{text}"""


class DocumentNotFound(LookupError):
    pass


def overall(flags: list[dict]) -> tuple[int, str]:
    """0-100 score: sum of severity^1.5 (so one critical clause outweighs several minor ones), capped."""
    score = min(100, round(sum(f["severity_score"] ** 1.5 for f in flags)))
    label = "LOW" if score < 25 else "MODERATE" if score < 50 else "HIGH" if score < 75 else "CRITICAL"
    return score, label


def _clean_list(v, limit=4):
    if not isinstance(v, list):
        return None
    out = [str(x).strip() for x in v if str(x).strip()]
    return out[:limit] or None


def _clean_str(v):
    return v.strip() if isinstance(v, str) and len(v.strip()) > 5 else None


def parse_llm_json(content: str) -> dict | None:
    if not content:
        return None
    content = content.strip()
    if "```" in content:
        parts = content.split("```")
        content = parts[1].removeprefix("json").strip() if len(parts) > 1 else content
    try:
        data = json.loads(content)
    except Exception:  # noqa: BLE001
        start, end = content.find("{"), content.rfind("}")
        try:
            data = json.loads(content[start:end + 1])
        except Exception:  # noqa: BLE001
            return None
    return data if isinstance(data, dict) else None


async def _enrich(flag: dict, sem: asyncio.Semaphore) -> None:
    prompt = ENRICH_PROMPT.format(clause_type=flag["clause_type"], level=flag["risk_level"], text=(flag.get("evidence") or flag["raw_text"])[:1200])
    async with sem:
        name, content = await llm.ainvoke(prompt, json_mode=True)
    data = parse_llm_json(content) if name else None
    if not data:
        return
    changed = False
    for key, clean in (("plain_english", _clean_str), ("concerns", _clean_list),
                       ("suggested_rewrite", _clean_str), ("negotiation_tip", _clean_str)):
        val = clean(data.get(key))
        if val:
            flag[key] = val
            changed = True
    if changed:
        flag["analysis_source"] = f"rules+llm:{name}"


def rule_flags(chunks: list[dict]) -> list[dict]:
    flags, seen = [], set()
    for ch in chunks:
        for hit in detect(ch["text"]):
            r = hit["rule"]
            key = (r.key, hit["evidence"][:120])
            if key in seen:  # same sentence seen in an overlapping neighbour chunk
                continue
            seen.add(key)
            flags.append({
                "clause_type": r.clause_type,
                "risk_level": level_for(hit["severity"]),
                "severity_score": hit["severity"],
                "plain_english": r.plain_english,
                "concerns": list(r.concerns),
                "chunk_index": ch["chunk_index"],
                "raw_text": ch["text"][:700],
                "evidence": hit["evidence"][:400],
                "suggested_rewrite": r.rewrite,
                "negotiation_tip": r.tip,
                "analysis_source": "rules",
            })
    flags.sort(key=lambda f: (-f["severity_score"], f["chunk_index"]))
    return flags


async def classify_clauses(doc_id: str, use_llm: bool = True) -> dict:
    chunks = store.get_chunks(doc_id)
    if not chunks:
        raise DocumentNotFound(doc_id)
    if doc_id in _cache and (_cache[doc_id]["llm_used"] or not use_llm):
        return _cache[doc_id]["result"]  # an enriched result also satisfies a rules-only request

    flags = rule_flags(chunks)
    st = llm.status()
    llm_used = False
    if use_llm and st["active"] != "none" and flags:
        sem = asyncio.Semaphore(1 if st["active"] == "ollama" else 4)
        await asyncio.gather(*(_enrich(f, sem) for f in flags[: config.MAX_LLM_CLAUSES]))
        llm_used = any(f["analysis_source"] != "rules" for f in flags)

    score, label = overall(flags)
    result = {
        "doc_id": doc_id,
        "filename": chunks[0].get("filename", ""),
        "flags": flags,
        "summary": {
            "high": sum(f["risk_level"] == "high" for f in flags),
            "medium": sum(f["risk_level"] == "medium" for f in flags),
            "low": sum(f["risk_level"] == "low" for f in flags),
            "overall_score": score,
            "overall_label": label,
        },
        "engine": "rules+llm:" + st["active"] if llm_used else "rules",
        "disclaimer": config.DISCLAIMER,
    }
    _cache[doc_id] = {"result": result, "llm_used": llm_used}
    return result


def forget(doc_id: str) -> None:
    _cache.pop(doc_id, None)
