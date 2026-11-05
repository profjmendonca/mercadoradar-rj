"""MercadoRadar RJ: 500 products and verified promotional offers only."""
import difflib
import json
import os
import re
import threading
import time
import unicodedata
import urllib.request
from datetime import date, datetime, timezone, timedelta
from html.parser import HTMLParser
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import Boolean, Column, Float, Integer, String, UniqueConstraint, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Session

ROOT = Path(__file__).resolve().parent
MARKETS = ("Guanabara", "Assaí", "Prezunic", "Mundial", "Rede Economia", "Supermarket")
GUANABARA_URL = "https://www.supermercadosguanabara.com.br/produtos/2"
GUANABARA_SOURCES = tuple("https://www.supermercadosguanabara.com.br/produtos/" + str(i) for i in
                           (2, 12, 22, 32, 42, 52, 62, 72, 82, 92, 102, 112, 152, 203))
MARKET_PAGES = {
    "Guanabara": "https://www.supermercadosguanabara.com.br/produtos",
    "Assaí": "https://www.assai.com.br/ofertas",
    "Prezunic": "https://www.prezunic.com.br/",
    "Mundial": "https://www.supermercadosmundial.com.br/encarte",
    "Rede Economia": "https://www.redeconomia.com.br/encartes/",
    "Supermarket": "https://redesupermarket.com.br/",
}
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
ENABLE_COLLECTOR = os.getenv("ENABLE_COLLECTOR", "true").lower() in ("true", "1", "yes")
INTERVAL = max(900, int(os.getenv("REFRESH_INTERVAL_SECONDS", "3600")))
DB = os.getenv("DATABASE_URL", "").strip()
if not DB:
    DB = "sqlite:///" + str(ROOT / "data" / "mercadoradar.sqlite3")
if DB.startswith("postgres://"):
    DB = "postgresql+psycopg://" + DB[11:]
elif DB.startswith("postgresql://"):
    DB = "postgresql+psycopg://" + DB[13:]
engine = create_engine(DB, pool_pre_ping=True, connect_args={"check_same_thread": False} if DB.startswith("sqlite:") else {"prepare_threshold": None})

class Base(DeclarativeBase):
    pass

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    name = Column(String(400), nullable=False)
    category = Column(String(120), nullable=False)

class Promotion(Base):
    __tablename__ = "promotions"
    id = Column(Integer, primary_key=True)
    market = Column(String(100), nullable=False)
    store = Column(String(200), nullable=False, default="")
    name = Column(String(500), nullable=False)
    brand = Column(String(200), nullable=False)
    kind = Column(String(200), nullable=False, default="")
    quantity = Column(Float, nullable=False)
    unit = Column(String(10), nullable=False)
    price = Column(Float, nullable=False)
    source = Column(String(2000), nullable=False)
    checked_at = Column(String(50), nullable=False)
    valid_until = Column(String(10), nullable=False)
    condition = Column(String(500), nullable=False, default="")
    is_promotion = Column(Boolean, nullable=False, default=False)
    __table_args__ = (UniqueConstraint("market", "store", "name", "quantity", "unit", "source", name="uq_promotion"),)

class CollectorLog(Base):
    __tablename__ = "collector_log"
    source = Column(String(2000), primary_key=True)
    last_attempt = Column(String(50))
    last_success = Column(String(50))
    last_error = Column(String(500))
    found = Column(Integer, default=0)

Base.metadata.create_all(engine)
with Session(engine) as session:
    if not session.query(Product).count():
        items = json.loads((ROOT / "data" / "catalogo.json").read_text(encoding="utf-8"))
        session.add_all(Product(id=p["id"], name=p["name"], category=p["category"]) for p in items)
        session.commit()

app = FastAPI(title="MercadoRadar RJ", version="10.0.0")

def today():
    return datetime.now(ZoneInfo("America/Sao_Paulo")).date()

def normalize(value):
    value = "".join(x for x in unicodedata.normalize("NFKD", str(value).lower()) if not unicodedata.combining(x))
    return re.sub(r"[^a-z0-9]+", " ", value).strip()

def canonical(value):
    aliases = {"feigao": "feijao", "fejao": "feijao", "arroiz": "arroz", "arros": "arroz",
               "dentifricio": "creme dental", "dentifrico": "creme dental"}
    value = normalize(value)
    value = re.sub(r"\bpasta\s+(?:de\s+)?dentes?\b", "creme dental", value)
    value = re.sub(r"\bpasta\s+dental\b", "creme dental", value)
    value = re.sub(r"\bextra\s+virgem\b", "extravirgem", value)
    return " ".join(aliases.get(x, x) for x in value.split())

def match(name, query):
    query = canonical(query)
    words = canonical(name).split()
    if not query or query in " ".join(words):
        return True
    return all(any(difflib.SequenceMatcher(None, a, b).ratio() >= .79 for b in words) for a in query.split())

