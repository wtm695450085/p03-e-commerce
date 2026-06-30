"""
Seed archiwum klientów (rejestr sprzedaży).

Uruchom PO zaseedowaniu produktów:

    python -m app.seed_customers

Czyta realne produkty z bazy, tworzy 500 klientów i dla każdego buduje:
  • historię zakupów z regułami par (hantle → proteina, buty → skarpety itd.),
  • zróżnicowaną demograficznie (wiek, płeć, zasobność, gospodarstwo domowe),
  • wizyty w sklepie (częstotliwość, część bez zakupu),
  • wątki z czatu obsługi klienta.

Skrypt jest idempotentny — przy ponownym uruchomieniu odtwarza archiwum
od zera (kasuje wcześniej wygenerowanych klientów i powiązane dane).
"""
from __future__ import annotations

import os
import random
from datetime import datetime, timedelta

from . import models  # rejestracja modeli
from .database import Base, SessionLocal, engine
from .models import (
    ChatMessage, Customer, Department, Order, OrderItem, Product, Store, Visit,
)
from .customers import (
    CHAT_TOPICS, COMPLEMENTS, SEG_BY_KEY, TIER_BY_KEY,
    build_customers, product_affinity, product_catkey,
)

SEED = 7
CUSTOMER_COUNT = int(os.getenv("CUSTOMER_COUNT", "500"))


# --------------------------------------------------------------------------
# Pomocnicze
# --------------------------------------------------------------------------
def _short(name: str) -> str:
    return (name or "").split(" – ")[0]


def _price_band(price: float) -> str:
    if price < 100:
        return "tani"
    if price < 400:
        return "sredni"
    return "drogi"


def _pick_products(rng, pool, weights, k):
    """Losuje k różnych produktów ważonych afinicją (bez powtórzeń)."""
    idx = list(range(len(pool)))
    w = list(weights)
    chosen = []
    for _ in range(min(k, len(pool))):
        j = rng.choices(idx, weights=[w[i] for i in idx], k=1)[0]
        chosen.append(pool[j])
        idx.remove(j)
    return chosen


def _complements_for(anchor, pool_by_catkey: dict, rng) -> list:
    """Zwraca listę produktów-komplementów do 'anchor' z puli sklepu.

    Dla każdej kategorii z listy COMPLEMENTS[anchor_catkey] losuje jeden
    pasujący produkt z prawdopodobieństwem określonym w tablicy par.
    """
    akey = product_catkey(anchor)
    rules = COMPLEMENTS.get(akey, [])
    result = []
    for comp_catkey, prob in rules:
        if rng.random() > prob:
            continue
        candidates = pool_by_catkey.get(comp_catkey, [])
        if candidates:
            result.append(rng.choice(candidates))
    return result


def _spread_dates(rng, start: datetime, end: datetime, n: int) -> list[datetime]:
    span = max((end - start).total_seconds(), 1)
    secs = sorted(rng.uniform(0, span) for _ in range(n))
    return [start + timedelta(seconds=s) for s in secs]


def _build_chat(rng, profile, bought, depts_by_slug):
    """Generuje wiadomości z czatu dla klienta. Zwraca listę (role, topic, text)."""
    tier = profile["tier_key"]
    base = {"VIP": (1, 4), "Stały": (1, 3), "Regularny": (0, 3),
            "Okazjonalny": (0, 2), "Nowy": (0, 1)}[tier]
    n_threads = rng.randint(*base)
    threads = []
    topics = list(CHAT_TOPICS.keys())
    for _ in range(n_threads):
        topic = rng.choice(topics)
        cust_msg, support_msg = rng.choice(CHAT_TOPICS[topic])
        if bought:
            p = rng.choice(bought)
            pname, pbrand, pcat = _short(p.name), p.brand, p.category.lower()
        else:
            pname, pbrand, pcat = "wybrany model", "Nike", "tej kategorii"
        fill = {"p": pname, "brand": pbrand, "cat": pcat}
        threads.append((topic, cust_msg.format(**fill), support_msg.format(**fill)))
    return threads


