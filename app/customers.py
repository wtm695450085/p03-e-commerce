"""
Generator archiwum klientów sklepu ProSport.

Tworzy deterministycznie (dla danego seeda) bazę 150 klientów wraz z profilem
zainteresowań, poziomem lojalności i danymi demograficznymi. Sam plik nie
dotyka bazy danych — to czysty generator danych (jak data/catalog.py).

Historia zakupów, wizyt i czatów jest budowana w seed_customers.py, bo zależy
od realnych produktów w bazie. Tutaj definiujemy:
  • dane do losowania (imiona, nazwiska, miasta),
  • SEGMENTY (profile zainteresowań) z afinicją do działów / kategorii / marek,
  • POZIOMY lojalności (ile wizyt i zamówień, jak dawno aktywny),
  • szablony wiadomości z czatu obsługi klienta.
"""
from __future__ import annotations

import random
import unicodedata
from dataclasses import dataclass, field

# --------------------------------------------------------------------------
# Dane do losowania profilu
# --------------------------------------------------------------------------
FIRST_M = [
    "Jakub", "Jan", "Piotr", "Mateusz", "Kamil", "Michał", "Tomasz", "Paweł",
    "Krzysztof", "Marcin", "Adam", "Łukasz", "Bartosz", "Dawid", "Filip",
    "Wojciech", "Grzegorz", "Maciej", "Rafał", "Sebastian", "Damian", "Patryk",
    "Hubert", "Konrad", "Dominik", "Szymon", "Adrian", "Mariusz", "Artur", "Igor",
]
FIRST_F = [
    "Anna", "Katarzyna", "Magdalena", "Agnieszka", "Joanna", "Aleksandra",
    "Natalia", "Karolina", "Monika", "Ewa", "Paulina", "Małgorzata", "Justyna",
    "Weronika", "Patrycja", "Sylwia", "Klaudia", "Dominika", "Zuzanna", "Marta",
    "Beata", "Dorota", "Emilia", "Wiktoria", "Oliwia", "Julia", "Iwona", "Renata",
    "Sandra", "Gabriela",
]
SURNAMES = [
    "Nowak", "Kowalski", "Wiśniewski", "Wójcik", "Kowalczyk", "Kamiński",
    "Lewandowski", "Zieliński", "Szymański", "Woźniak", "Dąbrowski", "Kozłowski",
    "Jankowski", "Mazur", "Kwiatkowski", "Krawczyk", "Piotrowski", "Grabowski",
    "Nowakowski", "Pawłowski", "Michalski", "Adamczyk", "Dudek", "Zając",
    "Wieczorek", "Jabłoński", "Król", "Majewski", "Olszewski", "Jaworski",
    "Wróbel", "Malinowski", "Pawlak", "Witkowski", "Walczak", "Stępień",
    "Górski", "Rutkowski", "Michalak", "Sikora", "Ostrowski", "Baran",
    "Duda", "Szewczyk", "Tomaszewski", "Pietrzak", "Marciniak", "Wróblewski",
    "Zalewski", "Jakubowski", "Sadowski", "Bąk", "Chmielewski", "Włodarczyk",
    "Borkowski", "Czarnecki", "Sawicki", "Sokołowski", "Urbański", "Kubiak",
]
CITIES = [
    "Warszawa", "Kraków", "Łódź", "Wrocław", "Poznań", "Gdańsk", "Szczecin",
    "Bydgoszcz", "Lublin", "Białystok", "Katowice", "Gdynia", "Częstochowa",
    "Radom", "Rzeszów", "Toruń", "Kielce", "Olsztyn", "Zabrze", "Bielsko-Biała",
    "Gliwice", "Sosnowiec", "Tarnów", "Opole", "Płock",
]
EMAIL_DOMAINS = ["gmail.com", "wp.pl", "o2.pl", "interia.pl", "onet.pl", "outlook.com"]


# --------------------------------------------------------------------------
# DEMOGRAFIA — osie do klastrowania (wiek · płeć · zasobność · miasto · dom)
# Profile są tak skonstruowane, by te cechy korelowały z tym, CO klient kupuje
# (młodszy ≠ starszy, kobieta ≠ mężczyzna, zamożny ≠ budżetowy, rodzic kupuje
# pod dzieci). Dzięki temu na danych widać sensowne klastry, a nie biały szum.
# --------------------------------------------------------------------------

