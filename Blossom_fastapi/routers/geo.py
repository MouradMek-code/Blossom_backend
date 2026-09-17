import json
import os
import unicodedata
from functools import lru_cache

from fastapi import APIRouter, HTTPException, Query

# Country and city lists for the location picker, so people choose where they
# live instead of sharing their GPS position. Data: GeoNames (CC BY 4.0), built
# into data/geo/ by scripts/build_geo_data.py.
router = APIRouter(
    prefix="/geo",
    tags=["geo"],
)

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "geo")


def _fold(text: str) -> str:
    """Search key ignoring case, accents and punctuation: "São Paulo" -> "sao paulo",
    "Saint-Denis" -> "saint denis"."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    return " ".join("".join(ch if ch.isalnum() else " " for ch in text).split())


@lru_cache(maxsize=1)
def _countries():
    with open(os.path.join(_DATA_DIR, "countries.json"), encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _country_codes():
    return frozenset(c["code"] for c in _countries())


# Loaded per country on first use and kept in memory: a few countries' lists
# are small, and loading all 156k cities up front would waste RAM on Render.
@lru_cache(maxsize=48)
def _cities(code: str):
    with open(os.path.join(_DATA_DIR, "cities", f"{code}.json"), encoding="utf-8") as f:
        return tuple((name, _fold(name)) for name in json.load(f))


@router.get("/countries")
def list_countries():
    """Every country, alphabetically: [{"code": "FR", "name": "France"}, ...]."""
    return _countries()


@router.get("/cities")
def search_cities(
    country: str,
    q: str = "",
    limit: int = Query(20, ge=1, le=50),
):
    """Cities of a country matching what the user typed, biggest first.

    Names starting with the text come first, then names with a later word
    starting with it ("denis" -> "Saint-Denis"). With no text, the country's
    biggest cities are returned as suggestions.
    """
    code = (country or "").strip().upper()
    if code not in _country_codes():
        raise HTTPException(status_code=404, detail="Unknown country.")

    cities = _cities(code)
    query = _fold(q)
    if not query:
        return [name for name, _ in cities[:limit]]

    starts, words = [], []
    for name, folded in cities:
        if folded.startswith(query):
            starts.append(name)
            if len(starts) == limit:
                break
        elif len(words) < limit and f" {query}" in folded:
            words.append(name)
    return (starts + words)[:limit]
