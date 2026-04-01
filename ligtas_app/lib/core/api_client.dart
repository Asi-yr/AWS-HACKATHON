import 'dart:convert';
import 'dart:io';
import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../models/explore_models.dart';

/// Thin HTTP client for talking to the SafeRoute Flask backend.
///
/// This is intentionally minimal and defensive:
/// - If the server cannot be reached or returns unexpected data,
///   callers can decide to fall back to mock data.
class ApiClient {
  ApiClient._();
  static final ApiClient instance = ApiClient._();

  // ── Dynamic backend discovery ─────────────────────────────────────────────
  //
  // HOW IT WORKS:
  //   Everything runs in ONE parallel batch — no sequential phases wasting time.
  //   All candidates are fired simultaneously and the first 200 /ping wins.
  //
  //   Candidate pool (all probed at once):
  //     • Manual override  — _manualBaseUrl if set via setManualUrl()
  //     • Emulator alias   — 10.0.2.2        (Android emulator → host machine)
  //     • Loopback         — 127.0.0.1        (iOS sim / desktop / web)
  //     • Full subnet scan — every .1–.254 on every RFC-1918 /24 the phone is on
  //
  // TROUBLESHOOTING (corporate/school Wi-Fi that blocks device-to-device):
  //   If the phone is on a network that isolates devices (common on 10.x.x.x
  //   enterprise nets), the scan will never find the server.
  //   Fix: call ApiClient.setManualUrl('http://YOUR_LAPTOP_IP:5000') once at
  //   app startup (e.g. from a debug settings screen or a .env-style config).
  //   Your laptop IP: run `ipconfig` (Windows) or `ifconfig` (Mac/Linux) and
  //   look for the IP on the same Wi-Fi adapter.

  static String? _cachedBaseUrl;
  static String? _manualBaseUrl; // set via setManualUrl() to skip discovery

  /// Force a specific server URL — useful when network isolation blocks scanning.
  /// Call this before any API request, e.g. in main() or a debug settings screen.
  /// Example: ApiClient.setManualUrl('http://10.143.0.42:5000');
  static void setManualUrl(String url) {
    _manualBaseUrl = url;
    _cachedBaseUrl = url; // cache immediately so next call uses it
    debugPrint('[API] Manual URL set: $url');
  }

  /// Clear cached URL and re-run discovery on next call.
  static void resetBaseUrl() {
    _cachedBaseUrl = null;
    // Note: _manualBaseUrl is intentionally kept — reset it explicitly if needed.
  }

  static Future<String> getBaseUrl() async {
    if (_cachedBaseUrl != null) return _cachedBaseUrl!;

    // Build the full candidate pool — everything probed simultaneously.
    final candidates = <String>{};

    // Manual override wins immediately if set.
    if (_manualBaseUrl != null) {
      _cachedBaseUrl = _manualBaseUrl;
      debugPrint('[API] ✓ Using manual URL: $_manualBaseUrl');
      return _manualBaseUrl!;
    }

    // Known fixed candidates tried first (emulator + loopback via ADB tunnel).
    candidates.addAll([
      'http://10.0.2.2:5000',
      'http://127.0.0.1:5000',
      'http://localhost:5000',
    ]);

    // Discover every /24 subnet the phone is on, probe ALL hosts in parallel.
    final subnets = await _getLocalSubnets();
    debugPrint('[API] Device subnets: $subnets');
    for (final s in subnets) {
      for (int h = 1; h <= 254; h++) { candidates.add('http://$s.$h:5000'); }
    }

    debugPrint('[API] Probing \${candidates.length} candidates simultaneously...');

    // Fire every candidate at once — 5 s total budget.
    final found = await _probeAll(candidates.toList(), timeout: const Duration(seconds: 5));

    if (found != null) {
      _cachedBaseUrl = found;
      debugPrint('[API] ✓ Backend found at $found');
      return found;
    }

    // Nothing responded. Log the subnet so the developer knows what to put in setManualUrl.
    debugPrint('[API] ✗ Backend not found. Device subnets were: $subnets');
    debugPrint('[API]   → If on a network that blocks device-to-device traffic,');
    debugPrint('[API]     call ApiClient.setManualUrl("http://<YOUR_LAPTOP_IP>:5000")');
    debugPrint('[API]     then restart the app.');
    _cachedBaseUrl = 'http://localhost:5000';
    return _cachedBaseUrl!;
  }

  /// Probe all [urls] simultaneously. Returns the first URL that answers
  /// HTTP 200 to GET /ping within [timeout], or null if none do.
  static Future<String?> _probeAll(
    List<String> urls, {
    required Duration timeout,
  }) async {
    if (urls.isEmpty) return null;
    final completer = Completer<String?>();
    int remaining = urls.length;

    for (final url in urls) {
      http
          .get(Uri.parse('$url/ping'))
          .timeout(timeout)
          .then((resp) {
            if (!completer.isCompleted && resp.statusCode == 200) {
              debugPrint('[API] /ping OK → $url');
              completer.complete(url);
            }
          })
          .catchError((_) {}) // connection refused, timeout, etc. — all silently ignored
          .whenComplete(() {
            remaining--;
            if (remaining == 0 && !completer.isCompleted) {
              completer.complete(null); // all probes finished, none succeeded
            }
          });
    }
    return completer.future;
  }

  /// Returns the /24 subnet prefix for every private IPv4 interface on the device.
  /// e.g. phone on 10.143.0.55 → returns ['10.143.0'].
  /// Uses dart:io NetworkInterface — no extra packages needed.
  static Future<List<String>> _getLocalSubnets() async {
    final subnets = <String>{};
    try {
      final ifaces = await NetworkInterface.list(
        includeLinkLocal: false,
        type: InternetAddressType.IPv4,
      );
      for (final iface in ifaces) {
        for (final addr in iface.addresses) {
          final p = addr.address.split('.');
          if (p.length != 4) continue;
          final a = int.tryParse(p[0]) ?? 0;
          final b = int.tryParse(p[1]) ?? 0;
          // RFC-1918 private ranges only.
          if (a == 10 ||
              a == 192 ||
              (a == 172 && b >= 16 && b <= 31)) {
            final prefix = '${p[0]}.${p[1]}.${p[2]}';
            subnets.add(prefix);
            debugPrint('[API] Interface ${iface.name}: ${addr.address} → subnet $prefix.0/24');
          }
        }
      }
    } catch (e) {
      debugPrint('[API] NetworkInterface.list failed: $e');
    }
    return subnets.toList();
  }

  Future<Uri> _uriAsync(String path) async {
    final base = await getBaseUrl();
    return Uri.parse('$base$path');
  }

