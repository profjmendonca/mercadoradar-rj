import os
import sys
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient

def test_catalog_and_search():
    with tempfile.TemporaryDirectory() as d:
        os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(d) / "test.sqlite3")
        os.environ["ENABLE_COLLECTOR"] = "false"
        os.environ["ADMIN_TOKEN"] = "testing-only"
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        import main
        client = TestClient(main.app)
        assert client.get("/api/health").json()["ok"]
        assert client.get("/api/status").json()["products"] == 500
        for q in ("feijão", "feijao", "feigao", "fejao"):
            assert client.get("/api/products", params={"q": q}).json()["count"] > 0
        assert client.get("/api/products", params={"q": "arroz"}).json()["count"] > 0
        assert client.get("/api/offers", params={"q": "arroz"}).json()["count"] == 0
        assert client.get("/").status_code == 200
        assert client.post("/api/admin/refresh").status_code == 403
