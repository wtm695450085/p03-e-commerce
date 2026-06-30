from __future__ import annotations

import csv
import os
from pathlib import Path

from .database import Base, SessionLocal, engine
from .models import Department, Order, OrderItem, Product, Store

STORE = {
    "slug": "sport",
    "name": "ProSport",
    "tagline": "Sklep sportowy",
    "currency": "PLN",
    "theme": "dynamic",
}

BASE_DIR = Path(__file__).resolve().parent
SEED_DIR = BASE_DIR / "seed_data"
PRODUCTS_CSV = SEED_DIR / "products_100.csv"
DEPARTMENTS_CSV = SEED_DIR / "departments.csv"

FORCE_RESEED = os.getenv("FORCE_RESEED", "0") == "1"


def _bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "tak"}


def _float_or_none(value: str):
    value = str(value or "").strip()
    return float(value) if value else None


def _int(value: str) -> int:
    return int(float(str(value).strip()))


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        store = db.query(Store).filter_by(slug=STORE["slug"]).first()
        if not store:
            store = Store(**STORE)
            db.add(store)
            db.flush()

        existing_count = db.query(Product).filter_by(store_id=store.id).count()

        if existing_count == 100 and not FORCE_RESEED:
            print("Baza ma już 100 produktów. Pomijam seed. Ustaw FORCE_RESEED=1, aby wymusić podmianę.")
            return

        print("Czyszczę starą bazę sklepu i tworzę czyste 100 produktów...")

        db.query(OrderItem).delete()
        db.query(Order).delete()
        db.query(Product).delete()
        db.query(Department).delete()
        db.flush()

        deps_by_slug = {}
        with DEPARTMENTS_CSV.open("r", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                dep = Department(
                    store_id=store.id,
                    slug=row["slug"],
                    name=row["name"],
                    icon=row.get("icon"),
                    color=row.get("color"),
                    description=row.get("description"),
                    position=_int(row.get("position", 0)),
                )
                db.add(dep)
                db.flush()
                deps_by_slug[dep.slug] = dep

        with PRODUCTS_CSV.open("r", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                dep = deps_by_slug[row["department"]]
                db.add(Product(
                    id=_int(row["id"]),
                    store_id=store.id,
                    department_id=dep.id,
                    sku=row["sku"],
                    name=row["name"],
                    brand=row["brand"],
                    category=row["category"],
                    variant=row.get("variant"),
                    description=row.get("description"),
                    tags=row.get("tags"),
                    icon=row.get("icon"),
                    color=row.get("color"),
                    image_filename=row.get("image_filename") or f"product_{_int(row['id']):03d}.png",
                    price=float(row["price"]),
                    old_price=_float_or_none(row.get("old_price")),
                    is_promo=_bool(row.get("is_promo")),
                    stock=_int(row.get("stock", 0)),
                    rating=float(row.get("rating", 0)),
                    reviews=_int(row.get("reviews", 0)),
                ))

        db.commit()
        final_count = db.query(Product).filter_by(store_id=store.id).count()
        print(f"Baza gotowa. Liczba produktów: {final_count}")

    finally:
        db.close()


if __name__ == "__main__":
    seed()
