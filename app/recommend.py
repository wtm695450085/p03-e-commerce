"""
Rekomendacje produktów — LightGBM Ranking.

Pipeline:
  1. Budowa macierzy interakcji customer×product (implicit feedback)
  2. Feature engineering:
       - cechy klienta (wiek, płeć, klaster, RFM, PCA, zasobność)
       - cechy produktu (dział, cena, rating, popularność, band cenowy)
       - cechy interakcji (kupiony kiedyś, liczba zakupów, dni od ost. zakupu,
                           popularność produktu w klastrze klienta)
  3. LightGBM LambdaRank (rankingowy, NDCG-aware)
  4. Ewaluacja: NDCG@5, MAP@5, AUC, Precision@5
  5. Dla każdego klienta:
       - top-10 rekomendacji per dział (bez produktów kupionych niedawno)
       - top-5 cyfrowych bliźniaków (najbliższych w przestrzeni PCA+cechy)
       - powód rekomendacji (human-readable)

Uruchomienie:
    python -m app.recommend

Wyniki zapisywane do tabeli 'customer_recommendations' i 'digital_twins'.
"""
from __future__ import annotations

import json
import math
import os
import warnings
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupShuffleSplit
# UWAGA: lightgbm importujemy LENIWIE w run_recommendations(), bo wymaga
# systemowej libgomp.so.1 (OpenMP). Dzięki temu reszta modułu — w tym
# get_offer() i get_recommendations() — działa nawet bez libgomp.

warnings.filterwarnings("ignore")

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session

Base = declarative_base()

DATA_DIR     = os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))
DB_PATH      = os.path.join(DATA_DIR, "prosport.db")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")

RECENCY_DAYS   = 60     # produkt kupiony w ciągu X dni = "niedawno" (pomijamy w rekomendacjach)
WORN_OUT_DAYS  = 180    # buty/koszulki mogą się "zużyć" po X dniach
TOP_N          = 10     # rekomendacji per dział
N_TWINS        = 5      # cyfrowych bliźniaków
RANDOM_STATE   = 42


# --------------------------------------------------------------------------
# ORM — tabele wynikowe
# --------------------------------------------------------------------------
class CustomerRecommendation(Base):
    __tablename__ = "customer_recommendations"
    id            = Column(Integer, primary_key=True, autoincrement=True)
    customer_id   = Column(Integer, index=True)
    department    = Column(String(40))
    rank          = Column(Integer)
    product_id    = Column(Integer)
    product_name  = Column(String(200))
    product_price = Column(Float)
    score         = Column(Float)          # raw LightGBM score
    probability   = Column(Float)          # znormalizowane 0-1
    reason        = Column(String(200))
    updated_at    = Column(DateTime, default=datetime.utcnow)


class DigitalTwin(Base):
    __tablename__ = "digital_twins"
    id            = Column(Integer, primary_key=True, autoincrement=True)
    customer_id   = Column(Integer, index=True)
    twin_id       = Column(Integer)
    twin_name     = Column(String(120))
    twin_segment  = Column(String(40))
    twin_cluster  = Column(String(2))
    similarity    = Column(Float)          # 0-1, im wyższy tym bardziej podobny
    updated_at    = Column(DateTime, default=datetime.utcnow)


class RecommendationMeta(Base):
    __tablename__ = "recommendation_meta"
    id            = Column(Integer, primary_key=True, autoincrement=True)
    trained_at    = Column(DateTime, default=datetime.utcnow)
    n_customers   = Column(Integer)
    n_products    = Column(Integer)
    n_interactions= Column(Integer)
    ndcg_at5      = Column(Float)
    map_at5       = Column(Float)
    auc           = Column(Float)
    precision_at5 = Column(Float)
    model_params  = Column(Text)    # JSON


# --------------------------------------------------------------------------
# Feature engineering
# --------------------------------------------------------------------------
DEPT_IDX  = {"obuwie": 0, "odziez": 1, "silownia": 2, "akcesoria": 3}
AFF_IDX   = {"budżetowy": 0, "średni": 1, "zamożny": 2, "premium": 3}
AGE_IDX   = {"18-25": 0, "26-35": 1, "36-45": 2, "46-60": 3, "60+": 4}
CLUSTER_IDX = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4}

