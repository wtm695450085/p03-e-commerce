"""
Pary rekomendacji per klaster — reguły asocjacyjne (market basket).

Idea: te same buty do biegania dają INNE dopełnienia klientowi z klastra A
(np. zegarek sportowy, premium skarpety) niż z klastra E (budżetowe spodenki).
Dlatego współwystępowanie liczymy OSOBNO w każdym klastrze.

Algorytm (odporny na rzadkość danych przy 300 SKU):
  1. Dla każdego klastra budujemy koszyki zamówień.
  2. Liczymy współwystępowanie KATEGORII (gęste, sensowne):
       support, confidence, lift między kategoriami.
  3. Dla każdego produktu P (kategoria C):
       - bierzemy kategorie najczęściej kupowane z C w tym klastrze (lift > 1),
       - z nich dobieramy konkretne produkty najpopularniejsze w klastrze,
       - score = lift_kategorii × popularność_produktu_w_klastrze.
  4. Zapisujemy TOP-8 dopełnień per (klaster, produkt) do tabeli product_pairs.

Uruchomienie (PO seed_customers + cluster_customers):
    python -m app.cluster_pairs

API: get_product_pairs(product_id, db, customer_id=...) → dobiera klaster klienta.
"""
from __future__ import annotations

import math
import os
from collections import defaultdict, Counter
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, Float, Integer, String, create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session

Base = declarative_base()

DATA_DIR     = os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))
DB_PATH      = os.path.join(DATA_DIR, "prosport.db")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")

TOP_PAIRS      = 8     # ile dopełnień zapisać per (klaster, produkt)
MIN_CAT_SUPPORT = 3    # min. liczba współwystąpień kategorii, by reguła była ważna
CLUSTERS       = list("ABCDE")


# --------------------------------------------------------------------------
# ORM — tabela wynikowa
# --------------------------------------------------------------------------
class ProductPair(Base):
    __tablename__ = "product_pairs"
    id                 = Column(Integer, primary_key=True, autoincrement=True)
    cluster            = Column(String(2), index=True)
    product_id         = Column(Integer, index=True)
    rank               = Column(Integer)
    paired_product_id  = Column(Integer)
    paired_name        = Column(String(200))
    paired_price       = Column(Float)
    paired_category    = Column(String(120))
    score              = Column(Float)     # 0-1
    lift               = Column(Float)     # siła reguły kategorii
    reason             = Column(String(200))
    updated_at         = Column(DateTime, default=datetime.utcnow)


