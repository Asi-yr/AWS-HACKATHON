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
  static const String baseUrl = 'http://10.0.2.2:5000';

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
  }) async {
    final resp = await http.post(
      _uri('/api/routes'),
      headers: const {'Content-Type': 'application/json'},
      body: jsonEncode({
        'origin': origin,
        'destination': destination,
        'mode': mode,
      }),
    );

    if (resp.statusCode != 200) {
      throw Exception('Backend returned ${resp.statusCode}');
    }

    final dynamic decoded = jsonDecode(resp.body);
    if (decoded is! Map<String, dynamic>) {
      throw Exception('Unexpected /api/routes payload shape');
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
    };
  }

  /// Original method for backward compatibility.
  /// Call the backend `/api/routes` endpoint and adapt the result into
  /// the app's `RouteModel` shape used by ExploreView.
  Future<List<RouteModel>> searchRoutes({
    required String origin,
    required String destination,
    String mode = 'commute',
  }) async {
    final resp = await http.post(
      _uri('/api/routes'),
      headers: const {'Content-Type': 'application/json'},
      body: jsonEncode({
        'origin': origin,
        'destination': destination,
        // The backend accepts `mode` or `commuterType`.
        'mode': mode,
      }),
    );

    if (resp.statusCode != 200) {
      throw Exception('Backend returned ${resp.statusCode}');
    }

    final dynamic decoded = jsonDecode(resp.body);
    if (decoded is! Map<String, dynamic>) {
      throw Exception('Unexpected /api/routes payload shape');
    }

    final routesJson = decoded['routes'];
    if (routesJson is! List) {
      return const [];
    }

    final List<RouteModel> result = [];
    for (var i = 0; i < routesJson.length; i++) {
      final r = routesJson[i];
      if (r is! Map<String, dynamic>) continue;
      result.add(_routeFromApi(i, r));
    }
    return result;
  }

  RouteModel _routeFromApi(int index, Map<String, dynamic> r) {
    final String timeStr = (r['time'] ?? '').toString();
    final String distanceStr = (r['distance'] ?? '').toString();
    final int minutes = _parseMinutes(timeStr);

    final numFare = r['fare'];
    final int fare = numFare is num ? numFare.round() : 0;

    final numScore = r['safety_score'] ?? 75;
    final int safetyScore = numScore is num ? numScore.round() : 75;

    final String modeLabelRaw =
        (r['mode_label'] ?? r['route_name'] ?? 'Route ${index + 1}').toString();
    final String modes = modeLabelRaw;

    final String tag = _tagFromModeLabel(modeLabelRaw);

    final String safetyNote =
        (r['safety_note'] ?? 'Safety score $safetyScore based on live risk data.')
            .toString();

    // Basic step list: keep it simple and let the design drive the text.
    final List<RouteStep> steps = [
      RouteStep(
        title: modes,
        description: [
          if (timeStr.isNotEmpty) timeStr,
          if (distanceStr.isNotEmpty) distanceStr,
        ].join(' · '),
      ),
    ];

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
      // Back-end does not yet expose explicit commuter/ligtas tags.
      commuterTags: const [],
      ligtasTags: const [],
      // ── Live risk warnings from /api/routes pipeline ──────────────────────
      seismicWarning:  r['seismic_warning']  as String?,
      floodWarning:    r['flood_warning']    as String?,
      crimeWarning:    r['crime_warning']    as String?,
      profileWarnings: r['profile_warnings'] as List<dynamic>?,
    );
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
            if (sc.first is List && (sc.first as List).isNotEmpty && (sc.first as List).first is List) {
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

  String _tagFromModeLabel(String modeLabel) {
    final lower = modeLabel.toLowerCase();
    if (lower.contains('fastest')) return 'fastest';
    if (lower.contains('balanced')) return 'balanced';
    if (lower.contains('only route')) return 'balanced';
    if (lower.contains('alternate')) return 'moderate';
    return 'balanced';
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
        body: jsonEncode({
          'username': username,
          'password': password,
        }),
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

      await http.post(
        _uri('/api/auth/logout'),
        headers: headers,
      );
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

      final resp = await http.get(
        _uri('/api/user/current'),
        headers: headers,
      );

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

      final resp = await http.get(
        _uri('/api/reports'),
        headers: headers,
      );

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
    required double lng,
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
        _uri('/api/report'),  // Note: check if backend uses /report or /api/report
        headers: headers,
        body: jsonEncode({
          'lat': lat,
          'lon': lng,
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

      final resp = await http.get(
        _uri('/api/safety?lat=$lat&lon=$lon'),
        headers: headers,
      );

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

      final resp = await http.get(
        _uri('/api/safe-spots/flutter?lat=$lat&lon=$lon&radius=$radiusMeters'),
        headers: headers,
      );

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

      final resp = await http.get(
        _uri('/api/report-types'),
        headers: headers,
      );

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

      final resp = await http.get(
        _uri('/api/history'),
        headers: headers,
      );

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
  Future<List<Map<String, dynamic>>> getSosContacts({String? token}) async {
    try {
      final headers = {
        'Content-Type': 'application/json',
        if (token != null) 'Authorization': 'Bearer $token',
      };

      final resp = await http.get(
        _uri('/api/sos/contacts'),
        headers: headers,
      );

      if (resp.statusCode != 200) {
        throw Exception('Failed to fetch SOS contacts');
      }

      final decoded = jsonDecode(resp.body);
      if (decoded is Map<String, dynamic>) {
        final contactsList = decoded['contacts'];
        if (contactsList is List) {
          return contactsList.cast<Map<String, dynamic>>();
        }
      }
      return [];
    } catch (e) {
      rethrow;
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

      final resp = await http.get(
        _uri('/api/settings'),
        headers: headers,
      );

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
        if (displayName != null) ...
          {'display_name': displayName},
        if (email != null) ...
          {'email': email},
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

  /// Submit a community report (JSON API version).
  /// Note: This fixes the endpoint path to /api/report (JSON version).
  Future<Map<String, dynamic>> submitReportJson({
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
        _uri('/api/report'),  // JSON API version
        headers: headers,
        body: jsonEncode({
          'lat': lat,
          'lon': lon,
          'report_type': reportType,
          'description': description,
        }),
      );

      final decoded = jsonDecode(resp.body);
      if (resp.statusCode != 200) {
        throw Exception(decoded['message'] ?? 'Failed to submit report');
      }

      return decoded;
    } catch (e) {
      rethrow;
    }
  }
}