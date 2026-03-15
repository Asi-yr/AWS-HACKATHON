"""
community_reports.py
--------------------
Feature: Community Hazard & Traffic Reports for SafeRoute.

Users submit reports about real-world conditions on routes:
  - Flooding, dark areas, crime hotspots, traffic, road damage, etc.
  - Reports are geotagged (lat/lon) and auto-expire based on type.
  - Upvote/confirm system increases report credibility.
  - Report count and severity affect the safety score of nearby routes.

This is the "Waze for safety" layer — the more users report, the better
the data. No external API needed — all data lives in your existing DB.

Nothing runs on import. Call init_report_tables(db) once at startup.

Integration points:
  - main.py     : init_report_tables(chDB_perf) after chDB_perf.init_db()
                  Add Flask routes /report (POST), /api/reports (GET)
                  Pass reports to map: get_reports_near(db, lat, lon)
                  Pass safety penalty: get_area_safety_penalty(db, lat, lon)
  - navigation.py: call apply_reports_to_routes(routes, db, orig_lat, orig_lon,
                   dest_lat, dest_lon) before returning routes
  - index.html  : add report button + {{ reports_js | safe }} for map pins

New modules needed (add to requirements.txt):
  # new modules to add
  # (none — uses sqlite3/mysql.connector already in db_opt.py)
"""

import json
from datetime import datetime, timezone, timedelta

_PHT = timezone(timedelta(hours=8))

# ── Report types ──────────────────────────────────────────────────────────────
# Each type has: label, icon, expiry_hours, base_penalty, color

REPORT_TYPES = {
    # Safety hazards
    # affect_radius_m: how far FROM THE ROUTE PATH this report must be to count.
    # Tight (≤40m)   = road-specific — only matters if you're ON that road.
    # Medium (60–120m) = some spillover (crowd, blocked junction, visible hazard).
    # Wide (150–250m) = area-wide threats that affect nearby roads too.
    "flooding":      {"label": "Flooding",           "icon": "🌊", "expiry_hours": 3,  "base_penalty": 30, "color": "#1a5276", "category": "hazard",  "affect_radius_m": 200},
    "fire":          {"label": "Fire / Blaze",        "icon": "🔥", "expiry_hours": 2,  "base_penalty": 45, "color": "#c0392b", "category": "hazard",  "affect_radius_m": 250},
    "dark_area":     {"label": "Dark / Unlit Area",   "icon": "🌑", "expiry_hours": 12, "base_penalty": 15, "color": "#2c3e50", "category": "safety",  "affect_radius_m": 35},
    "crime":         {"label": "Crime / Snatching",   "icon": "🚨", "expiry_hours": 6,  "base_penalty": 25, "color": "#c0392b", "category": "safety",  "affect_radius_m": 80},
    "harassment":    {"label": "Harassment",           "icon": "⚠️", "expiry_hours": 6,  "base_penalty": 20, "color": "#e74c3c", "category": "safety",  "affect_radius_m": 60},
    "road_damage":   {"label": "Road Damage",          "icon": "🕳️", "expiry_hours": 24, "base_penalty": 10, "color": "#e67e22", "category": "hazard",  "affect_radius_m": 30},
    "accident":      {"label": "Accident",             "icon": "💥", "expiry_hours": 2,  "base_penalty": 20, "color": "#e74c3c", "category": "hazard",  "affect_radius_m": 40},
    # Traffic
    "heavy_traffic": {"label": "Heavy Traffic",        "icon": "🚗", "expiry_hours": 1,  "base_penalty": 10, "color": "#f39c12", "category": "traffic", "affect_radius_m": 120},
    "road_closed":   {"label": "Road Closed",          "icon": "🚧", "expiry_hours": 6,  "base_penalty": 20, "color": "#e67e22", "category": "traffic", "affect_radius_m": 50},
    "construction":  {"label": "Construction",         "icon": "🏗️", "expiry_hours": 48, "base_penalty": 8,  "color": "#d35400", "category": "traffic", "affect_radius_m": 50},
    # Community info
    "safe_spot":     {"label": "Safe Spot / Well-Lit", "icon": "✅", "expiry_hours": 24, "base_penalty": -10,"color": "#27ae60", "category": "positive","affect_radius_m": 80},
    "police_visible":{"label": "Police Visible",       "icon": "👮", "expiry_hours": 2,  "base_penalty": -8, "color": "#2980b9", "category": "positive","affect_radius_m": 100},
}

# DB fetch radius — wide enough to catch all types as candidates.
# Actual match threshold is per-type affect_radius_m, checked precisely below.
# 250m max / 111,000m per degree ≈ 0.00225 → 0.003 gives a safe margin.
_REPORT_RADIUS_DEG = 0.003   # ~330m — used for DB queries only

# Metres per degree latitude (constant). Lon correction applied per-point below.
_M_PER_DEG_LAT = 111_000.0

# Minimum confirmations before a report is considered "verified"
_CONFIRM_THRESHOLD = 2


# ═════════════════════════════════════════════════════════════════════════════
# DB SETUP
# ═════════════════════════════════════════════════════════════════════════════

def _is_mysql(db) -> bool:
    """Detect whether db is a MySQL (msql) or SQLite (nsql) instance."""
    return hasattr(db, 'DB_HOST')