# Wielkość miasta (metro / duże / średnie) — przesuwa zasobność portfela.
CITY_TIER = {
    "Warszawa": "metro", "Kraków": "metro", "Wrocław": "metro", "Poznań": "metro",
    "Gdańsk": "metro", "Łódź": "metro",
    "Szczecin": "duze", "Bydgoszcz": "duze", "Lublin": "duze", "Białystok": "duze",
    "Katowice": "duze", "Gdynia": "duze", "Częstochowa": "duze", "Gliwice": "duze",
    "Sosnowiec": "duze",
}  # pozostałe miasta -> "srednie"

# Grupy wiekowe: (etykieta, (min, max), udział w populacji).
AGE_GROUPS = [
    ("18-25", (18, 25), 0.20),
    ("26-35", (26, 35), 0.30),
    ("36-45", (36, 45), 0.25),
    ("46-60", (46, 60), 0.18),
    ("60+",   (61, 74), 0.07),
]

# Jak wiek przesuwa prawdopodobieństwo segmentu (mnożnik wagi segmentu).
AGE_SEGMENT_BIAS = {
    "18-25": {"streetwear": 2.2, "koszykarz": 1.8, "pilkarz": 1.6, "silownia": 1.3,
              "suplementy": 1.2, "fitness": 1.0, "biegacz": 0.9, "outdoor": 0.7, "okazjonalny": 0.9},
    "26-35": {"biegacz": 1.4, "silownia": 1.4, "fitness": 1.3, "suplementy": 1.2,
              "streetwear": 1.1, "pilkarz": 1.0, "outdoor": 1.0, "okazjonalny": 1.0, "koszykarz": 0.9},
    "36-45": {"biegacz": 1.3, "fitness": 1.3, "outdoor": 1.3, "okazjonalny": 1.2,
              "silownia": 1.1, "suplementy": 1.0, "pilkarz": 0.8, "streetwear": 0.7, "koszykarz": 0.6},
    "46-60": {"fitness": 1.5, "outdoor": 1.5, "okazjonalny": 1.4, "biegacz": 1.1,
              "suplementy": 1.0, "silownia": 0.7, "streetwear": 0.4, "pilkarz": 0.4, "koszykarz": 0.3},
    "60+":   {"okazjonalny": 1.6, "fitness": 1.6, "outdoor": 1.3, "suplementy": 1.1,
              "biegacz": 0.8, "silownia": 0.5, "streetwear": 0.3, "pilkarz": 0.2, "koszykarz": 0.2},
}

# Zasobność portfela. Bazowy rozkład × wielkość miasta × poziom lojalności.
AFFLUENCE = ["budżetowy", "średni", "zamożny", "premium"]
AFFLUENCE_BASE = {"budżetowy": 1.0, "średni": 1.3, "zamożny": 0.8, "premium": 0.35}
CITY_AFFLUENCE_MULT = {
    "metro":   {"budżetowy": 0.7, "średni": 1.0, "zamożny": 1.4, "premium": 1.8},
    "duze":    {"budżetowy": 1.0, "średni": 1.1, "zamożny": 1.0, "premium": 0.9},
    "srednie": {"budżetowy": 1.5, "średni": 1.1, "zamożny": 0.7, "premium": 0.4},
}
TIER_AFFLUENCE_MULT = {
    "VIP":         {"budżetowy": 0.3, "średni": 0.7, "zamożny": 1.6, "premium": 2.4},
    "Stały":       {"budżetowy": 0.6, "średni": 1.0, "zamożny": 1.4, "premium": 1.4},
    "Regularny":   {"budżetowy": 1.0, "średni": 1.2, "zamożny": 1.0, "premium": 0.8},
    "Okazjonalny": {"budżetowy": 1.4, "średni": 1.1, "zamożny": 0.7, "premium": 0.4},
    "Nowy":        {"budżetowy": 1.3, "średni": 1.1, "zamożny": 0.8, "premium": 0.5},
}

# Gospodarstwo domowe wg wieku (wpływa na zakupy dziecięce/rodzinne).
HOUSEHOLD_BY_AGE = {
    "18-25": [("singiel", 0.70), ("para", 0.25), ("rodzina z dziećmi", 0.05)],
    "26-35": [("singiel", 0.35), ("para", 0.35), ("rodzina z dziećmi", 0.30)],
    "36-45": [("rodzina z dziećmi", 0.50), ("rodzina z nastolatkiem", 0.25), ("para", 0.25)],
    "46-60": [("rodzina z nastolatkiem", 0.40), ("para", 0.40), ("singiel", 0.20)],
    "60+":   [("para", 0.60), ("singiel", 0.40)],
}

