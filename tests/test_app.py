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
        sources = client.get("/api/sources").json()["sources"]
        assert len(sources) == 6
        assert sources["Rede Economia"]["url"] == "https://www.redeconomia.com.br/encartes/"
        assert sources["Rede Economia"]["format"] == "pdf_and_images"
        assert sources["Rede Economia"]["collector"] == "pending"
        assert sources["Supermarket"]["url"] == "https://www.redesupermarket.com.br/ofertas/"
        assert sources["Supermarket"]["collector"] == "pending"
        for q in ("feijão", "feijao", "feigao", "fejao"):
            assert client.get("/api/products", params={"q": q}).json()["count"] > 0
        assert client.get("/api/products", params={"q": "arroz"}).json()["count"] > 0
        offers = client.get("/api/offers", params={"q": "arroz"}).json()
        if main.today() <= date(2026, 11, 6):
            assert offers["count"] >= 9
            assert offers["offers"][0]["market"] == "Guanabara"
        else:
            assert offers["count"] == 0
        white = client.get("/api/offers", params={"q": "arroz branco"}).json()
        assert main.offer_match("Arroz Branco Prato Fino 5kg", "branco", "arroz branco") == "confirmed"
        assert main.offer_match("Arroz Camil 5kg", "não identificado", "arroz branco") == "type_unspecified"
        assert main.offer_match("Arroz Integral Camil 1kg", "integral", "arroz branco") is None
        if main.today() <= date(2026, 11, 6):
            assert white["confirmed"] >= 1
            assert white["type_unspecified"] >= 1
            assert any(x["brand"] == "Prato Fino" and x["match_quality"] == "confirmed" for x in white["offers"])
        else:
            assert white["count"] == 0
        assert client.get("/api/health").json()["version"] == "10.0.0"
        assert len(client.get("/api/prices", params={"q": "azeite"}).json()["markets"]) == 6
        assert client.get("/api/products", params={"q": "pasta de dente"}).json()["count"] > 0
        assert client.get("/api/products", params={"q": "creme dental"}).json()["count"] > 0
        if main.today() == date(2026, 11, 6):
            assai_milk = client.get("/api/prices", params={"q": "leite", "market": "Assaí"}).json()
            assert assai_milk["count"] >= 1
            assert any(x["brand"] == "Quatá" and x["price"] == 4.39 for x in assai_milk["prices"])
            assai_olive = client.get("/api/prices", params={"q": "azeite", "market": "Assaí"}).json()
            assert any(x["brand"] == "Gallo" and x["price"] == 24.90 for x in assai_olive["prices"])
            assai_beans = client.get("/api/prices", params={"q": "feigao", "market": "Assaí"}).json()
            assert any(x["brand"] == "Sabor Máximo" for x in assai_beans["prices"])
            assert all(x["is_promotion"] for x in assai_beans["prices"])
        if main.today() <= date(2026, 11, 15):
            toothpaste = client.get("/api/prices", params={"q": "pasta de dente"}).json()
            assert toothpaste["count"] >= 2
            assert all("dental" in x["name"].lower() for x in toothpaste["prices"])
            assert "Prezunic" in toothpaste["per_market"]
            assert toothpaste["per_market"]["Prezunic"] > 0
            assert toothpaste["per_market"]["Assaí"] == 0
            milk = client.get("/api/prices", params={"q": "leite"}).json()
            assert milk["count"] >= 1
            oil = client.get("/api/prices", params={"q": "azeite"}).json()
            assert any(x["market"] == "Prezunic" and not x["is_promotion"] for x in oil["prices"])
            promos = client.get("/api/prices", params={"q": "azeite", "only_promotions": "true"}).json()
            assert all(x["is_promotion"] for x in promos["prices"])
        else:
            assert client.get("/api/prices", params={"q": "pasta de dente"}).json()["count"] == 0
        sample_other = (f"<div>Validade: {date.today().strftime('%d/%m/%Y')}</div>"
                        "<div>28,98</div><div>Azeite Extra Virgem Seleção Andorinha 500ml</div>"
                        "<div>2,99</div><div>Creme de Leite Piracanjuba TP 200g</div>")
        parsed_other = main.parse_guanabara(sample_other)
        assert len(parsed_other) == 2
        assert parsed_other[0]["brand"] == "Andorinha"
        assert parsed_other[0]["unit"] == "l"
        assert parsed_other[1]["brand"] == "Piracanjuba"
        assert parsed_other[1]["unit"] == "kg"
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
