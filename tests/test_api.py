import io
import json

import pytest
from pypdf import PdfReader

TYPES = {
    "Unlimited Liability", "Automatic Renewal", "One-Sided Termination", "Non-Compete",
    "Indemnification", "Intellectual Property Assignment", "Binding Arbitration",
}


def _upload(client, name, data):
    return client.post("/upload", files={"file": (name, data)})


def test_health_reports_backends(client):
    h = client.get("/health").json()
    assert h["vector_store"]["backend"] == "qdrant-local-disk"
    assert h["llm"]["active"] == "none"
    assert "not legal advice" in h["disclaimer"]


@pytest.mark.parametrize("name", ["risky.txt", "risky.docx", "risky.pdf"])
def test_upload_formats_and_risk_detection(client, fixtures, name):
    r = _upload(client, name, (fixtures / name).read_bytes())
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"doc_id", "chunks", "filename"} and body["chunks"] >= 1
    d = client.get(f"/risks/{body['doc_id']}").json()
    found = {f["clause_type"] for f in d["flags"]}
    assert TYPES <= found, TYPES - found
    assert d["summary"]["high"] >= 6 and d["summary"]["overall_label"] in {"HIGH", "CRITICAL"}
    assert d["filename"] == name and d["engine"] == "rules"
    # contract with frontend: every field the UI reads
    for f in d["flags"]:
        for k in ("clause_type", "risk_level", "plain_english", "concerns", "chunk_index", "raw_text",
                  "severity_score", "suggested_rewrite", "negotiation_tip"):
            assert k in f
        assert f["risk_level"] in {"low", "medium", "high"}


def test_clean_contract_scores_low(client, fixtures):
    doc = _upload(client, "clean_nda.txt", (fixtures / "clean_nda.txt").read_bytes()).json()["doc_id"]
    d = client.get(f"/risks/{doc}").json()
    assert d["summary"]["high"] == 0 and d["summary"]["overall_label"] == "LOW"


def test_validation(client, fixtures):
    assert _upload(client, "x.exe", b"abc").status_code == 400
    r = _upload(client, "scan.pdf", (fixtures / "scanned.pdf").read_bytes())
    assert r.status_code == 422 and "scanned" in r.json()["detail"]
    assert _upload(client, "fake.pdf", b"not a pdf").status_code == 422
    assert _upload(client, "empty.txt", b"").status_code == 422
    assert _upload(client, "big.txt", b"a" * (10 * 1024 * 1024 + 10)).status_code == 413


def test_unknown_and_malformed_ids(client):
    assert client.get("/risks/not-a-uuid").status_code == 400
    assert client.get("/risks/00000000-0000-4000-8000-000000000000").status_code == 404
    r = client.post("/query", json={"doc_id": "00000000-0000-4000-8000-000000000000", "question": "hi"})
    assert r.status_code == 404


def test_query_without_llm_is_clear_and_cites_sources(client, risky_id):
    r = client.post("/query", json={"doc_id": risky_id, "question": "How long is the non-compete?"}).json()
    assert "[NO-LLM MODE]" in r["answer"] and r["engine"] == "none"
    assert any("five (5) years" in s["text"] for s in r["sources"])
    for s in r["sources"]:
        assert set(s) == {"text", "chunk_index", "score"}


def test_documents_are_isolated(client, fixtures, risky_id):
    other = _upload(client, "clean_nda.txt", (fixtures / "clean_nda.txt").read_bytes()).json()["doc_id"]
    r = client.post("/query", json={"doc_id": other, "question": "worldwide non-compete five years"}).json()
    assert r["sources"] and all("Acme" not in s["text"] and "worldwide" not in s["text"] for s in r["sources"])


def test_stream_contract(client, risky_id):
    with client.stream("POST", "/query/stream", json={"doc_id": risky_id, "question": "termination?"}) as r:
        events = [json.loads(l) for l in r.iter_lines() if l.strip()]
    assert events[-1]["done"] is True and events[-1]["sources"] and "engine" in events[-1]
    assert "".join(e["token"] for e in events[:-1])


def test_report_pdf_text(client, risky_id):
    r = client.get(f"/report/{risky_id}")
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
    assert "Legal Risk Analysis Report" in text and "Unlimited Liability" in text
    assert "risky.txt" in text and "not legal advice" in text


def test_report_survives_markup_characters(client):
    txt = b"The Contractor shall indemnify <b>any and all</b> claims & losses; liability is unlimited. A & B < C."
    doc = _upload(client, "markup.txt", txt).json()["doc_id"]
    assert client.get(f"/report/{doc}").status_code == 200


def test_delete_document(client, fixtures):
    doc = _upload(client, "clean_nda.txt", (fixtures / "clean_nda.txt").read_bytes()).json()["doc_id"]
    assert client.delete(f"/documents/{doc}").status_code == 200
    assert client.get(f"/risks/{doc}").status_code == 404


def test_cors_restricted(client):
    h = {"Access-Control-Request-Method": "POST"}
    ok = client.options("/upload", headers={**h, "Origin": "http://localhost:5173"})
    bad = client.options("/upload", headers={**h, "Origin": "http://evil.example"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "access-control-allow-origin" not in bad.headers
