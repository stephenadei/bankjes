#!/usr/bin/env python3
"""
Stephen's Bankjes - Live Amsterdam Street Furniture Explorer
Real-time data from Amsterdam APIs including BGT street benches
"""

import http.server
import socketserver
import json
import math
import webbrowser
import threading
import time
import requests
from concurrent.futures import ThreadPoolExecutor

def rd_to_wgs84(x, y):
    """Convert Dutch RD coordinates to WGS84 lat/lon"""
    # Simplified but working transformation for Netherlands region
    # Based on empirical validation with Amsterdam coordinates
    
    # Amsterdam-centered approximation
    # Dam Square RD: (121287, 487335) -> WGS84: (52.373, 4.893)
    
    # Linear approximation that works for Amsterdam area
    lat = 52.373 + (y - 487335) * 9e-6 + (x - 121287) * 3e-7
    lon = 4.893 + (x - 121287) * 1.5e-5 + (y - 487335) * 1e-7
    
    return lat, lon

def fetch_bgt_benches():
    """Fetch real street benches from Amsterdam BGT API"""
    benches = []
    
    try:
        print("🪑 Fetching real street benches from BGT...")
        
        # Start with first page, filtered for Amsterdam municipality (G0363)
        url = 'https://api.data.amsterdam.nl/v1/bgt/straatmeubilair/?plusType=bank&bronhouder=G0363&_pageSize=50'
        page_count = 0
        
        while url and page_count < 4:  # Limit to 4 pages max
            page_count += 1
            print(f"   📄 Fetching page {page_count}...")
            
            response = requests.get(url, timeout=15)
            if response.status_code != 200:
                print(f"   ❌ Page {page_count} failed: {response.status_code}")
                break
                
            data = response.json()
            page_benches = data.get('_embedded', {}).get('straatmeubilair', [])
            
            if not page_benches:
                print(f"   📄 Page {page_count}: No more benches")
                break
                
            print(f"   📄 Page {page_count}: +{len(page_benches)} benches")
            
            for bench in page_benches:
                # Extract coordinates
                geom = bench.get('geometrie', {})
                geom_punt = bench.get('geometriePunt', {})
                
                # Use point geometry if available, otherwise main geometry
                coords = None
                if geom_punt and 'coordinates' in geom_punt:
                    coords = geom_punt['coordinates']
                elif geom and 'coordinates' in geom:
                    if geom.get('type') == 'Point':
                        coords = geom['coordinates']
                    elif geom.get('type') == 'Polygon' and geom['coordinates']:
                        # Take first point of polygon
                        coords = geom['coordinates'][0][0] if geom['coordinates'][0] else None
                
                if coords and len(coords) >= 2:
                    # Convert RD to WGS84
                    rd_x, rd_y = coords[0], coords[1]
                    lat, lon = rd_to_wgs84(rd_x, rd_y)
                    
                    # Create bench entry
                    bench_data = {
                        'id': bench.get('identificatie', f'bench_{len(benches)}'),
                        'lat': lat,
                        'lon': lon,
                        'type': 'Street Bench',
                        'status': bench.get('bgtStatus', 'unknown'),
                        'installed': bench.get('objectBegintijd', 'unknown'),
                        'rd_coords': f"({rd_x:.0f}, {rd_y:.0f})",
                        'source': 'BGT API'
                    }
                    benches.append(bench_data)
            
            # Check for next page URL
            next_url = None
            if '_links' in data and 'next' in data['_links']:
                next_url = data['_links']['next']['href']
                print(f"   🔗 Next page: {next_url}")
            
            url = next_url  # Continue with next page or None to stop
            
            # If this page had fewer items than page size, we're also done
            if len(page_benches) < 50:
                print(f"   📄 Last page reached (fewer items)")
                break
                
    except Exception as e:
        print(f"❌ Error fetching BGT benches: {e}")
        # Return empty list if API fails
        return []
    
    print(f"✅ Fetched {len(benches)} real street benches from BGT")
    return benches

class LiveBankjesHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            
            html = '''
<!DOCTYPE html>
<html>
 <head>
     <meta charset="UTF-8">
     <meta name="viewport" content="width=device-width, initial-scale=1.0">
     <title>Stephen's Bankjes - LIVE Amsterdam Data</title>
     <link rel="stylesheet" href="https://unpkg.com/leaflet@1.7.1/dist/leaflet.css" />
    <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.0/dist/MarkerCluster.css" />
    <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.0/dist/MarkerCluster.Default.css" />
    <style>
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            margin: 0; 
            padding: 0; 
            background: #f5f5f5;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            text-align: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .header h1 {
            margin: 0;
            font-size: 2.5em;
            font-weight: 300;
        }
        .header p {
            margin: 10px 0 0 0;
            opacity: 0.9;
            font-size: 1.1em;
        }
        .live-indicator {
            background: #4CAF50;
            color: white;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.9em;
            display: inline-block;
            margin-top: 10px;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.7; }
            100% { opacity: 1; }
        }
        .container {
            display: flex;
            height: calc(100vh - 150px);
        }
        .sidebar {
            width: 320px;
            background: white;
            padding: 20px;
            box-shadow: 2px 0 5px rgba(0,0,0,0.1);
            overflow-y: auto;
        }
        .sidebar h3 {
            color: #333;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
        }
        .filter-group {
            margin: 15px 0;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 8px;
        }
        .filter-group label {
            display: block;
            margin: 8px 0;
            cursor: pointer;
            font-weight: 500;
        }
        .filter-group input[type="checkbox"] {
            margin-right: 8px;
            transform: scale(1.2);
        }
        .stats {
            background: #e3f2fd;
            padding: 15px;
            border-radius: 8px;
            margin: 15px 0;
        }
        .loading-stats {
            background: #fff3cd;
            padding: 15px;
            border-radius: 8px;
            margin: 15px 0;
        }
        .map-container {
            flex: 1;
            position: relative;
        }
        #map {
            height: 100%;
            width: 100%;
        }
        .loading {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            text-align: center;
            z-index: 1000;
        }
        .spinner {
            border: 4px solid #f3f3f3;
            border-top: 4px solid #667eea;
            border-radius: 50%;
            width: 30px;
            height: 30px;
            animation: spin 1s linear infinite;
            margin: 0 auto 10px auto;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        .refresh-btn {
            background: #667eea;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            cursor: pointer;
            font-weight: bold;
            margin: 10px 0;
            width: 100%;
        }
        .refresh-btn:hover {
            background: #5a6fd8;
        }
    </style>
</head>
<body>
    <div class="header">
                 <h1>&#x1FA91; Stephen's Bankjes</h1>
         <p>LIVE Amsterdam Street Furniture Data</p>
         <div class="live-indicator">&#x1F534; LIVE DATA</div>
    </div>
    
    <div class="container">
        <div class="sidebar">
                         <h3>&#x1F50D; Live Data Filters</h3>
             <div class="filter-group">
                                 <label><input type="checkbox" id="waste" checked> &#x1F5D1;&#xFE0F; Waste Containers</label>
                <label><input type="checkbox" id="bikes" checked> &#x1F6B2; Bike Poles</label>
                <label><input type="checkbox" id="street_benches" checked> &#x1FA91; Street Benches (BGT)</label>
                <label><input type="checkbox" id="sports_facility_benches" checked> &#x1F3C0; Sports Facility Benches</label>
             </div>
             
             <button class="refresh-btn" onclick="refreshData()">&#x1F504; Refresh Live Data</button>
            
            <div id="stats" class="loading-stats">
                                 <h4>&#x1F4CA; Loading Statistics...</h4>
                 <div>Fetching real Amsterdam data...</div>
             </div>
             
             <div class="filter-group">
                 <h4>&#x1F4E1; Data Sources</h4>
                 <div style="font-size: 0.9em;">
                     <div id="api-status-waste">&#x1F5D1;&#xFE0F; Waste: Loading...</div>
                     <div id="api-status-bikes">&#x1F6B2; Bikes: Loading...</div>
                     <div id="api-status-sports">&#x1FA91; Benches: Loading...</div>
                </div>
            </div>
            
            <div style="margin-top: 20px; font-size: 0.9em; color: #666;">
                                 <p><strong>Real Data From:</strong></p>
                 <ul>
                     <li>&#x1F3DB;&#xFE0F; data.amsterdam.nl</li>
                     <li>&#x1F4CD; Live coordinates</li>
                     <li>&#x1F504; Updated every refresh</li>
                 </ul>
            </div>
        </div>
        
        <div class="map-container">
            <div id="loading" class="loading">
                <div class="spinner"></div>
                <div>Loading LIVE Amsterdam data...</div>
            </div>
            <div id="map"></div>
        </div>
    </div>
    
    <script src="https://unpkg.com/leaflet@1.7.1/dist/leaflet.js"></script>
    <script src="https://unpkg.com/leaflet.markercluster@1.5.0/dist/leaflet.markercluster.js"></script>
    <script>
        let map;
        let markerGroups = {
            waste: L.markerClusterGroup(),
            bikes: L.markerClusterGroup(),
            street_benches: L.markerClusterGroup(),
            sports_facility_benches: L.markerClusterGroup()
        };
        
        // Initialize map
        function initMap() {
            map = L.map('map').setView([52.3676, 4.9041], 12);
            
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                maxZoom: 19,
                attribution: '© OpenStreetMap | Stephen\\'s Bankjes LIVE'
            }).addTo(map);
            
            // Load real data
            loadLiveData();
            
            // Setup filter controls
            setupFilters();
        }
        
        function loadLiveData() {
            document.getElementById('loading').style.display = 'block';
            
            // Fetch from our live API endpoint
            fetch('/api/live-data')
                .then(response => response.json())
                .then(data => {
                    console.log('Received live data:', data);
                    
                    // Clear existing markers
                    Object.values(markerGroups).forEach(group => group.clearLayers());
                    
                    // Add waste containers
                    if (data.waste) {
                        data.waste.forEach(item => {
                            if (item.lat && item.lon) {
                                const marker = L.marker([item.lat, item.lon], {
                                    icon: getIcon('waste')
                                });
                                                                 marker.bindPopup(`
                                     <b>&#x1F5D1;&#xFE0F; Waste Container</b><br>
                                     ID: ${item.id}<br>
                                     Status: ${item.status || 'Active'}<br>
                                     <small>Real Amsterdam data</small>
                                 `);
                                markerGroups.waste.addLayer(marker);
                            }
                        });
                                                 document.getElementById('api-status-waste').innerHTML = `&#x1F5D1;&#xFE0F; Waste: ${data.waste.length} items &#x2705;`;
                    }
                    
                    // Add bike poles
                    if (data.bikes) {
                        data.bikes.forEach(item => {
                            if (item.lat && item.lon) {
                                const marker = L.marker([item.lat, item.lon], {
                                    icon: getIcon('bikes')
                                });
                                                                 marker.bindPopup(`
                                     <b>&#x1F6B2; Bike Pole</b><br>
                                     ID: ${item.id}<br>
                                     Street: ${item.street || 'Unknown'}<br>
                                     <small>Real Amsterdam data</small>
                                 `);
                                markerGroups.bikes.addLayer(marker);
                            }
                        });
                                                 document.getElementById('api-status-bikes').innerHTML = `&#x1F6B2; Bikes: ${data.bikes.length} items &#x2705;`;
                    }
                    
                                        // Add street benches from BGT
                    if (data.street_benches) {
                        data.street_benches.forEach(item => {
                            if (item.lat && item.lon) {
                                const marker = L.marker([item.lat, item.lon], {
                                    icon: getIcon('street_benches')
                                });
                                marker.bindPopup(`
                                    <b>&#x1FA91; Street Bench</b><br>
                                    ID: ${item.id}<br>
                                    Type: ${item.type}<br>
                                    Status: ${item.status}<br>
                                    Installed: ${item.installed}<br>
                                    RD: ${item.rd_coords}<br>
                                    <small>Real BGT data</small>
                                `);
                                markerGroups.street_benches.addLayer(marker);
                            }
                        });
                    }
                    
                    // Add sports facility benches
                    if (data.sports_facility_benches) {
                        data.sports_facility_benches.forEach(item => {
                            if (item.lat && item.lon) {
                                const marker = L.marker([item.lat, item.lon], {
                                    icon: getIcon('sports_facility_benches')
                                });
                                marker.bindPopup(`
                                    <b>&#x1F3C0; Sports Facility Bench</b><br>
                                    ID: ${item.id}<br>
                                    Name: ${item.name || 'Sports Area'}<br>
                                    Info: ${item.description || 'Seating available'}<br>
                                    <small>Real Amsterdam sports data</small>
                                `);
                                markerGroups.sports_facility_benches.addLayer(marker);
                            }
                        });
                    }
                    
                    // Update API status
                    const streetBenchCount = data.street_benches ? data.street_benches.length : 0;
                    const sportsBenchCount = data.sports_facility_benches ? data.sports_facility_benches.length : 0;
                    document.getElementById('api-status-sports').innerHTML = `&#x1FA91; Benches: ${streetBenchCount + sportsBenchCount} items &#x2705;`;
                    
                    // Add all groups to map
                    Object.values(markerGroups).forEach(group => map.addLayer(group));
                    
                    // Update statistics
                    updateStats(data);
                    
                    document.getElementById('loading').style.display = 'none';
                })
                .catch(error => {
                    console.error('Error loading live data:', error);
                    document.getElementById('loading').style.display = 'none';
                    document.getElementById('stats').innerHTML = '<h4>❌ Error loading data</h4><div>Check console for details</div>';
                });
        }
        
        function getIcon(type) {
            const colors = {
                waste: '#FF9800',
                bikes: '#2196F3', 
                street_benches: '#8B4513',
                sports_facility_benches: '#E91E63'
            };
            
            const color = colors[type] || '#757575';
            return L.divIcon({
                className: 'custom-div-icon',
                html: `<div style="background-color:${color};width:16px;height:16px;border-radius:50%;border:2px solid white;box-shadow:0 2px 5px rgba(0,0,0,0.3);"></div>`,
                iconSize: [16, 16],
                iconAnchor: [8, 8]
            });
        }
        
        function setupFilters() {
            ['waste', 'bikes', 'street_benches', 'sports_facility_benches'].forEach(type => {
                document.getElementById(type).addEventListener('change', function() {
                    if (this.checked) {
                        map.addLayer(markerGroups[type]);
                    } else {
                        map.removeLayer(markerGroups[type]);
                    }
                });
            });
        }
        
                function updateStats(data) {
            const wasteCount = data.waste?.length || 0;
            const bikesCount = data.bikes?.length || 0;
            const streetBenchCount = data.street_benches?.length || 0;
            const sportsBenchCount = data.sports_facility_benches?.length || 0;
            const total = wasteCount + bikesCount + streetBenchCount + sportsBenchCount;
            
            const statsHtml = `
                <h4>&#x1F4CA; Live Statistics</h4>
                &#x1F5D1;&#xFE0F; Waste Containers: ${wasteCount.toLocaleString()}<br>
                &#x1F6B2; Bike Poles: ${bikesCount.toLocaleString()}<br>
                &#x1FA91; Street Benches (BGT): ${streetBenchCount.toLocaleString()}<br>
                &#x1F3C0; Sports Benches: ${sportsBenchCount.toLocaleString()}<br>
                <strong>Total: ${total.toLocaleString()}</strong><br>
                <small>Last updated: ${new Date().toLocaleTimeString()}</small>
            `;
            document.getElementById('stats').innerHTML = statsHtml;
            document.getElementById('stats').className = 'stats';
        }
        
        function refreshData() {
            loadLiveData();
        }
        
        // Initialize when page loads
        document.addEventListener('DOMContentLoaded', initMap);
    </script>
</body>
</html>
            '''
            self.wfile.write(html.encode())
            
        elif self.path == '/api/live-data':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            # Fetch real data from Amsterdam APIs
            try:
                data = fetch_amsterdam_data()
                self.wfile.write(json.dumps(data).encode())
            except Exception as e:
                error_response = {
                    'error': str(e),
                    'waste': [],
                    'bikes': [],
                    'street_benches': [],
                    'sports_facility_benches': []
                }
                self.wfile.write(json.dumps(error_response).encode())
        
        else:
            self.send_response(404)
            self.end_headers()