  // Use _uriAsync for all URL construction

  /// Call the backend `/api/routes` endpoint with full response including alerts.
  /// Returns: {
  ///   'routes': `List<RouteModel>`,
  ///   'incidents': `List<Map>` or [],
  ///   'mmda_banner': `String` or '',
  ///   'mmda_closures_count': `int` or 0,
  ///   'earthquakes': `List<Map>` or [],
  ///   'seismic_banner': `String` or '',
  /// }
  Future<Map<String, dynamic>> searchRoutesWithAlerts({
    required String origin,
    required String destination,
    String mode = 'commute',
    Map<String, dynamic>? extraParams,
  }) async {
    final uri = await _uriAsync('/api/routes');
    final resp = await http
        .post(
          uri,
          headers: const {'Content-Type': 'application/json'},
          body: jsonEncode({
            'origin': origin,
            'destination': destination,
            'mode': mode,
            ...?extraParams,
          }),
        )
        .timeout(const Duration(seconds: 180));

    // ── Never throw on HTTP errors — always return a usable map ──────────
    // The controller checks routes.isEmpty and surfaces the error as a toast.
    // Throwing here crashes the app with an unhandled exception on every
    // "no route found" / geocoding failure from the backend.
    dynamic decoded;
    try {
      decoded = jsonDecode(resp.body);
    } catch (_) {
      decoded = <String, dynamic>{};
    }
    if (decoded is! Map<String, dynamic>) {
      decoded = <String, dynamic>{};
    }

    // 4xx / 5xx — backend returned an error payload like {"error": "..."}
    if (resp.statusCode != 200) {
      return {
        'routes': <RouteModel>[],
        'error':
            (decoded['error'] ??
                    decoded['message'] ??
                    'No route found (${resp.statusCode})')
                .toString(),
        'error_type': decoded['error_type']?.toString() ?? '',
        'incidents': <dynamic>[],
        'mmda_banner': '',
        'mmda_closures_count': 0,
        'earthquakes': <dynamic>[],
        'seismic_banner': '',
        'weather_risk': 'clear',
        'flood_risk': 'none',
        'orig_lat': decoded['origin_lat'],
        'orig_lon': decoded['origin_lon'],
        'dest_lat': null,
        'dest_lon': null,
      };
    }

    // Extract routes
    final routesJson = decoded['routes'];
    final List<RouteModel> routeList = [];
    if (routesJson is List) {
      for (var i = 0; i < routesJson.length; i++) {
        final r = routesJson[i];
        if (r is Map<String, dynamic>) {
          routeList.add(_routeFromApi(i, r));
        }
      }
    }

    // Extract alert data
    final incidents = decoded['incidents'] ?? [];
    final mmdaBanner = decoded['mmda_banner'] ?? '';
    final mmdaClosures = decoded['mmda_closures_count'] ?? 0;
    final earthquakes = decoded['earthquakes'] ?? [];
    final seismicBanner = decoded['seismic_banner'] ?? '';
    final weatherRisk = decoded['weather_risk'] ?? 'clear';
    final floodRisk = decoded['flood_risk'] ?? 'none';

    return {
      'routes': routeList,
      'incidents': incidents is List ? incidents : [],
      'mmda_banner': mmdaBanner.toString(),
      'mmda_closures_count': mmdaClosures is int ? mmdaClosures : 0,
      'earthquakes': earthquakes is List ? earthquakes : [],
      'seismic_banner': seismicBanner.toString(),
      'weather_risk': weatherRisk.toString(),
      'flood_risk': floodRisk.toString(),
      // Resolved geocoded coordinates for A/B map pins
      'orig_lat': decoded['orig_lat'],
      'orig_lon': decoded['orig_lon'],
      'dest_lat': decoded['dest_lat'],
      'dest_lon': decoded['dest_lon'],
    };
  }

  Future<List<RouteModel>> searchRoutes({
    required String origin,
    required String destination,
    String mode = 'commute',
  }) async {
    try {
      final resp = await http
          .post(
            await _uriAsync('/api/routes'),
            headers: const {'Content-Type': 'application/json'},
            body: jsonEncode({
              'origin': origin,
              'destination': destination,
              'mode': mode,
            }),
          )
          .timeout(const Duration(seconds: 180));

      if (resp.statusCode != 200) return const [];

      final dynamic decoded = jsonDecode(resp.body);
      if (decoded is! Map<String, dynamic>) return const [];

      final routesJson = decoded['routes'];
      if (routesJson is! List) return const [];

      final List<RouteModel> result = [];
      for (var i = 0; i < routesJson.length; i++) {
        final r = routesJson[i];
        if (r is! Map<String, dynamic>) continue;
        result.add(_routeFromApi(i, r));
      }
      return result;
    } catch (_) {
      return const [];
    }
  }