def offer_match(name, kind, query):
    """Return confirmed or unspecified variety; never label unknown as white/black rice."""
    if match(name, query):
        return "confirmed"
    pieces = canonical(query).split()
    varieties = {"branco", "preto", "carioca", "integral", "parboilizado"}
    required = [p for p in pieces if p in varieties]
    if not required:
        return None
    residual = " ".join(p for p in pieces if p not in varieties)
    if not residual or not match(name, residual):
        return None
    declared = normalize(kind)
    if declared not in ("", "nao identificado", "nao especificado"):
        return None
    # Relevant candidate only: its variety must be confirmed with the retailer.
    return "type_unspecified"


class IncomingOffer(BaseModel):
    market: str
    store: str = ""
    name: str = Field(min_length=3)
    brand: str = Field(min_length=1)
    kind: str = ""
    quantity: float = Field(gt=0)
    unit: str
    price: float = Field(gt=0)
    source: HttpUrl
    checked_at: str
    valid_until: str = ""
    condition: str = ""
    is_promotion: bool = False

def save_promotions(records):
    saved = 0
    with Session(engine) as session:
        for raw in records:
            try:
                o = IncomingOffer.model_validate(raw)
                if o.market not in MARKETS or o.unit not in ("kg", "l", "un"):
                    continue
                if date.fromisoformat(o.checked_at[:10]) > today():
                    continue
                if o.is_promotion:
                    if not o.valid_until or date.fromisoformat(o.valid_until) < today():
                        continue
                else:
                    # Ordinary online prices are indicative and expire from the index after ten days.
                    if date.fromisoformat(o.checked_at[:10]) < today() - timedelta(days=10):
                        continue
                    o.valid_until = ""
                vals = o.model_dump(mode="json")
                key = dict(market=o.market, store=o.store, name=o.name, quantity=o.quantity, unit=o.unit, source=str(o.source))
                prior = session.execute(select(Promotion).filter_by(**key)).scalar_one_or_none()
                if prior:
                    for k, v in vals.items():
                        setattr(prior, k, v)
                else:
                    session.add(Promotion(**vals))
                saved += 1
            except (ValueError, TypeError):
                continue
        session.commit()
    return saved

def load_verified_seed():
    """Load dated, publicly checked promotions. Expired rows are rejected."""
    total = 0
    for name in ("promotions_seed_2026_11_05.json", "precos_publicados_2026_11_05.json"):
        path = ROOT / "data" / name
        if path.exists():
            try:
                total += save_promotions(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError, TypeError):
                pass
    return total

load_verified_seed()

class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0
    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script"):
            self.skip += 1
        if tag in ("div", "li", "span", "p", "h2", "h3", "br"):
            self.parts.append("\n")
    def handle_endtag(self, tag):
        if tag in ("style", "script"):
            self.skip = max(0, self.skip - 1)
        if tag in ("div", "li", "span", "p", "h2", "h3"):
            self.parts.append("\n")
    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)

def parse_guanabara(html, checked_at=None):
    """Experimental parser. Does not import prices without an explicit, unexpired validity date."""
    parser = PlainText()
    parser.feed(html)
    lines = [re.sub(r"\s+", " ", x).strip() for x in "".join(parser.parts).splitlines()]
    lines = [x for x in lines if x]
    m = re.search(r"Validade\s*:\s*(\d{2})/(\d{2})/(\d{4})", " ".join(lines), re.I)
    if not m:
        return []
    try:
        validity = date(int(m[3]), int(m[2]), int(m[1]))
    except ValueError:
        return []
    if validity < today():
        return []
    result = []
    for i, line in enumerate(lines[:-1]):
        if not re.fullmatch(r"(?:R\$\s*)?\d{1,4}[.,]\d{2}(?:\s+cada)?", line, re.I):
            continue
        name = lines[i + 1]
        if not re.search(r"\b(arroz|feij[aã]o)\b", name, re.I):
            continue
        weight = re.search(r"(?:(\d+(?:[,.]\d+)?)\s*)?(kg|g)\b", name, re.I)
        if not weight:
            continue
        quantity = float((weight[1] or "1").replace(",", ".")) * (.001 if weight[2].lower() == "g" else 1)
        price = float(re.search(r"\d{1,4}[.,]\d{2}", line)[0].replace(",", "."))
        norm = normalize(name)
        kind = next((k for k in ("preto", "carioca", "parboilizado", "integral", "branco") if k in norm), "não identificado")
        brand = re.sub(r"^\s*(arroz|feij[aã]o)\s*", "", name, flags=re.I)
        brand = re.sub(r"\b(?:branco|preto|carioca|parboilizado|integral)\b", " ", brand, flags=re.I)
        brand = re.sub(r"\s*(?:\d+(?:[,.]\d+)?\s*)?(?:kg|g)\b.*$", "", brand, flags=re.I)
        brand = re.sub(r"\s+", " ", brand).strip() or "Não identificada"
        result.append(dict(market="Guanabara", store="", name=name, brand=brand, kind=kind, quantity=quantity,
                           unit="kg", price=price, source=GUANABARA_URL, checked_at=checked_at or datetime.now(timezone.utc).isoformat(),
                           valid_until=validity.isoformat(), condition="Confira validade e regras na loja", is_promotion=True))
    return result

