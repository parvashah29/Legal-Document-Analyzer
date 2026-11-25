import logging
import re

from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse

import classifier
import config
import ingestion
import llm
import retrieval
import store
from models import QueryRequest, QueryResponse, RiskAnalysisResponse

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("legal.api")

@asynccontextmanager
async def lifespan(_app):
    store.get_client()  # connect (remote Qdrant or local on-disk) so /health reports the real backend
    log.info("Vector store: %s | LLM: %s", store.backend_info()["backend"], llm.status()["active"])
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Legal Document Analyzer API",
    description="Upload contracts, flag risky clauses, ask grounded questions, export a PDF report. Not legal advice.",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def _check_id(doc_id: str) -> str:
    if not _UUID.match(doc_id or ""):
        raise HTTPException(status_code=400, detail="Invalid document id.")
    return doc_id


def _require_doc(doc_id: str) -> None:
    _check_id(doc_id)
    if not store.get_chunks(doc_id):
        raise HTTPException(status_code=404, detail="Document not found. It may have been deleted; please upload it again.")


@app.get("/")
def read_root():
    return {"service": "Legal Document Analyzer API", "version": app.version, "docs": "/docs", "health": "/health"}


@app.get("/health")
def health():
    st = llm.status()
    return {
        "status": "ok",
        "vector_store": store.backend_info(),
        "llm": {"active": st["active"], "groq": st["groq"], "ollama": st["ollama"]},
        "classifier": "rules+llm:" + st["active"] if st["active"] != "none" else "rules",
        "limits": {"max_upload_mb": config.MAX_UPLOAD_MB, "extensions": list(config.ALLOWED_EXTENSIONS)},
        "disclaimer": config.DISCLAIMER,
    }


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    filename = (file.filename or "").replace("\\", "/").split("/")[-1]
    if not filename.lower().endswith(config.ALLOWED_EXTENSIONS):
        raise HTTPException(status_code=400, detail="Unsupported file type. Upload a PDF, DOCX or TXT file.")
    contents = await file.read(config.MAX_UPLOAD_BYTES + 1)
    if len(contents) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File is larger than the {config.MAX_UPLOAD_MB} MB limit.")
    try:
        import asyncio
        doc_id, chunk_count = await asyncio.to_thread(ingestion.ingest_document, contents, filename)
    except ingestion.IngestionError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception:
        log.exception("Upload failed")
        raise HTTPException(status_code=500, detail="Failed to process the document (see server logs).")
    return {"doc_id": doc_id, "chunks": chunk_count, "filename": filename}


@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest):
    _require_doc(req.doc_id)
    history = [m.model_dump() for m in req.chat_history] if req.chat_history else None
    try:
        return await retrieval.query_rag(req.doc_id, req.question, history)
    except Exception:
        log.exception("Query failed")
        raise HTTPException(status_code=500, detail="Failed to query the document (see server logs).")


@app.post("/query/stream")
async def query_stream(req: QueryRequest):
    _require_doc(req.doc_id)
    history = [m.model_dump() for m in req.chat_history] if req.chat_history else None
    return StreamingResponse(
        retrieval.query_rag_stream(req.doc_id, req.question, history),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/chat/clear/{doc_id}")
async def clear_chat(doc_id: str):
    retrieval.clear_chat_history(_check_id(doc_id))
    return {"status": "cleared", "doc_id": doc_id}


@app.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    _require_doc(doc_id)
    store.delete_document(doc_id)
    retrieval.clear_chat_history(doc_id)
    classifier.forget(doc_id)
    return {"status": "deleted", "doc_id": doc_id}


@app.get("/risks/{doc_id}", response_model=RiskAnalysisResponse)
async def risks(doc_id: str, enrich: bool = False):
    _require_doc(doc_id)
    try:
        return await classifier.classify_clauses(doc_id, use_llm=enrich)
    except classifier.DocumentNotFound:
        raise HTTPException(status_code=404, detail="Document not found.")
    except Exception:
        log.exception("Risk analysis failed")
        raise HTTPException(status_code=500, detail="Failed to analyze risks (see server logs).")


@app.get("/report/{doc_id}")
async def generate_report(doc_id: str):
    _require_doc(doc_id)
    try:
        from report import build_pdf_report
        data = await classifier.classify_clauses(doc_id, use_llm=False)
        pdf = build_pdf_report(data)
    except Exception:
        log.exception("Report failed")
        raise HTTPException(status_code=500, detail="Failed to generate the report (see server logs).")
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="risk_report_{doc_id[:8]}.pdf"'},
    )
