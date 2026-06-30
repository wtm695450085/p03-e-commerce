"""
Sparse Customer Clustering — klasteryzacja klientów ProSport.

Pipeline:
  1. Ekstrakcja cech (behawioralne + demograficzne + RFM)
  2. RFM scoring (5-stopniowy, quintile-based) + segment RFM
  3. PCA → 3 komponenty główne (redukcja wymiarowości)
  4. K-Means na 5 klastrach → twarda przynależność (C0–C4)
  5. Sparse clustering — miękkie prawdopodobieństwa przez odległości
     od centroidów (proporcja odwrotności odległości → %)

Uruchomienie standalone:
    python -m app.cluster_customers

Zapisuje wyniki do tabeli 'customer_clusters' w tej samej bazie SQLite.
Tabela jest nadpisywana przy każdym retreningu.

Wynik dla każdego klienta:
  - rfm_r, rfm_f, rfm_m (1-5)
  - rfm_score (np. "4-5-3")
  - rfm_segment (np. "Lojalny klient")
  - pca_1, pca_2, pca_3
  - km_cluster (np. "C")
  - cl_a … cl_e (float 0-1, suma = 1.0)
"""
from __future__ import annotations

import os
import sys
import json
import warnings
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans

# SQLAlchemy — używamy tej samej bazy co reszta aplikacji
from sqlalchemy import (
    Column, DateTime, Float, Integer, String, Text,
    create_engine, text,
)
from sqlalchemy.orm import declarative_base, Session, sessionmaker

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

# --------------------------------------------------------------------------
# Konfiguracja
# --------------------------------------------------------------------------
N_CLUSTERS = 5
CLUSTER_LABELS = list("ABCDE")          # C0→A, C1→B, ...
PCA_COMPONENTS = 3
RANDOM_STATE   = 42
REFERENCE_DATE: Optional[datetime] = None   # None = datetime.utcnow()

DATA_DIR    = os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))
DB_PATH     = os.path.join(DATA_DIR, "prosport.db")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")

# --------------------------------------------------------------------------
# ORM — minimalne (czytamy z istniejących tabel, piszemy do nowej)
# --------------------------------------------------------------------------
Base = declarative_base()


class CustomerCluster(Base):
    """Wynik klasteryzacji — jeden wiersz na klienta."""
    __tablename__ = "customer_clusters"

    customer_id  = Column(Integer, primary_key=True)   # odpowiada customers.id
    updated_at   = Column(DateTime, default=datetime.utcnow)

    # RFM raw (znormalizowane do skali 1-5)
    rfm_r        = Column(Integer)   # Recency  1=dawno, 5=ostatnio
    rfm_f        = Column(Integer)   # Frequency 1=rzadko, 5=często
    rfm_m        = Column(Integer)   # Monetary  1=mało, 5=dużo
    rfm_score    = Column(String(8)) # np. "4-5-3"
    rfm_segment  = Column(String(60))

    # PCA
    pca_1 = Column(Float)
    pca_2 = Column(Float)
    pca_3 = Column(Float)

    # K-Means — twarda przynależność
    km_cluster   = Column(String(2)) # "A"..."E"

    # Sparse — miękkie prawdopodobieństwa (JSON + 5 kolumn float)
    sparse_json  = Column(Text)      # {"A":0.12,"B":0.22,...}
    cl_a = Column(Float)
    cl_b = Column(Float)
    cl_c = Column(Float)
    cl_d = Column(Float)
    cl_e = Column(Float)

    # Etykieta klastra (np. "Aktywni biegacze premium")
    cluster_label = Column(String(80))


# --------------------------------------------------------------------------
# RFM scoring
# --------------------------------------------------------------------------
RFM_SEGMENTS = [
    # (min_r, min_f, min_m, label)
    (5, 5, 5, "Champions"),
    (4, 5, 4, "Lojalny klient"),
    (5, 4, 5, "Lojalny klient"),
    (4, 4, 4, "Lojalny klient"),
    (5, 5, 3, "Potencjalny Champion"),
    (4, 5, 3, "Potencjalny Champion"),
    (5, 3, 5, "Potencjalny Champion"),
    (5, 1, 5, "Nowy VIP"),
    (5, 1, 4, "Nowy VIP"),
    (4, 1, 4, "Nowy VIP"),
    (3, 5, 5, "Zagrożony wysoki"),
    (3, 4, 5, "Zagrożony wysoki"),
    (3, 3, 4, "Potrzebuje uwagi"),
    (3, 3, 3, "Potrzebuje uwagi"),
    (2, 5, 5, "Nie może stracić"),
    (2, 4, 5, "Nie może stracić"),
    (2, 4, 4, "Śpiący klient"),
    (2, 3, 3, "Śpiący klient"),
    (1, 5, 5, "Odejście VIP"),
    (1, 4, 4, "Odejście VIP"),
    (1, 3, 3, "Odchodzący"),
    (1, 2, 2, "Odchodzący"),
    (1, 1, 1, "Stracony"),
]


