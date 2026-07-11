"""
ProSport — backend sklepu sportowego (FastAPI).

Serwuje API produktów oraz statyczny frontend HTML. Baza: SQLite (MVP),
gotowa do migracji na PostgreSQL przez zmienną DATABASE_URL.
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Session

from .database import get_db
from .images import product_svg
from .models import (
    ChatMessage, Customer, Department, Order, OrderItem, Product, Store, Visit,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")
APP_DIR = os.path.dirname(os.path.abspath(__file__))

# Gdzie szukać prawdziwych zdjęć produktów (product_001.png itd.).
# Można nadpisać zmienną środowiskową IMAGES_DIR. Jeśli pliku nie ma —
# endpoint i tak zwróci placeholder SVG (brak twardej zależności).
IMAGE_DIRS = [d for d in [
    os.getenv("IMAGES_DIR"),
    os.path.join(STATIC_DIR, "images"),
    os.path.join(STATIC_DIR, "img"),
    os.path.join(STATIC_DIR, "images", "products"),
    os.path.join(APP_DIR, "seed_data", "images"),
] if d]


def _find_product_image(filename: str) -> Optional[str]:
    if not filename:
        return None
    for d in IMAGE_DIRS:
        path = os.path.join(d, filename)
        if os.path.isfile(path):
            return path
    return None

app = FastAPI(title="ProSport API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

STORE_SLUG = "sport"


# --------------------------------------------------------------------------
# Schematy żądań
# --------------------------------------------------------------------------
class OrderItemIn(BaseModel):
    product_id: int
    quantity: int = 1


class OrderIn(BaseModel):
    items: list[OrderItemIn]
    customer_id: Optional[int] = None


# --------------------------------------------------------------------------
# Pomocnicze
# --------------------------------------------------------------------------
def _store(db: Session) -> Store:
    store = db.query(Store).filter_by(slug=STORE_SLUG).first()
    if not store:
        raise HTTPException(503, "Baza nie została zaseedowana. Uruchom: python -m app.seed")
    return store


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/store")
def get_store(db: Session = Depends(get_db)):
    store = _store(db)
    deps = (
        db.query(Department)
        .filter_by(store_id=store.id)
        .order_by(Department.position)
        .all()
    )
    counts = dict(
        db.query(Product.department_id, func.count(Product.id))
        .filter_by(store_id=store.id)
        .group_by(Product.department_id)
        .all()
    )
    total = db.query(func.count(Product.id)).filter_by(store_id=store.id).scalar()
    return {
        "slug": store.slug, "name": store.name, "tagline": store.tagline,
        "currency": store.currency, "theme": store.theme,
        "product_count": total,
        "departments": [
            {
                "slug": d.slug, "name": d.name, "icon": d.icon, "color": d.color,
                "description": d.description, "product_count": counts.get(d.id, 0),
            }
            for d in deps
        ],
    }


@app.get("/api/products")
def list_products(
    department: Optional[str] = None,
    q: Optional[str] = None,
    brand: Optional[str] = None,
    promo: bool = False,
    sort: str = Query("popular", pattern="^(popular|price_asc|price_desc|name|rating)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    db: Session = Depends(get_db),
):
    store = _store(db)
    query = db.query(Product).filter_by(store_id=store.id)

    if department and department != "all":
        dep = db.query(Department).filter_by(store_id=store.id, slug=department).first()
        if not dep:
            raise HTTPException(404, "Nie znaleziono działu")
        query = query.filter(Product.department_id == dep.id)

    if brand:
        query = query.filter(Product.brand == brand)

    if promo:
        query = query.filter(Product.is_promo.is_(True))

    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(Product.name.ilike(like), Product.brand.ilike(like),
                Product.category.ilike(like), Product.tags.ilike(like))
        )

    total = query.count()

    if sort == "price_asc":
        query = query.order_by(Product.price.asc())
    elif sort == "price_desc":
        query = query.order_by(Product.price.desc())
    elif sort == "name":
        query = query.order_by(Product.name.asc())
    elif sort == "rating":
        query = query.order_by(Product.rating.desc(), Product.reviews.desc())
    else:  # popular
        query = query.order_by(Product.reviews.desc(), Product.rating.desc())

    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total, "page": page, "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
        "items": [p.as_dict() for p in items],
    }


@app.get("/api/brands")
def list_brands(department: Optional[str] = None, db: Session = Depends(get_db)):
    store = _store(db)
    query = db.query(Product.brand, func.count(Product.id)).filter_by(store_id=store.id)
    if department and department != "all":
        dep = db.query(Department).filter_by(store_id=store.id, slug=department).first()
        if dep:
            query = query.filter(Product.department_id == dep.id)
    rows = query.group_by(Product.brand).order_by(Product.brand).all()
    return [{"brand": b, "count": c} for b, c in rows]


@app.get("/api/products/{product_id}")
def get_product(product_id: int, db: Session = Depends(get_db)):
    p = db.query(Product).filter_by(id=product_id).first()
    if not p:
        raise HTTPException(404, "Nie znaleziono produktu")
    data = p.as_dict()
    # dobierz kilka produktów z tego samego działu jako "podobne"
    similar = (
        db.query(Product)
        .filter(Product.department_id == p.department_id, Product.id != p.id)
        .order_by(func.random())
        .limit(4)
        .all()
    )
    data["similar"] = [s.as_dict() for s in similar]
    return data


@app.get("/api/products/{product_id}/image")
def product_image(product_id: int, db: Session = Depends(get_db)):
    p = db.query(Product).filter_by(id=product_id).first()
    if not p:
        raise HTTPException(404, "Nie znaleziono produktu")
    # 1) prawdziwe zdjęcie, jeśli plik istnieje
    real = _find_product_image(getattr(p, "image_filename", None))
    if real:
        return FileResponse(real, headers={"Cache-Control": "public, max-age=86400"})
    # 2) fallback — brandowany placeholder SVG
    svg = product_svg(p)
    return Response(content=svg, media_type="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=86400"})


@app.post("/api/orders")
def create_order(payload: OrderIn, db: Session = Depends(get_db)):
    """Symulowane zamówienie — BEZ realnej płatności i checkoutu.
    Zapisuje koszyk, aby w przyszłości zasilić historię zakupów klienta."""
    store = _store(db)
    if not payload.items:
        raise HTTPException(400, "Koszyk jest pusty")

    customer = None
    if payload.customer_id is not None:
        customer = db.query(Customer).filter_by(
            id=payload.customer_id, store_id=store.id
        ).first()
        if not customer:
            raise HTTPException(404, "Nie znaleziono wybranego klienta")

    order = Order(
        store_id=store.id,
        customer_id=customer.id if customer else None,
        status="zrealizowane" if customer else "symulacja",
    )
    db.add(order)
    db.flush()

    total = 0.0
    count = 0
    for it in payload.items:
        p = db.query(Product).filter_by(id=it.product_id).first()
        if not p:
            continue
        qty = max(1, it.quantity)
        total += p.price * qty
        count += qty
        db.add(OrderItem(order_id=order.id, product_id=p.id, name=p.name,
                         price=p.price, quantity=qty))

    order.total = round(total, 2)
    order.items_count = count
    if customer:
        customer.orders_count = (customer.orders_count or 0) + 1
        customer.total_spent = round((customer.total_spent or 0) + order.total, 2)
    db.commit()
    return {
        "order_id": order.id, "status": order.status,
        "total": order.total, "items_count": order.items_count,
        "message": "Zamówienie zarejestrowane (symulacja — brak realnej płatności).",
    }


# --------------------------------------------------------------------------
# KLIENCI — archiwum / rejestr sprzedaży + wybór tożsamości
# --------------------------------------------------------------------------
@app.get("/api/customers")
def list_customers(
    q: Optional[str] = None,
    segment: Optional[str] = None,
    tier: Optional[str] = None,
    age_group: Optional[str] = None,
    affluence: Optional[str] = None,
    household: Optional[str] = None,
    sort: str = Query("recent", pattern="^(recent|spent|orders|name)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(150, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Lista klientów do menu wyboru tożsamości (lekkie karty)."""
    store = _store(db)
    query = db.query(Customer).filter_by(store_id=store.id)

    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(
            Customer.full_name.ilike(like), Customer.email.ilike(like),
            Customer.city.ilike(like), Customer.segment.ilike(like),
        ))
    if segment:
        query = query.filter(Customer.segment == segment)
    if tier:
        query = query.filter(Customer.loyalty_tier == tier)
    if age_group:
        query = query.filter(Customer.age_group == age_group)
    if affluence:
        query = query.filter(Customer.affluence == affluence)
    if household:
        query = query.filter(Customer.household == household)

    total = query.count()

    if sort == "spent":
        query = query.order_by(Customer.total_spent.desc())
    elif sort == "orders":
        query = query.order_by(Customer.orders_count.desc())
    elif sort == "name":
        query = query.order_by(Customer.full_name.asc())
    else:  # recent
        query = query.order_by(desc(Customer.last_visit_at))

    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total, "page": page, "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
        "items": [c.as_card() for c in items],
    }