# Produkty które "się zużywają" — mogą być rekomendowane nawet po zakupie
WEARABLE_CATS = {"buty", "biegania", "korki", "trailowe", "treningowe",
                 "koszykówki", "sneakersy", "koszulki", "spodenki",
                 "legginsy", "skarpety", "bielizna"}


def _is_wearable(category: str) -> bool:
    cat = (category or "").lower()
    return any(w in cat for w in WEARABLE_CATS)


def _price_band(price: float) -> int:
    if price < 100: return 0
    if price < 400: return 1
    return 2


def build_datasets(db: Session):
    """Buduje DataFrame z cechami do trenowania i predykcji."""
    from app.models import Customer, Order, OrderItem, Product, Department
    from app.cluster_customers import CustomerCluster

    # --- ładowanie danych ---
    customers   = {c.id: c for c in db.query(Customer).all()}
    products    = {p.id: p for p in db.query(Product).all()}
    dept_slug   = {d.id: d.slug for d in db.query(Department).all()}
    clusters    = {cl.customer_id: cl for cl in db.query(CustomerCluster).all()}

    for p in products.values():
        setattr(p, "dept_slug", dept_slug.get(p.department_id, "inne"))

    # historia zamówień
    orders = db.query(Order).filter(
        Order.customer_id.isnot(None),
        Order.status == "zrealizowane"
    ).all()
    order_map = {o.id: o for o in orders}

    items = db.query(OrderItem).filter(
        OrderItem.order_id.in_(list(order_map.keys()))
    ).all()

    now = datetime.utcnow()

    # macierz: customer → {product_id: (count, last_date, total_spend)}
    cust_prod_stats: dict[int, dict[int, dict]] = defaultdict(lambda: defaultdict(
        lambda: {"count": 0, "last_date": None, "total_spend": 0.0}
    ))
    for it in items:
        o = order_map.get(it.order_id)
        if not o or not it.product_id:
            continue
        s = cust_prod_stats[o.customer_id][it.product_id]
        s["count"]       += it.quantity
        s["total_spend"] += it.price * it.quantity
        if s["last_date"] is None or o.created_at > s["last_date"]:
            s["last_date"] = o.created_at

    # popularność produktu globalnie i per klaster
    prod_global_count: dict[int, int] = defaultdict(int)
    prod_cluster_count: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for cid, prods_dict in cust_prod_stats.items():
        cl = clusters.get(cid)
        km = cl.km_cluster if cl else "C"
        for pid, s in prods_dict.items():
            prod_global_count[pid] += s["count"]
            prod_cluster_count[km][pid] += s["count"]

    max_global = max(prod_global_count.values(), default=1)

    # --- buduj wiersze ---
    rows = []
    for cid, cust in customers.items():
        cl = clusters.get(cid)
        if not cl:
            continue

        km = cl.km_cluster
        cust_history = cust_prod_stats.get(cid, {})

        for pid, prod in products.items():
            stat = cust_history.get(pid)
            bought_count = stat["count"] if stat else 0
            days_since   = (now - stat["last_date"]).days if (stat and stat["last_date"]) else 9999
            total_spend  = stat["total_spend"] if stat else 0.0

            # etykieta: 1 jeśli kupił kiedykolwiek (implicit positive feedback)
            label = 1 if bought_count > 0 else 0

            rows.append({
                # identyfikatory
                "customer_id":    cid,
                "product_id":     pid,
                # etykieta
                "label":          label,
                # cechy klienta
                "c_age":          cust.age or 30,
                "c_age_group":    AGE_IDX.get(cust.age_group or "26-35", 1),
                "c_gender":       1 if cust.gender == "m" else 0,
                "c_affluence":    AFF_IDX.get(cust.affluence or "średni", 1),
                "c_cluster":      CLUSTER_IDX.get(km, 2),
                "c_rfm_r":        cl.rfm_r or 3,
                "c_rfm_f":        cl.rfm_f or 3,
                "c_rfm_m":        cl.rfm_m or 3,
                "c_pca1":         cl.pca_1 or 0.0,
                "c_pca2":         cl.pca_2 or 0.0,
                "c_orders":       cust.orders_count or 0,
                "c_visits":       cust.visits_count or 0,
                "c_total_spent":  cust.total_spent or 0.0,
                # cechy produktu
                "p_dept":         DEPT_IDX.get(prod.dept_slug, 0),
                "p_price":        prod.price,
                "p_price_band":   _price_band(prod.price),
                "p_rating":       prod.rating or 0.0,
                "p_reviews":      prod.reviews or 0,
                "p_is_promo":     1 if prod.is_promo else 0,
                "p_wearable":     1 if _is_wearable(prod.category or "") else 0,
                # cechy interakcji
                "i_bought_count":  bought_count,
                "i_days_since":    min(days_since, 9999),
                "i_total_spend":   total_spend,
                "i_global_pop":    prod_global_count.get(pid, 0) / max_global,
                "i_cluster_pop":   prod_cluster_count[km].get(pid, 0),
                # afinicja dział klienta × dział produktu
                "i_dept_match":    1 if prod.dept_slug == (cust.favorite_department or "") else 0,
                # zasobność × cena
                "i_price_aff":    AFF_IDX.get(cust.affluence or "średni", 1) - _price_band(prod.price),
            })

    df = pd.DataFrame(rows)
    return df, cust_prod_stats, products, customers, clusters, prod_cluster_count


