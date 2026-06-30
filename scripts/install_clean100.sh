#!/usr/bin/env bash
set -e

cd /srv/mlops/apps/p03-e-commerc

echo "Kopia bezpieczeństwa..."
mkdir -p _backup_clean100
cp -a app static docker-compose.yml entrypoint.sh _backup_clean100/ 2>/dev/null || true

echo "Pliki patcha powinny być już rozpakowane w katalogu projektu."
echo "Usuwam starą bazę SQLite..."
docker compose down || true
rm -f data/prosport.db

echo "Buduję i uruchamiam..."
docker compose up -d --build

echo "Test API:"
curl -s http://localhost:8501/api/store | python -m json.tool | grep product_count || true

echo "Sprawdzenie brakujących obrazków:"
python scripts/check_images.py || true

echo "Gotowe: http://62.72.20.95:8501"