@app.get("/api/customers/segments")
def customer_segments(db: Session = Depends(get_db)):
    """Słownik segmentów i poziomów lojalności (z licznikami) do filtrów menu."""
    store = _store(db)
    base = db.query(Customer).filter_by(store_id=store.id)

    def counts(col):
        return [{"value": v, "count": c} for v, c in
                base.with_entities(col, func.count(Customer.id))
                .group_by(col).order_by(func.count(Customer.id).desc()).all()
                if v is not None]

    segs  = base.with_entities(Customer.segment, func.count(Customer.id))\
                .group_by(Customer.segment).order_by(func.count(Customer.id).desc()).all()
    tiers = base.with_entities(Customer.loyalty_tier, func.count(Customer.id))\
                .group_by(Customer.loyalty_tier).all()

    # kolejność wiekowa zamiast alfabetycznej
    age_order = {"18-25": 0, "26-35": 1, "36-45": 2, "46-60": 3, "60+": 4}
    age_groups = sorted(counts(Customer.age_group),
                        key=lambda x: age_order.get(x["value"], 9))

    return {
        "segments":   [{"segment": s, "count": c} for s, c in segs],
        "tiers":      [{"tier": t,    "count": c} for t, c in tiers],
        "age_groups": age_groups,
        "affluence":  counts(Customer.affluence),
        "households": counts(Customer.household),
        "total": base.count(),
    }


