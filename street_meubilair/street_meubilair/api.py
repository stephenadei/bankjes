
import frappe
from frappe import _

@frappe.whitelist()
def furniture_nearby(lat, lon, radius=1, type=None):
    """
    Retrieves street furniture items within a given radius of a location.
    Uses the Haversine formula for distance calculation.
    """
    if not lat or not lon:
        frappe.throw(_("Latitude and Longitude are required."))

    try:
        lat = float(lat)
        lon = float(lon)
        radius = float(radius)
    except ValueError:
        frappe.throw(_("Invalid coordinates or radius."))

    # Haversine formula for distance in km
    query = f"""
        SELECT name, dataset, latitude, longitude,
        (
            6371 * acos(
                cos(radians({lat})) * cos(radians(latitude))
                * cos(radians(longitude) - radians({lon}))
                + sin(radians({lat})) * sin(radians(latitude))
            )
        ) AS distance
        FROM `tabStreet Furniture Item`
        HAVING distance < {radius}
    """

    if type:
        query += f" AND dataset = '{type}'"

    query += " ORDER BY distance"

    return frappe.db.sql(query, as_dict=True) 