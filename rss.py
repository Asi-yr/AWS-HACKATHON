"""
rss.py
------
Builds a combined RSS 2.0 feed for SafeRoute containing:
  - Active community hazard reports (Baha Watch, flooding, crime, etc.)
  - Active typhoon / storm signal alerts
  - Live weather risk warnings (heavy rain / storm only)

Endpoint:  GET /rss
           GET /rss?lat=14.5995&lon=120.9842   (weather localized to coords)
           GET /rss?type=reports                (reports only)
           GET /rss?type=weather                (weather + typhoon only)

No new packages needed — uses only Python stdlib xml.etree + existing modules.
"""

import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from html import escape as _esc

_PHT   = timezone(timedelta(hours=8))
_LINK  = "https://saferoute.app"          # change to your actual domain if deployed
_EMAIL = "saferoute@example.com"          # optional, shown in feed metadata


# ── Internal helpers ──────────────────────────────────────────────────────────

def _rfc822(dt: datetime) -> str:
    """Format a datetime as RFC 822 (RSS pubDate format)."""
    return dt.strftime("%a, %d %b %Y %H:%M:%S +0800")


def _now_rfc822() -> str:
    return _rfc822(datetime.now(_PHT))


def _sub(parent, tag: str, text: str = ""):
    el = ET.SubElement(parent, tag)
    el.text = text
    return el


def _item(channel, title: str, description: str, link: str,
          pub_date: str, category: str, guid: str):
    """Append a single <item> to the RSS channel."""
    item = ET.SubElement(channel, "item")
    _sub(item, "title",       title)
    _sub(item, "description", description)
    _sub(item, "link",        link)
    _sub(item, "pubDate",     pub_date)
    _sub(item, "category",    category)
    _sub(item, "guid",        guid)


# ── Report items ──────────────────────────────────────────────────────────────

def _reports_to_items(channel, reports: list):
    """Add one RSS <item> per active community report."""
    for r in reports:
        title = f"[{r.get('label', r.get('report_type', 'Report')).upper()}] " \
                f"{r.get('label', 'Hazard report')} reported"

        lat  = r.get("lat", "")
        lon  = r.get("lon", "")
        desc = r.get("description", "").strip()
        conf = r.get("confirmations", 0)
        veri = "✅ Verified" if r.get("verified") else f"⏳ {conf} confirmation(s)"

        description = (
            f"{_esc(desc + ' — ') if desc else ''}"
            f"Reported at coordinates ({lat}, {lon}). "
            f"Status: {veri}. "
            f"Reported: {r.get('reported_at', 'Unknown time')}."
        )

        # Parse reported_at into RFC 822 if possible
        try:
            raw_dt = r.get("reported_at", "")
            # Try common format from user_data.py: "2025-03-08 14:30 PHT"
            dt = datetime.strptime(raw_dt[:16], "%Y-%m-%d %H:%M")
            dt = dt.replace(tzinfo=_PHT)
            pub_date = _rfc822(dt)
        except Exception:
            pub_date = _now_rfc822()

        _item(
            channel,
            title=title,
            description=description,
            link=f"{_LINK}/community",
            pub_date=pub_date,
            category=r.get("report_type", "hazard"),
            guid=f"saferoute-report-{r.get('id', 'unknown')}",
        )


# ── Typhoon item ──────────────────────────────────────────────────────────────

def _typhoon_to_item(channel, typhoon: dict):
    """Add a typhoon signal alert <item> if a cyclone is active."""
    if not typhoon.get("active"):
        return

    signal  = typhoon.get("signal", "?")
    name    = typhoon.get("name", "Tropical Cyclone")
    source  = typhoon.get("source", _LINK)

    _item(
        channel,
        title=f"🌀 PAGASA Signal #{signal} — Typhoon {name} Active",
        description=(
            f"PAGASA has raised Tropical Cyclone Wind Signal #{signal} "
            f"for Typhoon {name}. Commuters are advised to monitor updates "
            f"and avoid unnecessary travel. Source: {source}"
        ),
        link=source,
        pub_date=_now_rfc822(),
        category="typhoon",
        guid=f"saferoute-typhoon-{name.lower().replace(' ', '-')}",
    )