  RouteModel _routeFromApi(int index, Map<String, dynamic> r) {
    final String timeStr = (r['time'] ?? '').toString();
    final String distanceStr = (r['distance'] ?? '').toString();
    final int minutes = _parseMinutes(timeStr);

    // Fare: attach_fares() in features.py overwrites route fare with a dict:
    //   { display: '₱13–₱18', min_fare: 13.0, max_fare: 18.0, note: '...', unit: 'PHP' }
    // When commuter_type has no fare rule (was missing 'transit'), returns:
    //   { display: 'N/A (private)', min_fare: null, ... }
    // We handle all cases and suppress non-useful display strings.
    final fareRaw = r['fare'];
    final int fare;
    String fareDisplay = '';

    if (fareRaw is num) {
      fare = fareRaw.round();
      fareDisplay = fare > 0 ? '₱$fare' : '';
    } else if (fareRaw is Map) {
      final minFare = fareRaw['min_fare'];
      final maxFare = fareRaw['max_fare'];
      final displayStr = (fareRaw['display'] ?? '').toString();

      // min_fare is None/null for private modes — treat as 0
      if (minFare == null) {
        fare = 0;
        // Suppress unhelpful strings like "N/A (private)"
        fareDisplay = '';
      } else if (minFare is num) {
        fare = minFare.round();
        // Use range display if available e.g. "₱13–₱18"
        if (displayStr.isNotEmpty &&
            !displayStr.contains('N/A') &&
            !displayStr.contains('private')) {
          fareDisplay = displayStr;
        } else if (maxFare is num && maxFare.round() != fare) {
          fareDisplay = '₱$fare–₱${maxFare.round()}';
        } else {
          fareDisplay = fare > 0 ? '₱$fare' : '';
        }
      } else {
        fare = 0;
        fareDisplay = '';
      }
    } else if (fareRaw is String) {
      // Plain string e.g. "PHP 17.71"
      final cleaned = fareRaw.replaceAll(RegExp(r'[^\d.]'), '');
      fare = double.tryParse(cleaned)?.round() ?? 0;
      fareDisplay = fare > 0 ? '₱$fare' : '';
    } else {
      fare = 0;
      fareDisplay = '';
    }

    final numScore = r['safety_score'] ?? 75;
    final int safetyScore = numScore is num ? numScore.round() : 75;

    final String modeLabelRaw =
        (r['mode_label'] ?? r['route_name'] ?? 'Route ${index + 1}').toString();
    final String modes = modeLabelRaw;

    // Position-based tag: route 0 = Fastest, 1 = Balanced, 2 = Safest
    final String tag = _tagFromIndex(index, safetyScore, r['tag'] as String?);

    // Strip any HTML tags from backend banner strings leaking into text fields
    final String safetyNote = _stripHtml(
      (r['safety_note'] ?? 'Safety score $safetyScore based on live risk data.')
          .toString(),
    );

    // Flood warning: only show if it indicates active flooding, not just
    // "flood-prone area — not currently raining" which is misleading
    final rawFlood = r['flood_warning'] as String?;
    final String? floodWarning =
        (rawFlood != null &&
            rawFlood.isNotEmpty &&
            !rawFlood.toLowerCase().contains('not currently raining'))
        ? rawFlood
        : null;

    // ── Build step list from segments (rich breakdown) ───────────────────
    final List<RouteStep> steps = _buildSteps(r, modes, timeStr, distanceStr);

    final List<List<double>> polyline = _extractPolyline(r);

    // Store raw segments for per-segment map coloring
    final rawSegsJson = r['segments'];
    final List<Map<String, dynamic>>? rawSegments = (rawSegsJson is List)
        ? rawSegsJson.whereType<Map<String, dynamic>>().toList()
        : null;

    // ── Merge endpoint crime warning + route-path zone warning ──────────────
    // crime_warning    → set by apply_crime_both_ends()  (origin/dest risk)
    // route_zones_warning → set by apply_route_crime_to_routes() (zones crossed)
    // Both are safety penalties that affect safety_score; surface both to user.
    final String? crimeWarning = _mergeWarnings(
      r['crime_warning'] as String?,
      r['route_zones_warning'] as String?,
    );

    return RouteModel(
      id: (r['id'] ?? 'route_$index').toString(),
      modes: modes,
      minutes: minutes,
      fare: fare,
      fareDisplay: fareDisplay,
      safetyScore: safetyScore,
      tag: tag,
      safetyNote: safetyNote,
      steps: steps,
      polyline: polyline,
      distance: distanceStr,
      rawSegments: rawSegments,
      commuterTags: const [],
      ligtasTags: const [],
      seismicWarning: r['seismic_warning'] as String?,
      floodWarning: floodWarning,
      crimeWarning: crimeWarning,
      profileWarnings: r['profile_warnings'] as List<dynamic>?,
      routeCrimeZones: (r['route_crime_zones'] is List)
          ? (r['route_crime_zones'] as List)
                .whereType<Map<String, dynamic>>()
                .toList()
          : null,
      floodZonesMap: (r['flood_zones_map'] is List)
          ? (r['flood_zones_map'] as List)
                .whereType<Map<String, dynamic>>()
                .toList()
          : null,
    );
  }

  /// Build a step list from backend segment data.
  /// Falls back to a single summary step when no segments are present.
  List<RouteStep> _buildSteps(
    Map<String, dynamic> r,
    String modes,
    String timeStr,
    String distanceStr,
  ) {
    final segments = r['segments'];
    if (segments is List && segments.isNotEmpty) {
      final steps = <RouteStep>[];
      for (final seg in segments) {
        if (seg is! Map<String, dynamic>) continue;
        final type = (seg['type'] ?? '').toString();
        final label = _stripHtml((seg['label'] ?? '').toString());
        if (label.isEmpty && type.isEmpty) continue;

        final String title;
        final String desc;
        switch (type) {
          case 'walk':
            title = label.isNotEmpty ? label : 'Walk';
            final walkDist = seg['distance']?.toString() ?? '';
            desc = walkDist.isNotEmpty ? walkDist : '';
            break;
          case 'train':
            title = label.isNotEmpty ? label : 'Train';
            final stations = seg['stations'] as List?;
            final sc = stations?.length ?? 0;
            desc = sc > 1 ? '$sc stations' : '';
            break;
          case 'jeepney':
            title = label.isNotEmpty ? label : 'Jeepney';
            desc = '';
            break;
          case 'bus':
            title = label.isNotEmpty ? label : 'Bus';
            desc = '';
            break;
          default:
            title = label.isNotEmpty ? label : type;
            desc = '';
        }
        steps.add(
          RouteStep(
            title: title,
            description: desc,
            vehicleName: type,
            crimeRisk: seg['crime_risk'] as String?,
            crimeNote: seg['crime_note'] as String?,
          ),
        );
      }
      if (steps.isNotEmpty) return steps;
    }

    // Fallback single step
    return [
      RouteStep(
        title: modes,
        description: [
          if (timeStr.isNotEmpty) timeStr,
          if (distanceStr.isNotEmpty) distanceStr,
        ].join(' · '),
      ),
    ];
  }

  List<List<double>> _extractPolyline(Map<String, dynamic> r) {
    final List<List<double>> pts = [];

    // 1. Direct coords: [ [lat, lon], ... ]
    final coords = r['coords'];
    if (coords is List && coords.isNotEmpty) {
      for (final p in coords) {
        if (p is List && p.length >= 2) {
          final lat = _toDouble(p[0]);
          final lon = _toDouble(p[1]);
          if (lat != null && lon != null) {
            pts.add([lat, lon]);
          }
        }
      }
    }

    // 2. Segment-based coords: segments[].coords may be a flat list or nested.
    if (pts.isEmpty) {
      final segments = r['segments'];
      if (segments is List) {
        for (final seg in segments) {
          if (seg is! Map<String, dynamic>) continue;
          final sc = seg['coords'];
          if (sc is List && sc.isNotEmpty) {
            // Either [[lat,lon], ...] or [[[lat,lon],...], ...]
            if (sc.first is List &&
                (sc.first as List).isNotEmpty &&
                (sc.first as List).first is List) {
              for (final sub in sc) {
                if (sub is List) {
                  for (final p in sub) {
                    if (p is List && p.length >= 2) {
                      final lat = _toDouble(p[0]);
                      final lon = _toDouble(p[1]);
                      if (lat != null && lon != null) {
                        pts.add([lat, lon]);
                      }
                    }
                  }
                }
              }
            } else {
              for (final p in sc) {
                if (p is List && p.length >= 2) {
                  final lat = _toDouble(p[0]);
                  final lon = _toDouble(p[1]);
                  if (lat != null && lon != null) {
                    pts.add([lat, lon]);
                  }
                }
              }
            }
          }
        }
      }
    }

    return pts;
  }