def rfm_segment(r: int, f: int, m: int) -> str:
    for min_r, min_f, min_m, label in RFM_SEGMENTS:
        if r >= min_r and f >= min_f and m >= min_m:
            return label
    return "Okazjonalny"


def quintile_score(series: pd.Series, ascending: bool = True) -> pd.Series:
    """Mapuje serię na kwintyle 1-5.

    ascending=True:  wyższy percentyl = wyższy score (F, M).
    ascending=False: niższy percentyl = wyższy score (R — im świeższy, tym lepiej).
    """
    labels = [1, 2, 3, 4, 5] if ascending else [5, 4, 3, 2, 1]
    return pd.qcut(series.rank(method="first"), q=5, labels=labels).astype(int)


# --------------------------------------------------------------------------
# Etykiety klastrów (nadawane po K-Means na podstawie cech centroidu)
# --------------------------------------------------------------------------
def _label_clusters(centers_df: pd.DataFrame) -> dict[int, str]:
    """
    Przypisuje opisowe etykiety do klastrów na podstawie najważniejszych cech
    centroidu. Etykiety są deterministyczne — posortowane wg centroidu.
    """
    labels_pool = [
        "Aktywni entuzjaści sportu",
        "Okazjonalni kupujący",
        "Klienci premium & fitness",
        "Budżetowi gracze zespołowi",
        "Seniorzy i outdoor",
    ]
    # Sortujemy klastry wg sumy znormalizowanych cech (proxy "ogólnej wartości")
    scores = centers_df.mean(axis=1).sort_values(ascending=False)
    return {int(idx): labels_pool[i] for i, idx in enumerate(scores.index)}


# --------------------------------------------------------------------------
# Sparse clustering — miękkie prawdopodobieństwa
# --------------------------------------------------------------------------
def soft_probabilities(X: np.ndarray, centers: np.ndarray,
                       temperature: float = 1.0) -> np.ndarray:
    """
    Przelicza odległości od centroidów na prawdopodobieństwa przynależności.

    Metoda: odwrotność odległości (1/d) znormalizowana do sumy 1.
    temperature > 1 → bardziej równomierny rozkład (softmax-like).
    temperature < 1 → ostrzejszy pik na domyślnym klastrze.

    Wynik: macierz (n_samples, n_clusters), wiersze sumują się do 1.
    """
    dists = np.linalg.norm(X[:, np.newaxis, :] - centers[np.newaxis, :, :], axis=2)
    # zabezpieczenie przed dzieleniem przez 0 (punkt = centroid)
    dists = np.maximum(dists, 1e-9)
    inv = (1.0 / dists) ** temperature
    return inv / inv.sum(axis=1, keepdims=True)


