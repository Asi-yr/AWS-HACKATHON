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
}