def init_report_tables(db) -> None:
    """
    Creates community_reports and report_confirmations tables.
    Handles both SQLite (nsql) and MySQL (msql) from db_opt.py automatically.

    Args:
        db: nsql or msql instance from db_opt.py

    Usage in main.py (add after chDB_perf.init_db()):
        from risk_monitor.community_reports import init_report_tables
        init_report_tables(chDB_perf)
    """
    mysql = _is_mysql(db)

    if mysql:
        auto_inc  = "INT AUTO_INCREMENT"
        text_type = "VARCHAR(255)"
        real_type = "DOUBLE"
        int_type  = "INT"
    else:
        auto_inc  = "INTEGER"      # SQLite: INTEGER PRIMARY KEY = rowid alias (auto-increments)
        text_type = "TEXT"
        real_type = "REAL"
        int_type  = "INTEGER"

    conn, c = db.get_db_connection()
    try:
        db.execute_query(c, f"""
            CREATE TABLE IF NOT EXISTS community_reports (
                id            {auto_inc} PRIMARY KEY,
                username      {text_type} NOT NULL,
                report_type   {text_type} NOT NULL,
                lat           {real_type} NOT NULL,
                lon           {real_type} NOT NULL,
                description   {text_type} DEFAULT '',
                confirmations {int_type}  DEFAULT 0,
                reported_at   {text_type} NOT NULL,
                expires_at    {text_type} NOT NULL,
                active        {int_type}  DEFAULT 1
            )
        """)

        db.execute_query(c, f"""
            CREATE TABLE IF NOT EXISTS report_confirmations (
                id           {auto_inc} PRIMARY KEY,
                report_id    {int_type}  NOT NULL,
                username     {text_type} NOT NULL,
                confirmed_at {text_type} NOT NULL
            )
        """)

        conn.commit()

        # ── Migrate old "PHT"-suffixed timestamps to ISO-8601 ────────────────
        # Old code stored "2025-01-15 14:30 PHT"; string < comparison only
        # works reliably with ISO-8601.  Fix any existing rows on startup.
        try:
            c.execute(
                "SELECT id, expires_at, reported_at FROM community_reports "
                "WHERE expires_at LIKE '% PHT'"
            )
            old_rows = c.fetchall()
            for row_id, exp_at, rep_at in old_rows:
                new_exp = exp_at.replace(" PHT", ":00") if exp_at else exp_at
                new_rep = rep_at.replace(" PHT", ":00") if rep_at else rep_at
                db.execute_query(c,
                    "UPDATE community_reports SET expires_at=?, reported_at=? WHERE id=?",
                    (new_exp, new_rep, row_id)
                )
            if old_rows:
                conn.commit()
                print(f"🔧 Migrated {len(old_rows)} report(s) to ISO timestamp format.")
        except Exception:
            pass  # migration is best-effort; don't block startup

        print("🟢 community_reports tables ready.")
    except Exception as e:
        print(f"🔴 community_reports init error: {e}")
    finally:
        c.close()
        conn.close()


# ═════════════════════════════════════════════════════════════════════════════
# SUBMIT A REPORT
# ═════════════════════════════════════════════════════════════════════════════

