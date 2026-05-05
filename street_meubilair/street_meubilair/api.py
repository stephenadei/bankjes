import frappe
from frappe import _

from street_meubilair.sync_all import TABLES

ALLOWED_DATASETS = {label for label, _path, _q in TABLES}
MAX_RADIUS_KM = 50.0
MAX_RESULTS = 5000


@frappe.whitelist()
def furniture_nearby(lat, lon, radius=1, type=None):
    """
    Retrieves street furniture items within a given radius of a location.
    Uses the Haversine formula for distance calculation.
    """
    if lat is None or lon is None:
        frappe.throw(_("Latitude and Longitude are required."))

    try:
        lat = float(lat)
        lon = float(lon)
        radius = float(radius)
    except (TypeError, ValueError):
        frappe.throw(_("Invalid coordinates or radius."))

    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        frappe.throw(_("Coordinates out of range."))
    if radius <= 0 or radius > MAX_RADIUS_KM:
        frappe.throw(_("Radius must be between 0 and {0} km.").format(MAX_RADIUS_KM))

    type_filter = ""
    sql_params = [lat, lon, lat, radius]
    if type:
        if type not in ALLOWED_DATASETS:
            frappe.throw(_("Unknown dataset type."))
        type_filter = " AND dataset = %s"
        sql_params.append(type)

    query = f"""
        SELECT name, dataset, latitude, longitude,
        (
            6371 * acos(
                cos(radians(%s)) * cos(radians(latitude))
                * cos(radians(longitude) - radians(%s))
                + sin(radians(%s)) * sin(radians(latitude))
            )
        ) AS distance
        FROM `tabStreet Furniture Item`
        HAVING distance < %s{type_filter}
        ORDER BY distance
        LIMIT {MAX_RESULTS}
    """

    return frappe.db.sql(query, sql_params, as_dict=True)
