"""Shared helpers for the Polyamide Index.

The Polyamide Index is a "Big Mac index" for one identical Zara garment: the
FINE STRAP POLYAMIDE T-SHIRT (reference 3905/532/800, colour Black). The same
physical product is sold in ~65 countries; comparing its price worldwide in a
single currency (USD) isolates what changes between markets — local operating
costs, global logistics, import duties/tariffs and VAT, and local margin.

This module holds the pieces every layer needs: project paths, config loading,
country metadata (name / region / flag / currency symbol) and a live USD FX
fetch (open.er-api.com — free, no key, USD base, market rates). Nothing here
touches the network or the DB at import time.
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

# --------------------------------------------------------------------- paths
ROOT = Path(__file__).resolve().parent
CONFIG_DIR = ROOT / "config"
OUTPUT_DIR = ROOT / "output"
SETTINGS_FILE = CONFIG_DIR / "settings.json"

FX_URL = "https://open.er-api.com/v6/latest/{base}"   # 1 <base> = rates[CCY] units


# ------------------------------------------------------------------- config
def load_settings() -> dict:
    """Read config/settings.json and resolve the two external paths (Zara DB +
    Zara email.ini) to absolute paths relative to the project root."""
    cfg = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    for key in ("zara_db", "zara_email_ini"):
        p = Path(cfg[key])
        cfg[key] = str(p if p.is_absolute() else (ROOT / p).resolve())
    return cfg


# ---------------------------------------------------------------------- FX
def fetch_rates(base: str = "EUR", timeout: int = 40) -> tuple[dict[str, float], str]:
    """Live market rates for a chosen base currency. Returns (rates, as-of date).

    rates[CCY] = how many units of CCY equal 1 <base>, so a local price converts
    to the base currency as  value = price_local / rates[local_ccy].
    """
    with urllib.request.urlopen(FX_URL.format(base=base.upper()), timeout=timeout) as r:
        d = json.load(r)
    if d.get("result") != "success":
        raise RuntimeError(f"FX source returned result={d.get('result')!r}")
    rates = {k: float(v) for k, v in d["rates"].items()}
    rates[base.upper()] = 1.0
    return rates, d.get("time_last_update_utc", "")


# ------------------------------------------------------- country metadata
# cc -> (display name, region). Regions group the ranked chart the way The
# Economist groups its Big Mac table.
_COUNTRY = {
    "al": ("Albania", "Europe"), "at": ("Austria", "Europe"),
    "be": ("Belgium", "Europe"), "ba": ("Bosnia & Herz.", "Europe"),
    "bg": ("Bulgaria", "Europe"), "hr": ("Croatia", "Europe"),
    "cy": ("Cyprus", "Europe"), "cz": ("Czech Rep.", "Europe"),
    "dk": ("Denmark", "Europe"), "ee": ("Estonia", "Europe"),
    "fi": ("Finland", "Europe"), "fr": ("France", "Europe"),
    "de": ("Germany", "Europe"), "gr": ("Greece", "Europe"),
    "hu": ("Hungary", "Europe"), "is": ("Iceland", "Europe"),
    "ie": ("Ireland", "Europe"), "it": ("Italy", "Europe"),
    "lv": ("Latvia", "Europe"), "lt": ("Lithuania", "Europe"),
    "lu": ("Luxembourg", "Europe"), "mt": ("Malta", "Europe"),
    "me": ("Montenegro", "Europe"), "nl": ("Netherlands", "Europe"),
    "mk": ("North Macedonia", "Europe"), "no": ("Norway", "Europe"),
    "pl": ("Poland", "Europe"), "pt": ("Portugal", "Europe"),
    "ro": ("Romania", "Europe"), "rs": ("Serbia", "Europe"),
    "sk": ("Slovakia", "Europe"), "si": ("Slovenia", "Europe"),
    "es": ("Spain", "Europe"), "se": ("Sweden", "Europe"),
    "ch": ("Switzerland", "Europe"), "tr": ("Turkey", "Europe"),
    "ua": ("Ukraine", "Europe"), "uk": ("United Kingdom", "Europe"),
    "ca": ("Canada", "Americas"), "us": ("United States", "Americas"),
    "mx": ("Mexico", "Americas"), "br": ("Brazil", "Americas"),
    "ar": ("Argentina", "Americas"), "cl": ("Chile", "Americas"),
    "co": ("Colombia", "Americas"), "pe": ("Peru", "Americas"),
    "uy": ("Uruguay", "Americas"),
    "ae": ("UAE", "Middle East & Africa"), "sa": ("Saudi Arabia", "Middle East & Africa"),
    "qa": ("Qatar", "Middle East & Africa"), "kw": ("Kuwait", "Middle East & Africa"),
    "bh": ("Bahrain", "Middle East & Africa"), "om": ("Oman", "Middle East & Africa"),
    "jo": ("Jordan", "Middle East & Africa"), "lb": ("Lebanon", "Middle East & Africa"),
    "eg": ("Egypt", "Middle East & Africa"), "il": ("Israel", "Middle East & Africa"),
    "ma": ("Morocco", "Middle East & Africa"), "tn": ("Tunisia", "Middle East & Africa"),
    "za": ("South Africa", "Middle East & Africa"),
    "cn": ("China", "Asia-Pacific"), "jp": ("Japan", "Asia-Pacific"),
    "kr": ("South Korea", "Asia-Pacific"), "in": ("India", "Asia-Pacific"),
    "sg": ("Singapore", "Asia-Pacific"), "my": ("Malaysia", "Asia-Pacific"),
    "id": ("Indonesia", "Asia-Pacific"), "ph": ("Philippines", "Asia-Pacific"),
    "th": ("Thailand", "Asia-Pacific"), "vn": ("Vietnam", "Asia-Pacific"),
    "tw": ("Taiwan", "Asia-Pacific"), "hk": ("Hong Kong", "Asia-Pacific"),
    "mo": ("Macau", "Asia-Pacific"), "kz": ("Kazakhstan", "Asia-Pacific"),
    "au": ("Australia", "Asia-Pacific"), "nz": ("New Zealand", "Asia-Pacific"),
}

# Zara uses "uk"; the flag codepoints need ISO "gb".
_FLAG_CC = {"uk": "gb"}

_CCY_SYMBOL = {
    "EUR": "€", "USD": "$", "GBP": "£", "JPY": "¥", "CNY": "¥",
    "CHF": "CHF ", "AUD": "A$", "CAD": "C$", "HKD": "HK$", "SGD": "S$",
    "KRW": "₩", "INR": "₹", "THB": "฿", "PHP": "₱",
    "TRY": "₺", "ILS": "₪", "VND": "₫", "MXN": "$",
}


def country_name(cc: str) -> str:
    return _COUNTRY.get(cc, (cc.upper(), "Other"))[0]


def country_region(cc: str) -> str:
    return _COUNTRY.get(cc, (cc.upper(), "Other"))[1]


def flag_emoji(cc: str) -> str:
    """Regional-indicator flag emoji from a 2-letter code (uk -> gb)."""
    code = _FLAG_CC.get(cc, cc).lower()
    if len(code) != 2 or not code.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(ch) - ord("a")) for ch in code)


def currency_symbol(ccy: str) -> str:
    """Display symbol for a currency (falls back to the ISO code + space)."""
    return _CCY_SYMBOL.get(ccy.upper(), ccy.upper() + " ")


def money(amount: float, currency: str) -> str:
    """Human local-price label, e.g. '€8.95', '$14.90', '89 CNY'."""
    sym = _CCY_SYMBOL.get(currency)
    if amount >= 1000:
        body = f"{amount:,.0f}"
    elif amount == int(amount):
        body = f"{amount:.0f}"
    else:
        body = f"{amount:.2f}"
    if sym:
        return f"{sym}{body}" if not sym.endswith(" ") else f"{sym}{body}"
    return f"{body} {currency}"
