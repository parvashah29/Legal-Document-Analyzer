"""Document parsing and chunking (PDF / DOCX / TXT). Everything is processed in memory;
no uploaded file is ever written to disk."""
import io
import logging
import os
import uuid

from docx import Document as DocxDocument
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

import config
import store

log = logging.getLogger("legal.ingest")


class IngestionError(ValueError):
    """User-facing problem with the uploaded document (maps to HTTP 4xx)."""


def _ext(filename: str) -> str:
    return os.path.splitext(filename or "")[1].lower()


def _pdf_text(contents: bytes) -> str:
    if not contents.lstrip()[:5].startswith(b"%PDF"):
        raise IngestionError("File content is not a valid PDF.")
    try:
        reader = PdfReader(io.BytesIO(contents))
        if reader.is_encrypted:
            try:
                ok = reader.decrypt("")
            except Exception:  # noqa: BLE001
                ok = 0
            if not ok:
                raise IngestionError("The PDF is password-protected. Remove the password and re-upload.")
        pages = [(p.extract_text() or "").strip() for p in reader.pages]
    except IngestionError:
        raise
    except Exception as e:  # noqa: BLE001
        raise IngestionError(f"Could not read the PDF ({type(e).__name__}). It may be corrupt.") from e
    text = "\n\n".join(p for p in pages if p)
    if not text.strip():
        raise IngestionError(
            "No selectable text found in this PDF. It looks like a scanned image; OCR is not supported. "
            "Upload a text-based PDF, DOCX or TXT instead."
        )
    return text


def _docx_text(contents: bytes) -> str:
    try:
        doc = DocxDocument(io.BytesIO(contents))
    except Exception as e:  # noqa: BLE001
        raise IngestionError("Could not read the DOCX file. It may be corrupt or not a Word document.") from e
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:  # contracts often keep terms in tables
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(dict.fromkeys(cells)))
    return "\n\n".join(parts)


def _txt_text(contents: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            return contents.decode(enc)
        except UnicodeError:
            continue
    return ""


def extract_text(contents: bytes, filename: str) -> str:
    ext = _ext(filename)
    if ext == ".pdf":
        return _pdf_text(contents)
    if ext == ".docx":
        return _docx_text(contents)
    if ext == ".txt":
        return _txt_text(contents)
    raise IngestionError("Unsupported file type. Upload a PDF, DOCX or TXT file.")


def chunk_text(text: str) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=900, chunk_overlap=100, separators=["\n\n", "\n", ". ", " "]
    )
    return [c.strip() for c in splitter.split_text(text) if c.strip()]


def ingest_document(contents: bytes, filename: str) -> tuple[str, int]:
    """Parse, chunk, embed and index. Returns (doc_id, chunk_count)."""
    if not contents:
        raise IngestionError("The uploaded file is empty.")
    if len(contents) > config.MAX_UPLOAD_BYTES:
        raise IngestionError(f"File is larger than the {config.MAX_UPLOAD_MB} MB limit.")
    text = extract_text(contents, filename)
    if len(text.strip()) < 20:
        raise IngestionError("The document contains too little text to analyze.")
    chunks = chunk_text(text)
    doc_id = str(uuid.uuid4())
    store.add_chunks(doc_id, filename, chunks)
    log.info("Ingested %s as %s (%d chunks)", filename, doc_id, len(chunks))
    return doc_id, len(chunks)