FEATURE_COLS = [
    "c_age", "c_age_group", "c_gender", "c_affluence", "c_cluster",
    "c_rfm_r", "c_rfm_f", "c_rfm_m", "c_pca1", "c_pca2",
    "c_orders", "c_visits", "c_total_spent",
    "p_dept", "p_price", "p_price_band", "p_rating", "p_reviews",
    "p_is_promo", "p_wearable",
    "i_bought_count", "i_days_since", "i_total_spend",
    "i_global_pop", "i_cluster_pop", "i_dept_match", "i_price_aff",
]


# --------------------------------------------------------------------------
# Metryki rankingowe
# --------------------------------------------------------------------------
def _dcg(relevances: list[int], k: int) -> float:
    return sum(r / math.log2(i + 2) for i, r in enumerate(relevances[:k]))


def ndcg_at_k(y_true_groups, y_score_groups, k=5) -> float:
    scores = []
    for y_true, y_score in zip(y_true_groups, y_score_groups):
        order  = np.argsort(y_score)[::-1]
        ideal  = sorted(y_true, reverse=True)
        actual = [y_true[i] for i in order]
        idcg   = _dcg(ideal, k)
        if idcg == 0:
            continue
        scores.append(_dcg(actual, k) / idcg)
    return float(np.mean(scores)) if scores else 0.0


def map_at_k(y_true_groups, y_score_groups, k=5) -> float:
    aps = []
    for y_true, y_score in zip(y_true_groups, y_score_groups):
        order = np.argsort(y_score)[::-1][:k]
        hits, prec_sum = 0, 0.0
        for rank, idx in enumerate(order, 1):
            if y_true[idx] == 1:
                hits += 1
                prec_sum += hits / rank
        if any(y_true):
            aps.append(prec_sum / min(sum(y_true), k))
    return float(np.mean(aps)) if aps else 0.0


def precision_at_k(y_true_groups, y_score_groups, k=5) -> float:
    precs = []
    for y_true, y_score in zip(y_true_groups, y_score_groups):
        order = np.argsort(y_score)[::-1][:k]
        precs.append(sum(y_true[i] for i in order) / k)
    return float(np.mean(precs)) if precs else 0.0


# --------------------------------------------------------------------------
# Powody rekomendacji
# --------------------------------------------------------------------------
def _reason(row: dict, cluster_label: str) -> str:
    reasons = []
    if row.get("i_cluster_pop", 0) > 5:
        reasons.append(f"popularne w klastrze {row.get('cluster_letter','')}")
    if row.get("i_dept_match"):
        reasons.append("pasuje do ulubionego działu")
    if row.get("i_bought_count", 0) > 0 and row.get("i_days_since", 9999) > WORN_OUT_DAYS:
        reasons.append("kupowane wcześniej — czas na nowe")
    if row.get("p_is_promo"):
        reasons.append("aktualnie w promocji")
    if row.get("i_global_pop", 0) > 0.5:
        reasons.append("bestseller sklepu")
    if row.get("p_rating", 0) >= 4.8:
        reasons.append("najwyżej oceniany w kategorii")
    if not reasons:
        reasons.append(f"rekomendacja na podstawie profilu i klastra {row.get('cluster_letter','')}")
    return "; ".join(reasons[:2]).capitalize()


