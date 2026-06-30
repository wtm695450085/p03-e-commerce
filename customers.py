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
    """Jak bardzo dany produkt pasuje do klienta (do ważenia zakupów).

    product: obiekt/krotka z polami department(slug), category, brand.
    """
    seg = SEG_BY_KEY[profile["segment_key"]]
    dept = getattr(product, "department_slug", None) or product["department"]
    category = getattr(product, "category", None) or product["category"]
    brand = getattr(product, "brand", None) or product["brand"]

    score = seg.dept.get(dept, 0.25)
    if any(kw.lower() in (category or "").lower() for kw in seg.keywords):
        score *= 2.4
    if brand in seg.brands:
        score *= 2.0
    return max(score, 0.05)


# --------------------------------------------------------------------------
# Główny generator profili
# --------------------------------------------------------------------------
def build_customers(count: int = 150, seed: int = 7) -> list[dict]:
    """Zwraca listę słowników-profili klientów (deterministycznie dla seeda)."""
    rng = random.Random(seed)
    customers: list[dict] = []
    used_emails: set[str] = set()

    for i in range(count):
        seg = _weighted_choice(rng, SEGMENTS)
        tier = _weighted_choice(rng, TIERS)

        is_female = rng.random() < seg.gender_bias
        gender = "k" if is_female else "m"
        first = rng.choice(FIRST_F if is_female else FIRST_M)
        surname = rng.choice(SURNAMES)
        if is_female:
            surname = _feminize(surname)
        full_name = f"{first} {surname}"

        # unikalny e-mail
        base = f"{_ascii(first).lower()}.{_ascii(surname).lower()}"
        email = f"{base}@{rng.choice(EMAIL_DOMAINS)}"
        n = 1
        while email in used_emails:
            n += 1
            email = f"{base}{n}@{rng.choice(EMAIL_DOMAINS)}"
        used_emails.add(email)

        brands_pref = seg.brands[:3] if seg.brands else []
        summary = seg.summary.format(brands=" i ".join(brands_pref[:2]) if brands_pref else "różnych producentów")
        fav_dept = max(seg.dept, key=seg.dept.get)

        customers.append({
            "full_name": full_name,
            "email": email,
            "phone": f"{rng.choice(['50','51','53','60','66','69','72','78','79','88'])}{rng.randint(1000000, 9999999)}",
            "city": rng.choice(CITIES),
            "gender": gender,
            "age": rng.randint(18, 56),
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

    cs = build_customers()
    print(f"Wygenerowano {len(cs)} klientów")
    print("Segmenty:", dict(Counter(c["segment"] for c in cs)))
    print("Lojalność:", dict(Counter(c["loyalty_tier"] for c in cs)))
    print("Przykład:", cs[0]["full_name"], "·", cs[0]["segment"], "·", cs[0]["email"])