  int _parseMinutes(String s) {
    final lower = s.toLowerCase();
    if (lower.isEmpty) return 0;
    double total = 0;
    try {
      if (lower.contains('hr')) {
        final parts = lower.split('hr');
        final hStr = RegExp(r'[\d.]+').stringMatch(parts[0]) ?? '0';
        total += double.parse(hStr) * 60;
        if (parts.length > 1) {
          final mStr = RegExp(r'[\d.]+').stringMatch(parts[1]) ?? '0';
          total += double.parse(mStr);
        }
      } else {
        final mStr = RegExp(r'[\d.]+').stringMatch(lower) ?? '0';
        total = double.parse(mStr);
      }
    } catch (_) {
      return 0;
    }
    return total.round();
  }

  /// Derive a RouteModel tag from the backend `tag` field (if present)
  /// or from the safety score as a fallback.
  String _tagFromIndex(int index, int safetyScore, String? backendTag) {
    if (backendTag != null &&
        backendTag.isNotEmpty &&
        ['fastest', 'balanced', 'safest', 'cheapest'].contains(backendTag)) {
      return backendTag;
    }
    switch (index) {
      case 0:
        return 'fastest';
      case 1:
        return 'balanced';
      case 2:
        return 'safest';
      default:
        return safetyScore >= 75 ? 'balanced' : 'moderate';
    }
  }

  double? _toDouble(dynamic v) {
    if (v is double) return v;
    if (v is int) return v.toDouble();
    if (v is String) return double.tryParse(v);
    return null;
  }

  /// Strip HTML tags and decode common entities — cleans backend banner strings
  /// that occasionally leak into plain-text fields like safetyNote or labels.
  static String _stripHtml(String raw) {
    return raw
        .replaceAll(RegExp(r'<[^>]*>'), '')
        .replaceAll('&nbsp;', ' ')
        .replaceAll('&amp;', '&')
        .replaceAll('&lt;', '<')
        .replaceAll('&gt;', '>')
        .replaceAll('&quot;', '"')
        .trim();
  }

  /// Merges two nullable warning strings into one, separated by a newline.
  /// Returns null when both are empty/null (so the UI shows nothing).
  static String? _mergeWarnings(String? a, String? b) {
    final parts = [a, b]
        .where((s) => s != null && s.trim().isNotEmpty)
        .map((s) => _cleanWarningText(s!.trim()))
        .where((s) => s.isNotEmpty)
        .toList();
    if (parts.isEmpty) return null;
    return parts.join('\n');
  }

  /// Strip raw backend warning text to something readable.
  /// Backend sends: "⚠️ Jollibee, MCU EDSA: 🚨 High crime risk — keep doors locked | Also: long geocoded address..."
  /// We want: "High crime risk — keep doors locked, avoid isolated roads."
  static String _cleanWarningText(String raw) {
    // Remove everything after " | Also:" (geocoded address spam)
    var s = raw.split(RegExp(r'\s*\|\s*Also:')).first.trim();
    // Strip emoji characters
    s = s
        .replaceAll(RegExp(r'[\u{1F000}-\u{1FFFF}]', unicode: true), '')
        .trim();
    s = s.replaceAll(RegExp(r'[\u{2600}-\u{27BF}]', unicode: true), '').trim();
    // Strip location prefix "AreaName: warning" → keep only the warning
    final colonIdx = s.indexOf(': ');
    if (colonIdx > 0 && colonIdx < 60) {
      final prefix = s.substring(0, colonIdx);
      if (!prefix.toLowerCase().contains('risk') &&
          !prefix.toLowerCase().contains('crime')) {
        s = s.substring(colonIdx + 2).trim();
      }
    }
    return s.replaceAll(RegExp(r'\s{2,}'), ' ').trim();
  }

  // ── Forward geocoding ─────────────────────────────────────────────────────

  /// Forward-geocode a free-text query to coordinates.
  /// Tries progressively simplified variants of the query so that brand names
  /// and local shorthands (e.g. "Jollibee, MCU EDSA") still resolve even when
  /// the full string returns nothing from Nominatim.
  ///
  /// Used by the controller to set A/B pins BEFORE the full /api/routes
  /// call completes, so pins appear immediately on map regardless of whether
  /// routes can be fetched.
  Future<Map<String, double>?> geocodeText({
    required String query,
    String? token,
  }) async {
    final q = query.trim();
    if (q.isEmpty) return null;

    // Build a list of progressively simpler query variants to try in order.
    // e.g. "Jollibee, MCU EDSA" → ["Jollibee, MCU EDSA", "MCU EDSA", "EDSA"]
    final variants = _geocodeVariants(q);

    for (final variant in variants) {
      try {
        final uri = Uri.parse(
          '${await getBaseUrl()}/api/suggest',
        ).replace(queryParameters: {'q': variant});
        final resp = await http
            .get(uri, headers: _headers(token))
            .timeout(const Duration(seconds: 8));
        if (resp.statusCode != 200) continue;
        final dynamic decoded = jsonDecode(resp.body);
        if (decoded is! List || decoded.isEmpty) continue;
        final first = decoded.first;
        if (first is! Map<String, dynamic>) continue;
        final lat = _toDouble(first['lat']);
        final lon = _toDouble(first['lon']);
        if (lat == null || lon == null) continue;
        return {'lat': lat, 'lon': lon};
      } catch (_) {
        continue;
      }
    }
    return null;
  }

  /// Produces ordered query variants from most-specific to least-specific.
  /// Stops at 3 chars so we never send noise to the geocoder.
  static List<String> _geocodeVariants(String query) {
    final variants = <String>[query];
    // Split on commas and spaces to get sub-parts
    final parts = query
        .split(RegExp(r'[,]+'))
        .map((s) => s.trim())
        .where((s) => s.length >= 3)
        .toList();
    // Try each suffix: "A, B, C" → "B, C", "C"
    for (var i = 1; i < parts.length; i++) {
      final sub = parts.sublist(i).join(', ');
      if (sub.length >= 3 && !variants.contains(sub)) variants.add(sub);
    }
    // Also try individual words from the last part that look like landmarks
    if (parts.isNotEmpty) {
      final words = parts.last
          .split(RegExp(r'\s+'))
          .where((w) => w.length >= 4)
          .toList();
      for (final w in words) {
        if (!variants.contains(w)) variants.add(w);
      }
    }
    return variants;
  }

