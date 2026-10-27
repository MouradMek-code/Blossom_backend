"""Countries Blossom doesn't accept new members from (the app stays listed
everywhere on Google Play - this is enforced here, on the server, so neither
the app nor the website can get around it).

Not in the location picker's country list, and refused when a profile is
created or moved there. Members who already live there keep their account.
"""
import unicodedata

from fastapi import HTTPException

CLOSED_COUNTRY_CODES = frozenset({"IN"})
# The names a profile may carry (any language the clients use).
CLOSED_COUNTRY_NAMES = frozenset({"india", "inde", "indien", "bharat", "印度", "الهند"})


def _fold(value) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join("".join(ch for ch in text if not unicodedata.combining(ch)).lower().split())


def is_closed(country) -> bool:
    folded = _fold(country)
    return folded in CLOSED_COUNTRY_NAMES or folded.upper() in CLOSED_COUNTRY_CODES


def check_country(country):
    if is_closed(country):
        raise HTTPException(status_code=403, detail="Sorry, Blossom isn't available in your country yet.")