# ── Weather item ──────────────────────────────────────────────────────────────

_WEATHER_ALERT_LEVELS = {"heavy_rain", "storm", "rain"}

def _weather_to_item(channel, weather: dict, lat: float, lon: float):
    """Add a weather warning <item> for heavy rain / storm conditions."""
    if not weather.get("ok"):
        return
    risk = weather.get("risk_level", "clear")
    if risk not in _WEATHER_ALERT_LEVELS:
        return

    desc_text  = weather.get("description", "Adverse weather")
    temp       = weather.get("temp_c", 0)
    wind       = weather.get("wind_kph", 0)
    rain       = weather.get("rain_mm", 0)
    fetched_at = weather.get("fetched_at", "")

    icons = {"rain": "🌧️", "heavy_rain": "⛈️", "storm": "⚡"}
    icon  = icons.get(risk, "⚠️")

    _item(
        channel,
        title=f"{icon} Weather Alert: {desc_text} near ({lat:.4f}, {lon:.4f})",
        description=(
            f"{desc_text} conditions detected. "
            f"Temperature: {temp:.0f}°C | Wind: {wind:.0f} km/h"
            f"{f' | Rainfall: {rain:.1f} mm/hr' if rain > 0 else ''}. "
            f"Commuters are advised to allow extra travel time and prepare rain gear. "
            f"Updated: {fetched_at}."
        ),
        link=_LINK,
        pub_date=_now_rfc822(),
        category=f"weather-{risk}",
        guid=f"saferoute-weather-{risk}-{datetime.now(_PHT).strftime('%Y%m%d%H')}",
    )


# ── Main builder ──────────────────────────────────────────────────────────────

def build_rss(
    reports: list,
    typhoon: dict,
    weather: dict,
    lat: float = 14.5995,
    lon: float = 120.9842,
    feed_type: str = "all",   # "all" | "reports" | "weather"
) -> str:
    """
    Build and return the full RSS 2.0 XML string.

    Args:
        reports:   list from get_all_active_reports()
        typhoon:   dict from get_typhoon_signal()
        weather:   dict from get_weather_risk()
        lat/lon:   coordinates used for weather item location label
        feed_type: filter — "all", "reports", or "weather"

    Returns:
        UTF-8 XML string ready to serve as application/rss+xml
    """
    rss = ET.Element("rss", version="2.0")
    rss.set("xmlns:atom", "http://www.w3.org/2005/Atom")

    channel = ET.SubElement(rss, "channel")

    _sub(channel, "title",          "SafeRouteAI — Safety Alerts Feed")
    _sub(channel, "link",           _LINK)
    _sub(channel, "description",
         "Live community hazard reports, typhoon signals, and weather alerts "
         "for Metro Manila commuters.")
    _sub(channel, "language",       "en-ph")
    _sub(channel, "lastBuildDate",  _now_rfc822())
    _sub(channel, "ttl",            "15")   # refresh every 15 minutes

    # atom:link self-reference (RSS best practice)
    atom_link = ET.SubElement(channel, "atom:link")
    atom_link.set("href",  f"{_LINK}/rss")
    atom_link.set("rel",   "self")
    atom_link.set("type",  "application/rss+xml")

    include_reports = feed_type in ("all", "reports")
    include_weather = feed_type in ("all", "weather")

    if include_weather:
        _typhoon_to_item(channel, typhoon)
        _weather_to_item(channel, weather, lat, lon)

    if include_reports:
        _reports_to_items(channel, reports)

    # If nothing was added, include a placeholder item
    all_items = channel.findall("item")
    if not all_items:
        _item(
            channel,
            title="✅ No active alerts",
            description="There are currently no active hazard reports or weather alerts for Metro Manila.",
            link=_LINK,
            pub_date=_now_rfc822(),
            category="status",
            guid=f"saferoute-no-alerts-{datetime.now(_PHT).strftime('%Y%m%d')}",
        )

    ET.indent(rss, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(rss, encoding="unicode")
