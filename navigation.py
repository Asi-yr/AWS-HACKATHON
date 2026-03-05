from shapely.geometry import LineString
import requests
import math
import json
import os

def geocode_location(address):
    if "," in address and all(c.isdigit() or c in " .-" for c in address):
        try:
            parts = address.split(",")
            return float(parts[1].strip()), float(parts[0].strip())
        except ValueError:
            pass 
    url = f"https://nominatim.openstreetmap.org/search?q={address}&format=json&limit=1&countrycodes=ph"
    headers = {'User-Agent': 'SafeRoute-Flask-App/1.0'}
    try:
        resp = requests.get(url, headers=headers, timeout=10).json()
        if resp and len(resp) > 0:
            return float(resp[0]['lon']), float(resp[0]['lat'])
    except Exception as e:
        print(f"Geocoding Error: {e}")
    return None, None

def get_train_route_geometry(commuter_type, orig_lat, orig_lon, dest_lat, dest_lon):
    # Ensure it looks in the correct folder
    file_path = os.path.join("transit_data", "metro_manila_trains.json")
    
    if not os.path.exists(file_path):
        return None

    with open(file_path, 'r') as f:
        data = json.load(f)

    # Search for the line that matches the commuter_type
    for line in data:
        if commuter_type.lower() in line['line_name'].lower():
            # Extract coordinates
            path = [[s['lat'], s['lon']] for s in line['stops']]
            return path
            
    return None

def get_navigation_data(orig_lon, orig_lat, dest_lon, dest_lat, commuter_type, flood_zones):
    processed_routes = []
    
    # Check if the user is asking for a train
    is_train = "train" in commuter_type.lower() or "lrt" in commuter_type.lower() or "mrt" in commuter_type.lower()

    if is_train:
        coords = get_train_route_geometry(commuter_type, orig_lat, orig_lon, dest_lat, dest_lon)
        
        if coords:
            processed_routes.append({
                "name": f"{commuter_type} Line",
                "duration": 1800, # Mock duration
                "distance": 15000, # Mock distance
                "coords": coords, # This uses the JSON coordinates directly
                "safety_score": 95
            })
        else:
            return {"error": "Train line data not found or not mapped."}
            
    else:
        # --- OSRM Logic for Cars/Jeepneys/Buses ---
        headers = {'User-Agent': 'SafeRouteAI_Final_Year_Project_v1', 'Accept': 'application/json'}
        osrm_url = f"https://router.project-osrm.org/route/v1/driving/{orig_lon},{orig_lat};{dest_lon},{dest_lat}?overview=full&geometries=geojson&alternatives=true&steps=true"
        
        try:
            response = requests.get(osrm_url, headers=headers, timeout=10).json()
            if response.get("code") != "Ok":
                return {"error": "Could not calculate route via OSRM."}
                
            for i, r in enumerate(response.get("routes", [])[:3]):
                coords_lonlat = r["geometry"]["coordinates"]
                coords_latlon = [[pt[1], pt[0]] for pt in coords_lonlat]
                
                processed_routes.append({
                    "name": f"Route {i+1}",
                    "duration": r["duration"],
                    "distance": r["distance"],
                    "coords": coords_latlon,
                    "safety_score": 80
                })
        except Exception as e:
            return {"error": f"OSRM Error: {str(e)}"}

    # Format the final list
    final_output = []
    for i, r in enumerate(processed_routes):
        final_output.append({
            "id": i,
            "name": r["name"],
            "color": ["#3498db", "#f1c40f", "#2ecc71"][i] if i < 3 else "#95a5a6",
            "time": f"{int(r['duration'] / 60)} mins",
            "distance": f"{round(r['distance'] / 1000, 1)} km",
            "coords": r["coords"],
            "safety_score": r["safety_score"],
            "hazards_flagged": "Clear"
        })

    return {"routes": final_output}