lock = threading.Lock()
last_attempt = 0.
def refresh():
    global last_attempt
    if not lock.acquire(blocking=False):
        return
    try:
        last_attempt = time.monotonic()
        now = datetime.now(timezone.utc).isoformat()
        total, err = 0, None
        try:
            request = urllib.request.Request(GUANABARA_URL, headers={"User-Agent": "Mozilla/5.0 (compatible; MercadoRadarRJ/9.2; +https://github.com/profjmendonca/mercadoradar-rj)", "Accept": "text/html", "Accept-Language": "pt-BR,pt;q=0.9"})
            with urllib.request.urlopen(request, timeout=15) as response:
                html = response.read(2_500_000).decode("utf-8", "replace")
            total = save_promotions(parse_guanabara(html, now))
            if not total:
                err = "Nenhuma promoção válida extraída"
        except Exception as exc:
            err = (type(exc).__name__ + ": " + str(exc))[:500]
        with Session(engine) as session:
            row = session.get(CollectorLog, GUANABARA_URL) or CollectorLog(source=GUANABARA_URL)
            session.add(row)
            row.last_attempt = now
            if total:
                row.last_success = now
            row.found = total
            row.last_error = err
            session.commit()
    finally:
        lock.release()

def maybe_refresh(wait=False):
    if ENABLE_COLLECTOR and time.monotonic() - last_attempt > INTERVAL:
        if wait:
            refresh()
        else:
            threading.Thread(target=refresh, daemon=True).start()

@app.get("/")
def home():
    return FileResponse(ROOT / "static" / "index.html", headers={"Cache-Control": "no-store, max-age=0"})

@app.get("/api/health")
def health():
    return {"ok": True, "version": app.version}

@app.get("/api/products")
def products(q: str = Query("", max_length=100), limit: int = Query(50, ge=1, le=500)):
    with Session(engine) as session:
        rows = session.execute(select(Product).order_by(Product.name)).scalars().all()
    found = [dict(id=p.id, name=p.name, category=p.category) for p in rows if match(p.name, q)]
    return {"count": len(found), "products": found[:limit]}

@app.get("/api/offers")
def offers(q: str = Query("", max_length=100), market: str = ""):
    with Session(engine) as session:
        has_current = session.execute(
            select(Promotion.id).where(Promotion.is_promotion.is_(True), Promotion.valid_until >= today().isoformat()).limit(1)
        ).first() is not None
    # On an empty store, complete the first collection before responding.
    maybe_refresh(wait=not has_current)
    with Session(engine) as session:
        stmt = select(Promotion).where(Promotion.is_promotion.is_(True), Promotion.valid_until >= today().isoformat())
        if market:
            stmt = stmt.where(Promotion.market == market)
        data = session.execute(stmt).scalars().all()
        selected = []
        for x in data:
            quality = offer_match(x.name, x.kind, q)
            if not quality:
                continue
            selected.append(dict(id=x.id, market=x.market, store=x.store, name=x.name, brand=x.brand, kind=x.kind, quantity=x.quantity, unit=x.unit,
                                 price=x.price, source=x.source, checked_at=x.checked_at, valid_until=x.valid_until,
                                 condition=x.condition, match_quality=quality))
    selected.sort(key=lambda x: (x["match_quality"] != "confirmed", x["price"] / x["quantity"]))
    return {"count": len(selected), "offers": selected[:500], "markets": MARKETS, "promotion_only": True,
            "confirmed": sum(x["match_quality"] == "confirmed" for x in selected),
            "type_unspecified": sum(x["match_quality"] == "type_unspecified" for x in selected)}

@app.get("/api/status")
def status():
    with Session(engine) as session:
        return {"products": session.query(Product).count(),
                "offers": session.query(Promotion).filter(Promotion.is_promotion.is_(True), Promotion.valid_until >= today().isoformat()).count(),
                "collectors": [{"source": x.source, "last_attempt": x.last_attempt, "last_success": x.last_success,
                                "last_error": x.last_error, "found": x.found} for x in session.query(CollectorLog).all()],
                "configured_sources": {"Guanabara": GUANABARA_URL} if ENABLE_COLLECTOR else {},
                "markets_without_collector": list(MARKETS[1:]),
                "database_persistent": not DB.startswith("sqlite:")}

@app.post("/api/admin/refresh")
def manual_refresh(x_admin_token: str | None = Header(None)):
    if not ADMIN_TOKEN or x_admin_token != ADMIN_TOKEN:
        raise HTTPException(403, "Token administrativo necessário")
    threading.Thread(target=refresh, daemon=True).start()
    return {"started": True}

@app.post("/api/admin/offers")
def import_offers(offers: list[IncomingOffer], x_admin_token: str | None = Header(None)):
    if not ADMIN_TOKEN or x_admin_token != ADMIN_TOKEN:
        raise HTTPException(403, "Token administrativo necessário")
    return {"saved": save_promotions([x.model_dump(mode="json") for x in offers])}
