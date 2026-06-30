# ProSport: 10 realistycznych zdjęć produktów

Zawartość:
- `static/images/products/product_1.png` ... `product_10.png`
- `app/main.py` z poprawionym endpointem `/api/products/{id}/image`

Jak użyć na VPS:

```bash
cd /srv/mlops/apps/p03-e-commerc
unzip prosport_10_real_images_patch.zip -d .
docker compose down
docker compose up -d --build
```

Po zmianie produkty o ID 1-10 pokażą prawdziwe zdjęcia.
Pozostałe produkty dalej pokażą placeholder SVG.
