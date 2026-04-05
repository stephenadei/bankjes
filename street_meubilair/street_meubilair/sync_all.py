
# street_meubilair/sync_all.py
import requests, frappe, json, time
BASE = "https://api.data.amsterdam.nl/v1"

# Map dataset → table → optional filter params
TABLES = {
    "huishoudelijkafval": ("containerlocatie", {}),  # Waste containers
    "fietspaaltjes": ("fietspaaltjes", {}),           # Bike poles  
    "sport": ("openbaresportplek", {}),               # Sports facilities (may include benches)
}

def pull(url):
    while url:
        r = requests.get(url, timeout=30).json()
        
        # Handle different response formats:
        # 1. HAL format (_embedded with dataset name)
        if "_embedded" in r:
            embedded = r["_embedded"]
            # Get the first (and usually only) embedded collection
            items = next(iter(embedded.values())) if embedded else []
        # 2. GeoJSON format (features)
        elif "features" in r:
            items = r["features"]
        # 3. Standard format (results)
        else:
            items = r.get("results", [])
        
        yield from items
        
        # Handle pagination - check both _links.next and next
        url = r.get("next")
        if not url and "_links" in r and "next" in r["_links"]:
            url = r["_links"]["next"]["href"]

def sync():
    for ds, (tbl, q) in TABLES.items():
        params = "&".join(f"{k}={v}" for k, v in q.items()) if q else ""
        url = f"{BASE}/{ds}/{tbl}/?{params}&_pageSize=1000"
        for row in pull(url):
            # Extract coordinates from different formats
            lat, lon = None, None
            
            # Try different geometry field names and formats
            if "geometry" in row and "coordinates" in row["geometry"]:
                # GeoJSON format
                coords = row["geometry"]["coordinates"]
                lon, lat = coords[0], coords[1]
            elif "geometrie" in row and row["geometrie"]:
                # Dutch format - may need coordinate transformation
                geom = row["geometrie"]
                if isinstance(geom, dict) and "coordinates" in geom:
                    coords = geom["coordinates"]
                    lon, lat = coords[0], coords[1]
                # Note: These might be RD coordinates, need transformation
            
            # Skip items without valid coordinates
            if not (lat and lon):
                continue
                
            # Extract ID
            item_id = (row.get("id") or 
                      row.get("_id") or 
                      row.get("identificatie") or 
                      str(hash(str(row)))[:10])
            
            # Create document
            doc = frappe.get_doc({
                "doctype": "Street Furniture Item",
                "external_id": str(item_id),
                "dataset": ds,  # Use dataset name instead of type
                "latitude": lat,
                "longitude": lon,
                "material": (row.get("materiaal") or 
                           row.get("material") or 
                           row.get("soortOndergrond")),
                "status": (row.get("status") or 
                          row.get("mutatietype") or 
                          "unknown"),
                "last_inspection": (row.get("datumControle") or 
                                  row.get("datumLaatsteMelding") or 
                                  row.get("datumCreatie")),
                "raw_json": json.dumps(row),
            })
            doc.insert(ignore_permissions=True, ignore_mandatory=True, ignore_links=True, ignore_if_duplicate=True)
        frappe.db.commit()
        time.sleep(1)  # polite pause 