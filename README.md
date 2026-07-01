# ProSport — sklep sportowy (demo)

http://62.72.20.95:8501/

http://62.72.20.95:8501/dashboard



Sklep sportowy w formacie HTML z własną bazą produktów, koszykiem i symulowanym
składaniem zamówień. Backend: **FastAPI + SQLite** (gotowy pod PostgreSQL),
frontend: **HTML / CSS / JS**. Całość uruchamiana w **kontenerze Docker**,
przygotowana pod wdrożenie na **VPS**.

To pierwszy komponent większego demonstratora systemu rekomendacyjnego AI dla
e-commerce — dlatego struktura bazy (sklepy / działy / produkty / zamówienia)
jest podzbiorem docelowego schematu i łatwo ją rozbudować.

## Co zawiera

- **301 produktów** sportowych z realistycznymi nazwami (prawdziwe linie marek),
  cenami w PLN, ocenami, stanami magazynowymi i promocjami.
- **4 działy**: Obuwie sportowe · Odzież sportowa · Siłownia i Fitness ·
  Akcesoria i Suplementy — każdy produkt przypisany do działu.
- **Koszyk** z dodawaniem, zmianą ilości, usuwaniem i trwałością w przeglądarce.
- **Symulowane zamówienie** (bez realnej płatności) zapisywane w bazie.
- **Wyszukiwarka, filtr marki, filtr promocji, sortowanie i paginacja.**
- **Obrazy produktów** generowane jako brandowane placeholdery SVG
  (kodowane kolorem działu) — gotowe do podmiany na prawdziwe zdjęcia.

## Szybki start (Docker)

```bash
docker compose up --build
```

Sklep: <http://localhost:8000>

Baza SQLite jest seedowana automatycznie przy pierwszym starcie i zapisywana
w katalogu `./data` (wolumen), więc przetrwa restart kontenera.

## Uruchomienie lokalne (bez Dockera)

```bash
pip install -r requirements.txt
python -m app.seed            # utwórz i wypełnij bazę
uvicorn app.main:app --reload # start: http://127.0.0.1:8000
```

## Struktura

```
sports-store/
├── app/
│   ├── main.py            # FastAPI: API + serwowanie frontendu
│   ├── database.py        # SQLAlchemy (SQLite, gotowe pod PostgreSQL)
│   ├── models.py          # modele: Store, Department, Product, Order, OrderItem
│   ├── images.py          # generator placeholderów SVG
│   ├── seed.py            # wypełnianie bazy
│   └── data/catalog.py    # generator katalogu 301 produktów
├── static/                # frontend HTML / CSS / JS
│   ├── index.html
│   ├── css/style.css
│   └── js/app.js
├── data/                  # baza SQLite (wolumen, trwała na VPS)
├── Dockerfile
├── docker-compose.yml
├── entrypoint.sh
└── requirements.txt
```

## API

| Metoda | Endpoint                       | Opis                                            |
|--------|--------------------------------|-------------------------------------------------|
| GET    | `/api/health`                  | Status serwera                                  |
| GET    | `/api/store`                   | Dane sklepu + działy z licznikami produktów     |
| GET    | `/api/products`                | Lista produktów (filtry, sortowanie, paginacja) |
| GET    | `/api/products/{id}`           | Szczegóły produktu + podobne                     |
| GET    | `/api/products/{id}/image`     | Placeholder SVG produktu                         |
| GET    | `/api/brands`                  | Lista marek (opcjonalnie w dziale)              |
| POST   | `/api/orders`                  | Złożenie zamówienia (symulacja)                 |

Parametry `/api/products`: `department`, `q`, `brand`, `promo`, `sort`
(`popular` / `rating` / `price_asc` / `price_desc` / `name`), `page`, `page_size`.

## Migracja na PostgreSQL

Kod nie zakłada SQLite — wystarczy ustawić zmienną `DATABASE_URL`, np.:

```bash
DATABASE_URL=postgresql+psycopg://user:pass@host:5432/prosport
```

W `docker-compose.yml` przygotowano (zakomentowaną) usługę `db` z Postgresem.

## Uwagi

- Płatności, wysyłka i checkout są **symulowane** — zamówienie zapisuje się
  w bazie ze statusem `symulacja`, aby w przyszłości zasilić historię zakupów
  klienta w module rekomendacyjnym.
- Obrazy to placeholdery SVG (bez naruszania praw autorskich do zdjęć
  produktowych). Aby użyć prawdziwych zdjęć, dodaj pole `image_url` do modelu
  `Product` i zwróć je w `as_dict()`.
