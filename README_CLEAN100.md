# ProSport clean100 — czysta baza 100 produktów + łatwa podmiana obrazków

Ta paczka porządkuje sklep:

- baza ma zawsze dokładnie 100 produktów,
- ID produktów są stałe: 1–100,
- obrazki są przypisane po nazwie:
  - product_001.png → produkt ID 1
  - product_026.png → produkt ID 26
  - product_100.png → produkt ID 100
- dane produktów są w CSV: `app/seed_data/products_100.csv`,
- działy są w CSV: `app/seed_data/departments.csv`,
- brakujące obrazki można sprawdzić skryptem `scripts/check_images.py`.

## Instalacja na VPS

Wgraj ZIP do:

```bash
/srv/mlops/apps/p03-e-commerc/
```

Rozpakuj:

```bash
cd /srv/mlops/apps/p03-e-commerc
unzip -o prosport_clean_100_db_images_patch.zip -d .
```

Zrestartuj bazę i kontener:

```bash
docker compose down
rm -f data/prosport.db
docker compose up -d --build
```

Sprawdź:

```bash
curl -s http://localhost:8501/api/store | python -m json.tool | grep product_count
python scripts/check_images.py
```

## Jak podmienić obrazki

Wrzuć pliki do:

```text
static/images/products/
```

Nazwy muszą być:

```text
product_001.png
product_002.png
...
product_100.png
```

Jeżeli chcesz zmienić produkt lub obrazek, edytujesz tylko:

```text
app/seed_data/products_100.csv
```

Najważniejsza kolumna:

```text
image_filename
```

Potem wymuszasz reseed:

```bash
docker compose down
rm -f data/prosport.db
docker compose up -d --build
```

## Ile obrazków już jest w paczce?

Paczka zawiera 10 obrazków testowych:
- product_001.png
- product_003.png
- product_007.png
- product_026.png
- product_027.png
- product_028.png
- product_051.png
- product_052.png
- product_053.png
- product_076.png

Resztę trzeba dogenerować albo podmienić własnymi plikami.

## Kontrola braków

```bash
python scripts/check_images.py
```

Wynik pokaże listę brakujących plików.