# --------------------------------------------------------------------------
# Główny seed
# --------------------------------------------------------------------------
def seed_customers() -> None:
    Base.metadata.create_all(bind=engine)
    rng = random.Random(SEED)
    db = SessionLocal()
    try:
        store = db.query(Store).filter_by(slug="sport").first()
        if not store:
            raise SystemExit("Brak sklepu — najpierw zaseeduj produkty: python -m app.seed")

        products = db.query(Product).filter_by(store_id=store.id).all()
        if not products:
            raise SystemExit("Brak produktów — najpierw zaseeduj produkty: python -m app.seed")

        dept_slug = {
            d.id: d.slug
            for d in db.query(Department).filter_by(store_id=store.id).all()
        }
        # doklejamy slug działu i band cenowy do obiektów produktów
        for p in products:
            setattr(p, "department_slug", dept_slug.get(p.department_id))
            setattr(p, "price_band", _price_band(p.price))

        depts_by_slug = {d.slug: d for d in store.departments}

        # indeks produktów wg klucza kategorii (potrzebny do par)
        pool_by_catkey: dict[str, list] = {}
        for p in products:
            key = product_catkey(p)
            pool_by_catkey.setdefault(key, []).append(p)

        # --- czyszczenie poprzedniego archiwum (idempotentność) ---
        db.query(ChatMessage).delete(synchronize_session=False)
        db.query(Visit).delete(synchronize_session=False)
        hist = [o.id for o in db.query(Order).filter(Order.customer_id.isnot(None)).all()]
        if hist:
            db.query(OrderItem).filter(OrderItem.order_id.in_(hist)).delete(synchronize_session=False)
            db.query(Order).filter(Order.customer_id.isnot(None)).delete(synchronize_session=False)
        db.query(Customer).delete(synchronize_session=False)
        db.commit()

        now = datetime.utcnow()
        profiles = build_customers(CUSTOMER_COUNT, seed=SEED)

        n_orders_total = n_items_total = n_visits_total = n_chats_total = 0

        for prof in profiles:
            seg  = SEG_BY_KEY[prof["segment_key"]]
            tier = TIER_BY_KEY[prof["tier_key"]]

            span = rng.randint(*tier.span_days)
            first_active = now - timedelta(days=span)

            customer = Customer(
                store_id=store.id,
                full_name=prof["full_name"],
                email=prof["email"],
                phone=prof["phone"],
                city=prof["city"],
                gender=prof["gender"],
                age=prof["age"],
                age_group=prof.get("age_group"),
                affluence=prof.get("affluence"),
                household=prof.get("household"),
                segment=prof["segment"],
                interest_summary=prof["interest_summary"],
                favorite_department=prof["favorite_department"],
                favorite_brands=prof["favorite_brands"],
                loyalty_tier=prof["loyalty_tier"],
                newsletter=prof["newsletter"],
                avatar_hue=prof["avatar_hue"],
                created_at=first_active,
            )
            db.add(customer)
            db.flush()

            # wagi afinicji dla każdego produktu (uwzględniają demografię)
            weights = [
                product_affinity(prof, p) * rng.uniform(0.8, 1.2)
                for p in products
            ]

            # ---- ZAMÓWIENIA ----
            n_orders = rng.randint(*tier.orders)
            order_dates = _spread_dates(rng, first_active, now, n_orders)
            bought_products: list = []
            total_spent = 0.0
            orders_done = 0
            visit_marks = []  # (data, dział, converted)

            for od in order_dates:
                cancelled = rng.random() < 0.05

                # --- market basket: anchor + komplementy ---
                # Zasobni klienci kupują więcej pozycji naraz
                aff = prof.get("affluence", "średni")
                if aff == "premium":
                    k_weights = [20, 35, 30, 15]   # częściej 2-4 pozycje
                elif aff == "zamożny":
                    k_weights = [30, 35, 25, 10]
                elif aff == "budżetowy":
                    k_weights = [60, 28, 10, 2]    # częściej 1 pozycja
                else:
                    k_weights = [45, 32, 15, 8]

                k_anchor = rng.choices([1, 2, 3, 4], weights=k_weights, k=1)[0]
                anchors = _pick_products(rng, products, weights, k_anchor)

                # do każdego anchora dobierz komplementy z tablicy par
                complements = []
                seen_ids = {p.id for p in anchors}
                for anchor in anchors:
                    for comp in _complements_for(anchor, pool_by_catkey, rng):
                        if comp.id not in seen_ids:
                            # filtr demograficzny: klient premium nie kupuje
                            # produktu taniej marki jako dopełnienie
                            if aff == "premium" and comp.price_band == "tani":
                                continue
                            complements.append(comp)
                            seen_ids.add(comp.id)

                picks = anchors + complements

                order = Order(
                    store_id=store.id,
                    customer_id=customer.id,
                    created_at=od,
                    status="anulowane" if cancelled else "zrealizowane",
                )
                db.add(order)
                db.flush()

                o_total = 0.0
                o_count = 0
                for p in picks:
                    heavy = p.department_slug in ("akcesoria", "odziez")
                    qty = rng.choices(
                        [1, 2, 3],
                        weights=[70, 22, 8] if heavy else [85, 13, 2],
                        k=1
                    )[0]
                    db.add(OrderItem(
                        order_id=order.id, product_id=p.id,
                        name=p.name, price=p.price, quantity=qty,
                    ))
                    o_total += p.price * qty
                    o_count += qty
                    n_items_total += 1
                    if not cancelled:
                        bought_products.append(p)

                order.total = round(o_total, 2)
                order.items_count = o_count
                visit_marks.append((od, picks[0].department_slug, not cancelled))
                if not cancelled:
                    total_spent += o_total
                    orders_done += 1
                n_orders_total += 1

            # ---- WIZYTY (więcej niż zamówień — część bez zakupu) ----
            vpo = rng.uniform(*tier.visits_per_order)
            target_visits = max(len(order_dates), round(len(order_dates) * vpo))
            extra = max(0, target_visits - len(visit_marks))
            dept_keys = list(seg.dept.keys())
            dept_w    = list(seg.dept.values())
            for vd in _spread_dates(rng, first_active, now, extra):
                browsed = rng.choices(dept_keys, weights=dept_w, k=1)[0]
                visit_marks.append((vd, browsed, False))

            for vd, dep, conv in visit_marks:
                db.add(Visit(
                    customer_id=customer.id, visited_at=vd, department=dep,
                    source=rng.choices(["web", "mobile"], weights=[55, 45], k=1)[0],
                    converted=conv,
                ))
                n_visits_total += 1

            last_visit = max((vm[0] for vm in visit_marks), default=first_active)

            # ---- CZAT ----
            for topic, cust_text, support_text in _build_chat(rng, prof, bought_products, depts_by_slug):
                base_dt = first_active + timedelta(
                    seconds=rng.uniform(0, (now - first_active).total_seconds())
                )
                db.add(ChatMessage(customer_id=customer.id, created_at=base_dt,
                                   role="klient", topic=topic, text=cust_text))
                db.add(ChatMessage(customer_id=customer.id,
                                   created_at=base_dt + timedelta(minutes=rng.randint(2, 90)),
                                   role="obsługa", topic=topic, text=support_text))
                n_chats_total += 2

            # ---- statystyki zbiorcze ----
            customer.orders_count  = orders_done
            customer.visits_count  = len(visit_marks)
            customer.total_spent   = round(total_spent, 2)
            customer.last_visit_at = last_visit

        db.commit()

        all_custs = db.query(Customer).all()
        total_rev  = round(sum(c.total_spent for c in all_custs), 2)
        print(f"Zaseedowano {len(profiles)} klientów:")
        print(f"  • zamówienia:  {n_orders_total} (pozycji: {n_items_total})")
        print(f"  • wizyty:      {n_visits_total}")
        print(f"  • wiadomości:  {n_chats_total}")
        print(f"  • suma wydatków: {total_rev} PLN")

        # szybka weryfikacja jakości par (top 5 koegzystencji kategorii)
        from collections import Counter
        basket_pairs: Counter = Counter()
        for o in db.query(Order).filter(Order.customer_id.isnot(None),
                                        Order.status == "zrealizowane").all():
            cats = sorted({product_catkey(it) for it in o.items if it.product_id})
            for i in range(len(cats)):
                for j in range(i + 1, len(cats)):
                    basket_pairs[(cats[i], cats[j])] += 1
        print("  • top pary kategorii w koszyku:")
        for pair, cnt in basket_pairs.most_common(6):
            print(f"    {pair[0]} + {pair[1]}: {cnt}×")

    finally:
        db.close()


if __name__ == "__main__":
    seed_customers()