def submit_report(
    db,
    username:    str,
    report_type: str,
    lat:         float,
    lon:         float,
    description: str = "",
) -> dict:
    """
    Submit a new community report.

    Args:
        db:          nsql or msql instance
        username:    logged-in username (from session['user'])
        report_type: key from REPORT_TYPES (e.g. 'flooding', 'crime')
        lat:         latitude of the reported location
        lon:         longitude of the reported location
        description: optional free-text note (max 200 chars)

    Returns:
        {"ok": bool, "message": str, "report_id": int or None}

    Usage in main.py /report POST handler:
        from risk_monitor.community_reports import submit_report
        result = submit_report(chDB_perf, session['user'],
                               request.form['report_type'],
                               float(request.form['lat']),
                               float(request.form['lon']),
                               request.form.get('description', ''))
    """
    if report_type not in REPORT_TYPES:
        return {"ok": False, "message": f"Unknown report type: {report_type}", "report_id": None}

    rtype    = REPORT_TYPES[report_type]
    now      = datetime.now(_PHT)
    expires  = now + timedelta(hours=rtype["expiry_hours"])
    # Store as ISO-8601 so string comparison in _expire_old_reports works correctly
    now_str  = now.strftime("%Y-%m-%d %H:%M:%S")
    exp_str  = expires.strftime("%Y-%m-%d %H:%M:%S")
    desc     = str(description)[:200]

    conn, c = db.get_db_connection()
    try:
        db.execute_query(c,
            """INSERT INTO community_reports
               (username, report_type, lat, lon, description, reported_at, expires_at, active)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
            (username, report_type, lat, lon, desc, now_str, exp_str)
        )
        conn.commit()

        # Get the inserted ID — use lastrowid first (works for both SQLite and MySQL)
        report_id = getattr(c, 'lastrowid', None)
        if not report_id:
            db.execute_query(c,
                "SELECT id FROM community_reports WHERE username=? ORDER BY id DESC LIMIT 1",
                (username,)
            )
            row = c.fetchone()
            report_id = row[0] if row else None

        if report_id is None:
            return {"ok": False, "message": "Report insert appeared to succeed but no ID returned.", "report_id": None}

        return {
            "ok":        True,
            "message":   f"Report submitted: {rtype['icon']} {rtype['label']}",
            "report_id": report_id,
        }
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"ok": False, "message": f"Error saving report: {str(e)}", "report_id": None}
    finally:
        c.close()
        conn.close()


# ═════════════════════════════════════════════════════════════════════════════
# CONFIRM / UPVOTE A REPORT
# ═════════════════════════════════════════════════════════════════════════════

def confirm_report(db, report_id: int, username: str) -> dict:
    """
    Confirm/upvote an existing report (Waze-style).
    A user can only confirm a report once, and cannot confirm their own.

    Args:
        db:        nsql or msql instance
        report_id: ID of the report to confirm
        username:  logged-in username

    Returns:
        {"ok": bool, "message": str, "confirmations": int}
    """
    conn, c = db.get_db_connection()
    try:
        # Check report exists and isn't by the same user
        db.execute_query(c,
            "SELECT username, confirmations FROM community_reports WHERE id=? AND active=1",
            (report_id,)
        )
        row = c.fetchone()
        if not row:
            return {"ok": False, "message": "Report not found or expired.", "confirmations": 0}
        if row[0] == username:
            return {"ok": False, "message": "You cannot confirm your own report.", "confirmations": row[1]}

        # Check not already confirmed
        db.execute_query(c,
            "SELECT id FROM report_confirmations WHERE report_id=? AND username=?",
            (report_id, username)
        )
        if c.fetchone():
            return {"ok": False, "message": "You already confirmed this report.", "confirmations": row[1]}

        # Add confirmation
        now_str = datetime.now(_PHT).strftime("%Y-%m-%d %H:%M:%S")
        db.execute_query(c,
            "INSERT INTO report_confirmations (report_id, username, confirmed_at) VALUES (?, ?, ?)",
            (report_id, username, now_str)
        )
        db.execute_query(c,
            "UPDATE community_reports SET confirmations = confirmations + 1 WHERE id=?",
            (report_id,)
        )
        conn.commit()

        db.execute_query(c, "SELECT confirmations FROM community_reports WHERE id=?", (report_id,))
        new_count = c.fetchone()[0]

        return {"ok": True, "message": "Report confirmed.", "confirmations": new_count}
    except Exception as e:
        return {"ok": False, "message": str(e), "confirmations": 0}
    finally:
        c.close()
        conn.close()


# ═════════════════════════════════════════════════════════════════════════════
# QUERY REPORTS
# ═════════════════════════════════════════════════════════════════════════════

def _expire_old_reports(db, c, conn) -> None:
    """Mark expired reports as inactive. Called automatically on queries."""
    now_str = datetime.now(_PHT).strftime("%Y-%m-%d %H:%M:%S")
    try:
        db.execute_query(c,
            "UPDATE community_reports SET active=0 WHERE expires_at < ? AND active=1",
            (now_str,)
        )
        conn.commit()
    except Exception:
        pass


def get_reports_near(db, lat: float, lon: float, radius_deg: float = _REPORT_RADIUS_DEG) -> list:
    """
    Get all active, non-expired reports near a coordinate.

    Args:
        db:         nsql or msql instance
        lat:        center latitude
        lon:        center longitude
        radius_deg: search radius in degrees (default ~330m)

    Returns:
        List of report dicts sorted by confirmations desc.
        Each dict: {id, username, report_type, label, icon, color,
                    lat, lon, description, confirmations, reported_at,
                    expires_at, verified}
    """
    conn, c = db.get_db_connection()
    try:
        _expire_old_reports(db, c, conn)

        lat_min = lat - radius_deg
        lat_max = lat + radius_deg
        lon_min = lon - radius_deg
        lon_max = lon + radius_deg

        db.execute_query(c,
            """SELECT id, username, report_type, lat, lon, description,
                      confirmations, reported_at, expires_at
               FROM community_reports
               WHERE active=1
                 AND lat BETWEEN ? AND ?
                 AND lon BETWEEN ? AND ?
               ORDER BY confirmations DESC, id DESC""",
            (lat_min, lat_max, lon_min, lon_max)
        )
        rows = c.fetchall()
        return [_row_to_report(r) for r in rows]
    except Exception as e:
        print(f"[reports] get_reports_near error: {e}")
        return []
    finally:
        c.close()
        conn.close()


def get_all_active_reports(db, limit: int = 100) -> list:
    """
    Get all currently active reports (for rendering on the full map).

    Returns list of report dicts, most recent first.
    """
    conn, c = db.get_db_connection()
    try:
        _expire_old_reports(db, c, conn)
        db.execute_query(c,
            """SELECT id, username, report_type, lat, lon, description,
                      confirmations, reported_at, expires_at
               FROM community_reports
               WHERE active=1
               ORDER BY confirmations DESC, id DESC
               LIMIT ?""",
            (limit,)
        )
        rows = c.fetchall()
        return [_row_to_report(r) for r in rows]
    except Exception as e:
        print(f"[reports] get_all_active_reports error: {e}")
        return []
    finally:
        c.close()
        conn.close()


def _row_to_report(row) -> dict:
    """Convert a DB row tuple to a report dict."""
    report_id, username, rtype, lat, lon, desc, confirmations, reported_at, expires_at = row
    meta = REPORT_TYPES.get(rtype, {})
    return {
        "id":            report_id,
        "username":      username,
        "report_type":   rtype,
        "label":         meta.get("label", rtype),
        "icon":          meta.get("icon", "⚠️"),
        "color":         meta.get("color", "#e74c3c"),
        "category":      meta.get("category", "hazard"),
        "lat":           lat,
        "lon":           lon,
        "description":   desc,
        "confirmations": confirmations,
        "reported_at":   reported_at,
        "expires_at":    expires_at,
        "verified":      confirmations >= _CONFIRM_THRESHOLD,
    }


# ═════════════════════════════════════════════════════════════════════════════
# SAFETY SCORE INTEGRATION
# ═════════════════════════════════════════════════════════════════════════════

def get_area_safety_penalty(db, lat: float, lon: float) -> int:
    """
    Returns a safety score penalty (int) based on active reports near a coordinate.

    Penalty is cumulative but capped. Positive reports (safe_spot, police)
    reduce the penalty.

    Args:
        db:  nsql or msql instance
        lat: latitude to check
        lon: longitude to check

    Returns:
        Integer penalty to subtract from safety score (can be negative = bonus).
    """
    reports = get_reports_near(db, lat, lon)
    return _calc_penalty_from_reports(reports)


# ═════════════════════════════════════════════════════════════════════════════
# PRECISE ROUTE-MATCHING GEOMETRY
# ═════════════════════════════════════════════════════════════════════════════

def _pt_to_segment_dist_m(plat, plon, alat, alon, blat, blon):
    """
    Perpendicular distance in metres from point P to segment A->B.
    Flat-earth approximation, accurate within ~1% for distances < 50km.
    This is what makes reports road-specific: a dark_area (radius 35m) on a
    side street won't match a highway segment 60m away.
    """
    import math
    cos_lat = math.cos(math.radians((alat + blat) / 2.0))
    m_per_deg_lon = _M_PER_DEG_LAT * cos_lat
    bx = (blon - alon) * m_per_deg_lon
    by = (blat - alat) * _M_PER_DEG_LAT
    px = (plon - alon) * m_per_deg_lon
    py = (plat - alat) * _M_PER_DEG_LAT
    seg_len_sq = bx * bx + by * by
    if seg_len_sq < 1e-6:
        return math.sqrt(px * px + py * py)
    t = max(0.0, min(1.0, (px * bx + py * by) / seg_len_sq))
    dx = px - t * bx
    dy = py - t * by
    return math.sqrt(dx * dx + dy * dy)


def _report_hits_route(rep_lat, rep_lon, report_type, waypoints):
    """
    True if the report falls within its type-specific affect_radius_m of
    any segment of the route polyline.

    Replaces the old bounding-box check. A dark_area (35m radius) on a
    parallel side street won't bleed onto the adjacent highway. Fire/flooding
    (200-250m radius) will still propagate to nearby roads as expected.
    """
    import math
    radius_m = REPORT_TYPES.get(report_type, {}).get("affect_radius_m", 80)
    n = len(waypoints)
    if n == 0:
        return False
    if n == 1:
        cos_lat = math.cos(math.radians(rep_lat))
        dx = (rep_lon - waypoints[0][1]) * _M_PER_DEG_LAT * cos_lat
        dy = (rep_lat - waypoints[0][0]) * _M_PER_DEG_LAT
        return math.sqrt(dx * dx + dy * dy) <= radius_m
    for i in range(n - 1):
        a, b = waypoints[i], waypoints[i + 1]
        if _pt_to_segment_dist_m(rep_lat, rep_lon, a[0], a[1], b[0], b[1]) <= radius_m:
            return True
    return False


def apply_reports_to_routes(
    routes: list,
    db,
    orig_lat: float, orig_lon: float,
    dest_lat: float, dest_lon: float,
) -> list:
    """
    Applies community report safety penalties to routes.
    Checks reports near origin, destination, AND waypoints along each route path.
    Adds 'report_warnings' list to each route.

    Call this AFTER apply_weather_to_routes() in navigation.py.

    Args:
        routes:   list of route dicts
        db:       nsql or msql instance
        orig_lat, orig_lon: origin coordinates
        dest_lat, dest_lon: destination coordinates

    Returns:
        Same list with updated safety_score and report_warnings.
    """
    from risk_monitor.features import get_score_color, get_score_label

    # Collect reports at origin and destination using per-type radius filter.
    # get_reports_near does a wide DB fetch; we then filter by affect_radius_m.
    def _filter_by_radius(reports, pt_lat, pt_lon):
        import math
        out = []
        for rep in reports:
            radius_m = REPORT_TYPES.get(rep["report_type"], {}).get("affect_radius_m", 80)
            cos_lat = math.cos(math.radians(pt_lat))
            dx = (rep["lon"] - pt_lon) * _M_PER_DEG_LAT * cos_lat
            dy = (rep["lat"] - pt_lat) * _M_PER_DEG_LAT
            if math.sqrt(dx * dx + dy * dy) <= radius_m:
                out.append(rep)
        return out

    orig_reports = _filter_by_radius(get_reports_near(db, orig_lat, orig_lon), orig_lat, orig_lon)
    dest_reports = _filter_by_radius(get_reports_near(db, dest_lat, dest_lon), dest_lat, dest_lon)

    # Also collect ALL active reports once, for path-based scanning
    all_active = get_all_active_reports(db, limit=200)

    for r in routes:
        # ── 1. Sample waypoints along this route's path ───────────────────
        midpoint_reports = []
        waypoints = []
        if r.get("segments"):
            for seg in r["segments"]:
                coords = seg.get("coords", [])
                # train segments may be nested: [[[lat,lon],...],...]
                if coords and isinstance(coords[0], list) and \
                        coords[0] and isinstance(coords[0][0], list):
                    for sub in coords:
                        waypoints.extend(sub)
                else:
                    waypoints.extend(coords)
        elif r.get("coords"):
            waypoints = r["coords"]

        # ── Precise segment-based matching ───────────────────────────────
        # Each active report is tested against the FULL route polyline using
        # perpendicular point-to-segment distance, capped by per-type radius.
        # This prevents a dark_area on a side street (radius=35m) from bleeding
        # onto an adjacent highway 60m away, while fire/flooding (radius=200-250m)
        # still correctly propagates to nearby roads.
        seen_ids = {rep["id"] for rep in orig_reports + dest_reports}
        clean_wps = [
            (float(wp[0]), float(wp[1]))
            for wp in waypoints
            if isinstance(wp, (list, tuple)) and len(wp) >= 2
        ]
        for active_rep in all_active:
            if active_rep["id"] in seen_ids:
                continue
            if _report_hits_route(
                active_rep["lat"], active_rep["lon"],
                active_rep["report_type"],
                clean_wps,
            ):
                midpoint_reports.append(active_rep)
                seen_ids.add(active_rep["id"])

        # ── 2. Compute penalty from all sources ───────────────────────────
        orig_penalty = _calc_penalty_from_reports(orig_reports)
        dest_penalty = _calc_penalty_from_reports(dest_reports)
        path_penalty = _calc_penalty_from_reports(midpoint_reports)

        # Use worst endpoint penalty + any additional path penalty
        endpoint_penalty = max(orig_penalty, dest_penalty)
        # Path penalty is additive but capped so it doesn't dominate alone
        total_penalty = min(50, endpoint_penalty + min(20, path_penalty))

        # ── 3. Build warning strings ──────────────────────────────────────
        warnings = []
        all_nearby = orig_reports + dest_reports + midpoint_reports
        seen_types = set()
        for rep in sorted(all_nearby, key=lambda x: -x["confirmations"]):
            if rep["report_type"] not in seen_types and rep["category"] != "positive":
                seen_types.add(rep["report_type"])
                conf_text = f" ({rep['confirmations']} confirmed)" if rep["verified"] else ""
                loc_hint = ""
                if rep in midpoint_reports and rep not in orig_reports + dest_reports:
                    loc_hint = " along route"
                warnings.append(f"{rep['icon']} {rep['label']}{conf_text} reported{loc_hint} nearby")
            if len(warnings) >= 4:
                break

        # ── 4. Apply to route ─────────────────────────────────────────────
        if total_penalty > 0:
            r["safety_score"] = max(0, r.get("safety_score", 75) - total_penalty)
            r["score_color"]  = get_score_color(r["safety_score"])
            r["score_label"]  = get_score_label(r["safety_score"])
        r["report_warnings"] = warnings

        # Fire warning — shown prominently with alternative route hint
        fire_reports = [rep for rep in all_nearby if rep["report_type"] == "fire"]
        if fire_reports:
            fr = fire_reports[0]
            conf = f" ({fr['confirmations']} confirmed)" if fr["verified"] else ""
            r["fire_warning"] = (
                f"Active fire reported nearby{conf}. "
                "This route passes through a hazard zone — an alternative route is strongly recommended."
            )
        else:
            r["fire_warning"] = ""

    return routes


def _calc_penalty_from_reports(reports: list) -> int:
    """Calculate a cumulative safety penalty from a list of report dicts."""
    if not reports:
        return 0
    total = 0
    for rep in reports:
        meta    = REPORT_TYPES.get(rep["report_type"], {})
        penalty = meta.get("base_penalty", 0)
        weight  = 1.0 if rep["verified"] else 0.5
        boost   = min(1.5, 1.0 + (rep["confirmations"] * 0.1))
        total  += int(penalty * weight * boost)
    return max(-15, min(40, total))


# ═════════════════════════════════════════════════════════════════════════════
# MAP MARKERS (JS for Folium iframe)
# ═════════════════════════════════════════════════════════════════════════════

def get_report_panel_html() -> str:
    """
    Returns a floating panel that appears over the map when the user clicks it
    to file a report. Hidden by default, shown via JS when map is clicked while
    report mode is active.

    Replaces get_report_form_html() — inject once in index.html outside the
    sidebar, just before </body>.
    """
    type_buttons = "\n".join(
        f'''<button type="button" class="rtype-btn" data-type="{k}"
              style="background:{v['color']}22;border:1px solid {v['color']};
                     color:#222;padding:7px 10px;border-radius:6px;cursor:pointer;
                     font-size:13px;text-align:left;transition:background 0.15s;"
              onmouseover="this.style.background='{v['color']}44'"
              onmouseout="this.style.background='{v['color']}22'"
              onclick="selectReportType('{k}', this)">
           {v['icon']} {v['label']}
         </button>'''
        for k, v in REPORT_TYPES.items()
    )

    return f"""
<!-- ── Report Mode Toggle Button (inside map area) ──────────────────────── -->
<button id="report-mode-btn"
  onclick="toggleReportMode()"
  title="Report a hazard"
  style="position:absolute;bottom:24px;left:16px;z-index:1000;
         background:#c0392b;color:white;border:none;border-radius:50%;
         width:48px;height:48px;font-size:22px;cursor:pointer;
         box-shadow:0 3px 8px rgba(0,0,0,0.35);transition:transform 0.15s;">
  🚨
</button>

<!-- ── Floating report panel (appears where user clicks) ────────────────── -->
<div id="report-panel"
  style="display:none;position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);
         z-index:9998;background:#fff;border-radius:12px;
         box-shadow:0 8px 32px rgba(0,0,0,0.28);
         width:320px;max-height:90vh;overflow-y:auto;font-family:inherit;">

  <!-- Header -->
  <div style="background:#c0392b;color:#fff;padding:14px 18px;border-radius:12px 12px 0 0;
              display:flex;justify-content:space-between;align-items:center;">
    <span style="font-weight:700;font-size:15px;">🚨 Report a Hazard</span>
    <button onclick="closeReportPanel()"
      style="background:none;border:none;color:#fff;font-size:20px;cursor:pointer;line-height:1;">✕</button>
  </div>

  <div style="padding:16px;">
    <!-- Location display -->
    <div id="report-loc-badge"
      style="background:#f0f4ff;border:1px solid #c5d5f5;border-radius:6px;
             padding:7px 12px;font-size:12px;color:#2c3e50;margin-bottom:12px;">
      📍 <span id="report-loc-text">Waiting for map click…</span>
    </div>

    <!-- Report type grid -->
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-bottom:12px;">
      {type_buttons}
    </div>

    <div id="selected-type-display"
      style="display:none;font-size:13px;font-weight:600;color:#2c3e50;
             margin-bottom:8px;padding:6px 10px;border-radius:5px;background:#f5f5f5;">
    </div>

    <!-- Optional description -->
    <textarea id="report-desc" placeholder="Optional: what did you see? (max 200 chars)"
      maxlength="200"
      style="width:100%;padding:8px;border:1px solid #ddd;border-radius:6px;
             resize:vertical;min-height:54px;font-size:13px;box-sizing:border-box;
             margin-bottom:12px;"></textarea>

    <!-- Hidden form fields -->
    <input type="hidden" id="report-lat" value="">
    <input type="hidden" id="report-lon" value="">
    <input type="hidden" id="report-type-val" value="">

    <!-- Actions -->
    <div style="display:flex;gap:8px;">
      <button onclick="closeReportPanel()"
        style="flex:1;padding:9px;background:#ecf0f1;border:none;border-radius:6px;
               cursor:pointer;font-size:13px;">Cancel</button>
      <button id="report-submit-btn" onclick="submitReport()" disabled
        style="flex:1;padding:9px;background:#c0392b;color:#fff;border:none;
               border-radius:6px;cursor:pointer;font-size:13px;opacity:0.45;
               font-weight:600;">Submit Report</button>
    </div>
    <div id="report-msg" style="font-size:12px;margin-top:8px;color:#27ae60;"></div>
  </div>
</div>

<!-- ── Backdrop ──────────────────────────────────────────────────────────── -->
<div id="report-backdrop"
  style="display:none;position:fixed;inset:0;z-index:9997;
         background:rgba(0,0,0,0.35);" onclick="closeReportPanel()">
</div>

<script>
// ── Report mode state ─────────────────────────────────────────────────────
var _reportModeActive = false;
var _selectedReportType = null;

function toggleReportMode() {{
    _reportModeActive = !_reportModeActive;
    var btn = document.getElementById('report-mode-btn');
    if (_reportModeActive) {{
        btn.style.transform = 'scale(1.15)';
        btn.style.background = '#922b21';
        btn.title = 'Click the map to place your report';
        // Small pulsing ring via outline animation
        btn.style.outline = '3px solid #e74c3c';
        btn.style.outlineOffset = '3px';
        showToast('🚨 Report mode ON — click the map where the hazard is');
    }} else {{
        btn.style.transform = '';
        btn.style.background = '#c0392b';
        btn.style.outline = '';
        closeReportPanel();
    }}
}}

function showToast(msg) {{
    var t = document.getElementById('report-toast');
    if (!t) {{
        t = document.createElement('div');
        t.id = 'report-toast';
        t.style.cssText = 'position:fixed;bottom:90px;left:16px;z-index:9999;' +
            'background:#2c3e50;color:#fff;padding:10px 16px;border-radius:8px;' +
            'font-size:13px;box-shadow:0 4px 12px rgba(0,0,0,0.3);' +
            'transition:opacity 0.4s;pointer-events:none;';
        document.body.appendChild(t);
    }}
    t.textContent = msg;
    t.style.opacity = '1';
    clearTimeout(t._hide);
    t._hide = setTimeout(function() {{ t.style.opacity = '0'; }}, 3000);
}}

function openReportPanel(lat, lon) {{
    document.getElementById('report-lat').value = lat.toFixed(6);
    document.getElementById('report-lon').value = lon.toFixed(6);
    // Show coordinates immediately, then replace with reverse-geocoded area name
    document.getElementById('report-loc-text').textContent =
        lat.toFixed(5) + ', ' + lon.toFixed(5);
    fetch('/api/reverse?lat=' + lat + '&lon=' + lon)
        .then(function(r) {{ return r.json(); }})
        .then(function(d) {{
            if (d && d.address) {{
                document.getElementById('report-loc-text').textContent = d.address;
            }}
        }})
        .catch(function() {{ /* keep raw coordinates if reverse geocode fails */ }});
    document.getElementById('report-panel').style.display = 'block';
    document.getElementById('report-backdrop').style.display = 'block';
    // Reset selections
    _selectedReportType = null;
    document.getElementById('report-type-val').value = '';
    document.getElementById('report-desc').value = '';
    document.getElementById('selected-type-display').style.display = 'none';
    document.getElementById('report-msg').textContent = '';
    document.querySelectorAll('.rtype-btn').forEach(function(b) {{
        b.style.fontWeight = '';
        b.style.boxShadow = '';
    }});
    updateSubmitBtn();
}}

function closeReportPanel() {{
    document.getElementById('report-panel').style.display = 'none';
    document.getElementById('report-backdrop').style.display = 'none';
    _reportModeActive = false;
    var btn = document.getElementById('report-mode-btn');
    if (btn) {{
        btn.style.transform = '';
        btn.style.background = '#c0392b';
        btn.style.outline = '';
    }}
}}

function selectReportType(typeKey, btnEl) {{
    _selectedReportType = typeKey;
    document.getElementById('report-type-val').value = typeKey;
    document.querySelectorAll('.rtype-btn').forEach(function(b) {{
        b.style.fontWeight = '';
        b.style.boxShadow = '';
    }});
    btnEl.style.fontWeight = '700';
    btnEl.style.boxShadow = '0 0 0 2px ' + btnEl.style.borderColor;
    var label = btnEl.textContent.trim();
    var disp = document.getElementById('selected-type-display');
    disp.textContent = 'Selected: ' + label;
    disp.style.display = 'block';
    updateSubmitBtn();
}}

function updateSubmitBtn() {{
    var latOk = document.getElementById('report-lat').value !== '';
    var typeOk = _selectedReportType !== null;
    var btn = document.getElementById('report-submit-btn');
    btn.disabled = !(latOk && typeOk);
    btn.style.opacity = (latOk && typeOk) ? '1' : '0.45';
}}

function submitReport() {{
    var lat  = document.getElementById('report-lat').value;
    var lon  = document.getElementById('report-lon').value;
    var type = document.getElementById('report-type-val').value;
    var desc = document.getElementById('report-desc').value;
    if (!lat || !type) return;

    fetch('/report', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/x-www-form-urlencoded'}},
        body: 'report_type=' + encodeURIComponent(type) +
              '&lat=' + encodeURIComponent(lat) +
              '&lon=' + encodeURIComponent(lon) +
              '&description=' + encodeURIComponent(desc),
    }})
    .then(function(r) {{ return r.ok ? r.json() : Promise.reject('HTTP ' + r.status); }})
    .then(function(data) {{
        if (!data.ok) {{
            document.getElementById('report-msg').textContent = '❌ ' + (data.message || 'Error submitting report.');
            document.getElementById('report-msg').style.color = '#c0392b';
            return;
        }}
        document.getElementById('report-msg').textContent = '✅ ' + (data.message || 'Report submitted! Thank you.');
        document.getElementById('report-msg').style.color = '#27ae60';
        document.getElementById('report-submit-btn').disabled = true;
        // Reload the safety overlay so the new pin appears immediately
        if (typeof loadSafetyOverlay === 'function') setTimeout(loadSafetyOverlay, 800);
        setTimeout(closeReportPanel, 1800);
    }})
    .catch(function(e) {{
        document.getElementById('report-msg').textContent = '❌ Error submitting report. Try again.';
        document.getElementById('report-msg').style.color = '#c0392b';
    }});
}}

