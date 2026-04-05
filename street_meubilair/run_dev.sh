#!/bin/bash

echo "🚀 Amsterdam Street Furniture Explorer - Quick Start"
echo "=================================================="

# Check if we're in the right directory
if [ ! -f "manifest.json" ]; then
    echo "❌ Please run this script from the street_meubilair directory"
    exit 1
fi

echo "📦 Installing Python dependencies..."
pip3 install frappe requests

echo "🎯 Creating a simple demo server..."
python3 -c "
import json
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse as urlparse

class DemoHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            html = '''
<!DOCTYPE html>
<html>
<head>
    <title>Amsterdam Street Furniture Explorer</title>
    <link rel=\"stylesheet\" href=\"https://unpkg.com/leaflet@1.7.1/dist/leaflet.css\" />
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; }
        #map { height: 500px; width: 100%; border: 1px solid #ccc; }
        .info { background: #f0f0f0; padding: 15px; margin-bottom: 20px; border-radius: 5px; }
        .loading { text-align: center; padding: 50px; }
    </style>
</head>
<body>
    <div class=\"info\">
        <h1>🏛️ Amsterdam Street Furniture Explorer</h1>
        <p>This is a demo showing Amsterdam street furniture data from the city\'s open data APIs.</p>
        <p><strong>Data sources:</strong> Benches, trash bins, bike poles, lighting, and waste containers</p>
    </div>
    
    <div id=\"map\">
        <div class=\"loading\">🗺️ Loading Amsterdam street furniture data...</div>
    </div>
    
    <script src=\"https://unpkg.com/leaflet@1.7.1/dist/leaflet.js\"></script>
    <script>
        // Initialize map centered on Amsterdam
        var map = L.map(\"map\").setView([52.3676, 4.9041], 13);
        
        L.tileLayer(\"https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png\", {
            maxZoom: 19,
            attribution: \"© OpenStreetMap contributors\"
        }).addTo(map);
        
        // Add some sample markers to show the concept
        var sampleData = [
            {name: \"Central Station Bench\", lat: 52.379189, lon: 4.899431, type: \"bench\"},
            {name: \"Dam Square Trash Bin\", lat: 52.3731, lon: 4.8924, type: \"trash\"},
            {name: \"Vondelpark Bench\", lat: 52.3579, lon: 4.8686, type: \"bench\"},
            {name: \"Museum Quarter Bike Pole\", lat: 52.3598, lon: 4.8810, type: \"bike_pole\"}
        ];
        
        sampleData.forEach(function(item) {
            var marker = L.marker([item.lat, item.lon]).addTo(map);
            marker.bindPopup(\"<b>\" + item.name + \"</b><br>Type: \" + item.type);
        });
        
        // Show instructions
        var popup = L.popup()
            .setLatLng([52.3676, 4.9041])
            .setContent(\"<b>Demo Mode</b><br>This shows sample data. To get live data, set up the full Frappe application.\")
            .openOn(map);
    </script>
</body>
</html>
            '''
            self.wfile.write(html.encode())
            
        elif self.path == '/api/demo':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            # Demo API response
            response = {
                'status': 'demo',
                'message': 'This is a demo. Install full Frappe app for live data.',
                'sample_endpoints': [
                    '/api/method/street_meubilair.api.furniture_nearby',
                    '/api/method/frappe.client.get_list'
                ]
            }
            self.wfile.write(json.dumps(response).encode())
        
        else:
            self.send_response(404)
            self.end_headers()

if __name__ == '__main__':
    server = HTTPServer(('localhost', 8080), DemoHandler)
    print('🌐 Demo server running at http://localhost:8080')
    print('📍 View the interactive map to see the concept!')
    print('⏹️  Press Ctrl+C to stop')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n👋 Demo server stopped')
"

echo "✅ Done! The demo should have opened in your browser." 