"""Central configuration. Everything is driven by environment variables (see .env.example)."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def _csv(name: str, default: str) -> list[str]:
    return [v.strip() for v in os.getenv(name, default).split(",") if v.strip()]


# --- Server -----------------------------------------------------------------
CORS_ORIGINS = _csv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173",
)
MAX_UPLOAD_MB = _int("MAX_UPLOAD_MB", 10)
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
ALLOWED_EXTENSIONS = (".pdf", ".docx", ".txt")

# --- Vector store -----------------------------------------------------------
# Remote Qdrant is used only when both values are set AND the server answers.
# Otherwise an on-disk local Qdrant database under DATA_DIR is used (no account needed).
QDRANT_URL = os.getenv("QDRANT_URL", "").strip()
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "").strip()
DATA_DIR = Path(os.getenv("DATA_DIR", "").strip() or BASE_DIR / "data")
QDRANT_LOCAL_PATH = DATA_DIR / "qdrant"
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "legal_docs").strip() or "legal_docs"
# ":memory:" is mainly useful for tests
QDRANT_FORCE_LOCAL = _bool("QDRANT_FORCE_LOCAL", False)

EMBED_MODEL_NAME = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5").strip()
EMBED_DIM = 384  # bge-small-en-v1.5

# --- LLM --------------------------------------------------------------------
# auto = Groq if the key works, else Ollama if reachable, else rule-based / no-LLM fallback.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto").strip().lower()  # auto|groq|ollama|none
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant").strip()
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").strip().rstrip("/")
if not OLLAMA_HOST.startswith("http"):
    OLLAMA_HOST = "http://" + OLLAMA_HOST
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2").strip()
LLM_TIMEOUT_S = _int("LLM_TIMEOUT_S", 120)
# Max flagged clauses sent to an LLM for plain-English enrichment per document.
MAX_LLM_CLAUSES = _int("MAX_LLM_CLAUSES", 10)

DISCLAIMER = (
    "This tool provides automated, preliminary analysis only. It is not legal advice and "
    "does not create an attorney-client relationship. Consult a qualified attorney before "
    "signing or relying on any contract."
)