def fetch_amsterdam_data():
    """Fetch live data from Amsterdam APIs"""
    
    datasets = {
        'waste': {
            'url': 'https://api.data.amsterdam.nl/v1/huishoudelijkafval/container/',
            'icon': '&#x1F5D1;&#xFE0F;',
            'name': 'Waste Container'
        },
        'bikes': {
            'url': 'https://api.data.amsterdam.nl/v1/fietspaaltjes/fietspaaltjes/',
            'icon': '&#x1F6B2;',
            'name': 'Bike Pole'  
        },
        'sports_facility_benches': {
            'url': 'https://api.data.amsterdam.nl/v1/sport/openbaresportplek/',
            'icon': '&#x1F3C0;',
            'name': 'Sports Facility Bench'
        }
    }
    
    results = {}
    
    def fetch_dataset(name, config):
        """Fetch a single dataset with pagination"""
        items = []
        bench_keywords = ['zitbank', 'bank', 'bench', 'zit']
        
        try:
            print(f"📡 Fetching {name}...")
            
            # Determine page size based on dataset
            page_size = 200 if name == 'sports_facility_benches' else 100
            
            # Fetch up to 5 pages
            for page in range(5):
                url = f"{config['url']}?_pageSize={page_size}"
                if page > 0:
                    url += f"&page={page}"
                
                response = requests.get(url, timeout=15)
                if response.status_code != 200:
                    print(f"   ❌ {name} page {page} failed: {response.status_code}")
                    break
                
                data = response.json()
                
                # Handle different response formats
                page_items = []
                if '_embedded' in data:
                    embedded = data['_embedded']
                    if embedded:
                        key = next(iter(embedded.keys()))
                        page_items = embedded[key]
                elif 'features' in data:
                    page_items = data['features']
                elif 'results' in data:
                    page_items = data['results']
                
                if not page_items:
                    break
                
                print(f"   📄 Page {page}: {len(page_items)} items")
                
                # Process items
                for item in page_items:
                    processed = process_item(item, name, config)
                    if processed:
                        # Special filtering for sports benches
                        if name == 'sports_facility_benches':
                            # Check if description mentions benches
                            description = (processed.get('description', '') + ' ' + 
                                         processed.get('name', '')).lower()
                            
                            if any(keyword in description for keyword in bench_keywords):
                                processed['name'] = 'Bench Location'
                                processed['icon'] = '&#x1FA91;'
                                items.append(processed)
                        else:
                            items.append(processed)
                
                # Break if we got less than expected (last page)
                if len(page_items) < page_size:
                    break
                    
        except Exception as e:
            print(f"❌ Error fetching {name}: {e}")
        
        print(f"✅ {name}: {len(items)} items")
        return items
    
    # Fetch all datasets in parallel
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(fetch_dataset, name, config): name 
                  for name, config in datasets.items()}
        
        for future in futures:
            name = futures[future]
            try:
                results[name] = future.result()
            except Exception as e:
                print(f"❌ {name} failed: {e}")
                results[name] = []
    
    # Add real BGT street benches
    print("\n🪑 Adding real street benches from BGT...")
    results['street_benches'] = fetch_bgt_benches()
    
    return results

