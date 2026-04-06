from dotenv import load_dotenv
from google.genai import types
from bs4 import BeautifulSoup
from google import genai
from ddgs import DDGS
from datetime import datetime
import requests
import json
import os
import re

load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), 'grounding_tool', '.env'))

TRANSIT_DIR = "transit_data"
API_KEY = os.getenv("exclusive_genai_key")
if not API_KEY:
    raise ValueError("API Key missing! Check your .env file.")

client = genai.Client(api_key=API_KEY)


# ══════════════════════════════════════════════════════════════════════════════
#  ORIGINAL LLM FUNCTIONS (web search + scraping + Gemini route discovery)
# ══════════════════════════════════════════════════════════════════════════════

def search_transport_info(query):
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=5))
        return results

def scrape_url(url):
    """Extracts text content from a URL using BeautifulSoup."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(response.text, 'html.parser')

        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.extract()

        text = soup.get_text(separator=' ')
        return text[:15000] # Limit to 15000 chars to save token usage
    except Exception:
        return ""

def context_model(context: str, sysinstruct: str, rthoughts: bool, thinking_budget: int, model: str) -> str:
    config = types.GenerateContentConfig(
        system_instruction=sysinstruct,
        thinking_config=types.ThinkingConfig(
            include_thoughts=rthoughts,
            thinking_budget=thinking_budget
        )
    )

    response = client.models.generate_content(
        model=model,
        contents=context,
        config=config
    )

    return response.text

def clean_filename(name):
    return re.sub(r'[^a-zA-Z0-9]', '_', name).strip('_')

def init(origin, destination, commuter_type):
    if not os.path.exists(TRANSIT_DIR):
        os.makedirs(TRANSIT_DIR)

    filename = f"{TRANSIT_DIR}/{clean_filename(origin)}_to_{clean_filename(destination)}_{commuter_type}.json"

    # --- 1. CACHE CHECK ---
    if os.path.exists(filename):
        try:
            with open(filename, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            pass

    # --- 2. WEB DATA GATHERING (If Cache Miss) ---
    web_data = ""
    query = f"jeepney bus route {origin} to {destination} Philippines"
    search_results = search_transport_info(query)

    for result in search_results:
        web_data += scrape_url(result.get('href', '')) + "\n"

    # --- 3. PROMPT GENERATION WITH WEB DATA ---
    sysinstruct = (
        "You are a Philippine commute assistant. "
        "Use the provided Web Data (if any) to create an accurate route. "
        "Output ONLY raw JSON. No markdown code blocks, no intro text. "
        "Schema: {\"advice\": \"string\", \"estimated_cost\": \"string\", \"waypoints\": [\"list of strings\"]}. "
        "If no specific waypoints apply, leave the array empty."
    )

    context = f"Web Data: {web_data}\n\nTask: How do I commute from {origin} to {destination} via {commuter_type}?"

    try:
        raw_output = context_model(context, sysinstruct, rthoughts=True, thinking_budget=10240, model="gemini-2.5-flash-lite")

        clean_json = re.sub(r'```json|```', '', raw_output).strip()
        parsed_data = json.loads(clean_json)

        parsed_data.setdefault("waypoints", [])
        parsed_data.setdefault("advice", "No specific route found.")
        parsed_data.setdefault("estimated_cost", "N/A")

        # --- 4. SAVE TO FILE ---
        with open(filename, 'w') as f:
            json.dump(parsed_data, f, indent=4)

        return parsed_data

    except Exception:
        return {
            "advice": "Unable to calculate route via web.",
            "estimated_cost": "N/A",
            "waypoints": []
        }


# ══════════════════════════════════════════════════════════════════════════════
#  AI COMMUTER HELPER — Advisor layer on top of the routing engine
# ══════════════════════════════════════════════════════════════════════════════

_SYSTEM_PROMPT = """You are Ligtas AI, a Filipino commuter assistant for Metro Manila.
You help commuters find the quickest and cheapest combination of jeepney, bus, and train routes.

RULES:
- Be concise and friendly. Use Filipino-English mix if the user does.
- Always recommend the cheapest option first, then the fastest.
- Mention specific jeepney route names, bus routes, or train lines (LRT-1, LRT-2, MRT-3).
- Include estimated fares in PHP and travel times.
- Warn about safety risks, flood-prone areas, or heavy traffic if relevant.
- If transfer-walking is needed, mention the approximate distance.
- When weather is bad, suggest covered or indoor transfer points.
- Output ONLY valid JSON with no markdown code blocks, no intro text.

