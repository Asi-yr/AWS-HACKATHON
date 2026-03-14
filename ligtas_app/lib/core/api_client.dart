import 'dart:convert';

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

  /// Base URL of the Flask backend.
  ///
  /// - On Android emulator, `10.0.2.2` points to the host machine.
  /// - On iOS simulator or real devices, change this to your machine's LAN IP,
  ///   e.g. `http://192.168.1.10:5000`.
  static const String baseUrl = 'http://localhost:5000';

  Uri _uri(String path) => Uri.parse('$baseUrl$path');

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
    final resp = await http.post(
      _uri('/api/routes'),
      headers: const {'Content-Type': 'application/json'},
      body: jsonEncode({
        'origin': origin,
        'destination': destination,
        'mode': mode,
        ...?extraParams,
      }),
    ).timeout(const Duration(seconds: 90));

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
        'error': (decoded['error'] ?? decoded['message'] ?? 'No route found (${resp.statusCode})').toString(),
        'incidents': <dynamic>[],
        'mmda_banner': '',
        'mmda_closures_count': 0,
        'earthquakes': <dynamic>[],
        'seismic_banner': '',
        'weather_risk': 'clear',
        'flood_risk': 'none',
        'orig_lat': null,
        'orig_lon': null,
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
      final resp = await http.post(
        _uri('/api/routes'),
        headers: const {'Content-Type': 'application/json'},
        body: jsonEncode({
          'origin': origin,
          'destination': destination,
          'mode': mode,
        }),
      ).timeout(const Duration(seconds: 90));

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

    // ── Fare: backend sends either a plain num OR { display, value } ──────
    final fareRaw = r['fare'];
    final int fare;
    if (fareRaw is num) {
      fare = fareRaw.round();
    } else if (fareRaw is Map) {
      final v = fareRaw['value'];
      fare = v is num ? v.round() : 0;
    } else {
      fare = 0;
    }

    final numScore = r['safety_score'] ?? 75;
    final int safetyScore = numScore is num ? numScore.round() : 75;

    final String modeLabelRaw =
        (r['mode_label'] ?? r['route_name'] ?? 'Route ${index + 1}').toString();
    final String modes = modeLabelRaw;

    final String tag = _tagFromScore(safetyScore, r['tag'] as String?);

    final String safetyNote =
        (r['safety_note'] ??
                'Safety score $safetyScore based on live risk data.')
            .toString();

    // ── Build step list from segments (rich breakdown) ───────────────────
    final List<RouteStep> steps = _buildSteps(r, modes, timeStr, distanceStr);

    final List<List<double>> polyline = _extractPolyline(r);

    return RouteModel(
      id: (r['id'] ?? 'route_$index').toString(),
      modes: modes,
      minutes: minutes,
      fare: fare,
      safetyScore: safetyScore,
      tag: tag,
      safetyNote: safetyNote,
      steps: steps,
      polyline: polyline,
      commuterTags: const [],
      ligtasTags: const [],
      seismicWarning: r['seismic_warning'] as String?,
      floodWarning: r['flood_warning'] as String?,
      crimeWarning: r['crime_warning'] as String?,
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
        final label = (seg['label'] ?? '').toString();
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
        steps.add(RouteStep(title: title, description: desc, vehicleName: type));
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
  String _tagFromScore(int safetyScore, String? backendTag) {
    if (backendTag != null && backendTag.isNotEmpty) return backendTag;
    if (safetyScore >= 85) return 'safest';
    if (safetyScore >= 75) return 'balanced';
    if (safetyScore >= 65) return 'moderate';
    return 'dangerous';
  }

  double? _toDouble(dynamic v) {
    if (v is double) return v;
    if (v is int) return v.toDouble();
    if (v is String) {
      return double.tryParse(v);
    }
    return null;
  }

  // ── Authentication API methods ─────────────────────────────────────────────

  /// Register a new user account.
  Future<Map<String, dynamic>> register({
    required String username,
    required String password,
    String email = '',
  }) async {
    try {
      final resp = await http.post(
        _uri('/api/auth/register'),
        headers: const {'Content-Type': 'application/json'},
        body: jsonEncode({
          'username': username,
          'password': password,
          'email': email,
        }),
      );

      final decoded = jsonDecode(resp.body);
      if (resp.statusCode != 201) {
        throw Exception(decoded['message'] ?? 'Registration failed');
      }
      return decoded;
    } catch (e) {
      rethrow;
    }
  }

  /// Login to an existing account.
  Future<Map<String, dynamic>> login({
    required String username,
    required String password,
  }) async {
    try {
      final resp = await http.post(
        _uri('/api/auth/login'),
        headers: const {'Content-Type': 'application/json'},
        body: jsonEncode({'username': username, 'password': password}),
      );

      final decoded = jsonDecode(resp.body);
      if (resp.statusCode != 200) {
        throw Exception(decoded['message'] ?? 'Login failed');
      }
      return decoded;
    } catch (e) {
      rethrow;
    }
  }

  /// Logout from current session.
  Future<void> logout({String? token}) async {
    try {
      final headers = {
        'Content-Type': 'application/json',
        if (token != null) 'Authorization': 'Bearer $token',
      };

      await http.post(_uri('/api/auth/logout'), headers: headers);
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

      final resp = await http.get(_uri('/api/user/current'), headers: headers);

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

      final resp = await http.get(_uri('/api/reports'), headers: headers);

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
        _uri('/api/report'),
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
        _uri('/api/reports/confirm'),
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
        '$baseUrl/api/safety',
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

      final uri = Uri.parse('$baseUrl/api/safe-spots/flutter').replace(
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

      final resp = await http.get(_uri('/api/report-types'), headers: headers);

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

      final resp = await http.get(_uri('/api/history'), headers: headers);

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
        _uri('/api/history/clear'),
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
        _uri('/api/auth/change-password'),
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

      final resp = await http.get(_uri('/api/sos/contacts'), headers: headers);

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
        _uri('/api/sos/contacts'),
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
        _uri('/api/sos/contacts/$contactId'),
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
        _uri('/api/sos'),
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
        _uri('/api/user/survey'),
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

      final resp = await http.get(_uri('/api/settings'), headers: headers);

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
        _uri('/api/settings'),
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
      '$baseUrl/api/reverse',
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
      '$baseUrl/api/suggest',
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
        .get(Uri.parse('$baseUrl/api/mmda'), headers: _headers(token))
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
}