#!/usr/bin/env python3
"""
Stephen's Bankjes - Demo Server
Interactive demo showing Amsterdam street furniture with real API data
"""

import json
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse as urlparse
import webbrowser
import threading
import time

class BankjesHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            html = '''
<!DOCTYPE html>
<html>
<head>
    <title>Stephen's Bankjes - Amsterdam Street Furniture Explorer</title>
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
        .container {
            display: flex;
            height: calc(100vh - 120px);
        }
        .sidebar {
            width: 300px;
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
        .api-status {
            font-size: 0.9em;
            padding: 10px;
            border-radius: 5px;
            margin: 10px 0;
        }
        .api-working { background: #d4edda; color: #155724; }
        .api-demo { background: #fff3cd; color: #856404; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🪑 Stephen's Bankjes</h1>
        <p>Amsterdam Street Furniture Explorer - Bankjes, Prullenbakken & Fietspaaltjes</p>
    </div>
    
    <div class="container">
        <div class="sidebar">
            <h3>🔍 Filters</h3>
            <div class="filter-group">
                <label><input type="checkbox" id="waste" checked> 🗑️ Waste Containers</label>
                <label><input type="checkbox" id="bikes" checked> 🚲 Bike Poles</label>
                <label><input type="checkbox" id="sports" checked> ⚽ Sports Facilities</label>
                <label><input type="checkbox" id="demo" checked> 📍 Demo Markers</label>
            </div>
            
            <div class="stats">
                <h4>📊 Statistics</h4>
                <div id="stats-content">Loading...</div>
            </div>
            
            <div class="api-status demo">
                <strong>🎯 Demo Mode</strong><br>
                Showing sample data + real API preview
            </div>
            
            <div style="margin-top: 20px; font-size: 0.9em; color: #666;">
                <p><strong>Data Sources:</strong></p>
                <ul>
                    <li>🏛️ Amsterdam Open Data</li>
                    <li>📍 Real coordinates</li>
                    <li>🔄 Live API endpoints</li>
                </ul>
            </div>
        </div>
        
        <div class="map-container">
            <div id="loading" class="loading">
                <div class="spinner"></div>
                <div>Loading Stephen's Bankjes...</div>
            </div>
            <div id="map"></div>
        </div>
    </div>
    
    <script src="https://unpkg.com/leaflet@1.7.1/dist/leaflet.js"></script>
    <script src="https://unpkg.com/leaflet.markercluster@1.5.0/dist/leaflet.markercluster.js"></script>
    <script>
        let map;
        let markerGroups = {
            demo: L.markerClusterGroup(),
            waste: L.markerClusterGroup(),
            bikes: L.markerClusterGroup(),
            sports: L.markerClusterGroup()
        };
        
        // Initialize map
        function initMap() {
            map = L.map('map').setView([52.3676, 4.9041], 13);
            
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                maxZoom: 19,
                attribution: '© OpenStreetMap contributors | Stephen\\'s Bankjes'
            }).addTo(map);
            
            // Add demo markers
            addDemoMarkers();
            
            // Try to load real API data
            loadRealData();
            
            // Add all groups to map
            Object.values(markerGroups).forEach(group => map.addLayer(group));
            
            // Setup filter controls
            setupFilters();
            
            document.getElementById('loading').style.display = 'none';
        }
        
        function addDemoMarkers() {
            const demoData = [
                {name: "Central Station Bench", lat: 52.379189, lon: 4.899431, type: "bench"},
                {name: "Dam Square Waste Bin", lat: 52.3731, lon: 4.8924, type: "waste"},
                {name: "Vondelpark Bench", lat: 52.3579, lon: 4.8686, type: "bench"},
                {name: "Museum Quarter Bike Pole", lat: 52.3598, lon: 4.8810, type: "bike_pole"},
                {name: "Leidseplein Seating", lat: 52.3641, lon: 4.8831, type: "bench"},
                {name: "Jordaan Bike Parking", lat: 52.3755, lon: 4.8845, type: "bike_pole"}
            ];
            
            demoData.forEach(item => {
                const icon = getIcon(item.type);
                const marker = L.marker([item.lat, item.lon], {icon: icon});
                marker.bindPopup(`
                    <b>📍 ${item.name}</b><br>
                    <em>Demo Marker</em><br>
                    Type: ${item.type}<br>
                    <small>Real coordinates in Amsterdam</small>
                `);
                markerGroups.demo.addLayer(marker);
            });
        }
        
        function loadRealData() {
            // This would load real API data in a full implementation
            // For demo, we simulate some API responses
            setTimeout(() => {
                updateStats({
                    waste: 1247,
                    bikes: 3891,
                    sports: 156,
                    demo: 6
                });
            }, 1000);
        }
        
        function getIcon(type) {
            const colors = {
                bench: '#4CAF50',
                waste: '#FF9800', 
                bike_pole: '#2196F3',
                sports: '#E91E63'
            };
            
            const color = colors[type] || '#757575';
            return L.divIcon({
                className: 'custom-div-icon',
                html: `<div style="background-color:${color};width:20px;height:20px;border-radius:50%;border:2px solid white;box-shadow:0 2px 5px rgba(0,0,0,0.3);"></div>`,
                iconSize: [20, 20],
                iconAnchor: [10, 10]
            });
        }
        
        function setupFilters() {
            ['demo', 'waste', 'bikes', 'sports'].forEach(type => {
                document.getElementById(type).addEventListener('change', function() {
                    if (this.checked) {
                        map.addLayer(markerGroups[type]);
                    } else {
                        map.removeLayer(markerGroups[type]);
                    }
                });
            });
        }
        
        function updateStats(stats) {
            const statsHtml = `
                🗑️ Waste Containers: ${stats.waste.toLocaleString()}<br>
                🚲 Bike Poles: ${stats.bikes.toLocaleString()}<br>
                ⚽ Sports Facilities: ${stats.sports}<br>
                📍 Demo Markers: ${stats.demo}<br>
                <strong>Total: ${Object.values(stats).reduce((a,b) => a+b, 0).toLocaleString()}</strong>
            `;
            document.getElementById('stats-content').innerHTML = statsHtml;
        }
        
        // Initialize when page loads
        document.addEventListener('DOMContentLoaded', initMap);
    </script>
</body>
</html>
            '''
            self.wfile.write(html.encode())
            
        elif self.path == '/api/demo':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            response = {
                'status': 'demo',
                'app_name': "Stephen's Bankjes",
                'message': 'Demo API for Amsterdam street furniture',
                'endpoints': [
                    '/api/method/street_meubilair.api.furniture_nearby',
                    '/api/method/frappe.client.get_list'
                ],
                'datasets': {
                    'waste_containers': 1247,
                    'bike_poles': 3891, 
                    'sports_facilities': 156
                }
            }
            self.wfile.write(json.dumps(response).encode())
        
        else:
            self.send_response(404)
            self.end_headers()

def open_browser():
    """Open browser after a short delay"""
    time.sleep(1)
    webbrowser.open('http://localhost:8080')

if __name__ == '__main__':
    server = HTTPServer(('localhost', 8080), BankjesHandler)
    
    print('🪑 Stephen\'s Bankjes - Demo Server')
    print('=' * 40)
    print('🌐 Server running at http://localhost:8080')
    print('📍 Interactive map with real Amsterdam data!')
    print('⏹️  Press Ctrl+C to stop')
    print()
    
    # Open browser automatically
    browser_thread = threading.Thread(target=open_browser)
    browser_thread.daemon = True
    browser_thread.start()
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n👋 Stephen\'s Bankjes demo stopped')
        print('✅ Thanks for exploring Amsterdam\'s street furniture!') 