// Listen for map clicks — open panel when report mode is on
window.addEventListener('message', function(event) {{
    if (event.data && event.data.type === 'map_click' && _reportModeActive) {{
        openReportPanel(event.data.lat, event.data.lng);
    }}
}});
</script>
"""


def get_report_form_html() -> str:
    """Legacy alias — returns empty string, panel is now injected via get_report_panel_html()."""
    return ""


def get_reports_map_js(reports: list) -> str:
    """
    Returns a JS snippet that places report markers on the Folium map iframe.
    Follows the same postMessage pattern already used in the codebase.

    Args:
        reports: list from get_all_active_reports()

    Returns:
        JS string. Inject via Jinja: {{ reports_map_js | safe }}

    Usage in index.html (add inside the main <script> block):
        // After map iframe loads:
        window.addEventListener('load', function() {
            var iframe = document.getElementById('map-frame');
            // The JS in reports_map_js handles this automatically
        });
    """
    if not reports:
        return ""

    # Serialize reports to JS
    reports_json = json.dumps([
        {
            "lat":   r["lat"],
            "lon":   r["lon"],
            "icon":  r["icon"],
            "label": r["label"],
            "color": r["color"],
            "desc":  r["description"],
            "conf":  r["confirmations"],
            "verified": r["verified"],
        }
        for r in reports
    ])

    return f"""
