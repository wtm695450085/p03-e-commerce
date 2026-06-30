"""
Katalog produktów sklepu sportowego.

Generuje deterministycznie ~300 realistycznych produktów sportowych
przyporządkowanych do 4 działów. Nazwy bazują na prawdziwych liniach
produktowych istniejących marek, ceny są realistyczne (PLN), a warianty
(kolory / pojemności / wagi) tworzą realistyczną liczbę SKU.

Zdjęcia nie są dołączane jako pliki (prawa autorskie do fotografii
produktowych) — backend generuje czytelne, brandowane placeholdery SVG,
gotowe do podmiany na prawdziwe zdjęcia w przyszłości.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

# --------------------------------------------------------------------------
# Definicja sklepu i działów
# --------------------------------------------------------------------------

STORE = {
    "slug": "sport",
    "name": "ProSport",
    "tagline": "Sklep sportowy",
    "currency": "PLN",
    "theme": "dynamic",
}

# Każdy dział ma kolor akcentu (kodowanie kolorystyczne w UI i na placeholderach).
DEPARTMENTS = [
    {
        "slug": "obuwie",
        "name": "Obuwie sportowe",
        "icon": "shoe",
        "color": "#2D6CDF",
        "description": "Buty do biegania, piłki nożnej, koszykówki, treningu i na co dzień.",
    },
    {
        "slug": "odziez",
        "name": "Odzież sportowa",
        "icon": "shirt",
        "color": "#E8590C",
        "description": "Koszulki, spodenki, legginsy, bluzy, kurtki i bielizna termoaktywna.",
    },
    {
        "slug": "silownia",
        "name": "Siłownia i Fitness",
        "icon": "dumbbell",
        "color": "#0CA678",
        "description": "Hantle, kettlebell, sztangi, maty, gumy oporowe i sprzęt do ćwiczeń w domu.",
    },
    {
        "slug": "akcesoria",
        "name": "Akcesoria i Suplementy",
        "icon": "supplement",
        "color": "#7048E8",
        "description": "Odżywki, suplementy, piłki, zegarki sportowe, plecaki i akcesoria.",
    },
]

# --------------------------------------------------------------------------
# Definicje generatorów dla każdej kategorii
# --------------------------------------------------------------------------


@dataclass
class Category:
    department: str
    name: str          # nazwa kategorii (po polsku)
    icon: str          # klucz ikony dla placeholdera SVG
    price_min: int
    price_max: int
    models: list = field(default_factory=list)   # (marka, linia)
    variants: list = field(default_factory=list)  # warianty (kolor / pojemność / waga)
    tags: list = field(default_factory=list)
    target: int = 0     # ile produktów wygenerować w tej kategorii


COLORWAYS = [
    "Czerń/Biel", "Granat", "Grafit", "Volt", "Czerwony", "Royal Blue",
    "Szary melanż", "Biel", "Oliwka", "Koral", "Turkus", "Pomarańcz",
    "Fiolet", "Limonka", "Bordo", "Antracyt",
]


def _categories() -> list[Category]:
    cats: list[Category] = []

    # ===================== DZIAŁ: OBUWIE SPORTOWE =====================
    cats.append(Category(
        "obuwie", "Buty do biegania", "shoe", 269, 949,
        models=[
            ("Nike", "Air Zoom Pegasus 41"), ("Nike", "InfinityRN 4"),
            ("Nike", "Vomero 17"), ("Adidas", "Ultraboost Light"),
            ("Adidas", "Supernova Rise"), ("Adidas", "Adizero SL"),
            ("Asics", "Gel-Kayano 31"), ("Asics", "Gel-Nimbus 26"),
            ("Asics", "Novablast 4"), ("Brooks", "Ghost 16"),
            ("Brooks", "Glycerin 21"), ("New Balance", "Fresh Foam 1080v13"),
            ("New Balance", "FuelCell Rebel v4"), ("Hoka", "Clifton 9"),
            ("Hoka", "Mach 6"), ("Puma", "Velocity Nitro 3"),
            ("Mizuno", "Wave Rider 27"), ("Saucony", "Endorphin Speed 4"),
        ],
        variants=COLORWAYS, tags=["bieganie", "amortyzacja", "trening"], target=22,
    ))
    cats.append(Category(
        "obuwie", "Korki piłkarskie", "shoe", 199, 1099,
        models=[
            ("Nike", "Mercurial Vapor 16"), ("Nike", "Phantom GX II"),
            ("Nike", "Tiempo Legend 10"), ("Adidas", "Predator Elite"),
            ("Adidas", "X Crazyfast"), ("Adidas", "Copa Pure II"),
            ("Puma", "Future 7"), ("Puma", "Ultra 5"),
            ("Mizuno", "Morelia Neo IV"),
        ],
        variants=["FG", "AG", "Turf", "Halowe IC", "FG Czerń", "FG Biel", "AG Volt"],
        tags=["piłka nożna", "korki", "boisko"], target=15,
    ))
    cats.append(Category(
        "obuwie", "Buty treningowe", "shoe", 249, 749,
        models=[
            ("Nike", "Metcon 9"), ("Nike", "Free Metcon 5"),
            ("Reebok", "Nano X4"), ("Adidas", "Dropset 3"),
            ("Under Armour", "TriBase Reign 6"), ("Puma", "Fuse 3.0"),
        ],
        variants=COLORWAYS, tags=["trening", "siłownia", "crossfit"], target=12,
    ))
    cats.append(Category(
        "obuwie", "Buty do koszykówki", "shoe", 299, 899,
        models=[
            ("Nike", "LeBron XXI"), ("Nike", "Giannis Immortality 3"),
            ("Adidas", "Harden Vol. 8"), ("Adidas", "Dame 8"),
            ("Under Armour", "Curry 11"), ("Puma", "MB.03"),
        ],
        variants=COLORWAYS, tags=["koszykówka", "hala", "wsparcie kostki"], target=10,
    ))
    cats.append(Category(
        "obuwie", "Buty trailowe", "shoe", 329, 899,
        models=[
            ("Salomon", "Speedcross 6"), ("Salomon", "Sense Ride 5"),
            ("Hoka", "Speedgoat 5"), ("Asics", "Trabuco Max 3"),
            ("Brooks", "Cascadia 17"), ("Nike", "Pegasus Trail 4"),
        ],
        variants=COLORWAYS, tags=["trail", "góry", "off-road"], target=8,
    ))
    cats.append(Category(
        "obuwie", "Sneakersy", "shoe", 279, 699,
        models=[
            ("Nike", "Air Force 1 '07"), ("Nike", "Air Max 90"),
            ("Adidas", "Samba OG"), ("Adidas", "Gazelle"),
            ("New Balance", "574"), ("New Balance", "327"),
            ("Puma", "Suede Classic"), ("Reebok", "Club C 85"),
        ],
        variants=COLORWAYS, tags=["lifestyle", "na co dzień", "sneakers"], target=8,
    ))

    # ===================== DZIAŁ: ODZIEŻ SPORTOWA =====================
    cats.append(Category(
        "odziez", "Koszulki treningowe", "shirt", 49, 219,
        models=[
            ("Nike", "Dri-FIT Miler"), ("Nike", "Pro Tank"),
            ("Adidas", "Aeroready Designed 2 Move"), ("Under Armour", "Tech 2.0"),
            ("Puma", "teamLIGA Jersey"), ("4F", "Funkcyjna Quick-Dry"),
            ("Asics", "Core Top"),
        ],
        variants=COLORWAYS, tags=["koszulka", "oddychająca", "trening"], target=18,
    ))
    cats.append(Category(
        "odziez", "Spodenki sportowe", "shirt", 59, 229,
        models=[
            ("Nike", "Dri-FIT Stride 7\""), ("Adidas", "Run It Shorts"),
            ("Under Armour", "Launch 5\""), ("Puma", "Run Favourite"),
            ("4F", "Spodenki Treningowe"), ("New Balance", "Accelerate 5\""),
        ],
        variants=COLORWAYS, tags=["spodenki", "bieganie", "lekkie"], target=13,
    ))
    cats.append(Category(
        "odziez", "Legginsy i getry", "shirt", 89, 299,
        models=[
            ("Nike", "Pro 365 Tight"), ("Adidas", "Optime Training"),
            ("Under Armour", "Meridian"), ("Puma", "Studio Foundation"),
            ("4F", "Legginsy Treningowe"),
        ],
        variants=COLORWAYS, tags=["legginsy", "kompresja", "joga"], target=12,
    ))
    cats.append(Category(
        "odziez", "Bluzy i hoody", "shirt", 129, 449,
        models=[
            ("Nike", "Sportswear Club Hoodie"), ("Adidas", "Essentials Fleece"),
            ("Under Armour", "Rival Fleece"), ("Puma", "ESS Logo Hoodie"),
            ("Champion", "Powerblend Hoodie"), ("4F", "Bluza z Kapturem"),
        ],
        variants=COLORWAYS, tags=["bluza", "hoodie", "rozgrzewka"], target=12,
    ))
    cats.append(Category(
        "odziez", "Kurtki sportowe", "shirt", 199, 799,
        models=[
            ("Nike", "Windrunner"), ("Adidas", "Terrex Multi"),
            ("Columbia", "Watertight II"), ("The North Face", "Quest Jacket"),
            ("4F", "Kurtka Softshell"), ("Under Armour", "Storm Run"),
        ],
        variants=["Czerń", "Granat", "Grafit", "Oliwka", "Czerwony", "Royal Blue"],
        tags=["kurtka", "wiatrówka", "ochrona"], target=9,
    ))
    cats.append(Category(
        "odziez", "Skarpety i bielizna termo", "shirt", 25, 189,
        models=[
            ("Nike", "Everyday Cushioned (3-pak)"), ("Adidas", "Cushioned Crew (3-pak)"),
            ("Under Armour", "ColdGear Base 2.0"), ("Stance", "Run Crew"),
            ("4F", "Bielizna Termoaktywna"), ("Brubeck", "Active Wool"),
        ],
        variants=["Czerń", "Biel", "Szary", "Granat", "Mix kolorów"],
        tags=["skarpety", "termoaktywne", "baza"], target=11,
    ))

    # ===================== DZIAŁ: SIŁOWNIA I FITNESS =====================
    cats.append(Category(
        "silownia", "Hantle", "dumbbell", 39, 549,
        models=[
            ("Eb Fit", "Hantla Gumowana Heksagonalna"), ("York Fitness", "Hantla Hex"),
            ("Domyos", "Hantla Winylowa"), ("Bauer Fitness", "Hantla Stalowa"),
            ("Hammer", "Hantla Neopren"),
        ],
        variants=["1 kg", "2 kg", "3 kg", "5 kg", "7,5 kg", "10 kg",
                  "12,5 kg", "15 kg", "20 kg", "25 kg", "30 kg"],
        tags=["hantle", "obciążenie", "trening siłowy"], target=18,
    ))
    cats.append(Category(
        "silownia", "Kettlebell", "kettlebell", 59, 499,
        models=[
            ("Eb Fit", "Kettlebell Żeliwny"), ("Thorn+Fit", "Competition Kettlebell"),
            ("Domyos", "Kettlebell Kompaktowy"), ("Bauer Fitness", "Kettlebell Gumowany"),
        ],
        variants=["4 kg", "6 kg", "8 kg", "10 kg", "12 kg", "16 kg", "20 kg", "24 kg", "32 kg"],
        tags=["kettlebell", "kettle", "siła wytrzymałościowa"], target=12,
    ))
    cats.append(Category(
        "silownia", "Sztangi i talerze", "dumbbell", 79, 899,
        models=[
            ("Eb Fit", "Gryf Olimpijski 220 cm"), ("York Fitness", "Talerz Olimpijski"),
            ("Bauer Fitness", "Gryf Prosty 120 cm"), ("Hammer", "Talerz Gumowany"),
            ("Thorn+Fit", "Gryf Treningowy"),
        ],
        variants=["1,25 kg", "2,5 kg", "5 kg", "10 kg", "15 kg", "20 kg",
                  "Gryf 10 kg", "Gryf 20 kg"],
        tags=["sztanga", "talerze", "wolne ciężary"], target=12,
    ))
    cats.append(Category(
        "silownia", "Maty i akcesoria fitness", "mat", 35, 329,
        models=[
            ("Domyos", "Mata do Jogi"), ("Eb Fit", "Mata Fitness NBR"),
            ("Manduka", "PRO Mat"), ("Reebok", "Mata Treningowa"),
            ("Adidas", "Mata do Ćwiczeń"),
        ],
        variants=["6 mm Czerń", "8 mm Granat", "10 mm Fiolet", "6 mm Turkus",
                  "8 mm Koral", "10 mm Szary"],
        tags=["mata", "joga", "rozciąganie"], target=10,
    ))
    cats.append(Category(
        "silownia", "Gumy i taśmy oporowe", "band", 19, 199,
        models=[
            ("Thorn+Fit", "Guma Power Band"), ("Eb Fit", "Taśma Oporowa"),
            ("Domyos", "Mini Band (zestaw)"), ("Bauer Fitness", "Taśma Mini"),
            ("4F", "Zestaw Gum Oporowych"),
        ],
        variants=["Lekka", "Średnia", "Mocna", "Bardzo mocna", "Zestaw 3 szt.", "Zestaw 5 szt."],
        tags=["guma oporowa", "mobilność", "rozgrzewka"], target=10,
    ))
    cats.append(Category(
        "silownia", "Sprzęt treningowy", "dumbbell", 69, 1299,
        models=[
            ("Domyos", "Ławka Treningowa Regulowana"), ("Eb Fit", "Drążek do Podciągania"),
            ("Thorn+Fit", "TRX Trener Zawieszany"), ("Tunturi", "Piłka Gimnastyczna"),
            ("Eb Fit", "Roller do Masażu"), ("Domyos", "Skakanka Szybka"),
            ("Bauer Fitness", "Stojak na Hantle"),
        ],
        variants=["Standard", "Pro", "Czerń", "Granat", "Czerwony"],
        tags=["sprzęt", "trening w domu", "wyposażenie"], target=14,
    ))

    # ===================== DZIAŁ: AKCESORIA I SUPLEMENTY =====================
    cats.append(Category(
        "akcesoria", "Odżywki białkowe", "supplement", 49, 279,
        models=[
            ("Olimp", "Whey Protein Complex 100%"), ("Trec", "Gold Core Whey 100%"),
            ("BioTech USA", "100% Pure Whey"), ("KFD", "Premium Whey"),
            ("Real Pharm", "Real Whey"),
        ],
        variants=["700 g Wanilia", "700 g Czekolada", "2 kg Truskawka",
                  "2 kg Czekolada", "900 g Banan", "1,8 kg Wanilia"],
        tags=["białko", "whey", "regeneracja"], target=16,
    ))
    cats.append(Category(
        "akcesoria", "Kreatyna i pre-workout", "supplement", 39, 199,
        models=[
            ("Olimp", "Creatine Monohydrate Powder"), ("Trec", "CM3 Powder"),
            ("BioTech USA", "100% Creatine Monohydrate"), ("KFD", "Kreatyna Monohydrat"),
            ("Olimp", "Redweiler Pre-Workout"),
        ],
        variants=["250 g", "500 g Cytryna", "500 g Owoce Leśne", "300 g Pomarańcz", "550 g"],
        tags=["kreatyna", "siła", "pre-workout"], target=11,
    ))
    cats.append(Category(
        "akcesoria", "Witaminy i regeneracja", "supplement", 25, 159,
        models=[
            ("Olimp", "Gold Omega 3"), ("Trec", "Vitamin D3"),
            ("BioTech USA", "Multivitamin for Men"), ("Now Foods", "Magnesium"),
            ("Olimp", "BCAA Xplode"), ("Trec", "L-Carnitine"),
        ],
        variants=["60 kaps.", "120 kaps.", "90 tab.", "500 g", "200 g Cytryna"],
        tags=["witaminy", "zdrowie", "suplementacja"], target=12,
    ))
    cats.append(Category(
        "akcesoria", "Piłki sportowe", "ball", 49, 449,
        models=[
            ("Adidas", "UCL Pro Piłka Nożna"), ("Nike", "Academy Piłka Nożna"),
            ("Select", "Brillant Super"), ("Wilson", "NBA Authentic Koszykowa"),
            ("Spalding", "TF-1000 Koszykowa"), ("Molten", "V5M5000 Siatkowa"),
            ("Mikasa", "MVA200 Siatkowa"),
        ],
        variants=["Rozmiar 3", "Rozmiar 4", "Rozmiar 5", "Rozmiar 7", "Halowa", "Outdoor"],
        tags=["piłka", "gra zespołowa", "boisko"], target=12,
    ))
    cats.append(Category(
        "akcesoria", "Zegarki i opaski sportowe", "watch", 149, 2799,
        models=[
            ("Garmin", "Forerunner 165"), ("Garmin", "Venu 3"),
            ("Polar", "Pacer Pro"), ("Suunto", "Race"),
            ("Coros", "Pace 3"), ("Xiaomi", "Smart Band 9"),
            ("Amazfit", "Active Edge"),
        ],
        variants=["Czerń", "Granat", "Szary", "Koral", "Royal Blue"],
        tags=["zegarek", "GPS", "puls", "monitoring"], target=12,
    ))
    cats.append(Category(
        "akcesoria", "Torby, plecaki i bidony", "bag", 29, 399,
        models=[
            ("Nike", "Brasilia Torba Treningowa"), ("Adidas", "Linear Plecak"),
            ("Under Armour", "Hustle 5.0 Plecak"), ("Puma", "TeamGOAL Torba"),
            ("Camelbak", "Bidon Podio 0,7 l"), ("Nike", "Bidon HyperFuel 0,7 l"),
            ("4F", "Plecak Sportowy 25 l"),
        ],
        variants=["Czerń", "Granat", "Grafit", "Czerwony", "Oliwka", "Royal Blue"],
        tags=["torba", "plecak", "bidon", "transport"], target=12,
    ))

    return cats


# --------------------------------------------------------------------------
# Generowanie produktów
# --------------------------------------------------------------------------

_DEPT_TINT = {d["slug"]: d["color"] for d in DEPARTMENTS}


def _round_price(value: float) -> float:
    """Zaokrągla cenę do realistycznej końcówki (np. ,99 / ,90 / ,00)."""
    endings = [0.99, 0.99, 0.90, 0.00, 0.95]
    base = int(value)
    return round(base + random.choice(endings), 2)


def build_catalog(seed: int = 2024) -> list[dict]:
    """Zwraca listę słowników-produktów (deterministycznie dla danego seeda)."""
    rng = random.Random(seed)
    random.seed(seed)
    products: list[dict] = []
    sku_counter = 1000

    for cat in _categories():
        # twórz pary (model, wariant) aż osiągniemy target dla kategorii
        combos = [(m, v) for m in cat.models for v in cat.variants]
        rng.shuffle(combos)
        chosen = combos[: cat.target]

        for (brand, line), variant in chosen:
            sku_counter += 1
            price = _round_price(rng.uniform(cat.price_min, cat.price_max))
            old_price = None
            if rng.random() < 0.28:  # ~28% produktów w promocji
                old_price = _round_price(price * rng.uniform(1.12, 1.45))

            name = f"{brand} {line}"
            full_name = f"{name} – {variant}"
            tags = list(cat.tags) + [brand.lower()]

            stock = rng.choice([0, 3, 5, 8, 12, 20, 35, 50, 60])
            rating = round(rng.uniform(3.9, 5.0), 1)
            reviews = rng.randint(4, 480)

            description = _description(cat, brand, line, variant)

            products.append({
                "sku": f"SP-{sku_counter}",
                "name": full_name,
                "brand": brand,
                "category": cat.name,
                "department": cat.department,
                "price": price,
                "old_price": old_price,
                "variant": variant,
                "description": description,
                "tags": ",".join(tags),
                "icon": cat.icon,
                "color": _DEPT_TINT[cat.department],
                "stock": stock,
                "rating": rating,
                "reviews": reviews,
                "is_promo": old_price is not None,
            })

    # nadaj stabilną kolejność / numerację
    products.sort(key=lambda p: (p["department"], p["category"], p["name"]))
    return products


def _description(cat: Category, brand: str, line: str, variant: str) -> str:
    templates = {
        "obuwie": (
            f"{brand} {line} w wersji {variant}. Lekka konstrukcja, dobra amortyzacja "
            f"i oddychająca cholewka — sprawdzą się zarówno na treningu, jak i na co dzień."
        ),
        "odziez": (
            f"{brand} {line} ({variant}). Oddychający, szybkoschnący materiał odprowadzający "
            f"wilgoć, zapewniający komfort podczas każdej aktywności."
        ),
        "silownia": (
            f"{brand} {line} – {variant}. Solidne wykonanie i trwałe materiały. "
            f"Idealne do treningu w domu i na siłowni."
        ),
        "akcesoria": (
            f"{brand} {line} ({variant}). Wysokiej jakości produkt sportowy renomowanej marki, "
            f"który wspiera Twoje treningi i regenerację."
        ),
    }
    return templates.get(cat.department, f"{brand} {line} – {variant}.")


if __name__ == "__main__":
    cat = build_catalog()
    print(f"Wygenerowano {len(cat)} produktów")
    from collections import Counter
    by_dep = Counter(p["department"] for p in cat)
    for dep, n in by_dep.items():
        print(f"  {dep}: {n}")
