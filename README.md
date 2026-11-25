# Legal Document Analyzer

Upload a contract (PDF, DOCX or TXT), get a risk scan of its clauses, ask questions answered from the document with source excerpts, and download a PDF report. Runs fully locally; cloud accounts are optional.

> **Not legal advice.** Output is automated, preliminary and can be wrong or incomplete. It does not create an attorney-client relationship. Have a qualified attorney review any contract before you sign it.

## What it does (and how)

| Feature | How it works |
| --- | --- |
| Ingestion | PDF (`pypdf`), DOCX (`python-docx`, including tables) and TXT, up to 10 MB, parsed in memory (no uploaded file is written to disk). Scanned/image-only PDFs and password-protected PDFs are rejected with a clear message (no OCR). |
| Chunking + vectors | ~900-character chunks, embedded locally with `fastembed` (`BAAI/bge-small-en-v1.5`), stored in Qdrant. |
| Risk scan | A deterministic rule engine (`backend/rules.py`, 19 clause types) flags e.g. unlimited liability, nominal liability caps, auto-renewal, one-sided termination, non-compete (escalated for long/worldwide), unilateral indemnity, IP assignment, arbitration, rights waivers, unilateral changes, late fees. Severity 1-10 per flag, overall 0-100 score and label. |
| LLM enrichment | If a language model is available, it rewrites the plain-English explanation, concerns, suggested rewrite and negotiation tip per flag. Detection and severity always come from the rules, so results are auditable. |
| Q&A | Top-5 retrieval **restricted to the one document** you ask about, then an LLM answers using only those numbered excerpts (`[Excerpt N]`) with streaming and multi-turn memory. With no LLM you get the retrieved excerpts and a clear notice instead of an answer. |
| PDF report | `/report/{doc_id}`: summary, every flagged clause, rewrites and the disclaimer. |

Limits worth knowing: the rule engine only finds what its patterns cover (English, common phrasing); small local models (e.g. `llama3.2` 3B) sometimes misjudge or write weak explanations; there is no OCR; there are no user accounts (the "profile" in the UI is a list of past analyses kept in your browser's localStorage, no password).

## Backends: what runs where

Chosen automatically at startup and shown in the UI header strip and at `GET /health`:

- **Vector store:** remote Qdrant only if `QDRANT_URL` and `QDRANT_API_KEY` are set and reachable; otherwise a **local on-disk Qdrant** in `backend/data/qdrant` (git-ignored, survives restarts).
- **LLM (`LLM_PROVIDER=auto`):** Groq if `GROQ_API_KEY` works, else **Ollama** at `OLLAMA_HOST` if running with the `OLLAMA_MODEL` (default `llama3.2`) pulled, else none (rule-based analysis and excerpt-only Q&A).

## Run locally

Requires Python 3.12 and Node 20+. The first run downloads the embedding model (~130 MB) once.

```bash
git clone https://github.com/parvashah29/Legal-Document-Analyzer.git
cd Legal-Document-Analyzer

# backend
cd backend
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.example .env            # optional; everything has a default
./venv/bin/uvicorn main:app --port 8000
# open http://localhost:8000/health and /docs

# frontend (new terminal)
cd frontend
npm install
npm run dev                     # http://localhost:5173
```

For generated explanations/answers without any cloud account: install [Ollama](https://ollama.com), `ollama pull llama3.2`, and make sure `ollama serve` is running. The UI shows which backend is active.

### Configuration (`backend/.env`, see `.env.example`)

`LLM_PROVIDER` (auto|groq|ollama|none), `GROQ_API_KEY`, `GROQ_MODEL`, `OLLAMA_HOST`, `OLLAMA_MODEL`, `QDRANT_URL`, `QDRANT_API_KEY`, `DATA_DIR`, `CORS_ORIGINS` (default: localhost:5173/4173 only), `MAX_UPLOAD_MB`. Frontend: `VITE_API_URL` (default `http://localhost:8000`). Never commit `.env`.

## API

`POST /upload` (multipart `file`) -> `{doc_id, chunks, filename}` | `GET /risks/{doc_id}[?enrich=true]` | `POST /query` and `POST /query/stream` (`{doc_id, question, chat_history?}`) | `GET /report/{doc_id}` (PDF) | `DELETE /documents/{doc_id}` | `POST /chat/clear/{doc_id}` | `GET /health`.

Documents are isolated by `doc_id` (random UUID): every vector search is filtered to one document. There is no per-user authentication, so anyone who can reach the API and knows a `doc_id` can read that document. Do not expose it publicly as-is.

## Tests

```bash
backend/venv/bin/pip install -r backend/requirements-dev.txt
backend/venv/bin/python -m pytest -q      # offline; LLMs are mocked/disabled
```

Covers upload formats (TXT/DOCX/PDF), validation (type, size, scanned/corrupt PDFs), risky-clause detection, clean-contract scoring, retrieval isolation between documents, streaming contract, PDF report text, CORS and mocked-LLM paths. `test_documents/` holds 25 fictional sample contracts (regenerate with `backend/generate_test_data.py`).

## Deploy

`render.yaml` deploys the backend as a Docker web service. Without Ollama or a Groq key it runs rule-based only, and free-plan disk is ephemeral. The frontend is a static Vite build (`npm run build`, set `VITE_API_URL`); add its origin to `CORS_ORIGINS`.

## Project layout

`backend/` `main.py` (API), `config.py`, `store.py` (Qdrant + embeddings), `ingestion.py`, `rules.py`, `classifier.py`, `llm.py` (provider selection), `retrieval.py`, `report.py`, `models.py` | `frontend/` React 19 + Vite | `tests/` pytest suite.