# --------------------------------------------------------------------------
# Główna funkcja ekstrakcji cech
# --------------------------------------------------------------------------
def build_feature_matrix(db: Session, ref_date: datetime) -> pd.DataFrame:
    """
    Buduje macierz cech dla wszystkich klientów.

    Cechy behawioralne (z historii zamówień/wizyt):
      - days_since_last_order  (Recency raw)
      - n_orders, n_visits (Frequency raw)
      - total_spent, avg_order_value (Monetary raw)
      - conversion_rate = n_orders / n_visits
      - udział każdego działu w wydatkach (4 kolumny: obuwie/odziez/silownia/akcesoria)
      - avg_basket_size (śr. liczba pozycji na zamówienie)

    Cechy demograficzne (zakodowane numerycznie):
      - age (liczba)
      - gender_m (0/1)
      - city_tier (0=srednie,1=duze,2=metro)
      - affluence_score (0=budżetowy … 3=premium)
      - has_children (0/1 — rodzina z dziećmi / nastolatkiem)
    """
    from app.models import Customer, Order, OrderItem, Product, Department, Visit

    rows = []
    customers = db.query(Customer).all()

    dept_slugs_map = {
        d.id: d.slug
        for d in db.query(Department).all()
    }
    prod_dept_map = {
        p.id: dept_slugs_map.get(p.department_id)
        for p in db.query(Product).all()
    }

    CITY_TIER_NUM = {
        "Warszawa": 2, "Kraków": 2, "Wrocław": 2, "Poznań": 2,
        "Gdańsk": 2, "Łódź": 2,
        "Szczecin": 1, "Bydgoszcz": 1, "Lublin": 1, "Białystok": 1,
        "Katowice": 1, "Gdynia": 1, "Częstochowa": 1, "Gliwice": 1,
        "Sosnowiec": 1,
    }
    AFF_NUM = {"budżetowy": 0, "średni": 1, "zamożny": 2, "premium": 3}

    DEPTS = ["obuwie", "odziez", "silownia", "akcesoria"]

    for c in customers:
        orders = [o for o in c.orders if o.status == "zrealizowane"]
        n_orders   = len(orders)
        n_visits   = c.visits_count or 0
        total_spent = c.total_spent or 0.0

        # --- Recency ---
        if orders:
            last_order_date = max(o.created_at for o in orders)
            days_since = max(0, (ref_date - last_order_date).days)
        else:
            days_since = (ref_date - (c.created_at or ref_date)).days
            days_since = max(days_since, 0)

        # --- Monetary details ---
        avg_order = total_spent / n_orders if n_orders > 0 else 0.0

        # --- Udział działów w wydatkach ---
        dept_spent = {d: 0.0 for d in DEPTS}
        total_items = 0
        for o in orders:
            for it in o.items:
                dept = prod_dept_map.get(it.product_id)
                if dept in dept_spent:
                    dept_spent[dept] += it.price * it.quantity
                total_items += it.quantity

        dept_share = {}
        for d in DEPTS:
            dept_share[f"share_{d}"] = (
                dept_spent[d] / total_spent if total_spent > 0 else 0.0
            )

        avg_basket = total_items / n_orders if n_orders > 0 else 0.0
        conv_rate  = n_orders / n_visits if n_visits > 0 else 0.0

        # --- Demograficzne ---
        city_tier  = CITY_TIER_NUM.get(c.city or "", 0)
        aff_score  = AFF_NUM.get(c.affluence or "średni", 1)
        has_kids   = 1 if (c.household or "") in (
            "rodzina z dziećmi", "rodzina z nastolatkiem") else 0
        gender_m   = 1 if c.gender == "m" else 0

        row = {
            "customer_id": c.id,
            # RFM raw
            "days_since_last_order": days_since,
            "n_orders":   n_orders,
            "total_spent": total_spent,
            # dodatkowe behawioralne
            "n_visits":   n_visits,
            "avg_order":  avg_order,
            "avg_basket": avg_basket,
            "conv_rate":  conv_rate,
            **dept_share,
            # demograficzne
            "age":        c.age or 30,
            "gender_m":   gender_m,
            "city_tier":  city_tier,
            "aff_score":  aff_score,
            "has_kids":   has_kids,
        }
        rows.append(row)

    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Główny pipeline
