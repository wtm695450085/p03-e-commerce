"""
Generator placeholderów produktów w formacie SVG.

Tworzy estetyczne, brandowane kafle (ikona kategorii + marka + nazwa)
w kolorze działu. Brak zewnętrznych zależności — gotowe do podmiany
na prawdziwe zdjęcia produktów w przyszłości (wystarczy podać URL/plik).
"""
from __future__ import annotations

import html

# Uproszczone, rozpoznawalne ikony (białe linie) wyśrodkowane w obszarze ~140x140.
ICONS = {
    "shoe": (
        '<path d="M60 150 q0 -28 22 -34 q14 -4 26 6 l30 24 q10 8 24 9 l40 4 '
        'q22 2 22 18 v9 H60 Z" fill="white" opacity="0.95"/>'
        '<path d="M96 130 l18 14 M120 134 l16 12 M144 140 l14 9" '
        'stroke="rgba(0,0,0,.18)" stroke-width="4" fill="none"/>'
    ),
    "shirt": (
        '<path d="M120 58 l-30 14 -22 26 18 18 16 -12 v66 q0 6 6 6 h64 q6 0 6 -6 '
        'v-66 l16 12 18 -18 -22 -26 -30 -14 q-18 14 -36 0 Z" fill="white" opacity="0.95"/>'
    ),
    "dumbbell": (
        '<g fill="white" opacity="0.95">'
        '<rect x="56" y="92" width="20" height="56" rx="5"/>'
        '<rect x="76" y="104" width="14" height="32" rx="4"/>'
        '<rect x="90" y="112" width="60" height="16" rx="6"/>'
        '<rect x="150" y="104" width="14" height="32" rx="4"/>'
        '<rect x="164" y="92" width="20" height="56" rx="5"/></g>'
    ),
    "kettlebell": (
        '<path d="M120 64 q-22 0 -22 22 q0 8 6 14 q-26 12 -26 44 q0 32 42 32 '
        'q42 0 42 -32 q0 -32 -26 -44 q6 -6 6 -14 q0 -22 -22 -22 Z M120 76 '
        'q10 0 10 12 q0 12 -10 12 q-10 0 -10 -12 q0 -12 10 -12 Z" fill="white" opacity="0.95"/>'
    ),
    "mat": (
        '<g fill="white" opacity="0.95">'
        '<rect x="62" y="86" width="116" height="68" rx="10"/>'
        '<circle cx="74" cy="120" r="20" fill="rgba(0,0,0,.18)"/>'
        '<rect x="62" y="86" width="14" height="68" rx="7" fill="rgba(0,0,0,.12)"/></g>'
    ),
    "band": (
        '<g fill="none" stroke="white" stroke-width="12" opacity="0.95" stroke-linecap="round">'
        '<path d="M84 90 q-22 30 0 60"/><path d="M156 90 q22 30 0 60"/>'
        '<path d="M84 90 h72 M84 150 h72"/></g>'
    ),
    "supplement": (
        '<g fill="white" opacity="0.95">'
        '<rect x="78" y="92" width="84" height="68" rx="10"/>'
        '<rect x="92" y="74" width="56" height="22" rx="6"/>'
        '<rect x="92" y="116" width="56" height="20" rx="5" fill="rgba(0,0,0,.16)"/></g>'
    ),
    "ball": (
        '<circle cx="120" cy="118" r="46" fill="white" opacity="0.95"/>'
        '<path d="M120 72 v92 M74 118 h92 M88 86 l64 64 M152 86 l-64 64" '
        'stroke="rgba(0,0,0,.18)" stroke-width="4" fill="none"/>'
    ),
    "watch": (
        '<g fill="white" opacity="0.95">'
        '<rect x="96" y="70" width="48" height="22" rx="6"/>'
        '<rect x="96" y="146" width="48" height="22" rx="6"/>'
        '<rect x="86" y="88" width="68" height="62" rx="16"/></g>'
        '<path d="M120 104 v18 h14" stroke="rgba(0,0,0,.22)" stroke-width="5" '
        'fill="none" stroke-linecap="round"/>'
    ),
    "bag": (
        '<g fill="none" stroke="white" stroke-width="9" opacity="0.95" '
        'stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M96 86 q24 -16 48 0"/>'  # górny pałąk (uchwyt)
        '<path d="M82 104 q0 -22 38 -22 q38 0 38 22 v54 q0 14 -14 14 H96 q-14 0 -14 -14 Z" '
        'fill="white"/>'
        '<path d="M104 140 q16 -10 32 0 v22 H104 Z" fill="rgba(0,0,0,.18)" stroke="none"/>'
        '<path d="M120 104 v14" stroke="rgba(0,0,0,.18)"/></g>'
    ),
}


def _shorten(text: str, limit: int = 26) -> str:
    text = text.split(" – ")[0]
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _lighten(hex_color: str, factor: float = 0.55) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    r = int(r + (255 - r) * factor)
    g = int(g + (255 - g) * factor)
    b = int(b + (255 - b) * factor)
    return f"#{r:02x}{g:02x}{b:02x}"


def product_svg(product) -> str:
    """Zwraca string SVG dla danego produktu (obiekt ORM lub dict)."""
    get = (lambda k: getattr(product, k)) if not isinstance(product, dict) else product.get
    color = get("color") or "#2D6CDF"
    icon_key = get("icon") or "ball"
    brand = html.escape((get("brand") or "").upper())
    name = html.escape(_shorten(get("name") or ""))
    category = html.escape(get("category") or "")
    icon = ICONS.get(icon_key, ICONS["ball"])
    light = _lighten(color, 0.30)

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 300" role="img" aria-label="{name}">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{light}"/>
      <stop offset="1" stop-color="{color}"/>
    </linearGradient>
    <pattern id="stripes" width="26" height="26" patternUnits="userSpaceOnUse" patternTransform="rotate(35)">
      <rect width="26" height="26" fill="none"/>
      <rect width="9" height="26" fill="rgba(255,255,255,0.06)"/>
    </pattern>
  </defs>
  <rect width="240" height="300" fill="url(#g)"/>
  <rect width="240" height="300" fill="url(#stripes)"/>
  <text x="20" y="34" font-family="Arial, sans-serif" font-size="13" font-weight="800"
        letter-spacing="1.5" fill="rgba(255,255,255,0.92)">{brand}</text>
  <g transform="translate(0,46) scale(1)">{icon}</g>
  <rect x="0" y="232" width="240" height="68" fill="rgba(0,0,0,0.18)"/>
  <text x="20" y="258" font-family="Arial, sans-serif" font-size="15" font-weight="700"
        fill="#ffffff">{name}</text>
  <text x="20" y="280" font-family="Arial, sans-serif" font-size="11"
        fill="rgba(255,255,255,0.8)">{category}</text>
</svg>"""
