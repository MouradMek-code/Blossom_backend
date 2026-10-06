"""Where each date spot is, for the map (lat / lng).

  1. Most Google Maps links carry the position: "!3d48.85!4d2.35" (the place
     itself) or "@48.85,2.35,17z" (the map around it). Short share links
     (maps.app.goo.gl) are opened first to read the full address.
  2. Otherwise the place is looked up by name and city on OpenStreetMap
     (Nominatim: free, at most one request a second). A result more than
     50 km from the city is ignored - a café with the same name elsewhere.
  3. Not found: no pin. The spot stays in the list; pasting a better Maps link
     puts it on the map.

`geo_key` remembers what a position was worked out from (link, name, city,
country). Whatever changes one of them - an edit, a partner request, an
import - the background job (every 10 minutes) works the spot out again.
"""
import hashlib
import logging
import math
import re
import threading
import time
from urllib.parse import parse_qs, unquote_plus, urlparse

import requests
from sqlalchemy.orm import Session

from database.models import DbDateSpot

NOMINATIM = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "BlossomDate/1.0 (+https://blossom-date.com)"
MAX_KM_FROM_CITY = 50
SPOTS_PER_RUN = 40

log = logging.getLogger(__name__)

_PLACE_PIN = re.compile(r"!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)")
_MAP_CENTRE = re.compile(r"@(-?\d+\.\d+),(-?\d+\.\d+)")
_PAIR = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*\+?(-?\d+(?:\.\d+)?)\s*$")
_PATH_PAIR = re.compile(r"/maps/(?:place|search|dir)/(?:[^/]*/)*?(-?\d+\.\d+),\s*\+?(-?\d+\.\d+)")


def _valid(lat, lng):
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180) or (lat == 0 and lng == 0):
        return None
    return round(lat, 6), round(lng, 6)


def coords_from_url(url: str):
    """(lat, lng) written in a Google Maps address, or None."""
    if not url:
        return None
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    if params.get("continue"):  # Google's consent page wraps the real address
        return coords_from_url(params["continue"][0])
    found = _PLACE_PIN.search(url)
    if found:
        return _valid(*found.groups())
    for key in ("q", "query", "ll", "center", "destination", "daddr"):
        for value in params.get(key, []):
            pair = _PAIR.match(value)
            if pair:
                return _valid(*pair.groups())
    found = _PATH_PAIR.search(unquote_plus(parsed.path))
    if found:
        return _valid(*found.groups())
    found = _MAP_CENTRE.search(url)
    if found:
        return _valid(*found.groups())
    return None


def km_between(a, b):
    lat1, lng1, lat2, lng2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


# ---- OpenStreetMap -----------------------------------------------------------------

class LookupFailed(Exception):
    """OpenStreetMap didn't answer (down, too busy): try again on the next run
    rather than recording "not found"."""


_lock = threading.Lock()
_last_call = [0.0]
_city_centres = {}


def _nominatim(query: str):
    """First result for a free-text search, or None when there's none. One
    request a second at most, from every thread together (Nominatim's rule)."""
    with _lock:
        wait = 1.1 - (time.monotonic() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.monotonic()
        try:
            resp = requests.get(
                NOMINATIM,
                params={"q": query, "format": "jsonv2", "limit": 1},
                headers={"User-Agent": USER_AGENT, "Accept-Language": "en"},
                timeout=10,
            )
        except requests.RequestException as exc:
            raise LookupFailed(str(exc))
    if resp.status_code != 200:
        raise LookupFailed(f"HTTP {resp.status_code}")
    try:
        results = resp.json()
    except ValueError:
        raise LookupFailed("not JSON")
    if not results:
        return None
    return _valid(results[0].get("lat"), results[0].get("lon"))


def city_centre(city: str, country: str):
    key = ((city or "").lower(), (country or "").lower())
    if key not in _city_centres:
        _city_centres[key] = _nominatim(f"{city}, {country}") if city else None
    return _city_centres[key]


def geocode(name, city, country, neighborhood=None, address=None):
    """The place on OpenStreetMap, checked to be in (or near) its city."""
    queries = []
    if address:
        queries.append(f"{name}, {address}")
    if neighborhood:
        queries.append(f"{name}, {neighborhood}, {city}, {country}")
    queries.append(f"{name}, {city}, {country}")
    centre = city_centre(city, country)
    for query in dict.fromkeys(queries):  # no duplicates, same order
        found = _nominatim(query)
        if found and (centre is None or km_between(found, centre) <= MAX_KM_FROM_CITY):
            return found
    return None


# ---- spots ------------------------------------------------------------------------

def geo_key(spot: DbDateSpot) -> str:
    raw = "|".join(str(v or "").strip().lower() for v in (spot.map_url, spot.name, spot.city, spot.country))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def locate(spot: DbDateSpot):
    """(lat, lng) for a spot, or None. Network calls; no database writes."""
    # Imported here: the router imports this module.
    from routers.date_spot import _expand_short_link, _place_from_url

    address = None
    if spot.map_url:
        full = _expand_short_link(spot.map_url)
        found = coords_from_url(full)
        if found:
            return found
        _, address = _place_from_url(full)
    return geocode(spot.name, spot.city, spot.country, spot.neighborhood, address)


def locate_spot(db: Session, spot: DbDateSpot) -> bool:
    key = geo_key(spot)
    found = locate(spot)
    # Edited while we were looking: the next run starts again.
    db.refresh(spot)
    if geo_key(spot) != key:
        return False
    spot.lat, spot.lng = found if found else (None, None)
    spot.geo_key = key
    db.commit()
    return found is not None


def locate_pending(db: Session, limit: int = SPOTS_PER_RUN):
    """Background job: spots never located, or changed since."""
    rows = db.query(DbDateSpot).order_by(DbDateSpot.id.desc()).all()
    todo = [spot for spot in rows if spot.geo_key != geo_key(spot)][:limit]
    located = 0
    for spot in todo:
        try:
            located += locate_spot(db, spot)
        except Exception as exc:  # one bad spot never stops the others
            db.rollback()
            log.warning("Locating spot %s failed: %s", spot.id, exc)
    if todo:
        log.info("Spot positions: %s/%s located", located, len(todo))
    return located


def locate_spot_id(spot_id: int):
    """Right after a spot is added or edited (a background task), so its pin
    shows without waiting for the job."""
    from database.database import SessionLocal

    db = SessionLocal()
    try:
        spot = db.get(DbDateSpot, spot_id)
        if spot and spot.geo_key != geo_key(spot):
            locate_spot(db, spot)
    except Exception as exc:
        log.warning("Locating spot %s failed: %s", spot_id, exc)
    finally:
        db.close()