# Wskazówki do afinicji produktowej (dopasowanie cech klienta do cech produktu).
# Wykrywane w nazwie+kategorii produktu (małymi literami).
_FEMALE_HINTS = ["legginsy", "joga", "maty", "fitness", "studio"]
_MALE_HINTS = ["korki", "piłkarskie", "sztangi", "hantle", "koszykówki", "kettlebell"]
_YOUNG_HINTS = ["sneakersy", "koszykówki", "bluzy", "piłkarskie", "streetwear"]
_OLDER_HINTS = ["witaminy", "regeneracja", "maty", "kurtki", "trailowe", "zegarki", "omega", "magnesium"]
# Produkty dla dzieci/młodzieży — wykrywane po słowach kluczowych. Dziś katalog
# raczej ich nie ma, ale gdy asortyment urośnie do 300 i pojawią się pozycje
# juniorskie, segment rodzinny automatycznie zacznie je kupować.
_KID_HINTS = ["dziecięc", "junior", "kids", "młodzie", "rozmiar 3", "rozmiar 4", "mini band"]
_PREMIUM_BRANDS = {"Garmin", "Polar", "Suunto", "Coros", "Hoka", "Salomon",
                   "The North Face", "Manduka", "Columbia", "Asics", "Brooks", "Mizuno"}
_BUDGET_BRANDS = {"4F", "Domyos", "KFD", "Eb Fit", "Bauer Fitness", "Real Pharm",
                  "Hammer", "York Fitness"}


# --------------------------------------------------------------------------
# SEGMENTY — profile zainteresowań klienta
#   dept:     waga afinicji do działu (slug -> waga)
#   keywords: fragmenty nazw kategorii, które klient kupuje chętniej
#   brands:   preferowane marki (mocniejsze ważenie produktu)
# --------------------------------------------------------------------------
@dataclass
class Segment:
    key: str
    label: str
    summary: str               # szablon opisu zainteresowań ({brands} -> marki)
    dept: dict = field(default_factory=dict)
    keywords: list = field(default_factory=list)
    brands: list = field(default_factory=list)
    weight: float = 1.0        # jak częsty jest ten segment w populacji
    gender_bias: float = 0.5   # P(kobieta) dla tego segmentu