# --------------------------------------------------------------------------
# Cyfrowi bliźniacy (nearest neighbors w przestrzeni cech)
# --------------------------------------------------------------------------
def find_digital_twins(target_cid: int, customers: dict, clusters: dict,
                       n: int = N_TWINS) -> list[dict]:
    """
    Nearest neighbors w przestrzeni:
    [pca1, pca2, rfm_r, rfm_f, rfm_m, age_norm, gender, affluence, cluster_idx]
    Metryka: odległość euklidesowa, znormalizowana do similarity 0-1.
    """
    cl_target = clusters.get(target_cid)
    c_target  = customers.get(target_cid)
    if not cl_target or not c_target:
        return []

    def feat(cid):
        cl = clusters.get(cid)
        c  = customers.get(cid)
        if not cl or not c:
            return None
        return np.array([
            (cl.pca_1 or 0) / 10,
            (cl.pca_2 or 0) / 10,
            (cl.rfm_r or 3) / 5,
            (cl.rfm_f or 3) / 5,
            (cl.rfm_m or 3) / 5,
            (c.age or 30) / 70,
            1 if c.gender == "m" else 0,
            AFF_IDX.get(c.affluence or "średni", 1) / 3,
            CLUSTER_IDX.get(cl.km_cluster, 2) / 4,
        ], dtype=float)

    target_vec = feat(target_cid)
    if target_vec is None:
        return []

    dists = []
    for cid in customers:
        if cid == target_cid:
            continue
        v = feat(cid)
        if v is None:
            continue
        dist = float(np.linalg.norm(target_vec - v))
        dists.append((cid, dist))

    dists.sort(key=lambda x: x[1])
    max_dist = dists[min(50, len(dists)-1)][1] if dists else 1.0

    result = []
    for cid, dist in dists[:n]:
        c  = customers[cid]
        cl = clusters[cid]
        sim = max(0.0, 1.0 - dist / max(max_dist, 1e-9))
        result.append({
            "twin_id":      cid,
            "twin_name":    c.full_name,
            "twin_segment": c.segment or "",
            "twin_cluster": cl.km_cluster,
            "similarity":   round(sim, 4),
        })
    return result