// ── Community Report Markers ─────────────────────────────────────────────────
(function() {{
    var REPORTS = {reports_json};

    function addReportMarkers(mapInstance) {{
        REPORTS.forEach(function(r) {{
            var icon = L.divIcon({{
                html: '<div style="font-size:20px;line-height:1;filter:drop-shadow(0 1px 2px rgba(0,0,0,0.5))">' + r.icon + '</div>',
                className: '',
                iconSize: [24, 24],
                iconAnchor: [12, 12],
            }});
            var conf = r.verified ? ' ✅ Verified (' + r.conf + ' confirmations)' : ' (' + r.conf + ' reports)';
            var popup = '<b>' + r.icon + ' ' + r.label + '</b>' + conf;
            if (r.desc) popup += '<br><i>' + r.desc + '</i>';
            L.marker([r.lat, r.lon], {{icon: icon, interactive: true}})
             .bindPopup(popup)
             .addTo(mapInstance);
        }});
    }}

    // Wait for map iframe to be ready, then inject markers
    setTimeout(function() {{
        var iframe = document.getElementById('map-frame');
        if (!iframe) return;
        var mapKeys = Object.keys(iframe.contentWindow).filter(function(k) {{
            return k.startsWith('map_');
        }});
        if (mapKeys.length > 0) {{
            addReportMarkers(iframe.contentWindow[mapKeys[0]]);
        }}
    }}, 1500);
}})();
"""


# ═════════════════════════════════════════════════════════════════════════════
# REPORT FORM HTML
# ═════════════════════════════════════════════════════════════════════════════

def get_report_form_html() -> str:
    """
    Returns an HTML snippet for the report submission form.
    Uses the map click postMessage to pre-fill lat/lon.

    Inject via Jinja in index.html: {{ report_form_html | safe }}
    Place this after the route results div in the sidebar.

    The form POSTs to /report (add this route to main.py).
    """
    type_options = "\n".join(
        f'<option value="{k}">{v["icon"]} {v["label"]}</option>'
        for k, v in REPORT_TYPES.items()
        if v["category"] != "positive" or k in ("safe_spot", "police_visible")
    )

    return f"""