SEGMENTS = [
    Segment(
        "biegacz", "Biegacz",
        "Aktywny biegacz — najczęściej sięga po buty do biegania i odzież "
        "techniczną. Ceni lekkość i amortyzację, lojalny wobec marek {brands}.",
        dept={"obuwie": 3.0, "odziez": 2.0, "akcesoria": 1.4, "silownia": 0.4},
        keywords=["biegania", "trailowe", "Koszulki", "Spodenki", "Skarpety",
                  "Kurtki", "Zegarki", "bidon"],
        brands=["Nike", "Asics", "Hoka", "Brooks", "Saucony", "Garmin", "New Balance"],
        weight=1.4, gender_bias=0.45,
    ),
    Segment(
        "silownia", "Siłownia",
        "Trenuje siłowo — kompletuje sprzęt na siłownię i suplementację. "
        "Kupuje hantle, sztangi i odżywki, głównie marek {brands}.",
        dept={"silownia": 3.0, "akcesoria": 2.0, "odziez": 1.2, "obuwie": 0.8},
        keywords=["Hantle", "Kettlebell", "Sztangi", "Sprzęt", "białkowe",
                  "Kreatyna", "treningowe"],
        brands=["Olimp", "Trec", "BioTech USA", "Eb Fit", "Under Armour", "Bauer Fitness"],
        weight=1.4, gender_bias=0.30,
    ),
    Segment(
        "fitness", "Fitness & Joga",
        "Stawia na fitness, jogę i mobilność. Najczęściej kupuje maty, gumy "
        "oporowe i legginsy. Lubi marki {brands}.",
        dept={"silownia": 2.2, "odziez": 2.4, "akcesoria": 1.2, "obuwie": 1.0},
        keywords=["Maty", "Gumy", "Legginsy", "Koszulki", "fitness", "treningowe"],
        brands=["Domyos", "Manduka", "Reebok", "Adidas", "4F", "Nike"],
        weight=1.2, gender_bias=0.78,
    ),
    Segment(
        "pilkarz", "Piłkarz",
        "Gra w piłkę nożną — kompletuje korki, getry i piłki. Wierny markom {brands}.",
        dept={"obuwie": 2.6, "akcesoria": 1.8, "odziez": 1.6, "silownia": 0.4},
        keywords=["Korki", "piłkarskie", "Piłki", "Skarpety", "Koszulki", "Torby"],
        brands=["Nike", "Adidas", "Puma", "Select", "Mizuno"],
        weight=1.1, gender_bias=0.20,
    ),
    Segment(
        "koszykarz", "Koszykarz",
        "Koszykówka to jego żywioł — buty do kosza i piłki to podstawa. "
        "Najchętniej {brands}.",
        dept={"obuwie": 2.6, "akcesoria": 1.8, "odziez": 1.4},
        keywords=["koszykówki", "Piłki", "Koszulki", "Spodenki"],
        brands=["Nike", "Adidas", "Under Armour", "Wilson", "Spalding"],
        weight=0.8, gender_bias=0.25,
    ),
    Segment(
        "streetwear", "Streetwear",
        "Sport po godzinach — sneakersy, bluzy i klasyki na co dzień. "
        "Poluje na modele marek {brands}.",
        dept={"obuwie": 2.6, "odziez": 2.2, "akcesoria": 0.8},
        keywords=["Sneakersy", "Bluzy", "Kurtki", "Koszulki", "plecaki"],
        brands=["Nike", "Adidas", "New Balance", "Puma", "Champion", "Reebok"],
        weight=1.2, gender_bias=0.50,
    ),
    Segment(
        "outdoor", "Outdoor",
        "Góry i trening w terenie — buty trailowe, kurtki i plecaki. "
        "Ufa markom {brands}.",
        dept={"obuwie": 2.0, "odziez": 2.0, "akcesoria": 2.0, "silownia": 0.4},
        keywords=["trailowe", "Kurtki", "plecaki", "bidony", "Zegarki", "Torby"],
        brands=["Salomon", "Columbia", "The North Face", "Garmin", "Suunto", "Hoka"],
        weight=0.9, gender_bias=0.40,
    ),
    Segment(
        "suplementy", "Suplementacja",
        "Skupiony na regeneracji i diecie — odżywki, kreatyna i witaminy. "
        "Kupuje głównie {brands}.",
        dept={"akcesoria": 3.0, "silownia": 1.4, "odziez": 0.8},
        keywords=["białkowe", "Kreatyna", "Witaminy", "regeneracja", "pre-workout"],
        brands=["Olimp", "Trec", "BioTech USA", "KFD", "Now Foods", "Real Pharm"],
        weight=1.0, gender_bias=0.40,
    ),
    Segment(
        "okazjonalny", "Okazjonalny",
        "Kupuje rzadko i przekrojowo — głównie pod konkretną potrzebę lub prezent. "
        "Bez przywiązania do jednej marki.",
        dept={"obuwie": 1.0, "odziez": 1.0, "silownia": 1.0, "akcesoria": 1.0},
        keywords=[],
        brands=[],
        weight=1.4, gender_bias=0.50,
    ),
]


# --------------------------------------------------------------------------
# POZIOMY LOJALNOŚCI — jak często przychodzi i ile kupuje
#   orders:   (min, max) liczba zamówień w całym okresie
#   visits_per_order: ile wizyt na każde zamówienie (część bez zakupu)
#   span_days: (min, max) jak długo (wstecz) trwa aktywność klienta
# --------------------------------------------------------------------------
@dataclass
class Tier:
    key: str
    orders: tuple
    visits_per_order: tuple
    span_days: tuple
    weight: float


TIERS = [
    Tier("VIP",         orders=(14, 26), visits_per_order=(2.5, 4.5), span_days=(540, 760), weight=0.06),
    Tier("Stały",       orders=(8, 14),  visits_per_order=(2.0, 3.5), span_days=(400, 700), weight=0.16),
    Tier("Regularny",   orders=(4, 8),   visits_per_order=(2.0, 3.5), span_days=(250, 600), weight=0.34),
    Tier("Okazjonalny", orders=(2, 4),   visits_per_order=(2.5, 5.0), span_days=(120, 480), weight=0.28),
    Tier("Nowy",        orders=(1, 2),   visits_per_order=(2.0, 4.0), span_days=(7, 90),    weight=0.16),
]