# --------------------------------------------------------------------------
# Główny pipeline
# --------------------------------------------------------------------------
def run_recommendations(verbose: bool = True) -> dict:
    import lightgbm as lgb   # leniwy import — wymaga libgomp.so.1 (OpenMP)

    engine = create_engine(DATABASE_URL,
        connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
    Base.metadata.create_all(engine)
    Sess = sessionmaker(bind=engine)
    db   = Sess()

    try:
        if verbose:
            print("="*60)
            print("REKOMENDACJE LightGBM — ProSport")
            print("="*60)

        # ── 1. DANE ───────────────────────────────────────────────
        if verbose: print("\n[1/5] Budowa zbioru cech…")
        df, cust_prod_stats, products, customers, clusters, prod_cluster_count = \
            build_datasets(db)
        if verbose:
            print(f"      {len(df):,} wierszy ({len(customers)} klientów × {len(products)} produktów)")

        X = df[FEATURE_COLS].values.astype(np.float32)
        y = df["label"].values.astype(np.int32)
        groups_arr = df["customer_id"].values

        # ── 2. PODZIAŁ TRAIN/TEST (po klientach) ─────────────────
        if verbose: print("\n[2/5] Podział train/test…")
        unique_custs = df["customer_id"].unique()
        gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=RANDOM_STATE)
        train_idx, test_idx = next(gss.split(X, y, groups=groups_arr))

        X_train, y_train = X[train_idx], y[train_idx]
        X_test,  y_test  = X[test_idx],  y[test_idx]
        groups_train = df.iloc[train_idx]["customer_id"].values
        groups_test  = df.iloc[test_idx] ["customer_id"].values

        # group sizes dla LightGBM ranking
        def group_sizes(g_arr):
            from collections import Counter
            cnt = Counter(g_arr)
            # zachowaj kolejność
            seen, sizes = set(), []
            for g in g_arr:
                if g not in seen:
                    seen.add(g)
                    sizes.append(cnt[g])
            return sizes

        gs_train = group_sizes(groups_train)
        gs_test  = group_sizes(groups_test)

        if verbose:
            print(f"      Train: {len(X_train):,} wierszy ({len(gs_train)} klientów)")
            print(f"      Test:  {len(X_test):,}  wierszy ({len(gs_test)} klientów)")

        # ── 3. LIGHTGBM LAMBDARANK ────────────────────────────────
        if verbose: print("\n[3/5] Trening LightGBM LambdaRank…")
        params = {
            "objective":       "lambdarank",
            "metric":          "ndcg",
            "ndcg_eval_at":    [5, 10],
            "learning_rate":   0.05,
            "num_leaves":      63,
            "max_depth":       6,
            "min_data_in_leaf": 10,
            "feature_fraction": 0.8,
            "bagging_fraction": 0.8,
            "bagging_freq":    5,
            "lambda_l1":       0.1,
            "lambda_l2":       0.1,
            "verbose":         -1,
            "seed":            RANDOM_STATE,
        }

        ds_train = lgb.Dataset(X_train, label=y_train, group=gs_train,
                               feature_name=FEATURE_COLS, free_raw_data=False)
        ds_val   = lgb.Dataset(X_test,  label=y_test,  group=gs_test,
                               feature_name=FEATURE_COLS, reference=ds_train)

        callbacks = [lgb.early_stopping(30, verbose=False), lgb.log_evaluation(period=-1)]
        model = lgb.train(params, ds_train, num_boost_round=400,
                          valid_sets=[ds_val], callbacks=callbacks)

        if verbose:
            print(f"      Drzew: {model.num_trees()} | best iteration: {model.best_iteration}")

        # ── 4. EWALUACJA ──────────────────────────────────────────
        if verbose: print("\n[4/5] Ewaluacja metryk rankingowych…")

        test_scores = model.predict(X_test)
        test_df = df.iloc[test_idx].copy()
        test_df["score"] = test_scores

        # grupuj per klient do metryk
        y_true_groups, y_score_groups = [], []
        for cid, grp in test_df.groupby("customer_id"):
            y_true_groups.append(grp["label"].tolist())
            y_score_groups.append(grp["score"].tolist())

        ndcg5  = ndcg_at_k(y_true_groups, y_score_groups, k=5)
        map5   = map_at_k(y_true_groups, y_score_groups, k=5)
        prec5  = precision_at_k(y_true_groups, y_score_groups, k=5)

        # AUC (binarny, globalnie)
        try:
            auc = roc_auc_score(y_test, test_scores)
        except Exception:
            auc = 0.0

        metrics = {"ndcg_at5": round(ndcg5,4), "map_at5": round(map5,4),
                   "auc": round(auc,4), "precision_at5": round(prec5,4)}

        if verbose:
            print(f"      NDCG@5:       {ndcg5:.4f}")
            print(f"      MAP@5:        {map5:.4f}")
            print(f"      AUC:          {auc:.4f}")
            print(f"      Precision@5:  {prec5:.4f}")

        # ── 5. GENEROWANIE REKOMENDACJI ───────────────────────────
        if verbose: print("\n[5/5] Generowanie rekomendacji dla wszystkich klientów…")

        # predykcja na całym zbiorze
        all_scores = model.predict(X)
        df["score"] = all_scores

        # cluster labels
        from app.cluster_customers import CustomerCluster as CC
        cl_labels = {
            row[0]: row[1]
            for row in db.query(CC.customer_id, CC.cluster_label).all()
        }
        cl_km = {
            row[0]: row[1]
            for row in db.query(CC.customer_id, CC.km_cluster).all()
        }

        # czyszczenie poprzednich
        db.execute(text("DELETE FROM customer_recommendations"))
        db.execute(text("DELETE FROM digital_twins"))
        db.execute(text("DELETE FROM recommendation_meta"))

        recs_to_add  = []
        twins_to_add = []
        n_recs_total = 0

        dept_slugs = {p.id: getattr(p, "dept_slug", "inne") for p in products.values()}

        for cid, grp in df.groupby("customer_id"):
            cust_history = cust_prod_stats.get(cid, {})
            km_letter    = cl_km.get(cid, "C")
            cl_label     = cl_labels.get(cid, "")

            # oznacz produkty do pominięcia (kupione niedawno i nie-wearable)
            skip_ids = set()
            for pid, stat in cust_history.items():
                days = (datetime.utcnow() - stat["last_date"]).days if stat["last_date"] else 9999
                prod = products.get(pid)
                if days < RECENCY_DAYS:
                    skip_ids.add(pid)
                elif days < WORN_OUT_DAYS and prod and not _is_wearable(prod.category or ""):
                    skip_ids.add(pid)

            # rankuj GLOBALNIE — jedna wspólna lista top 10 ze wszystkich działów
            grp = grp.copy()
            grp["dept_slug"] = grp["product_id"].map(dept_slugs)
            grp["skip"]      = grp["product_id"].isin(skip_ids)

            candidates = grp[~grp["skip"]].sort_values("score", ascending=False).head(TOP_N)
            if candidates.empty:
                candidates = grp.sort_values("score", ascending=False).head(TOP_N)

            # normalizuj prawdopodobieństwa w ramach całej listy (softmax)
            scores_arr = candidates["score"].values
            exp_s  = np.exp(scores_arr - scores_arr.max())
            probs  = exp_s / exp_s.sum()

            for rank, (_, row) in enumerate(candidates.iterrows(), 1):
                pid  = int(row["product_id"])
                prod = products.get(pid)
                if not prod:
                    continue
                row_dict = row.to_dict()
                row_dict["cluster_letter"] = km_letter
                row_dict["i_cluster_pop"]  = prod_cluster_count[km_letter].get(pid, 0)
                reason = _reason(row_dict, cl_label)
                recs_to_add.append(CustomerRecommendation(
                    customer_id   = cid,
                    department    = row["dept_slug"],   # dział produktu (informacyjnie)
                    rank          = rank,
                    product_id    = pid,
                    product_name  = prod.name,
                    product_price = prod.price,
                    score         = float(row["score"]),
                    probability   = float(probs[rank-1]),
                    reason        = reason,
                    updated_at    = datetime.utcnow(),
                ))
                n_recs_total += 1

            # cyfrowi bliźniacy
            twins = find_digital_twins(cid, customers, clusters)
            for t in twins:
                twins_to_add.append(DigitalTwin(
                    customer_id   = cid,
                    twin_id       = t["twin_id"],
                    twin_name     = t["twin_name"],
                    twin_segment  = t["twin_segment"],
                    twin_cluster  = t["twin_cluster"],
                    similarity    = t["similarity"],
                    updated_at    = datetime.utcnow(),
                ))

        # bulk insert
        db.bulk_save_objects(recs_to_add)
        db.bulk_save_objects(twins_to_add)

        # meta
        db.add(RecommendationMeta(
            trained_at    = datetime.utcnow(),
            n_customers   = len(customers),
            n_products    = len(products),
            n_interactions= int(df["label"].sum()),
            ndcg_at5      = metrics["ndcg_at5"],
            map_at5       = metrics["map_at5"],
            auc           = metrics["auc"],
            precision_at5 = metrics["precision_at5"],
            model_params  = json.dumps(params),
        ))
        db.commit()

        if verbose:
            print(f"\n✓ Zapisano {n_recs_total} rekomendacji i {len(twins_to_add)} bliźniaków")
            print("\n── Przykład: klient VIP ───────────────────────────────")
            from app.models import Customer as CM
            vip = db.query(CM).filter_by(loyalty_tier="VIP").first()
            if vip:
                recs = db.query(CustomerRecommendation)\
                    .filter_by(customer_id=vip.id)\
                    .order_by(CustomerRecommendation.rank)\
                    .all()
                twns = db.query(DigitalTwin)\
                    .filter_by(customer_id=vip.id)\
                    .order_by(DigitalTwin.similarity.desc())\
                    .all()
                print(f"  {vip.full_name} — TOP 10 (wszystkie działy razem):")
                for r in recs:
                    print(f"    #{r.rank:>2} {r.product_name[:42]:<42} {r.product_price:>8.2f} zł  {r.probability*100:>5.1f}%  [{r.department}]  — {r.reason}")
                print(f"  Cyfrowi bliźniacy:")
                for t in twns:
                    print(f"    {t.twin_name:<25} klaster {t.twin_cluster}  sim={t.similarity:.2f}  {t.twin_segment}")

        return metrics

    finally:
        db.close()