@app.get("/api/customers/{customer_id}")
def get_customer(customer_id: int, db: Session = Depends(get_db)):
    """Pełny profil klienta = rejestr sprzedaży + wizyty + czaty + statystyki."""
    c = db.query(Customer).filter_by(id=customer_id).first()
    if not c:
        raise HTTPException(404, "Nie znaleziono klienta")

    orders = list(c.orders)
    valid = [o for o in orders if o.status != "anulowane"]

    # mapowanie produktów z pozycji zamówień -> dział / kategoria / marka
    pids = {it.product_id for o in valid for it in o.items}
    pmap = {}
    if pids:
        prods = db.query(Product).filter(Product.id.in_(pids)).all()
        dep_name = {d.id: (d.slug, d.name) for d in c.store.departments}
        for p in prods:
            slug, name = dep_name.get(p.department_id, (None, None))
            pmap[p.id] = {"dept_slug": slug, "dept_name": name,
                          "category": p.category, "brand": p.brand}

    by_dept, by_cat, by_brand = {}, {}, {}
    items_total = 0
    for o in valid:
        for it in o.items:
            info = pmap.get(it.product_id)
            if not info:
                continue
            spent = it.price * it.quantity
            items_total += it.quantity
            d = by_dept.setdefault(info["dept_slug"],
                                   {"slug": info["dept_slug"], "name": info["dept_name"],
                                    "count": 0, "spent": 0.0})
            d["count"] += it.quantity
            d["spent"] += spent
            by_cat[info["category"]] = by_cat.get(info["category"], 0) + it.quantity
            by_brand[info["brand"]] = by_brand.get(info["brand"], 0) + it.quantity

    for d in by_dept.values():
        d["spent"] = round(d["spent"], 2)

    visits = list(c.visits)
    by_month = {}
    for v in visits:
        key = v.visited_at.strftime("%Y-%m")
        by_month[key] = by_month.get(key, 0) + 1

    total_spent = round(sum(o.total for o in valid), 2)

    profile = c.as_dict()
    profile["stats"] = {
        "orders_count": len(valid),
        "orders_cancelled": len(orders) - len(valid),
        "items_count": items_total,
        "total_spent": total_spent,
        "avg_order": round(total_spent / len(valid), 2) if valid else 0,
        "visits_count": len(visits),
        "last_visit_at": c.last_visit_at.isoformat() if c.last_visit_at else None,
        "by_department": sorted(by_dept.values(), key=lambda x: x["spent"], reverse=True),
        "top_categories": sorted(
            ({"category": k, "count": v} for k, v in by_cat.items()),
            key=lambda x: x["count"], reverse=True)[:6],
        "top_brands": sorted(
            ({"brand": k, "count": v} for k, v in by_brand.items()),
            key=lambda x: x["count"], reverse=True)[:6],
        "visits_by_month": [{"month": k, "count": by_month[k]} for k in sorted(by_month)],
    }
    profile["orders"] = [{
        "id": o.id,
        "created_at": o.created_at.isoformat() if o.created_at else None,
        "status": o.status, "total": round(o.total, 2), "items_count": o.items_count,
        "items": [{"product_id": it.product_id, "name": it.name,
                   "price": it.price, "quantity": it.quantity} for it in o.items],
    } for o in sorted(orders, key=lambda o: o.created_at or 0, reverse=True)]
    profile["visits"] = [v.as_dict() for v in sorted(
        visits, key=lambda v: v.visited_at, reverse=True)[:12]]
    profile["messages"] = [m.as_dict() for m in c.messages]

    # ---- klasteryzacja (opcjonalna — null gdy nie uruchomiono) ----
    try:
        from .cluster_customers import get_customer_cluster
        profile["clustering"] = get_customer_cluster(c.id, db)
    except Exception:
        profile["clustering"] = None

    return profile