# --------------------------------------------------------------------------
# SZABLONY CZATU — "co pisali w chatach"
#   Para (wiadomość klienta, odpowiedź obsługi). {p} -> nazwa produktu,
#   {brand} -> marka, {cat} -> kategoria (małymi literami).
# --------------------------------------------------------------------------
CHAT_TOPICS = {
    "dostawa": [
        ("Dzień dobry, kiedy mogę spodziewać się przesyłki z zamówieniem?",
         "Dzień dobry! Paczka jest już u kuriera — dostawa zwykle następnego dnia roboczego."),
        ("Czy zamówienie zdąży dotrzeć przed weekendem?",
         "Tak, przy nadaniu dziś powinno dotrzeć w piątek. Numer śledzenia wysłaliśmy mailem."),
        ("Nie dostałem jeszcze numeru do śledzenia paczki.",
         "Już sprawdzam — numer właśnie został wygenerowany i jest w drodze na Pana/Pani maila."),
    ],
    "rozmiar": [
        ("Czy {p} przymierzać normalnie, czy brać rozmiar większy?",
         "Ten model {brand} ma standardowy rozmiar — sugerujemy zostać przy swoim."),
        ("Mam wątpliwości co do rozmiaru w {cat}. Macie tabelę rozmiarów?",
         "Tak, tabela rozmiarów jest na karcie produktu — w razie wątpliwości polecamy rozmiar w górę."),
        ("Czy {p} jest dostępne w innym rozmiarze?",
         "Sprawdzę magazyn i wrócę z dostępnymi wariantami w ciągu kilku minut."),
    ],
    "dostepnosc": [
        ("Kiedy {p} wróci do sprzedaży?",
         "Spodziewamy się dostawy w przyszłym tygodniu — chętnie damy znać mailem, gdy będzie."),
        ("Czy planujecie uzupełnić stany na {cat}?",
         "Tak, kolejna dostawa jest w drodze. Można włączyć powiadomienie o dostępności."),
    ],
    "produkt": [
        ("Czy {p} nadaje się do codziennych treningów?",
         "Jak najbardziej — to jeden z naszych najczęściej wybieranych modeli do treningu."),
        ("Czym różni się {p} od poprzedniej wersji?",
         "Głównie lżejsza konstrukcja i lepsza amortyzacja — reszta parametrów zbliżona."),
        ("Szukam czegoś od {brand} do {cat}. Co polecacie?",
         "Mamy kilka świetnych opcji {brand} w tej kategorii — podeślę propozycje dopasowane do Pana/Pani potrzeb."),
    ],
    "promocja": [
        ("Czy na {p} szykuje się jakaś promocja?",
         "W tym tygodniu rusza akcja promocyjna — warto śledzić newsletter, żeby nie przegapić."),
        ("Mam kod rabatowy z newslettera, jak go użyć?",
         "Kod wpisuje się w koszyku przed złożeniem zamówienia — rabat naliczy się automatycznie."),
    ],
    "zwrot": [
        ("Chciałbym zwrócić {p} — jak to zrobić?",
         "Oczywiście. Wystarczy formularz zwrotu z maila; mamy 30 dni na zwrot bez podania przyczyny."),
        ("{p} okazało się za małe, czy mogę wymienić rozmiar?",
         "Tak, robimy wymianę rozmiaru bez dodatkowych kosztów — przygotuję etykietę zwrotną."),
    ],
    "platnosc": [
        ("Czy mogę zapłacić przy odbiorze?",
         "Tak, oferujemy płatność za pobraniem oraz BLIK i szybkie przelewy."),
        ("Płatność się nie zaksięgowała, a pieniądze pobrane.",
         "Już to weryfikujemy — jeśli środki nie wrócą w 24h, ręcznie potwierdzimy zamówienie."),
    ],
}


# --------------------------------------------------------------------------
# Pomocnicze
# --------------------------------------------------------------------------
def _ascii(text: str) -> str:
    """Usuwa polskie znaki do bezpiecznego adresu e-mail."""
    text = text.replace("ł", "l").replace("Ł", "L")
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _feminize(surname: str) -> str:
    for m, f in (("ski", "ska"), ("cki", "cka"), ("dzki", "dzka")):
        if surname.endswith(m):
            return surname[: -len(m)] + f
    return surname


def _weighted_choice(rng: random.Random, items, weight_attr="weight"):
    weights = [getattr(it, weight_attr) for it in items]
    return rng.choices(items, weights=weights, k=1)[0]