<div class="report-panel" style="margin-top:20px;border-top:1px solid #eee;padding-top:15px;">
  <h4 style="color:#c0392b;margin-bottom:10px;">🚨 Report a Hazard</h4>
  <form method="POST" action="/report" id="report-form">
    <select name="report_type" style="width:100%;padding:8px;margin-bottom:8px;border:1px solid #ddd;border-radius:4px;">
      {type_options}
    </select>
    <input type="hidden" name="lat" id="report-lat" value="">
    <input type="hidden" name="lon" id="report-lon" value="">
    <div style="font-size:12px;color:#888;margin-bottom:6px;" id="report-loc-status">
      📍 Click the map or use your location to set report location
    </div>
    <textarea name="description" placeholder="Optional: describe what you saw (max 200 chars)"
      maxlength="200"
      style="width:100%;padding:8px;margin-bottom:8px;border:1px solid #ddd;border-radius:4px;
             resize:vertical;min-height:60px;font-size:13px;"></textarea>
    <div style="display:flex;gap:8px;">
      <button type="button" onclick="useCurrentLocationForReport()"
        style="flex:1;padding:8px;background:#2980b9;color:white;border:none;border-radius:4px;cursor:pointer;font-size:13px;">
        🎯 Use My Location
      </button>
      <button type="submit" id="report-submit-btn" disabled
        style="flex:1;padding:8px;background:#c0392b;color:white;border:none;border-radius:4px;cursor:pointer;font-size:13px;opacity:0.5;">
        Submit Report
      </button>
    </div>
  </form>