# --------------------------------------------------------------------------
# Główny pipeline
# --------------------------------------------------------------------------
def build_pairs(verbose: bool = True) -> dict:
    engine = create_engine(DATABASE_URL,
        connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
    Base.metadata.create_all(engine)
    Sess = sessionmaker(bind=engine)
    db   = Sess()

    try:
        from app.models import Customer, Order, OrderItem, Product, Department
        from app.cluster_customers import CustomerCluster

        if verbose:
            print("="*60)
            print("PARY REKOMENDACJI PER KLASTER — market basket")
            print("="*60)

        # --- dane ---
        products  = {p.id: p for p in db.query(Product).all()}
        cat_of    = {p.id: (p.category or "inne") for p in products.values()}
        cluster_of = {cc.customer_id: cc.km_cluster for cc in db.query(CustomerCluster).all()}

        orders = db.query(Order).filter(
            Order.customer_id.isnot(None), Order.status == "zrealizowane"
        ).all()
        items_by_order: dict[int, list] = defaultdict(list)
        for it in db.query(OrderItem).filter(
            OrderItem.order_id.in_([o.id for o in orders])
        ).all():
            if it.product_id in products:
                items_by_order[it.order_id].append(it.product_id)

        # --- per klaster: koszyki ---
        baskets_by_cluster: dict[str, list[list[int]]] = defaultdict(list)
        for o in orders:
            km = cluster_of.get(o.customer_id)
            if not km:
                continue
            basket = items_by_order.get(o.id, [])
            if len(basket) >= 1:
                baskets_by_cluster[km].append(basket)

        if verbose:
            print("\n[1/3] Koszyki per klaster:")
            for km in CLUSTERS:
                print(f"      Klaster {km}: {len(baskets_by_cluster.get(km, []))} koszyków")

        # --- per klaster: statystyki kategorii i produktów ---
        # cat_count[km][cat] = liczba koszyków z tą kategorią
        # cat_cooc[km][(c1,c2)] = liczba koszyków z obiema kategoriami
        # prod_count[km][pid] = liczba zakupów produktu w klastrze
        # prod_in_cat[km][cat] = lista (pid, count) posortowana malejąco
        all_pairs_rows = []
        n_rules = 0

        if verbose:
            print("\n[2/3] Reguły asocjacyjne kategorii per klaster…")

        db.execute(text("DELETE FROM product_pairs"))

        for km in CLUSTERS:
            baskets = baskets_by_cluster.get(km, [])
            n_baskets = len(baskets)
            if n_baskets < 5:
                continue

            cat_count: Counter = Counter()
            cat_cooc: dict = defaultdict(int)
            prod_count: Counter = Counter()

            for basket in baskets:
                cats = set(cat_of.get(pid, "inne") for pid in basket)
                for pid in basket:
                    prod_count[pid] += 1
                for c in cats:
                    cat_count[c] += 1
                cats_sorted = sorted(cats)
                for i in range(len(cats_sorted)):
                    for j in range(i + 1, len(cats_sorted)):
                        cat_cooc[(cats_sorted[i], cats_sorted[j])] += 1

            # produkty pogrupowane po kategorii (posortowane po popularności w klastrze)
            prod_in_cat: dict[str, list] = defaultdict(list)
            for pid, cnt in prod_count.most_common():
                prod_in_cat[cat_of.get(pid, "inne")].append((pid, cnt))

            # confidence/lift między kategoriami
            # complement_cats[c] = [(c2, lift, conf), ...] posortowane po lift
            complement_cats: dict[str, list] = defaultdict(list)
            for (c1, c2), co in cat_cooc.items():
                if co < MIN_CAT_SUPPORT:
                    continue
                # lift = P(c1,c2) / (P(c1)*P(c2))
                p_c1 = cat_count[c1] / n_baskets
                p_c2 = cat_count[c2] / n_baskets
                p_both = co / n_baskets
                lift = p_both / (p_c1 * p_c2) if (p_c1 * p_c2) > 0 else 0
                # confidence w obie strony
                conf_12 = co / cat_count[c1] if cat_count[c1] else 0  # c1 -> c2
                conf_21 = co / cat_count[c2] if cat_count[c2] else 0  # c2 -> c1
                if lift > 1.0:
                    complement_cats[c1].append((c2, lift, conf_12))
                    complement_cats[c2].append((c1, lift, conf_21))
                    n_rules += 1

            for c in complement_cats:
                complement_cats[c].sort(key=lambda x: x[1], reverse=True)

            max_prod = max(prod_count.values(), default=1)

            # --- dla każdego produktu wyprowadź dopełnienia ---
            for pid, prod in products.items():
                cat = cat_of.get(pid, "inne")
                comp = complement_cats.get(cat, [])
                if not comp:
                    continue

                # zbierz produkty-kandydatów z kategorii dopełniających
                candidates = []  # (cand_pid, score, lift, comp_cat)
                for comp_cat, lift, conf in comp[:6]:   # max 6 kategorii dopełniających
                    for cand_pid, cand_cnt in prod_in_cat.get(comp_cat, [])[:5]:
                        if cand_pid == pid:
                            continue
                        pop = cand_cnt / max_prod
                        score = lift * (0.4 + 0.6 * pop)   # waga kategorii × popularność
                        candidates.append((cand_pid, score, lift, comp_cat, conf))

                if not candidates:
                    continue

                # deduplikacja — zostaw najlepszy score per produkt
                best: dict[int, tuple] = {}
                for cand_pid, score, lift, comp_cat, conf in candidates:
                    if cand_pid not in best or score > best[cand_pid][0]:
                        best[cand_pid] = (score, lift, comp_cat, conf)

                ranked_all = sorted(best.items(), key=lambda x: x[1][0], reverse=True)

                # dywersyfikacja: max 2 produkty z jednej kategorii dopełniającej,
                # i bez duplikatów nazwy bazowej (różne SKU tego samego modelu)
                ranked = []
                cat_used: Counter = Counter()
                names_used = set()
                for cand_pid, meta in ranked_all:
                    comp_cat = meta[2]
                    base_name = products[cand_pid].name.split(" – ")[0]
                    if cat_used[comp_cat] >= 2:
                        continue
                    if base_name in names_used:
                        continue
                    ranked.append((cand_pid, meta))
                    cat_used[comp_cat] += 1
                    names_used.add(base_name)
                    if len(ranked) >= TOP_PAIRS:
                        break

                max_score = ranked[0][1][0] if ranked else 1.0

                for rank, (cand_pid, (score, lift, comp_cat, conf)) in enumerate(ranked, 1):
                    cand = products[cand_pid]
                    norm_score = score / max_score if max_score > 0 else 0
                    reason = f"Kupowane z „{cat}” w klastrze {km} ({lift:.1f}x częściej)"
                    all_pairs_rows.append(ProductPair(
                        cluster           = km,
                        product_id        = pid,
                        rank              = rank,
                        paired_product_id = cand_pid,
                        paired_name       = cand.name,
                        paired_price      = cand.price,
                        paired_category   = comp_cat,
                        score             = round(float(norm_score), 4),
                        lift              = round(float(lift), 3),
                        reason            = reason,
                        updated_at        = datetime.utcnow(),
                    ))

        if verbose:
            print(f"      Reguł kategorii (lift>1): {n_rules}")
            print("\n[3/3] Zapis do bazy…")

        db.bulk_save_objects(all_pairs_rows)
        db.commit()

        if verbose:
            print(f"✓ Zapisano {len(all_pairs_rows)} par (klaster × produkt × dopełnienie)")
            # przykład — ten sam produkt w różnych klastrach
            example_pid = None
            for pid, p in products.items():
                if "biegania" in (p.category or "").lower():
                    example_pid = pid
                    break
            if example_pid:
                p = products[example_pid]
                print(f"\n-- Przyklad: {p.name[:40]} ({p.category}) --")
                for km in CLUSTERS:
                    rows = db.query(ProductPair).filter_by(
                        cluster=km, product_id=example_pid
                    ).order_by(ProductPair.rank).limit(4).all()
                    if rows:
                        pairs_str = ", ".join(f"{r.paired_name.split(' – ')[0]} ({r.paired_category})" for r in rows[:3])
                        print(f"  Klaster {km}: {pairs_str}")

        return {"n_pairs": len(all_pairs_rows), "n_rules": n_rules}

    finally:
        db.close()


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------
def get_product_pairs(product_id: int, db: Session,
                      customer_id: Optional[int] = None,
                      cluster: Optional[str] = None,
                      limit: int = 6) -> dict:
    """
    Zwraca produkty najczęściej kupowane z danym produktem — w klastrze klienta.

    Klaster ustalany w kolejności: jawny `cluster` > z `customer_id` > globalny
    fallback (najczęstszy klaster w danych dla tego produktu).
    """
    resolved_cluster = cluster
    if not resolved_cluster and customer_id:
        try:
            from app.cluster_customers import CustomerCluster
            cc = db.query(CustomerCluster).filter_by(customer_id=customer_id).first()
            if cc:
                resolved_cluster = cc.km_cluster
        except Exception:
            pass

    rows = []
    if resolved_cluster:
        rows = db.query(ProductPair).filter_by(
            product_id=product_id, cluster=resolved_cluster
        ).order_by(ProductPair.rank).limit(limit).all()

    # fallback — jeśli brak w tym klastrze, weź najlepsze z dowolnego
    fallback = False
    if not rows:
        rows = db.query(ProductPair).filter_by(product_id=product_id)\
            .order_by(ProductPair.score.desc()).limit(limit).all()
        fallback = True
        if rows:
            resolved_cluster = rows[0].cluster

    return {
        "cluster": resolved_cluster,
        "fallback": fallback,
        "pairs": [{
            "product_id": r.paired_product_id,
            "name":       r.paired_name,
            "price":      r.paired_price,
            "category":   r.paired_category,
            "score":      round(r.score, 4),
            "lift":       round(r.lift, 3),
            "reason":     r.reason,
            "image":      f"/api/products/{r.paired_product_id}/image",
        } for r in rows],
    }


if __name__ == "__main__":
    build_pairs(verbose=True)
