from pathlib import Path
import csv

root = Path(__file__).resolve().parents[1]
csv_path = root / "app" / "seed_data" / "products_100.csv"
img_dir = root / "static" / "images" / "products"

missing = []
with csv_path.open("r", encoding="utf-8", newline="") as f:
    for row in csv.DictReader(f):
        fn = row["image_filename"]
        if not (img_dir / fn).exists():
            missing.append(fn)

print(f"Brakujące obrazy: {len(missing)}")
for fn in missing:
    print(fn)