  // ── Authentication API methods ─────────────────────────────────────────────

  /// Register a new user account.
  Future<Map<String, dynamic>> register({
    required String username,
    required String password,
    String email = '',
  }) async {
    try {
      final uri = await _uriAsync('/api/auth/register');
      final resp = await http.post(
        uri,
        headers: const {'Content-Type': 'application/json'},
        body: jsonEncode({
          'username': username,
          'password': password,
          'email': email,
        }),
      ).timeout(const Duration(seconds: 15));

      final decoded = jsonDecode(resp.body);
      if (resp.statusCode != 201) {
        debugPrint('[REGISTER] Error: ${decoded['message']}');
        return {'ok': false, 'message': decoded['message'] ?? 'Registration failed'};
      }
      return decoded;
    } on TimeoutException catch (_) {
      debugPrint('[REGISTER] Timeout');
      return {'ok': false, 'message': 'Request timed out. Please try again.'};
    } on SocketException catch (_) {
      debugPrint('[REGISTER] SocketException');
      return {'ok': false, 'message': 'Cannot reach server. Check your connection.'};
    } catch (e) {
      debugPrint('[REGISTER] Exception: $e');
      return {'ok': false, 'message': e.toString().replaceFirst('Exception: ', '')};
    }
  }

  /// Login to an existing account.
  Future<Map<String, dynamic>> login({
    required String username,
    required String password,
  }) async {
    try {
      final uri = await _uriAsync('/api/auth/login');
      final resp = await http.post(
        uri,
        headers: const {'Content-Type': 'application/json'},
        body: jsonEncode({'username': username, 'password': password}),
      ).timeout(const Duration(seconds: 15));

      final decoded = jsonDecode(resp.body);
      if (resp.statusCode != 200) {
        debugPrint('[LOGIN] Error: ${decoded['message']}');
        return {'ok': false, 'message': decoded['message'] ?? 'Login failed'};
      }
      return decoded;
    } on TimeoutException catch (_) {
      debugPrint('[LOGIN] Timeout');
      return {'ok': false, 'message': 'Request timed out. Please try again.'};
    } on SocketException catch (_) {
      debugPrint('[LOGIN] SocketException');
      return {'ok': false, 'message': 'Cannot reach server. Check your connection.'};
    } catch (e) {
      debugPrint('[LOGIN] Exception: $e');
      return {'ok': false, 'message': e.toString().replaceFirst('Exception: ', '')};
    }
  }

  /// Fetch the authenticated user's profile (username, email, totp_enabled).
  Future<Map<String, dynamic>> getAuthMe({required String token}) async {
    try {
      final uri  = await _uriAsync('/api/auth/me');
      final resp = await http.get(
        uri,
        headers: {'Authorization': 'Bearer $token'},
      ).timeout(const Duration(seconds: 10));
      if (resp.statusCode != 200) return {'ok': false};
      return jsonDecode(resp.body) as Map<String, dynamic>;
    } catch (_) {
      return {'ok': false};
    }
  }