def process_item(item, dataset_type, config):
    """Process a single item from the API"""
    try:
        # Extract coordinates
        lat, lon = None, None
        
        if 'geometry' in item and item['geometry']:
            geom = item['geometry']
            if 'coordinates' in geom:
                coords = geom['coordinates']
                if len(coords) >= 2:
                    # Check if these are RD coordinates (typically > 100000)
                    if coords[0] > 100000 and coords[1] > 100000:
                        lat, lon = rd_to_wgs84(coords[0], coords[1])
                    else:
                        lon, lat = coords[0], coords[1]
        
        elif 'geometrie' in item and item['geometrie']:
            geom = item['geometrie']
            if isinstance(geom, dict) and 'coordinates' in geom:
                coords = geom['coordinates']
                if len(coords) >= 2:
                    if coords[0] > 100000 and coords[1] > 100000:
                        lat, lon = rd_to_wgs84(coords[0], coords[1])
                    else:
                        lon, lat = coords[0], coords[1]
        
        # Skip items without valid coordinates
        if not (lat and lon) or not (50 < lat < 55) or not (3 < lon < 8):
            return None
        
        # Extract basic info
        item_id = item.get('id', str(hash(str(item)))[:8])
        
        processed = {
            'id': item_id,
            'lat': lat,
            'lon': lon,
            'type': dataset_type
        }
        
        # Add dataset-specific fields
        if dataset_type == 'waste':
            processed.update({
                'status': item.get('status', 'unknown'),
                'owner': item.get('eigenaarNaam', 'Amsterdam')
            })
        elif dataset_type == 'bikes':
            processed.update({
                'street': item.get('street', 'Unknown'),
                'area': item.get('area', 'Amsterdam')
            })
        elif dataset_type == 'sports_facility_benches':
            # For sports facilities, highlight that they have benches
            description = item.get('omschrijving', '')
            processed.update({
                'name': item.get('naam', 'Sports Facility with Benches'),
                'facility': item.get('sportvoorziening', 'Unknown'),
                'description': description,
                'bench_info': 'Has benches/seating area'
            })
        
        return processed
        
    except Exception as e:
        return None

def open_browser():
    """Open browser after a short delay"""
    time.sleep(2)
    webbrowser.open('http://localhost:8080')

if __name__ == '__main__':
    server = socketserver.TCPServer(('localhost', 8080), LiveBankjesHandler)
    
    print('🪑 Stephen\'s Bankjes - LIVE DATA VERSION')
    print('=' * 45)
    print('🌐 Server running at http://localhost:8080')
    print('📡 Fetching REAL Amsterdam street furniture data!')
    print('⏹️  Press Ctrl+C to stop')
    print()
    
    # Open browser automatically
    browser_thread = threading.Thread(target=open_browser)
    browser_thread.daemon = True
    browser_thread.start()
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n👋 Stephen\'s Bankjes LIVE stopped')
        print('✅ Thanks for exploring REAL Amsterdam data!') 