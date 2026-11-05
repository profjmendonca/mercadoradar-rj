import os
import sys
import tempfile
from pathlib import Path
from datetime import date, timedelta
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
        offers = client.get("/api/offers", params={"q": "arroz"}).json()
        if main.today() <= date(2026, 11, 6):
            assert offers["count"] >= 9
            assert offers["offers"][0]["market"] == "Guanabara"
        else:
            assert offers["count"] == 0
        valid_until = (main.today() + timedelta(days=1)).strftime("%d/%m/%Y")
        sample = (
            f"<div>Validade: {valid_until}</div>"
            "<div>27,95</div><div>Arroz Branco Prato Fino 5kg</div>"
            "<div>4,99</div><div>Feijão Preto Sanes Kg</div>"
        )
        parsed = main.parse_guanabara(sample)
        assert len(parsed) == 2
        assert parsed[0]["brand"] == "Prato Fino"
        assert parsed[1]["brand"] == "Sanes"
        assert parsed[1]["quantity"] == 1.0
        assert client.get("/").status_code == 200
        assert client.post("/api/admin/refresh").status_code == 403