# --------------------------------------------------------------------------
# API — funkcje do użycia w main.py
# --------------------------------------------------------------------------
def get_recommendations(customer_id: int, db: Session,
                         department: Optional[str] = None) -> dict:
    """Zwraca rekomendacje + bliźniaków + metryki modelu dla jednego klienta."""
    recs = db.query(CustomerRecommendation)\
        .filter_by(customer_id=customer_id)\
        .order_by(CustomerRecommendation.rank)\
        .all()

    twins = db.query(DigitalTwin)\
        .filter_by(customer_id=customer_id)\
        .order_by(DigitalTwin.similarity.desc())\
        .all()

    meta = db.query(RecommendationMeta)\
        .order_by(RecommendationMeta.trained_at.desc()).first()

    # jedna wspólna lista top 10 ze wszystkich działów
    DEPT_NAMES = {"obuwie": "Obuwie sportowe", "odziez": "Odzież sportowa",
                  "silownia": "Siłownia i Fitness", "akcesoria": "Akcesoria i Suplementy"}
    items = [{
        "rank":        r.rank,
        "product_id":  r.product_id,
        "name":        r.product_name,
        "price":       r.product_price,
        "department":  r.department,
        "department_name": DEPT_NAMES.get(r.department, r.department),
        "probability": round(r.probability, 4),
        "reason":      r.reason,
    } for r in recs]

    return {
        "recommendations": items,
        "digital_twins": [{
            "id":         t.twin_id,
            "name":       t.twin_name,
            "segment":    t.twin_segment,
            "cluster":    t.twin_cluster,
            "similarity": round(t.similarity, 4),
        } for t in twins],
        "model": {
            "name":        "LightGBM LambdaRank",
            "trained_at":  meta.trained_at.isoformat() if meta else None,
            "n_customers": meta.n_customers if meta else None,
            "n_products":  meta.n_products if meta else None,
            "metrics": {
                "ndcg_at5":      meta.ndcg_at5     if meta else None,
                "map_at5":       meta.map_at5      if meta else None,
                "auc":           meta.auc          if meta else None,
                "precision_at5": meta.precision_at5 if meta else None,
            } if meta else None,
        } if meta else None,
    }


