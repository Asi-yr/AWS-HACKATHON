import requests
from shapely.geometry import LineString

def geocode_location(address):
    # If the address is just coordinates (fallback), handle that
    if "," in address and any(char.isdigit() for char in address):
        # Optional: logic to detect if it's already a coord string
        pass 

    url = f"https://nominatim.openstreetmap.org/search?q={address}&format=json&limit=1&countrycodes=ph"
    headers = {'User-Agent': 'SafeRouteAI_v2'}
    
    try:
        resp = requests.get(url, headers=headers, timeout=10).json()
        if resp:
            return float(resp[0]['lon']), float(resp[0]['lat'])
    except Exception as e:
        print(f"Geocoding Error: {e}")
    return None, None

def get_navigation_data(orig_lon, orig_lat, dest_lon, dest_lat, commuter_type, flood_zones):
    """
    Fetches routes from OSRM, calculates safety scores, and generates Turn-By-Turn navigation steps.
    """
    
    # Set a timeout and a specific User-Agent to prevent the server from dropping the connection
    headers = {
        'User-Agent': 'SafeRouteAI_Final_Year_Project_v1',
        'Accept': 'application/json'
    }
    
    # Precise OSRM URL
    osrm_url = f"https://router.project-osrm.org/route/v1/driving/{orig_lon},{orig_lat};{dest_lon},{dest_lat}?overview=full&geometries=geojson&alternatives=true&steps=true"
    
    try:
        # Added timeout=10 to prevent hanging
        response = requests.get(osrm_url, headers=headers, timeout=10)
        route_resp = response.json()
    except requests.exceptions.Timeout:
        return {"error": "The routing server is taking too long. Please try again."}
    except Exception as e:
        print(f"OSRM Error: {e}")
        return {"error": "Could not connect to the routing engine."}

    if route_resp.get("code") != "Ok":
        return {"error": f"Routing Error: {route_resp.get('message', 'Unknown Error')}"}

    if route_resp.get("code") != "Ok":
        return {"error": "Could not calculate a route between these points."}

    processed_routes = []
    colors =["#3498db", "#f1c40f", "#2ecc71"]
    names =["Fastest Route", "Alternative 1", "Alternative 2"]
    risk_multiplier = {"tricycle": 3.0, "car": 1.5, "jeepney": 1.0}.get(commuter_type, 1.0)

    for i, r in enumerate(route_resp.get("routes",[])[:3]):
        coords_lonlat = r["geometry"]["coordinates"]
        coords_latlon = [[pt[1], pt[0]] for pt in coords_lonlat]
        line = LineString(coords_lonlat)
        
        # --- 1. EVALUATE FLOOD SAFETY ---
        flood_intersection_length = 0
        for zone in flood_zones:
            if line.intersects(zone["polygon"]):
                intersection = line.intersection(zone["polygon"])
                flood_intersection_length += intersection.length

        hazard_penalty = flood_intersection_length * 5000 * risk_multiplier
        safety_score = max(0, int(100 - hazard_penalty))
        
        duration_mins = int(r["duration"] / 60)
        distance_km = round(r["distance"] / 1000, 1)

        # --- 2. EXTRACT TURN-BY-TURN NAVIGATION STEPS ---
        turn_by_turn = []
        for leg in r.get("legs",[]):
            for step in leg.get("steps",[]):
                maneuver = step.get("maneuver", {})
                
                # Parse OSRM maneuver data into human-readable sentences
                m_type = maneuver.get("type", "").replace("-", " ").title()
                m_modifier = maneuver.get("modifier", "")
                road_name = step.get("name", "")
                dist_meters = round(step.get("distance", 0))
                
                if m_type == "Depart":
                    text = f"Depart and head {m_modifier} on {road_name if road_name else 'the starting road'}"
                elif m_type == "Arrive":
                    text = "You have arrived at your destination."
                else:
                    modifier_text = f" {m_modifier}" if m_modifier else ""
                    road_text = f" onto {road_name}" if road_name else ""
                    text = f"{m_type}{modifier_text}{road_text}"

                turn_by_turn.append({
                    "instruction": text.strip(),
                    "distance_meters": dist_meters,
                    "location": [maneuver["location"][1], maneuver["location"][0]] # [Latitude, Longitude]
                })

        processed_routes.append({
            "id": i,
            "name": names[i] if i < len(names) else f"Route {i+1}",
            "color": colors[i] if i < len(colors) else "#95a5a6",
            "time": f"{duration_mins} mins",
            "distance": f"{distance_km} km",
            "coords": coords_latlon,
            "safety_score": safety_score,
            "hazards_flagged": "High Flood Risk" if safety_score < 50 else ("Moderate Risk" if safety_score < 80 else "Clear"),
            "turn_by_turn": turn_by_turn  # NEW FIELD!
        })

    # Return routes ordered by the safest one first
    return {"routes": sorted(processed_routes, key=lambda x: x["safety_score"], reverse=True)}