OUTPUT SCHEMA:
{
  "recommendation": "string — 1-2 sentence summary of the best option",
  "routes": [
    {
      "rank": 1,
      "label": "Cheapest" or "Fastest" or "Safest",
      "steps": [
        {"mode": "walk|jeepney|bus|train", "instruction": "string", "fare": 0.0, "duration_min": 0}
      ],
      "total_fare": 0.0,
      "total_duration_min": 0,
      "transfers": 0,
      "why": "string — brief reason this option is good"
    }
  ],
  "warnings": ["string — any safety/weather/traffic warnings"],
  "tip": "string — one pro commuter tip"
}
"""


def _build_route_summary(routes, weather=None):
    """Compress route data from navigation.py into a concise context string for the LLM."""
    lines = []
    for i, r in enumerate(routes):
        name = r.get('route_name') or r.get('name', f'Route {i}')
        fare = r.get('fare', 'N/A')
        time_str = r.get('time', 'N/A')
        dist = r.get('distance', 'N/A')
        score = r.get('safety_score', 'N/A')
        segments = r.get('segments', [])

        seg_desc = []
        for s in segments:
            stype = s.get('type', 'unknown')
            label = s.get('label', '')
            stations = s.get('stations', [])
            station_names = [st.get('name', '') for st in stations if st.get('name')]
            if station_names:
                seg_desc.append(f"{stype}: {label} ({' → '.join(station_names[:5])}{'...' if len(station_names) > 5 else ''})")
            else:
                seg_desc.append(f"{stype}: {label}")

        hazards = r.get('hazards_flagged', '')
        crime_zones = r.get('route_crime_zones', [])

        line = (
            f"Route {i+1}: {name}\n"
            f"  Fare: {fare} | Time: {time_str} | Distance: {dist} | Safety: {score}/100\n"
            f"  Segments: {'; '.join(seg_desc) if seg_desc else 'single leg'}"
        )
        if hazards:
            line += f"\n  Hazards: {hazards}"
        if crime_zones:
            zone_names = [z.get('name', '') for z in crime_zones[:3]]
            line += f"\n  Crime zones on route: {', '.join(zone_names)}"
        lines.append(line)

    summary = '\n'.join(lines)

    if weather and weather.get('ok'):
        summary += (
            f"\n\nCurrent Weather: {weather.get('description', 'Clear')}, "
            f"{weather.get('temp_c', 0)}°C, wind {weather.get('wind_kph', 0)} km/h, "
            f"rain {weather.get('rain_mm', 0)} mm, risk: {weather.get('risk_level', 'clear')}"
        )

    return summary


def get_commuter_advice(origin_text, dest_text, routes, weather=None, user_question=None):
    """Generate AI commuter advice based on actual routing engine results.

    Args:
        origin_text: Human-readable origin
        dest_text: Human-readable destination
        routes: List of route dicts from navigation.py
        weather: Weather dict from get_weather_risk() (optional)
        user_question: Optional free-text question from the user

    Returns:
        dict with AI recommendation, or error fallback
    """
    route_summary = _build_route_summary(routes, weather)

    now = datetime.now()
    time_context = f"Current time: {now.strftime('%I:%M %p')}, {now.strftime('%A, %B %d, %Y')}"
    is_night = now.hour < 6 or now.hour >= 20

    user_msg = (
        f"{time_context}\n"
        f"Origin: {origin_text}\n"
        f"Destination: {dest_text}\n"
        f"{'Night travel — suggest well-lit routes.' if is_night else ''}\n\n"
        f"Available routes from the routing engine:\n{route_summary}"
    )
    if user_question:
        user_msg += f"\n\nUser's question: {user_question}"
    else:
        user_msg += "\n\nPick the best options and explain why."

    try:
        config = types.GenerateContentConfig(
            system_instruction=_SYSTEM_PROMPT,
            thinking_config=types.ThinkingConfig(
                include_thoughts=False,
                thinking_budget=4096,
            ),
        )

        response = client.models.generate_content(
            model='gemini-2.5-flash-lite',
            contents=user_msg,
            config=config,
        )

        raw = response.text or ''
        clean = re.sub(r'```json|```', '', raw).strip()
        result = json.loads(clean)

        result.setdefault('recommendation', 'No specific recommendation.')
        result.setdefault('routes', [])
        result.setdefault('warnings', [])
        result.setdefault('tip', '')
        return {'ok': True, **result}

    except (json.JSONDecodeError, Exception) as e:
        print(f"[llm] AI advisor error: {e}")
        return _fallback_advice(routes)


def _fallback_advice(routes):
    """Non-AI fallback: pick cheapest and fastest from available routes."""
    if not routes:
        return {
            'ok': False,
            'recommendation': 'No routes found for this trip.',
            'routes': [],
            'warnings': [],
            'tip': 'Try a different transport mode or check your origin/destination.',
        }

    by_fare = sorted(routes, key=lambda r: r.get('fare_amount', 9999))
    cheapest = by_fare[0] if by_fare else routes[0]

    return {
        'ok': True,
        'recommendation': f"Take {cheapest.get('name', 'the first route')} — it's the cheapest at {cheapest.get('fare', 'N/A')}.",
        'routes': [
            {
                'rank': 1,
                'label': 'Cheapest',
                'steps': [{'mode': 'transit', 'instruction': cheapest.get('name', 'Follow the route'), 'fare': cheapest.get('fare_amount', 0), 'duration_min': 0}],
                'total_fare': cheapest.get('fare_amount', 0),
                'total_duration_min': 0,
                'transfers': 0,
                'why': 'Lowest fare option available.',
            }
        ],
        'warnings': [],
        'tip': 'AI advisor is currently unavailable. Showing basic recommendation.',
    }