# --------------------------------------------------------------------------
# DASHBOARD — dane analityczne (klastry, RFM, pary, demografia)
# --------------------------------------------------------------------------
@app.get("/api/dashboard")
def dashboard_data(db: Session = Depends(get_db)):
    """Agregaty do dashboardu analitycznego — klasteryzacja, RFM, pary."""
    from collections import Counter, defaultdict

    store = _store(db)

    # --- import lokalny żeby nie blokować startu gdy tabela nie istnieje ---
    try:
        from .cluster_customers import CustomerCluster
        from sqlalchemy import inspect as sa_inspect
        if not sa_inspect(db.bind).has_table("customer_clusters"):
            return {"error": "Brak wyników klasteryzacji. Uruchom: python -m app.cluster_customers"}
        cluster_rows = db.query(CustomerCluster).all()
    except Exception as e:
        return {"error": f"Klasteryzacja niedostępna: {e}"}

    if not cluster_rows:
        return {"error": "Brak wyników klasteryzacji. Uruchom: python -m app.cluster_customers"}

    customers_map = {c.id: c for c in db.query(Customer).filter_by(store_id=store.id).all()}

    # 1. Rozkład klastrów KM
    km_counter = Counter(r.km_cluster for r in cluster_rows)
    cluster_descriptions = {
        "A": "Aktywni entuzjaści sportu",
        "B": "Klienci premium & fitness",
        "C": "Okazjonalni kupujący",
        "D": "Seniorzy i outdoor",
        "E": "Budżetowi gracze zespołowi",
    }
    cluster_dist = []
    for letter in "ABCDE":
        cids = [r.customer_id for r in cluster_rows if r.km_cluster == letter]
        avg_spent = 0.0
        if cids:
            total = sum(customers_map[cid].total_spent or 0
                        for cid in cids if cid in customers_map)
            avg_spent = round(total / len(cids), 2)
        cluster_dist.append({
            "cluster": letter,
            "count": km_counter.get(letter, 0),
            "description": cluster_descriptions.get(letter, ""),
            "avg_spent": avg_spent,
        })

    # 2. Rozkład segmentów RFM
    rfm_counter = Counter(r.rfm_segment for r in cluster_rows)
    rfm_dist = [{"segment": s, "count": c} for s, c in rfm_counter.most_common()]

    # 3. Rozkład R, F, M (histogramy 1-5)
    rfm_hist = {
        "r": Counter(r.rfm_r for r in cluster_rows),
        "f": Counter(r.rfm_f for r in cluster_rows),
        "m": Counter(r.rfm_m for r in cluster_rows),
    }
    rfm_axes = {
        axis: [{"score": i, "count": rfm_hist[axis].get(i, 0)} for i in range(1, 6)]
        for axis in ["r", "f", "m"]
    }

    # 4. PCA scatter (próbka 300 punktów)
    import random as _random
    _random.seed(42)
    sample_rows = _random.sample(cluster_rows, min(300, len(cluster_rows)))
    pca_scatter = []
    for r in sample_rows:
        c = customers_map.get(r.customer_id)
        pca_scatter.append({
            "x": round(r.pca_1 or 0, 3),
            "y": round(r.pca_2 or 0, 3),
            "cluster": r.km_cluster,
            "rfm_seg": r.rfm_segment,
            "name": c.full_name if c else "?",
            "spent": round(c.total_spent or 0, 0) if c else 0,
        })

    # 5. Pary produktów (market basket)
    from .customers import product_catkey
    products_map = {p.id: p for p in db.query(Product).filter_by(store_id=store.id).all()}
    pairs: Counter = Counter()
    orders = (db.query(Order)
              .filter(Order.store_id == store.id,
                      Order.customer_id.isnot(None),
                      Order.status == "zrealizowane")
              .all())
    for o in orders:
        cats = sorted({
            product_catkey(products_map[it.product_id])
            for it in o.items
            if it.product_id in products_map
            and product_catkey(products_map[it.product_id]) != "inne"
        })
        for i in range(len(cats)):
            for j in range(i + 1, len(cats)):
                pairs[(cats[i], cats[j])] += 1

    CAT_LABELS = {
        "buty_bieg": "Buty biegowe", "buty_pilka": "Korki", "buty_kosz": "Buty do kosza",
        "buty_trail": "Buty trail", "buty_tren": "Buty treningowe",
        "sneakersy": "Sneakersy", "koszulki": "Koszulki", "spodenki": "Spodenki",
        "legginsy": "Legginsy", "bluzy": "Bluzy", "kurtki": "Kurtki",
        "skarpety": "Skarpety/bielizna", "hantle": "Hantle", "kettlebell": "Kettlebell",
        "sztangi": "Sztangi", "maty": "Maty", "gumy": "Gumy oporowe",
        "sprzet": "Sprzęt fitness", "protein": "Proteiny", "kreatyna": "Kreatyna",
        "witaminy": "Witaminy", "pilki": "Piłki", "zegarki": "Zegarki sport.",
        "torby": "Torby/plecaki",
    }
    top_pairs = [
        {
            "a": CAT_LABELS.get(a, a),
            "b": CAT_LABELS.get(b, b),
            "count": cnt,
        }
        for (a, b), cnt in pairs.most_common(15)
    ]

    # 6. Wiek × Klaster (heatmapa)
    age_cluster: dict = defaultdict(lambda: defaultdict(int))
    for r in cluster_rows:
        c = customers_map.get(r.customer_id)
        if c:
            age_cluster[c.age_group or "?"][r.km_cluster] += 1

    age_order = ["18-25", "26-35", "36-45", "46-60", "60+"]
    age_heatmap = []
    for ag in age_order:
        row_data = {"age_group": ag}
        for letter in "ABCDE":
            row_data[letter] = age_cluster[ag].get(letter, 0)
        age_heatmap.append(row_data)

    # 7. Zasobność × wydatki
    aff_order = ["budżetowy", "średni", "zamożny", "premium"]
    aff_data = []
    for aff in aff_order:
        vals = [c.total_spent or 0 for c in customers_map.values()
                if c.affluence == aff]
        if vals:
            aff_data.append({
                "affluence": aff,
                "count": len(vals),
                "avg_spent": round(sum(vals) / len(vals), 2),
                "max_spent": round(max(vals), 2),
            })

    # 8. Statystyki ogólne
    total_customers = len(customers_map)
    total_revenue = sum(c.total_spent or 0 for c in customers_map.values())
    clustered_at = max((r.updated_at for r in cluster_rows if r.updated_at),
                       default=None)

    return {
        "meta": {
            "total_customers": total_customers,
            "total_revenue": round(total_revenue, 2),
            "clustered_at": clustered_at.isoformat() if clustered_at else None,
            "n_clusters": 5,
        },
        "cluster_dist": cluster_dist,
        "rfm_dist": rfm_dist,
        "rfm_axes": rfm_axes,
        "pca_scatter": pca_scatter,
        "top_pairs": top_pairs,
        "age_heatmap": age_heatmap,
        "affluence": aff_data,
    }