def get_offer(customer_id: int, db: Session, n: int = 3) -> dict:
    """Spersonalizowana oferta: top N produktów z indywidualną promocją 5-15%.

    Oferta reklamowa musi być czytelna biznesowo, więc nie pokazujemy tu
    ślepo rankingu modelu. Najpierw dobieramy produkty zgodne z segmentem
    klienta, a rekomendacje LightGBM traktujemy jako dodatkowy boost.
    """
    from app.models import Product, Customer, Department

    def norm(value) -> str:
        return (value or "").casefold()

    def product_text(product) -> str:
        return " ".join(norm(getattr(product, field, "")) for field in (
            "name", "brand", "category", "variant", "description", "tags"
        ))

    segment_rules = {
        "biegacz": {
            "allow": ["biegan", "trail", "running", "pegasus", "gel-nimbus", "clifton", "speedgoat", "ghost", "endorphin", "wave rider", "fresh foam", "trabuco", "spodenki", "stride", "launch", "accelerate", "zegarek", "forerunner", "pacer", "pace 3", "bidon", "opaska"],
            "prefer_departments": ["obuwie", "akcesoria"],
        },
        "fitness & joga": {
            "allow": ["joga", "yoga", "mata", "maty", "guma", "taśma", "band", "legginsy", "tights", "fitness", "studio", "skakanka", "piłka gimnastyczna", "roller", "mobilność", "trx", "trener zawieszany"],
            "prefer_departments": ["silownia", "odziez"],
        },
        "siłownia": {
            "allow": ["siłown", "hant", "kettlebell", "sztang", "talerz", "ławka", "gryf", "białko", "whey", "kreatyna", "preworkout", "shaker", "rękawiczki", "treningowe", "metcon", "tribase", "nano"],
            "prefer_departments": ["silownia", "akcesoria", "obuwie"],
        },
        "koszykarz": {
            "allow": ["koszyk", "basket", "nba", "curry", "lebron", "harden", "hala", "outdoor"],
            "prefer_departments": ["obuwie", "akcesoria"],
        },
        "piłkarz": {
            "allow": ["piłka nożna", "piłkars", "korki", "predator", "mercurial", "future", "morelia", "fg", "football"],
            "prefer_departments": ["obuwie", "akcesoria"],
        },
        "streetwear": {
            "allow": ["sneakers", "lifestyle", "samba", "574", "suede", "hoodie", "bluza", "classic", "na co dzień"],
            "prefer_departments": ["obuwie", "odziez"],
        },
    }

    football_terms = ["piłka nożna", "piłkars", "korki", "football", " fg", "predator", "mercurial", "future 7", "morelia"]

    cust = db.query(Customer).filter_by(id=customer_id).first()
    segment = norm(getattr(cust, "segment", ""))
    rule_key = next((key for key in segment_rules if key in segment), None)
    rule = segment_rules.get(rule_key, {})
    allow_terms = rule.get("allow", [])
    prefer_departments = set(rule.get("prefer_departments", []))
    fav_department = norm(getattr(cust, "favorite_department", "")) if cust else ""
    fav_brands = {
        brand.strip().casefold()
        for brand in (getattr(cust, "favorite_brands", "") or "").split(",")
        if brand.strip()
    }

    departments = {d.id: norm(d.slug) for d in db.query(Department).all()}
    products = db.query(Product).all()

    rec_boost = {}
    recs = db.query(CustomerRecommendation)\
        .filter_by(customer_id=customer_id)\
        .order_by(CustomerRecommendation.rank)\
        .limit(30).all()
    for r in recs:
        rec_boost[r.product_id] = max(0.0, 35.0 - float(getattr(r, "rank", 99) or 99) * 2.0)

    scored = []
    for p in products:
        text_blob = product_text(p)
        dep_slug = departments.get(p.department_id, "")

        if rule_key != "piłkarz" and any(term in text_blob for term in football_terms):
            continue

        matches = sum(1 for term in allow_terms if term in text_blob)
        if allow_terms and matches == 0:
            continue

        score = 100.0 * matches
        score += rec_boost.get(p.id, 0.0)
        if rule_key == "biegacz" and dep_slug == "obuwie":
            score += 120.0
        if rule_key == "biegacz" and ("buty do biegania" in text_blob or "buty trailowe" in text_blob):
            score += 80.0
        if rule_key == "fitness & joga" and ("mata" in text_blob or "maty" in text_blob):
            score += 180.0
        if rule_key == "koszykarz" and dep_slug == "obuwie":
            score += 80.0
        if dep_slug in prefer_departments:
            score += 30.0
        if fav_department and dep_slug == fav_department:
            score += 18.0
        if norm(p.brand) in fav_brands:
            score += 14.0
        score += float(p.rating or 0) * 2.0
        score += min(float(p.reviews or 0), 800.0) / 80.0
        scored.append((score, p))

    if not scored:
        q = db.query(Product)
        if fav_department:
            dep = db.query(Department).filter_by(slug=fav_department).first()
            if dep:
                q = q.filter(Product.department_id == dep.id)
        scored = [(float(p.rating or 0) * 2.0 + min(float(p.reviews or 0), 800.0) / 80.0, p)
                  for p in q.order_by(Product.reviews.desc(), Product.rating.desc()).limit(n * 3).all()
                  if rule_key == "piłkarz" or not any(term in product_text(p) for term in football_terms)]

    scored.sort(key=lambda item: (-item[0], item[1].price, item[1].id))
    picks = [(p.id, p.name, p.price, None) for _, p in scored[:n]]

    if not picks:
        prods = db.query(Product).order_by(Product.reviews.desc(), Product.rating.desc()).limit(n).all()
        picks = [(p.id, p.name, p.price, None) for p in prods]

    items = []
    for pid, name, price, prob in picks[:n]:
        seed = (customer_id * 131 + pid * 17) % 11    # 0..10
        discount = 5 + seed                            # 5..15
        new_price = round(price * (1 - discount / 100), 2)
        items.append({
            "product_id":  pid,
            "name":        name,
            "price":       price,
            "discount":    discount,
            "new_price":   new_price,
            "probability": round(prob, 4) if prob is not None else None,
            "image":       f"/api/products/{pid}/image",
        })
    return {"items": items}


if __name__ == "__main__":
    run_recommendations(verbose=True)
