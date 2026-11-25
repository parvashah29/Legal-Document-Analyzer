import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "tests"))

# Must be set before backend modules are imported: offline, isolated, no cloud.
os.environ["LLM_PROVIDER"] = "none"
os.environ["QDRANT_URL"] = ""
os.environ["QDRANT_API_KEY"] = ""
os.environ["GROQ_API_KEY"] = ""
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="lda-test-")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client():
    import main
    with TestClient(main.app) as c:
        yield c


@pytest.fixture(scope="session")
def fixtures(tmp_path_factory):
    import make_fixtures
    d = tmp_path_factory.mktemp("fx")
    make_fixtures.build(d)
    return d


@pytest.fixture(scope="session")
def risky_id(client, fixtures):
    r = client.post("/upload", files={"file": ("risky.txt", (fixtures / "risky.txt").read_bytes())})
    assert r.status_code == 200, r.text
    return r.json()["doc_id"]