@app.get("/api/customers/{customer_id}/recommendations")
def customer_recommendations(
    customer_id: int,
    department: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Rekomendacje produktów + cyfrowi bliźniacy + metryki modelu."""
    c = db.query(Customer).filter_by(id=customer_id).first()
    if not c:
        raise HTTPException(404, "Nie znaleziono klienta")
    try:
        from .recommend import get_recommendations
        return get_recommendations(customer_id, db, department)
    except Exception as e:
        return {"error": str(e), "recommendations": {}, "digital_twins": [], "model": None}


@app.get("/api/customers/{customer_id}/offer")
def customer_offer(customer_id: int, db: Session = Depends(get_db)):
    """Spersonalizowana reklama: top 3 produkty z indywidualną promocją 5-15%."""
    c = db.query(Customer).filter_by(id=customer_id).first()
    if not c:
        raise HTTPException(404, "Nie znaleziono klienta")
    try:
        from .recommend import get_offer
        offer = get_offer(customer_id, db, n=3)
        offer["customer_name"] = c.full_name
        offer["first_name"] = (c.full_name or "").split(" ")[0]
        return offer
    except Exception as e:
        return {"error": str(e), "items": []}


@app.post("/api/retrain")
def retrain_recommendations():
    """Ponowny trening modelu rekomendacyjnego (może trwać ~30s)."""
    try:
        from .recommend import run_recommendations
        metrics = run_recommendations(verbose=False)
        return {"ok": True, "metrics": metrics}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/products/{product_id}/pairs")
def product_pairs_endpoint(
    product_id: int,
    customer_id: Optional[int] = None,
    cluster: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Produkty kupowane razem z danym — w klastrze aktywnego klienta."""
    p = db.query(Product).filter_by(id=product_id).first()
    if not p:
        raise HTTPException(404, "Nie znaleziono produktu")
    try:
        from .cluster_pairs import get_product_pairs
        return get_product_pairs(product_id, db, customer_id=customer_id, cluster=cluster)
    except Exception as e:
        return {"error": str(e), "cluster": None, "pairs": []}


@app.post("/api/rebuild-pairs")
def rebuild_pairs_endpoint():
    """Przelicza pary rekomendacji per klaster."""
    try:
        from .cluster_pairs import build_pairs
        return {"ok": True, **build_pairs(verbose=False)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def recluster(db: Session = Depends(get_db)):
    """Uruchamia pipeline klasteryzacji w tle i zwraca status."""
    try:
        from .cluster_customers import run_clustering
        result = run_clustering(verbose=False)
        return {"ok": True, "customers": len(result)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# --------------------------------------------------------------------------
# Frontend (statyczny)
# --------------------------------------------------------------------------
@app.get("/dashboard")
def dashboard_page():
    return FileResponse(os.path.join(STATIC_DIR, "dashboard.html"))


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
