"""
condemnation/
-------------
Bug fix + feature extension package for SafeRoute.

Modules:
    routing_profiles  - Bug Fix #1: correct OSRM profiles per commuter type
    autocomplete      - Bug Fix #2: location suggestion JS + backend helpers
    form_state        - Bug Fix #3: form repopulation after POST

Import example:
    from condemnation.routing_profiles import build_osrm_url, is_train_type
    from condemnation.autocomplete     import get_suggest_js, validate_suggest_response
    from condemnation.form_state       import extract_form_state, get_empty_form_state, get_commuter_options

Nothing in this package auto-executes on import.
"""
"""
#2
condemnation/
-------------
Bug fix + feature extension package for SafeRoute.

Modules:
    routing_profiles  - Bug Fix #1: correct ORS profiles per commuter type
    autocomplete      - Bug Fix #2: location suggestion JS + backend helpers
    form_state        - Bug Fix #3: form repopulation after POST
    features          - Route display, safety scores, fares, typhoon/night banners
    weather           - Live Weather Risk via Open-Meteo (no API key needed)
    noah              - NOAH Flood Zone Overlay via WMS/WFS
    user_data         - User settings, route history, account/profile management

Import example:
    from condemnation.routing_profiles import build_osrm_url, is_train_type
    from condemnation.autocomplete     import get_suggest_js, validate_suggest_response
    from condemnation.form_state       import extract_form_state, get_empty_form_state, get_commuter_options
    from condemnation.features         import get_typhoon_signal, get_banner_html, is_nighttime, get_night_banner_html
    from condemnation.weather          import get_weather_risk, get_weather_banner_html, apply_weather_to_routes
    from condemnation.noah             import add_noah_flood_layer, get_flood_risk_at, get_flood_warning_html
    from condemnation.user_data        import init_user_tables, get_user_settings, save_route_history

Nothing in this package auto-executes on import.
"""