# --------------------------------------------------------------------------
def run_clustering(verbose: bool = True) -> pd.DataFrame:
    """
    Przeprowadza pełny pipeline klasteryzacji i zapisuje wyniki do bazy.
    Zwraca DataFrame z wynikami (customer_id + wszystkie kolumny klastrów).
    """
    engine = create_engine(DATABASE_URL,
                           connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    ref_date = REFERENCE_DATE or datetime.utcnow()

    try:
        if verbose:
            print("="*60)
            print("SPARSE CUSTOMER CLUSTERING — ProSport")
            print("="*60)

        # ── 1. CECHY ──────────────────────────────────────────────────
        if verbose:
            print("\n[1/5] Ekstrakcja cech...")
        df = build_feature_matrix(db, ref_date)
        n = len(df)
        if verbose:
            print(f"      {n} klientów | {len(df.columns)-1} cech bazowych")

        feature_cols = [c for c in df.columns if c != "customer_id"]
        X_raw = df[feature_cols].values.astype(float)

        # ── 2. RFM ────────────────────────────────────────────────────
        if verbose:
            print("\n[2/5] RFM scoring (quintile, skala 1-5)...")

        rfm_df = df[["customer_id", "days_since_last_order",
                     "n_orders", "total_spent"]].copy()
        rfm_df["R"] = quintile_score(rfm_df["days_since_last_order"], ascending=False)
        rfm_df["F"] = quintile_score(rfm_df["n_orders"],              ascending=True)
        rfm_df["M"] = quintile_score(rfm_df["total_spent"],           ascending=True)
        rfm_df["rfm_score"]   = rfm_df.apply(lambda r: f"{r.R}-{r.F}-{r.M}", axis=1)
        rfm_df["rfm_segment"] = rfm_df.apply(lambda r: rfm_segment(r.R, r.F, r.M), axis=1)

        if verbose:
            seg_dist = rfm_df["rfm_segment"].value_counts()
            for seg, cnt in seg_dist.head(6).items():
                print(f"      {seg:<30s} {cnt:>4}")

        # ── 3. PCA ────────────────────────────────────────────────────
        if verbose:
            print(f"\n[3/5] Standaryzacja + PCA → {PCA_COMPONENTS} komponenty...")

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X_raw)

        pca = PCA(n_components=PCA_COMPONENTS, random_state=RANDOM_STATE)
        X_pca = pca.fit_transform(X_scaled)

        explained = pca.explained_variance_ratio_
        if verbose:
            total_var = sum(explained) * 100
            for i, v in enumerate(explained):
                print(f"      PC{i+1}: {v*100:.1f}%")
            print(f"      Łącznie: {total_var:.1f}% wariancji")

        # ── 4. K-MEANS ────────────────────────────────────────────────
        if verbose:
            print(f"\n[4/5] K-Means (k={N_CLUSTERS}, random_state={RANDOM_STATE})...")

        kmeans = KMeans(
            n_clusters=N_CLUSTERS,
            n_init=20,          # więcej prób → stabilniejsze centra
            max_iter=500,
            random_state=RANDOM_STATE,
        )
        labels = kmeans.fit_predict(X_pca)
        centers = kmeans.cluster_centers_   # (k, PCA_COMPONENTS)

        # ── 5. SPARSE (miękkie prawdopodobieństwa) ────────────────────
        if verbose:
            print(f"\n[5/5] Sparse clustering — miękkie prawdopodobieństwa...")

        probs = soft_probabilities(X_pca, centers, temperature=1.5)
        # temperatura 1.5 → łagodniejsze rozkłady (mniej radykalne niż KM)

        # ── Etykiety klastrów ─────────────────────────────────────────
        centers_df = pd.DataFrame(centers, columns=[f"pc{i}" for i in range(PCA_COMPONENTS)])
        cluster_label_map = _label_clusters(centers_df)

        # Mapowanie indeksu klastra (0-4) → litera (A-E)
        # Sortujemy klastry wg medianą total_spent DESC (żeby A=najcenniejsi)
        cluster_ranks = (
            pd.Series(labels)
            .to_frame("km")
            .join(df["total_spent"])
            .groupby("km")["total_spent"]
            .median()
            .sort_values(ascending=False)
        )
        km_idx_to_letter = {
            int(idx): CLUSTER_LABELS[rank]
            for rank, idx in enumerate(cluster_ranks.index)
        }

        if verbose:
            print("\n  Rozkład klastrów:")
            from collections import Counter
            cnt = Counter(km_idx_to_letter[l] for l in labels)
            for letter in CLUSTER_LABELS:
                n_cl = cnt.get(letter, 0)
                bar  = "█" * (n_cl // 5)
                lbl  = cluster_label_map.get(
                    [k for k,v in km_idx_to_letter.items() if v == letter][0], "")
                print(f"    Klaster {letter} ({n_cl:>3}): {bar} — {lbl}")

        # ── Zapis do bazy ─────────────────────────────────────────────
        db.execute(text("DELETE FROM customer_clusters"))

        records = []
        for i, row in df.iterrows():
            cid       = int(row["customer_id"])
            km_idx    = int(labels[i])
            letter    = km_idx_to_letter[km_idx]
            p         = probs[i]

            # prawdopodobieństwa w przestrzeni liter (A-E)
            letter_probs = {}
            for raw_idx, ltr in km_idx_to_letter.items():
                letter_probs[ltr] = round(float(p[raw_idx]), 4)

            rfm_row  = rfm_df[rfm_df["customer_id"] == cid].iloc[0]

            records.append(CustomerCluster(
                customer_id   = cid,
                updated_at    = datetime.utcnow(),
                rfm_r         = int(rfm_row["R"]),
                rfm_f         = int(rfm_row["F"]),
                rfm_m         = int(rfm_row["M"]),
                rfm_score     = rfm_row["rfm_score"],
                rfm_segment   = rfm_row["rfm_segment"],
                pca_1         = round(float(X_pca[i, 0]), 5),
                pca_2         = round(float(X_pca[i, 1]), 5),
                pca_3         = round(float(X_pca[i, 2]), 5),
                km_cluster    = letter,
                sparse_json   = json.dumps(letter_probs),
                cl_a          = letter_probs.get("A", 0.0),
                cl_b          = letter_probs.get("B", 0.0),
                cl_c          = letter_probs.get("C", 0.0),
                cl_d          = letter_probs.get("D", 0.0),
                cl_e          = letter_probs.get("E", 0.0),
                cluster_label = cluster_label_map.get(km_idx, ""),
            ))

        db.add_all(records)
        db.commit()

        # ── Wynik ─────────────────────────────────────────────────────
        result_df = pd.DataFrame([{
            "customer_id":   r.customer_id,
            "rfm_r":         r.rfm_r,
            "rfm_f":         r.rfm_f,
            "rfm_m":         r.rfm_m,
            "rfm_score":     r.rfm_score,
            "rfm_segment":   r.rfm_segment,
            "pca_1":         r.pca_1,
            "pca_2":         r.pca_2,
            "pca_3":         r.pca_3,
            "km_cluster":    r.km_cluster,
            "cl_a":          r.cl_a,
            "cl_b":          r.cl_b,
            "cl_c":          r.cl_c,
            "cl_d":          r.cl_d,
            "cl_e":          r.cl_e,
            "cluster_label": r.cluster_label,
        } for r in records])

        if verbose:
            print(f"\n✓ Zapisano {len(records)} wierszy do tabeli 'customer_clusters'")
            print("\n── Przykład: 3 losowych klientów ──────────────────────")
            sample = result_df.sample(3, random_state=1)
            for _, r in sample.iterrows():
                from app.models import Customer as Cust
                c = db.query(Cust).filter_by(id=r["customer_id"]).first()
                name = c.full_name if c else f"ID {r['customer_id']}"
                print(f"\n  {name}")
                print(f"  RFM: R:{r['rfm_r']}/5  F:{r['rfm_f']}/5  M:{r['rfm_m']}/5"
                      f"  → {r['rfm_segment']}")
                print(f"  Klaster KM: {r['km_cluster']}  ({r['cluster_label']})")
                probs_str = "  ".join(
                    f"Klaster {ltr}: {round(getattr(r, f'cl_{ltr.lower()}') * 100):>3}%"
                    for ltr in CLUSTER_LABELS
                )
                print(f"  {probs_str}")

        return result_df

    finally:
        db.close()


# --------------------------------------------------------------------------
# Endpoint API — może być importowany przez main.py
# --------------------------------------------------------------------------
def get_customer_cluster(customer_id: int, db_session: Session) -> Optional[dict]:
    """Zwraca słownik z wynikami klasteryzacji dla jednego klienta."""
    from sqlalchemy.orm import Session as SASession
    row = db_session.query(CustomerCluster).filter_by(customer_id=customer_id).first()
    if not row:
        return None
    return {
        "rfm": {
            "r": row.rfm_r, "f": row.rfm_f, "m": row.rfm_m,
            "score": row.rfm_score,
            "segment": row.rfm_segment,
        },
        "pca": [row.pca_1, row.pca_2, row.pca_3],
        "km_cluster": row.km_cluster,
        "cluster_label": row.cluster_label,
        "sparse": {
            "A": row.cl_a, "B": row.cl_b, "C": row.cl_c,
            "D": row.cl_d, "E": row.cl_e,
        },
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
if __name__ == "__main__":
    result = run_clustering(verbose=True)
    print(f"\nDataFrame wynikowy: {result.shape[0]} wierszy × {result.shape[1]} kolumn")
    print(result[["customer_id", "rfm_score", "rfm_segment",
                  "km_cluster", "cl_a", "cl_b", "cl_c", "cl_d", "cl_e"]].head(10).to_string(index=False))