def product_affinity(profile: dict, product) -> float:
    """Jak bardzo dany produkt pasuje do klienta (waga przy losowaniu zakupów).

    Łączy zainteresowania (segment) z demografią klienta: płcią, wiekiem,
    zasobnością portfela i tym, czy ma dzieci. Dzięki temu zakupy nie są losowe
    — układają się w klastry zależne od cech klienta.

    product: obiekt/krotka z polami department(slug), category, brand, name oraz
    (opcjonalnie) price_band ∈ {"tani","sredni","drogi"} doklejone w seederze.
    """
    seg = SEG_BY_KEY[profile["segment_key"]]
    dept = getattr(product, "department_slug", None) or product.get("department")
    category = getattr(product, "category", None) or product.get("category") or ""
    brand = getattr(product, "brand", None) or product.get("brand") or ""
    name = getattr(product, "name", None) or product.get("name") or ""
    price_band = getattr(product, "price_band", None) or product.get("price_band") or "sredni"
    text = f"{category} {name}".lower()

    # --- baza: zainteresowania (segment) ---
    score = seg.dept.get(dept, 0.25)
    if any(kw.lower() in category.lower() for kw in seg.keywords):
        score *= 2.4
    if brand in seg.brands:
        score *= 2.0

    # --- PŁEĆ ---
    if profile["gender"] == "k":
        if any(h in text for h in _FEMALE_HINTS):
            score *= 1.5
        if any(h in text for h in _MALE_HINTS):
            score *= 0.7
    else:
        if any(h in text for h in _MALE_HINTS):
            score *= 1.4
        if any(h in text for h in _FEMALE_HINTS):
            score *= 0.8

    # --- WIEK ---
    ag = profile.get("age_group", "26-35")
    if ag in ("18-25", "26-35"):
        if any(h in text for h in _YOUNG_HINTS):
            score *= 1.5
        if any(h in text for h in _OLDER_HINTS):
            score *= 0.8
    elif ag in ("46-60", "60+"):
        if any(h in text for h in _OLDER_HINTS):
            score *= 1.5
        if any(h in text for h in _YOUNG_HINTS):
            score *= 0.6

    # --- ZASOBNOŚĆ (cena + marki premium/budżetowe) ---
    aff = profile.get("affluence", "średni")
    if aff in ("zamożny", "premium"):
        if price_band == "drogi":
            score *= 1.7 if aff == "premium" else 1.4
        if price_band == "tani":
            score *= 0.7
        if brand in _PREMIUM_BRANDS:
            score *= 1.4
    elif aff == "budżetowy":
        if price_band == "tani":
            score *= 1.6
        if price_band == "drogi":
            score *= 0.5
        if brand in _BUDGET_BRANDS:
            score *= 1.3

    # --- DZIECI / RODZINA ---
    if any(h in text for h in _KID_HINTS):
        if profile.get("household") in ("rodzina z dziećmi", "rodzina z nastolatkiem"):
            score *= 3.0
        else:
            score *= 0.2

    return max(score, 0.03)


# --------------------------------------------------------------------------
# MARKET BASKET — co kupuje się PARAMI
#   product_catkey() sprowadza produkt do klucza kategorii,
#   COMPLEMENTS planuje pary: anchor -> [(komplement, prawdopodobieństwo), ...].
#   To one sprawiają, że np. buty do biegania + spodenki, hantle + proteina,
#   korki + piłka pojawiają się razem znacznie częściej niż losowo.
# --------------------------------------------------------------------------
_CATKEY_TABLE = [
    ("biegania", "buty_bieg"), ("korki", "buty_pilka"), ("piłkarskie", "buty_pilka"),
    ("koszykówki", "buty_kosz"), ("trailowe", "buty_trail"),
    ("buty treningowe", "buty_tren"), ("sneakersy", "sneakersy"),
    ("koszulki", "koszulki"), ("spodenki", "spodenki"), ("legginsy", "legginsy"),
    ("bluzy", "bluzy"), ("kurtki", "kurtki"), ("skarpety", "skarpety"), ("bielizna", "skarpety"),
    ("hantle", "hantle"), ("kettlebell", "kettlebell"), ("sztangi", "sztangi"),
    ("maty", "maty"), ("gumy", "gumy"), ("sprzęt", "sprzet"),
    ("białkowe", "protein"), ("kreatyna", "kreatyna"), ("witaminy", "witaminy"),
    ("piłki", "pilki"), ("zegarki", "zegarki"), ("torby", "torby"),
]