  /// Enable or disable 2FA for the current user.
  Future<Map<String, dynamic>> toggle2FA({
    required bool enable,
    required String token,
  }) async {
    try {
      final endpoint = enable ? '/api/auth/setup-2fa' : '/api/auth/disable-2fa';
      final uri = await _uriAsync(endpoint);
      final resp = await http.post(
        uri,
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $token',
        },
      ).timeout(const Duration(seconds: 15));
      final decoded = jsonDecode(resp.body);
      if (resp.statusCode != 200) {
        return {'ok': false, 'message': decoded['message'] ?? '2FA update failed'};
      }
      return decoded;
    } on TimeoutException catch (_) {
      return {'ok': false, 'message': 'Request timed out. Please try again.'};
    } on SocketException catch (_) {
      return {'ok': false, 'message': 'Cannot reach server. Check your connection.'};
    } catch (e) {
      return {'ok': false, 'message': e.toString().replaceFirst('Exception: ', '')};
    }
  }

  /// Verify OTP code during 2FA login.
  Future<Map<String, dynamic>> verify2FA({
    required String tempToken,
    required String otpCode,
  }) async {
    try {
      final uri = await _uriAsync('/api/auth/verify-2fa');
      final resp = await http.post(
        uri,
        headers: const {'Content-Type': 'application/json'},
        body: jsonEncode({'temp_token': tempToken, 'otp_code': otpCode}),
      ).timeout(const Duration(seconds: 15));
      final decoded = jsonDecode(resp.body);
      if (resp.statusCode != 200) {
        debugPrint('[2FA] Error: ${decoded['message']}');
        return {'ok': false, 'message': decoded['message'] ?? 'Verification failed'};
      }
      return decoded;
    } on TimeoutException catch (_) {
      debugPrint('[2FA] Timeout');
      return {'ok': false, 'message': 'Request timed out. Please try again.'};
    } on SocketException catch (_) {
      debugPrint('[2FA] SocketException');
      return {'ok': false, 'message': 'Cannot reach server. Check your connection.'};
    } catch (e) {
      debugPrint('[2FA] Exception: $e');
      return {'ok': false, 'message': e.toString().replaceFirst('Exception: ', '')};
    }
  }

  /// Logout from current session.
  Future<void> logout({String? token}) async {
    try {
      final headers = {
        'Content-Type': 'application/json',
        if (token != null) 'Authorization': 'Bearer $token',
      };

      await http.post(await _uriAsync('/api/auth/logout'), headers: headers);
    } catch (_) {
      // Logout errors are non-fatal, just best-effort
    }
  }

  /// Fetch current user profile and settings.
  Future<Map<String, dynamic>> getCurrentUser({String? token}) async {
    try {
      final headers = {
        'Content-Type': 'application/json',
        if (token != null) 'Authorization': 'Bearer $token',
      };

      final resp = await http.get(await _uriAsync('/api/user/current'), headers: headers);

      if (resp.statusCode != 200) {
        throw Exception('Failed to fetch user data');
      }

      final decoded = jsonDecode(resp.body);
      return decoded;
    } catch (e) {
      rethrow;
    }
  }

  /// Fetch community reports.
  Future<List<Map<String, dynamic>>> getReports({String? token}) async {
    try {
      final headers = {
        'Content-Type': 'application/json',
        if (token != null) 'Authorization': 'Bearer $token',
      };

      final resp = await http.get(await _uriAsync('/api/reports'), headers: headers);

      if (resp.statusCode != 200) {
        throw Exception('Failed to fetch reports');
      }

      final decoded = jsonDecode(resp.body);
      if (decoded is List) {
        return decoded.cast<Map<String, dynamic>>();
      }
      return [];
    } catch (e) {
      rethrow;
    }
  }

  /// Submit a community report.
  Future<Map<String, dynamic>> submitReport({
    required double lat,
    required double lon,
    required String reportType,
    required String description,
    String? token,
  }) async {
    try {
      final headers = {
        'Content-Type': 'application/json',
        if (token != null) 'Authorization': 'Bearer $token',
      };

      final resp = await http.post(
        await _uriAsync('/api/report'),
        headers: headers,
        body: jsonEncode({
          'lat': lat,
          'lon': lon,
          'report_type': reportType,
          'description': description,
        }),
      );

      return jsonDecode(resp.body);
    } catch (e) {
      rethrow;
    }
  }

  /// Upvote/confirm a community report.
  Future<Map<String, dynamic>> confirmReport({
    required int reportId,
    String? token,
  }) async {
    try {
      final headers = {
        'Content-Type': 'application/json',
        if (token != null) 'Authorization': 'Bearer $token',
      };

      final resp = await http.post(
        await _uriAsync('/api/reports/confirm'),
        headers: headers,
        body: jsonEncode({'report_id': reportId}),
      );

      return jsonDecode(resp.body);
    } catch (e) {
      rethrow;
    }
  }

  /// Fetch safety data for a location (weather, flood, crime, reports).
  Future<Map<String, dynamic>> getSafety({
    required double lat,
    required double lon,
    String? token,
  }) async {
    try {
      final headers = {
        'Content-Type': 'application/json',
        if (token != null) 'Authorization': 'Bearer $token',
      };

      final uri = Uri.parse(
        '${await getBaseUrl()}/api/safety',
      ).replace(queryParameters: {'lat': '$lat', 'lon': '$lon'});
      final resp = await http.get(uri, headers: headers);

      if (resp.statusCode != 200) {
        throw Exception('Failed to fetch safety data');
      }

      return jsonDecode(resp.body);
    } catch (e) {
      rethrow;
    }
  }

  /// Fetch safe spots (hospitals, police, pharmacies, etc.) near a coordinate.
  ///
  /// Calls GET /api/safe-spots/flutter?lat=&lon=&radius=
  ///
  /// Returns the decoded JSON map from the server:
  /// ```json
  /// {
  ///   "ok":    true,
  ///   "spots": [
  ///     { "id": "...", "name": "...", "type": "hospital",
  ///       "label": "Hospital", "lat": 14.57, "lon": 120.98,
  ///       "color": "#e74c3c", "priority": 1, "dist_m": 340 }
  ///   ]
  /// }
  /// ```
  /// Returns `{'ok': false, 'spots': []}` on any error — never throws.
  Future<Map<String, dynamic>> getSafeSpots({
    required double lat,
    required double lon,
    String? token,
    int radiusMeters = 1500,
  }) async {
    try {
      final headers = {
        'Content-Type': 'application/json',
        if (token != null) 'Authorization': 'Bearer $token',
      };

      final uri = Uri.parse('${await getBaseUrl()}/api/safe-spots/flutter').replace(
        queryParameters: {
          'lat': '$lat',
          'lon': '$lon',
          'radius': '$radiusMeters',
        },
      );
      final resp = await http.get(uri, headers: headers);

      if (resp.statusCode != 200) {
        return {'ok': false, 'spots': []};
      }

      final decoded = jsonDecode(resp.body);
      if (decoded is Map<String, dynamic>) return decoded;
      return {'ok': false, 'spots': []};
    } catch (e) {
      return {'ok': false, 'spots': []};
    }
  }

  /// Fetch report types available in the system.
  Future<List<Map<String, dynamic>>> getReportTypes({String? token}) async {
    try {
      final headers = {
        'Content-Type': 'application/json',
        if (token != null) 'Authorization': 'Bearer $token',
      };

      final resp = await http.get(await _uriAsync('/api/report-types'), headers: headers);

      if (resp.statusCode != 200) {
        throw Exception('Failed to fetch report types');
      }

      final decoded = jsonDecode(resp.body);
      if (decoded is List) {
        return decoded.cast<Map<String, dynamic>>();
      }
      return [];
    } catch (e) {
      rethrow;
    }
  }

  /// ────────────────────────────────────────────────────────────────────────
  /// NICE TO HAVE: Travel History & Account Management
  /// ────────────────────────────────────────────────────────────────────────

  /// Fetch user's route history.
  Future<List<Map<String, dynamic>>> getRouteHistory({String? token}) async {
    try {
      final headers = {
        'Content-Type': 'application/json',
        if (token != null) 'Authorization': 'Bearer $token',
      };

      final resp = await http.get(await _uriAsync('/api/history'), headers: headers);

      if (resp.statusCode != 200) {
        throw Exception('Failed to fetch route history');
      }

      final decoded = jsonDecode(resp.body);
      if (decoded is Map<String, dynamic>) {
        final historyList = decoded['history'];
        if (historyList is List) {
          return historyList.cast<Map<String, dynamic>>();
        }
      }
      return [];
    } catch (e) {
      rethrow;
    }
  }

  /// Clear user's route history.
  Future<Map<String, dynamic>> clearRouteHistory({String? token}) async {
    try {
      final headers = {
        'Content-Type': 'application/json',
        if (token != null) 'Authorization': 'Bearer $token',
      };

      final resp = await http.post(
        await _uriAsync('/api/history/clear'),
        headers: headers,
      );

      if (resp.statusCode != 200) {
        throw Exception('Failed to clear history');
      }

      return jsonDecode(resp.body);
    } catch (e) {
      rethrow;
    }
  }

  /// Change user's password.
  Future<Map<String, dynamic>> changePassword({
    required String currentPassword,
    required String newPassword,
    String? token,
  }) async {
    try {
      final headers = {
        'Content-Type': 'application/json',
        if (token != null) 'Authorization': 'Bearer $token',
      };

      final resp = await http.post(
        await _uriAsync('/api/auth/change-password'),
        headers: headers,
        body: jsonEncode({
          'current_password': currentPassword,
          'new_password': newPassword,
        }),
      );

      final decoded = jsonDecode(resp.body);
      if (resp.statusCode != 200) {
        throw Exception(decoded['message'] ?? 'Password change failed');
      }

      return decoded;
    } catch (e) {
      rethrow;
    }
  }

  /// Change user email (requires current password verification).
  /// Calls POST /api/auth/change-email
  Future<Map<String, dynamic>> changeEmail({
    required String currentPassword,
    required String newEmail,
    String? token,
  }) async {
    try {
      final headers = {
        'Content-Type': 'application/json',
        if (token != null) 'Authorization': 'Bearer $token',
      };

      final resp = await http.post(
        await _uriAsync('/api/auth/change-email'),
        headers: headers,
        body: jsonEncode({
          'current_password': currentPassword,
          'new_email':        newEmail,
        }),
      );

      final decoded = jsonDecode(resp.body);
      if (resp.statusCode != 200) {
        throw Exception(decoded['message'] ?? 'Email change failed');
      }

      return decoded;
    } catch (e) {
      rethrow;
    }
  }

  /// ────────────────────────────────────────────────────────────────────────
  /// WHAT NEEDS CONNECTION 🔗: SOS Emergency Contact Management
  /// ────────────────────────────────────────────────────────────────────────

  /// Fetch trusted SOS contacts for the current user.
  /// Returns empty list if unauthenticated or endpoint unavailable.
  Future<List<Map<String, dynamic>>> getSosContacts({String? token}) async {
    try {
      final headers = {
        'Content-Type': 'application/json',
        if (token != null) 'Authorization': 'Bearer $token',
      };

      final resp = await http.get(await _uriAsync('/api/sos/contacts'), headers: headers);

      // 401 = session not established yet — not an error, just not logged in
      if (resp.statusCode == 401) return [];
      if (resp.statusCode != 200) return [];

      final decoded = jsonDecode(resp.body);
      if (decoded is Map<String, dynamic>) {
        final contactsList = decoded['contacts'];
        if (contactsList is List) {
          return contactsList.cast<Map<String, dynamic>>();
        }
      }
      return [];
    } catch (e) {
      return []; // silently degrade — SOS contacts are non-critical on load
    }
  }

  /// Add a new trusted SOS contact.
  Future<Map<String, dynamic>> addSosContact({
    required String name,
    required String contactType, // 'phone', 'email', etc.
    required String contactValue,
    String? token,
  }) async {
    try {
      final headers = {
        'Content-Type': 'application/json',
        if (token != null) 'Authorization': 'Bearer $token',
      };

      final resp = await http.post(
        await _uriAsync('/api/sos/contacts'),
        headers: headers,
        body: jsonEncode({
          'name': name,
          'contact_type': contactType,
          'contact_value': contactValue,
        }),
      );

      if (resp.statusCode != 201 && resp.statusCode != 200) {
        throw Exception('Failed to add contact');
      }

      return jsonDecode(resp.body);
    } catch (e) {
      rethrow;
    }
  }

  /// Remove a trusted SOS contact.
  Future<Map<String, dynamic>> removeSosContact({
    required int contactId,
    String? token,
  }) async {
    try {
      final headers = {
        'Content-Type': 'application/json',
        if (token != null) 'Authorization': 'Bearer $token',
      };

      final resp = await http.delete(
        await _uriAsync('/api/sos/contacts/$contactId'),
        headers: headers,
      );

      if (resp.statusCode != 200) {
        throw Exception('Failed to remove contact');
      }

      return jsonDecode(resp.body);
    } catch (e) {
      rethrow;
    }
  }

  /// Trigger SOS emergency event.
  Future<Map<String, dynamic>> triggerSos({
    required double lat,
    required double lon,
    String message = 'SOS from SafeRoute user',
    String routeSummary = '',
    String? token,
  }) async {
    try {
      final headers = {
        'Content-Type': 'application/json',
        if (token != null) 'Authorization': 'Bearer $token',
      };

      final resp = await http.post(
        await _uriAsync('/api/sos'),
        headers: headers,
        body: jsonEncode({
          'lat': lat,
          'lon': lon,
          'message': message,
          'route_summary': routeSummary,
        }),
      );

      if (resp.statusCode != 200) {
        throw Exception('Failed to trigger SOS');
      }

      return jsonDecode(resp.body);
    } catch (e) {
      rethrow;
    }
  }

  /// ────────────────────────────────────────────────────────────────────────
  /// WHAT NEEDS CONNECTION 🔗: User Settings & Survey Persistence
  /// ────────────────────────────────────────────────────────────────────────

  /// Save user onboarding survey responses.
  Future<Map<String, dynamic>> saveSurvey({
    required List<String> commuterTypes,
    required List<String> transportModes,
    required List<String> safetyConcerns,
    String? token,
  }) async {
    try {
      final headers = {
        'Content-Type': 'application/json',
        if (token != null) 'Authorization': 'Bearer $token',
      };

      final resp = await http.post(
        await _uriAsync('/api/user/survey'),
        headers: headers,
        body: jsonEncode({
          'commuterTypes': commuterTypes,
          'transport': transportModes,
          'safety': safetyConcerns,
        }),
      );

      if (resp.statusCode != 200) {
        throw Exception('Failed to save survey');
      }

      return jsonDecode(resp.body);
    } catch (e) {
      rethrow;
    }
  }

  /// Fetch user settings from backend.
  Future<Map<String, dynamic>> getSettings({String? token}) async {
    try {
      final headers = {
        'Content-Type': 'application/json',
        if (token != null) 'Authorization': 'Bearer $token',
      };

      final resp = await http.get(await _uriAsync('/api/settings'), headers: headers);

      if (resp.statusCode != 200) {
        throw Exception('Failed to fetch settings');
      }

      return jsonDecode(resp.body);
    } catch (e) {
      rethrow;
    }
  }

  /// Save user settings to backend.
  Future<Map<String, dynamic>> saveSettings({
    required String defaultCommuterType,
    required List<String> transportPreference,
    bool showWeatherBanner = true,
    bool showCrimeBanner = true,
    bool showFloodBanner = true,
    String? displayName,
    String? email,
    String? token,
  }) async {
    try {
      final headers = {
        'Content-Type': 'application/json',
        if (token != null) 'Authorization': 'Bearer $token',
      };

      final body = {
        'default_commuter_type': defaultCommuterType,
        'transport_preference': transportPreference,
        'show_weather_banner': showWeatherBanner,
        'show_crime_banner': showCrimeBanner,
        'show_flood_banner': showFloodBanner,
        if (displayName != null) ...{'display_name': displayName},
        if (email != null) ...{'email': email},
      };

      final resp = await http.post(
        await _uriAsync('/api/settings'),
        headers: headers,
        body: jsonEncode(body),
      );

      if (resp.statusCode != 200) {
        throw Exception('Failed to save settings');
      }

      return jsonDecode(resp.body);
    } catch (e) {
      rethrow;
    }
  }

  // ── Reverse geocoding & autocomplete ──────────────────────────────────────

  /// GET /api/reverse?lat=&lon=
  /// Returns { "address": "string" }
  Future<Map<String, dynamic>> reverseGeocode({
    required double lat,
    required double lon,
    String? token,
  }) async {
    final uri = Uri.parse(
      '${await getBaseUrl()}/api/reverse',
    ).replace(queryParameters: {'lat': '$lat', 'lon': '$lon'});
    final resp = await http
        .get(uri, headers: _headers(token))
        .timeout(const Duration(seconds: 8));
    _checkStatus(resp);
    return jsonDecode(resp.body) as Map<String, dynamic>;
  }

  /// GET /api/suggest?q=
  /// Returns list of Nominatim place objects:
  ///   [{ display_name, address: { road, suburb, city }, lat, lon }, ...]
  Future<List<Map<String, dynamic>>> suggestLocations({
    required String query,
    String? token,
  }) async {
    final uri = Uri.parse(
      '${await getBaseUrl()}/api/suggest',
    ).replace(queryParameters: {'q': query});
    final resp = await http
        .get(uri, headers: _headers(token))
        .timeout(const Duration(seconds: 6));
    _checkStatus(resp);
    final list = jsonDecode(resp.body) as List;
    return list.cast<Map<String, dynamic>>();
  }

  /// GET /api/mmda
  /// Returns { coding, closures, closures_count, mmda_banner }
  Future<Map<String, dynamic>> getMmda({String? token}) async {
    final resp = await http
      .get(Uri.parse('${await getBaseUrl()}/api/mmda'), headers: _headers(token))
        .timeout(const Duration(seconds: 8));
    _checkStatus(resp);
    return jsonDecode(resp.body) as Map<String, dynamic>;
  }

  // ── Private helpers ────────────────────────────────────────────────────────

  Map<String, String> _headers(String? token) => {
    'Content-Type': 'application/json',
    if (token != null) 'Authorization': 'Bearer $token',
  };

  void _checkStatus(http.Response resp) {
    if (resp.statusCode < 200 || resp.statusCode >= 300) {
      throw Exception('Backend returned ${resp.statusCode}');
    }
  }

  /// Fetch location suggestions from backend Nominatim proxy.
  /// Returns up to 6 results as [MiniItem]s (type=pin).
  /// Falls back to empty list on any error or if query is < 3 chars.
  Future<List<MiniItem>> getSuggestions(String query) async {
    if (query.trim().length < 3) return const [];
    try {
      final resp = await http
          .get(await _uriAsync('/api/suggest?q=${Uri.encodeComponent(query.trim())}'))
          .timeout(const Duration(seconds: 6));
      if (resp.statusCode != 200) return const [];
      final decoded = jsonDecode(resp.body);
      if (decoded is! List) return const [];
      return decoded.take(6).map<MiniItem>((item) {
        final fullName = item['display_name']?.toString() ?? '';
        final parts = fullName.split(',');
        final name = parts.first.trim();
        final sub = parts.length > 1
            ? parts.skip(1).take(2).join(',').trim()
            : '';
        return MiniItem(
          type: MiniItemType.pin,
          name: name.isEmpty ? fullName : name,
          sub: sub,
        );
      }).toList();
    } catch (_) {
      return const [];
    }
  }

  /// Fetch nearby transit options (jeepneys, buses, MRT stops) around a point.
  /// Returns raw list from `/api/nearby?lat=&lon=&radius=800`.
  Future<List<Map<String, dynamic>>> getNearby({
    required double lat,
    required double lon,
    double radius = 800,
  }) async {
    try {
      final resp = await http
          .get(await _uriAsync('/api/nearby?lat=$lat&lon=$lon&radius=$radius'))
          .timeout(const Duration(seconds: 6));
      if (resp.statusCode != 200) return const [];
      final decoded = jsonDecode(resp.body);
      if (decoded is List) return decoded.cast<Map<String, dynamic>>();
      return const [];
    } catch (_) {
      return const [];
    }
  }

  /// GET /api/community/weather?lat=&lon=
  /// Returns { ok, current: {...}, flood: {...}, forecast: [...] }
  /// Falls back to empty map on any error.
  Future<Map<String, dynamic>> getCommunityWeather({
    required double lat,
    required double lon,
    String? token,
  }) async {
    try {
      final base = await getBaseUrl();
      final uri = Uri.parse('$base/api/community/weather').replace(
        queryParameters: {'lat': lat.toString(), 'lon': lon.toString()},
      );
      final resp = await http
          .get(uri, headers: _headers(token))
          .timeout(const Duration(seconds: 10));
      if (resp.statusCode != 200) return const {};
      final decoded = jsonDecode(resp.body);
      if (decoded is! Map<String, dynamic>) return const {};
      return decoded;
    } catch (_) {
      return const {};
    }
  }

  /// GET /api/community/news
  /// Returns list of official news items from PAGASA, MMDA, NDRRMC sources.
  /// Falls back to empty list on any error.
  Future<List<Map<String, dynamic>>> getOfficialNews({String? token}) async {
    try {
      final base = await getBaseUrl();
      final resp = await http
          .get(
            Uri.parse('$base/api/community/news'),
            headers: _headers(token),
          )
          .timeout(const Duration(seconds: 10));
      if (resp.statusCode != 200) return const [];
      final decoded = jsonDecode(resp.body);
      if (decoded is! Map<String, dynamic>) return const [];
      final items = decoded['items'];
      if (items is List) return items.cast<Map<String, dynamic>>();
      return const [];
    } catch (_) {
      return const [];
    }
  }

  /// GET /api/notifications[?since=<unix_epoch_seconds>]
  /// Returns aggregated real-time notifications from backend sources.
  /// Pass [since] (epoch seconds) to receive only newer items on incremental polls.
  /// Falls back to empty list on any error.
  Future<List<Map<String, dynamic>>> getNotifications({
    String? token,
    double? since,
  }) async {
    try {
      final qp = <String, String>{};
      if (since != null && since > 0) qp['since'] = since.toStringAsFixed(3);
      final base = await getBaseUrl();
      final uri = Uri.parse('$base/api/notifications').replace(queryParameters: qp.isEmpty ? null : qp);
      final resp = await http
          .get(uri, headers: _headers(token))
          .timeout(const Duration(seconds: 10));
      if (resp.statusCode != 200) return const [];
      final decoded = jsonDecode(resp.body);
      if (decoded is! Map<String, dynamic>) return const [];
      final items = decoded['notifications'];
      if (items is List) return items.cast<Map<String, dynamic>>();
      return const [];
    } catch (_) {
      return const [];
    }
  }
}