</div>

<script>
// ── Report form location handling ─────────────────────────────────────────────
function setReportLocation(lat, lon) {{
    document.getElementById('report-lat').value = lat.toFixed(6);
    document.getElementById('report-lon').value = lon.toFixed(6);
    document.getElementById('report-loc-status').innerHTML =
        '✅ Location set: ' + lat.toFixed(4) + ', ' + lon.toFixed(4);
    document.getElementById('report-submit-btn').disabled = false;
    document.getElementById('report-submit-btn').style.opacity = '1';
}}

function useCurrentLocationForReport() {{
    if (!navigator.geolocation) return alert('Geolocation not supported.');
    navigator.geolocation.getCurrentPosition(
        function(pos) {{ setReportLocation(pos.coords.latitude, pos.coords.longitude); }},
        function()    {{ alert('Could not get your location.'); }}
    );
}}

// Also allow setting report location by clicking the map (in pinpoint mode)
// This extends the existing map_click postMessage handler
window.addEventListener('message', function(event) {{
    if (event.data && event.data.type === 'map_click') {{
        var reportPanel = document.getElementById('report-form');
        var latField    = document.getElementById('report-lat');
        if (reportPanel && latField && !latField.value) {{
            // Only auto-fill if report lat is not yet set
            setReportLocation(event.data.lat, event.data.lng);
        }}
    }}
}});
</script>
"""


def get_report_type_options_for_api() -> list:
    """
    Returns REPORT_TYPES as a JSON-serializable list for the /api/report-types endpoint.

    Usage in main.py:
        @app.route('/api/report-types')
        def report_types():
            from risk_monitor.community_reports import get_report_type_options_for_api
            return jsonify(get_report_type_options_for_api())
    """
    return [
        {
            "value":    k,
            "label":    v["label"],
            "icon":     v["icon"],
            "color":    v["color"],
            "category": v["category"],
            "expiry_hours": v["expiry_hours"],
        }
        for k, v in REPORT_TYPES.items()
    ]