def product_catkey(product) -> str:
    if isinstance(product, dict):
        cat = (product.get("category") or "").lower()
    else:
        cat = (getattr(product, "category", None) or "").lower()
    for kw, key in _CATKEY_TABLE:
        if kw in cat:
            return key
    return "inne"


COMPLEMENTS = {
    "buty_bieg":  [("spodenki", .60), ("koszulki", .50), ("skarpety", .50), ("zegarki", .35), ("witaminy", .25), ("torby", .20)],
    "buty_pilka": [("pilki", .60), ("skarpety", .55), ("koszulki", .40), ("spodenki", .30), ("torby", .30)],
    "buty_kosz":  [("pilki", .60), ("koszulki", .45), ("spodenki", .40), ("torby", .25)],
    "buty_trail": [("kurtki", .45), ("zegarki", .35), ("torby", .35), ("witaminy", .20)],
    "buty_tren":  [("koszulki", .50), ("spodenki", .45), ("protein", .35), ("hantle", .25)],
    "sneakersy":  [("bluzy", .50), ("koszulki", .40), ("torby", .30), ("spodenki", .25)],
    "hantle":     [("protein", .60), ("kreatyna", .45), ("koszulki", .35), ("maty", .30), ("spodenki", .30)],
    "kettlebell": [("protein", .55), ("kreatyna", .40), ("maty", .35), ("koszulki", .30)],
    "sztangi":    [("protein", .60), ("kreatyna", .45), ("sprzet", .30), ("koszulki", .25)],
    "sprzet":     [("hantle", .40), ("maty", .40), ("protein", .40), ("gumy", .30)],
    "maty":       [("legginsy", .60), ("gumy", .45), ("koszulki", .30), ("witaminy", .20)],
    "gumy":       [("maty", .50), ("legginsy", .40), ("koszulki", .30)],
    "legginsy":   [("maty", .45), ("koszulki", .45), ("bluzy", .30), ("gumy", .25)],
    "protein":    [("kreatyna", .60), ("witaminy", .30), ("hantle", .30), ("torby", .30)],
    "kreatyna":   [("protein", .60), ("witaminy", .35), ("hantle", .25)],
    "witaminy":   [("protein", .40), ("kreatyna", .30)],
    "pilki":      [("buty_pilka", .40), ("skarpety", .35), ("koszulki", .30), ("torby", .30)],
    "zegarki":    [("buty_bieg", .40), ("koszulki", .25), ("witaminy", .20)],
    "kurtki":     [("buty_trail", .35), ("torby", .30), ("bluzy", .25)],
    "koszulki":   [("spodenki", .50), ("skarpety", .30)],
    "spodenki":   [("koszulki", .50), ("skarpety", .30)],
    "bluzy":      [("sneakersy", .30), ("koszulki", .30)],
    "skarpety":   [("koszulki", .30)],
}


