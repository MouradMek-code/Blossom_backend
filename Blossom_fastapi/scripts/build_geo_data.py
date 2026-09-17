"""Builds the country/city lists behind the location picker (routers/geo.py).

Source: GeoNames (https://www.geonames.org), licensed CC BY 4.0 - the apps
show a "City data © GeoNames" credit next to the picker.

To rebuild (e.g. once a year), download from
https://download.geonames.org/export/dump/ :
    cities1000.zip   (unzip it -> cities1000.txt: every place with 1,000+ people)
    countryInfo.txt
then, from Blossom_fastapi/:
    python scripts/build_geo_data.py <folder containing both files>

Writes:
    data/geo/countries.json   [{"code": "FR", "name": "France"}, ...] A-Z by name
    data/geo/cities/FR.json   ["Paris", "Marseille", ...] biggest first
"""
import json
import os
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(os.path.dirname(HERE), "data", "geo")

# profiles.city / profiles.country are VARCHAR(50).
MAX_NAME = 50


def fold(text):
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch)).lower().strip()


def main(source_dir):
    countries = {}
    with open(os.path.join(source_dir, "countryInfo.txt"), encoding="utf-8") as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            cols = line.rstrip("\n").split("\t")
            code, name, population = cols[0], cols[4], int(cols[7] or 0)
            # Uninhabited entries (Antarctica, Bouvet Island...) would be dead ends.
            if population > 0 and len(name) <= MAX_NAME:
                countries[code] = name

    # Per country: folded name -> (population, name). One entry per spelling,
    # keeping the biggest place: the profile only stores the name anyway.
    cities = {code: {} for code in countries}
    skipped = 0
    with open(os.path.join(source_dir, "cities1000.txt"), encoding="utf-8") as f:
        for line in f:
            cols = line.rstrip("\n").split("\t")
            name, code, population = cols[1].strip(), cols[8], int(cols[14] or 0)
            if code not in cities or not name or len(name) > MAX_NAME:
                skipped += 1
                continue
            key = fold(name)
            if key not in cities[code] or population > cities[code][key][0]:
                cities[code][key] = (population, name)

    # Countries with no towns at all are dissolved ones still listed by GeoNames
    # ("Netherlands Antilles", "Serbia and Montenegro") - leave them out.
    cities = {code: by_name for code, by_name in cities.items() if by_name}

    cities_dir = os.path.join(OUT_DIR, "cities")
    os.makedirs(cities_dir, exist_ok=True)
    for old in os.listdir(cities_dir):
        if old.endswith(".json"):
            os.remove(os.path.join(cities_dir, old))

    country_list = sorted(
        ({"code": code, "name": countries[code]} for code in cities),
        key=lambda c: fold(c["name"]),
    )
    with open(os.path.join(OUT_DIR, "countries.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(country_list, f, ensure_ascii=False, separators=(",", ":"))

    total = 0
    for code, by_name in cities.items():
        names = [name for _, name in sorted(by_name.values(), key=lambda p: (-p[0], fold(p[1])))]
        total += len(names)
        with open(os.path.join(OUT_DIR, "cities", f"{code}.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(names, f, ensure_ascii=False, separators=(",", ":"))

    print(f"{len(country_list)} countries, {total} cities written to {OUT_DIR} ({skipped} rows skipped)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
