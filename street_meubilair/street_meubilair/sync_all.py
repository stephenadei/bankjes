# street_meubilair/sync_all.py
import json
import time
from urllib.parse import urlencode

import frappe
import requests

BASE = "https://api.data.amsterdam.nl/v1"

# (label, dataset/table path, query params).
# Always requested as GeoJSON so the server reprojects RD → WGS84 (CRS84).
TABLES = [
    ("bench",            "bgt/straatmeubilair",                 {"plusType": "bank"}),
    ("picnic_table",     "bgt/straatmeubilair",                 {"plusType": "picknicktafel"}),
    ("trash_bin",        "huishoudelijkafval/containerlocatie", {}),
    ("bike_pole",        "fietspaaltjes/fietspaaltjes",         {}),
    ("sports_facility",  "sport/openbaresportplek",             {}),
]


def pull(url):
    while url:
        r = requests.get(url, timeout=30).json()
        for feat in r.get("features", []):
            yield feat
        # GeoJSON pagination: _links is a list with rel="next"
        next_url = None
        for link in r.get("_links") or []:
            if isinstance(link, dict) and link.get("rel") == "next":
                next_url = link.get("href")
                break
        url = next_url


def sync():
    for label, path, q in TABLES:
        params = dict(q)
        params["_format"] = "geojson"
        params["_pageSize"] = 1000
        url = f"{BASE}/{path}/?{urlencode(params)}"
        for feat in pull(url):
            geom = feat.get("geometry") or {}
            coords = geom.get("coordinates") if geom.get("type") == "Point" else None
            if not coords or len(coords) < 2:
                continue
            lon, lat = coords[0], coords[1]

            props = feat.get("properties") or {}
            item_id = (
                feat.get("id")
                or props.get("identificatie")
                or props.get("id")
            )
            if not item_id:
                continue

            doc = frappe.get_doc({
                "doctype": "Street Furniture Item",
                "external_id": str(item_id),
                "dataset": label,
                "latitude": lat,
                "longitude": lon,
                "material": (
                    props.get("materiaal")
                    or props.get("material")
                    or props.get("soortOndergrond")
                ),
                "status": (
                    props.get("status")
                    or props.get("bgtStatus")
                    or props.get("mutatietype")
                    or "unknown"
                ),
                "last_inspection": (
                    props.get("datumControle")
                    or props.get("datumLaatsteMelding")
                    or props.get("datumCreatie")
                    or props.get("tijdstipRegistratie")
                ),
                "raw_json": json.dumps(feat),
            })
            doc.insert(
                ignore_permissions=True,
                ignore_mandatory=True,
                ignore_links=True,
                ignore_if_duplicate=True,
            )
        frappe.db.commit()
        time.sleep(1)  # polite pause
