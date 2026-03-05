from dotenv import load_dotenv
from google.genai import types
from bs4 import BeautifulSoup
from google import genai
from ddgs import DDGS
import requests
import json
import os
import re

load_dotenv()
TRANSIT_DIR = "transit_data"
API_KEY = os.getenv("exclusive_genai_key")
if not API_KEY:
    raise ValueError("API Key missing! Check your .env file.")

client = genai.Client(api_key=API_KEY)
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
        return text[:15000] # Limit to 2000 chars to save token usage
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