# --------------------------------------------------------------------------
# Główny generator profili
# --------------------------------------------------------------------------
def build_customers(count: int = 150, seed: int = 7) -> list[dict]:
    """Zwraca listę słowników-profili klientów (deterministycznie dla seeda)."""
    rng = random.Random(seed)
    customers: list[dict] = []
    used_emails: set[str] = set()

    for i in range(count):
        # --- WIEK (losowanie grupy, potem konkretny wiek) ---
        ag_labels, ag_ranges, ag_weights = zip(*[(a, r, w) for a, r, w in AGE_GROUPS])
        age_group = rng.choices(ag_labels, weights=ag_weights, k=1)[0]
        age_range = dict(zip(ag_labels, ag_ranges))[age_group]
        age = rng.randint(*age_range)

        # --- SEGMENT (ważony wiekiem) ---
        age_bias = AGE_SEGMENT_BIAS[age_group]
        adjusted_segs = []
        for s in SEGMENTS:
            w = s.weight * age_bias.get(s.key, 1.0)
            adjusted_segs.append((s, w))
        seg = rng.choices([x[0] for x in adjusted_segs],
                          weights=[x[1] for x in adjusted_segs], k=1)[0]

        # --- POZIOM LOJALNOŚCI ---
        tier = _weighted_choice(rng, TIERS)

        # --- PŁEĆ (bias z segmentu, ale lekko wyregulowany wiekiem) ---
        gender_p = seg.gender_bias
        if age_group == "60+" and seg.key == "silownia":
            gender_p = 0.40  # więcej kobiet w starszej grupie na siłowni
        is_female = rng.random() < gender_p
        gender = "k" if is_female else "m"

        # --- IMIĘ I NAZWISKO ---
        first = rng.choice(FIRST_F if is_female else FIRST_M)
        surname = rng.choice(SURNAMES)
        if is_female:
            surname = _feminize(surname)
        full_name = f"{first} {surname}"

        # --- E-MAIL (unikalny) ---
        base = f"{_ascii(first).lower()}.{_ascii(surname).lower()}"
        email = f"{base}@{rng.choice(EMAIL_DOMAINS)}"
        n = 1
        while email in used_emails:
            n += 1
            email = f"{base}{n}@{rng.choice(EMAIL_DOMAINS)}"
        used_emails.add(email)

        # --- MIASTO I ZASOBNOŚĆ ---
        city = rng.choice(CITIES)
        city_tier_key = CITY_TIER.get(city, "srednie")
        aff_weights = {}
        for a in AFFLUENCE:
            w = (AFFLUENCE_BASE[a]
                 * CITY_AFFLUENCE_MULT[city_tier_key][a]
                 * TIER_AFFLUENCE_MULT[tier.key][a])
            # wiek też koreluje: 18-25 rzadziej premium, 36-50 najczęściej
            if age_group == "18-25" and a == "premium":
                w *= 0.4
            if age_group in ("36-45", "46-60") and a in ("zamożny", "premium"):
                w *= 1.2
            if age_group == "60+" and a == "premium":
                w *= 0.7
            aff_weights[a] = max(w, 0.05)
        affluence = rng.choices(AFFLUENCE, weights=[aff_weights[a] for a in AFFLUENCE], k=1)[0]

        # --- GOSPODARSTWO DOMOWE ---
        hh_opts = HOUSEHOLD_BY_AGE[age_group]
        household = rng.choices([h for h, _ in hh_opts], weights=[w for _, w in hh_opts], k=1)[0]

        # --- OPIS ZAINTERESOWAŃ ---
        brands_pref = seg.brands[:3] if seg.brands else []
        summary = seg.summary.format(
            brands=" i ".join(brands_pref[:2]) if brands_pref else "różnych producentów"
        )
        # wzbogac opis o demografię
        demo_notes = []
        if household in ("rodzina z dziećmi", "rodzina z nastolatkiem"):
            demo_notes.append("Kupuje też produkty dla dzieci/nastolatków.")
        if affluence == "premium":
            demo_notes.append("Wybiera produkty premium, nie kieruje się ceną.")
        elif affluence == "budżetowy":
            demo_notes.append("Zwraca uwagę na ceny, preferuje produkty z dobrego stosunku jakości do ceny.")
        if age_group == "60+":
            demo_notes.append("Skupia się na komforcie i zdrowiu.")
        if demo_notes:
            summary += " " + " ".join(demo_notes)

        fav_dept = max(seg.dept, key=seg.dept.get)

        customers.append({
            "full_name": full_name,
            "email": email,
            "phone": f"{rng.choice(['50','51','53','60','66','69','72','78','79','88'])}{rng.randint(1000000, 9999999)}",
            "city": city,
            "gender": gender,
            "age": age,
            "age_group": age_group,
            "affluence": affluence,
            "household": household,
            "segment_key": seg.key,
            "segment": seg.label,
            "interest_summary": summary,
            "favorite_department": fav_dept,
            "favorite_brands": ",".join(brands_pref),
            "loyalty_tier": tier.key,
            "tier_key": tier.key,
            "newsletter": rng.random() < 0.6,
            "avatar_hue": rng.randint(0, 359),
        })

    return customers


SEG_BY_KEY = {s.key: s for s in SEGMENTS}
TIER_BY_KEY = {t.key: t for t in TIERS}


if __name__ == "__main__":
    from collections import Counter

    cs = build_customers(500)
    print(f"Wygenerowano {len(cs)} klientów")
    print("Segmenty:", dict(Counter(c["segment"] for c in cs)))
    print("Lojalność:", dict(Counter(c["loyalty_tier"] for c in cs)))
    print("Wiek:", dict(Counter(c["age_group"] for c in cs)))
    print("Zasobność:", dict(Counter(c["affluence"] for c in cs)))
    print("Gospodarstwo:", dict(Counter(c["household"] for c in cs)))
    print("Płeć:", dict(Counter(c["gender"] for c in cs)))
    print("Przykład:", cs[0]["full_name"], "·", cs[0]["segment"], "·",
          cs[0]["age_group"], "·", cs[0]["affluence"], "·", cs[0]["household"])
