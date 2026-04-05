
import frappe
from unittest import TestCase

class TestSync(TestCase):
    def test_sync_brings_new_items(self):
        before = frappe.db.count("Street Furniture Item")
        # This will be a slow test if the network is slow
        # Consider mocking the requests.get call in the future
        frappe.get_attr("street_meubilair.sync_all.sync")()
        after = frappe.db.count("Street Furniture Item")
        self.assertTrue(after >= before)

    def test_nearby_filter(self):
        # Create two items approximately 50m apart
        # Amsterdam Central Station
        lat1, lon1 = 52.379189, 4.899431
        # Dam Square
        lat2, lon2 = 52.3731, 4.8924
        
        frappe.get_doc({
            "doctype": "Street Furniture Item",
            "external_id": "test_item_1",
            "latitude": lat1,
            "longitude": lon1
        }).insert(ignore_if_duplicate=True)

        frappe.get_doc({
            "doctype": "Street Furniture Item",
            "external_id": "test_item_2",
            "latitude": lat2,
            "longitude": lon2
        }).insert(ignore_if_duplicate=True)
        
        frappe.db.commit()

        from street_meubilair.api import furniture_nearby
        
        # Search in a 100m radius from the first point
        nearby_items = furniture_nearby(lat=lat1, lon=lon1, radius=0.1)
        self.assertEqual(len(nearby_items), 1)
        self.assertEqual(nearby_items[0]['name'], 'test_item_1')

        # Search in a 1km radius
        nearby_items = furniture_nearby(lat=lat1, lon=lon1, radius=1)
        self.assertEqual(len(nearby_items), 2) 