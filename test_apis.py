#!/usr/bin/env python3
"""
API Testing Script for Amsterdam Street Furniture Explorer
Tests both demo API and real Amsterdam data APIs
"""

import requests
import json
import sys
from datetime import datetime

def test_demo_api():
    """Test the local demo API"""
    print("🔍 Testing Demo API...")
    
    try:
        # Test if demo server is running
        response = requests.get("http://localhost:8080/api/demo", timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Demo API is working!")
            print(f"   Status: {data.get('status')}")
            print(f"   Message: {data.get('message')}")
            return True
        else:
            print(f"❌ Demo API returned status code: {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ Demo server is not running")
        print("   Start it with: ./run_dev.sh")
        return False
    except Exception as e:
        print(f"❌ Demo API error: {e}")
        return False

def test_amsterdam_apis():
    """Test the real Amsterdam data APIs"""
    print("\n🏛️ Testing Amsterdam Open Data APIs...")
    
    # The API endpoints from our sync script
    endpoints = {
        "BRT10 (Benches/Furniture)": "https://api.data.amsterdam.nl/v1/brt10/inrichtingselementen/?soort_object==Zitbank&_format=geojson&_page_size=5",
        "Household Waste": "https://api.data.amsterdam.nl/v1/huishoudelijkafval/containerlocatie/?_format=geojson&_page_size=5",
        "Public Lighting": "https://api.data.amsterdam.nl/v1/storingsmeldingen_openbare_verlichting_en_klokken/openbareVerlichting/?_format=geojson&_page_size=5",
        "Bike Poles": "https://api.data.amsterdam.nl/v1/fietspaaltjes/fietspaaltjes/?_format=geojson&_page_size=5",
        "Sports (Benches)": "https://api.data.amsterdam.nl/v1/sport/openbaresportplek/?type==bank&_format=geojson&_page_size=5"
    }
    
    results = {}
    
    for name, url in endpoints.items():
        print(f"\n   Testing {name}...")
        try:
            response = requests.get(url, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                # Check if it's valid GeoJSON
                if 'features' in data or 'results' in data:
                    count = len(data.get('features', data.get('results', [])))
                    print(f"   ✅ {name}: {count} items found")
                    
                    # Show sample data structure
                    if count > 0:
                        sample = data.get('features', data.get('results', []))[0]
                        if 'geometry' in sample and 'coordinates' in sample['geometry']:
                            coords = sample['geometry']['coordinates']
                            print(f"      Sample location: {coords[1]:.4f}, {coords[0]:.4f}")
                        
                        # Show available properties
                        if 'properties' in sample:
                            props = list(sample['properties'].keys())[:5]
                            print(f"      Available fields: {', '.join(props)}")
                    
                    results[name] = {"status": "success", "count": count}
                else:
                    print(f"   ⚠️  {name}: Unexpected data format")
                    results[name] = {"status": "unexpected_format", "count": 0}
                    
            else:
                print(f"   ❌ {name}: HTTP {response.status_code}")
                if response.status_code == 404:
                    print(f"      URL might have changed: {url}")
                results[name] = {"status": "error", "code": response.status_code}
                
        except requests.exceptions.Timeout:
            print(f"   ⏱️  {name}: Request timed out")
            results[name] = {"status": "timeout"}
        except requests.exceptions.ConnectionError:
            print(f"   🌐 {name}: Connection error")
            results[name] = {"status": "connection_error"}
        except Exception as e:
            print(f"   ❌ {name}: {e}")
            results[name] = {"status": "error", "error": str(e)}
    
    return results

def test_sync_script():
    """Test our sync script logic"""
    print("\n🔄 Testing Sync Script Logic...")
    
    try:
        # Import our sync module
        import sys
        import os
        sys.path.append('street_meubilair')
        
        from street_meubilair.sync_all import TABLES, pull
        
        print("✅ Sync script imports successfully")
        print(f"   Configured datasets: {len(TABLES)}")
        
        for dataset, (table, filters) in TABLES.items():
            print(f"   - {dataset}/{table}")
            if filters:
                print(f"     Filters: {filters}")
        
        # Test the pull function with a small dataset
        print("\n   Testing data pull function...")
        test_url = "https://api.data.amsterdam.nl/v1/brt10/inrichtingselementen/?soort_object==Zitbank&_format=geojson&_page_size=2"
        
        try:
            items = list(pull(test_url))
            print(f"   ✅ Pull function works: got {len(items)} items")
            
            if items:
                sample = items[0]
                if 'geometry' in sample and 'coordinates' in sample['geometry']:
                    print(f"   ✅ GeoJSON structure is correct")
                else:
                    print(f"   ⚠️  Missing geometry data")
                    
        except Exception as e:
            print(f"   ❌ Pull function error: {e}")
            
        return True
        
    except ImportError as e:
        print(f"❌ Cannot import sync script: {e}")
        return False
    except Exception as e:
        print(f"❌ Sync script test error: {e}")
        return False

def main():
    """Run all API tests"""
    print("🧪 Amsterdam Street Furniture Explorer - API Tests")
    print("=" * 55)
    print(f"Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Test 1: Demo API
    demo_ok = test_demo_api()
    
    # Test 2: Amsterdam APIs
    amsterdam_results = test_amsterdam_apis()
    
    # Test 3: Sync script
    sync_ok = test_sync_script()
    
    # Summary
    print("\n📊 TEST SUMMARY")
    print("=" * 55)
    
    if demo_ok:
        print("✅ Demo API: Working")
    else:
        print("❌ Demo API: Not working")
    
    amsterdam_success = sum(1 for r in amsterdam_results.values() if r.get('status') == 'success')
    total_amsterdam = len(amsterdam_results)
    print(f"🏛️  Amsterdam APIs: {amsterdam_success}/{total_amsterdam} working")
    
    if sync_ok:
        print("✅ Sync Script: Working")
    else:
        print("❌ Sync Script: Has issues")
    
    # Recommendations
    print("\n💡 RECOMMENDATIONS")
    print("=" * 55)
    
    if not demo_ok:
        print("• Start the demo server: ./run_dev.sh")
    
    if amsterdam_success < total_amsterdam:
        print("• Some Amsterdam APIs may have changed - check the official documentation")
        print("• Consider adding API key if required by new policies")
    
    if amsterdam_success > 0:
        print(f"• {amsterdam_success} data sources are working - you can proceed with development!")
    
    print("• Full Frappe setup will provide complete functionality")

if __name__ == "__main__":
    main() 