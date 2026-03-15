import 'package:flutter/material.dart';
import '../core/app_colors.dart';

// ── App State ────────────────────────────────────────────────────
enum AppState { state1, mini, state2, state3, state4 }

// ── Route Model ──────────────────────────────────────────────────
class RouteStep {
  final String title;
  final String description;
  final String vehicleName;

  /// Per-step crime risk injected by annotate_segments_with_crime() on the
  /// backend. Values: 'high' | 'moderate' | 'low' | 'none' | null.
  /// Null means the backend has not annotated this step (e.g. mock data).
  final String? crimeRisk;

  /// Short human-readable note from crime_zones.json for this segment.
  /// Empty string when the zone has no summary or risk is 'none'.
  final String? crimeNote;

  const RouteStep({
    required this.title,
    this.description = '',
    this.vehicleName = '',
    this.crimeRisk,
    this.crimeNote,
  });
}

class RouteModel {
  final String id;
  final String modes;
  final int minutes;
  final int fare;

  /// Human-readable fare range e.g. "₱13–₱18" from backend estimate_fare()
  final String fareDisplay;
  final int safetyScore;
  final String tag;
  final String safetyNote;
  final List<RouteStep> steps;
  final List<List<double>> polyline;

  /// Which commuter types this route is suitable for.
  /// Match these strings against the keys in commuterOptions in mock_data.dart.
  /// e.g. ['normal', 'student', 'women', 'lgbtq', 'disabled', 'minor']
  ///
  /// BACKEND HOOK: populate from your API response.
  final List<String> commuterTags;

  /// Which Ligtas safety features this route has.
  /// Match against the keys in ligtasFeatures in mock_data.dart.
  /// e.g. ['cctv', 'lit', 'patrol', 'emergency', 'crowded', 'reported']
  ///
  /// BACKEND HOOK: populate from your API response.
  final List<String> ligtasTags;

  // ── Live risk warnings from the /api/routes backend pipeline ───────────────
  // All nullable — the detail panel shows nothing when these are null/empty.
  //   seismicWarning  ← phivolcs.py  (apply_seismic_to_routes)
  //   floodWarning    ← noah.py       (apply_route_flood_analysis)
  //   crimeWarning    ← crime_data.py (apply_route_crime_to_routes)
  //   profileWarnings ← vulnerable_profiles.py (list of strings)
  /// Human-readable distance e.g. "7.1 km" from backend
  final String distance;

  /// Raw segment list for per-segment map coloring
  final List<Map<String, dynamic>>? rawSegments;

  final String? seismicWarning;
  final String? floodWarning;
  final String? crimeWarning;
  final List<dynamic>? profileWarnings;

  // ── Map overlay zone data (populated by _routeFromApi in api_client.dart) ──
  //   routeCrimeZones ← route_crime_zones from backend
  //     each entry: { risk: 'high'|'moderate', name, summary,
  //                   coords: [latMin, latMax, lonMin, lonMax] }
  //   floodZonesMap   ← flood_zones_map from backend
  //     each entry: { lat, lon, risk: 'high'|'moderate'|'low',
  //                   label, depth_m, rain_active }
  final List<Map<String, dynamic>>? routeCrimeZones;
  final List<Map<String, dynamic>>? floodZonesMap;

  const RouteModel({
    required this.id,
    required this.modes,
    required this.minutes,
    required this.fare,
    this.fareDisplay = '',
    required this.safetyScore,
    required this.tag,
    required this.safetyNote,
    required this.steps,
    required this.polyline,
    this.distance = '',
    this.rawSegments,
    this.commuterTags = const [],
    this.ligtasTags = const [],
    // Warning fields — null by default so all existing mock data is unaffected.
    this.seismicWarning,
    this.floodWarning,
    this.crimeWarning,
    this.profileWarnings,
    this.routeCrimeZones,
    this.floodZonesMap,
  });

  SafetyMeta get safetyMeta {
    if (safetyScore >= 85) {
      return SafetyMeta(color: AppColors.safeGreen, label: 'Safe');
    }
    if (safetyScore >= 70) {
      return SafetyMeta(color: AppColors.safeAmber, label: 'Moderate');
    }
    return SafetyMeta(color: AppColors.safeRed, label: 'Caution');
  }

  TagMeta get tagMeta {
    const map = {
      'fastest': TagMeta(
        bg: AppColors.tagFastest,
        fg: Colors.white,
        label: 'Fastest',
      ),
      'balanced': TagMeta(
        bg: AppColors.tagBalanced,
        fg: Colors.white,
        label: 'Balanced',
      ),
      'cheapest': TagMeta(
        bg: AppColors.tagCheapest,
        fg: Color(0xFF0F1F35),
        label: 'Cheapest',
      ),
      'safest': TagMeta(
        bg: AppColors.tagSafest,
        fg: Color(0xFF0F1F35),
        label: 'Safest',
      ),
      'moderate': TagMeta(
        bg: AppColors.tagModerate,
        fg: Colors.white,
        label: 'Moderate',
      ),
      'dangerous': TagMeta(
        bg: AppColors.tagDanger,
        fg: Colors.white,
        label: 'Dangerous',
      ),
    };
    return map[tag] ??
        TagMeta(bg: AppColors.teal, fg: Colors.white, label: tag);
  }
}

class SafetyMeta {
  final Color color;
  final String label;
  const SafetyMeta({required this.color, required this.label});
  Color get bgColor => color.withValues(alpha: 0.12);
}

class TagMeta {
  final Color bg;
  final Color fg;
  final String label;
  const TagMeta({required this.bg, required this.fg, required this.label});
}

// ── Filter Option ────────────────────────────────────────────────
class FilterOption {
  final String key;
  final String label;
  final IconData icon;
  const FilterOption({
    required this.key,
    required this.label,
    required this.icon,
  });
}

// ── Address Suggestion ───────────────────────────────────────────
class AddressSuggestion {
  final String address;
  final String district;
  const AddressSuggestion({required this.address, required this.district});
}

// ── Mini List Item ───────────────────────────────────────────────
enum MiniItemType { clock, home, heart, pin }

class MiniItem {
  final MiniItemType type;
  final String name;
  final String sub;
  const MiniItem({required this.type, required this.name, required this.sub});

  IconData get icon {
    switch (type) {
      case MiniItemType.clock:
        return Icons.history_rounded;
      case MiniItemType.home:
        return Icons.home_rounded;
      case MiniItemType.heart:
        return Icons.favorite_rounded;
      case MiniItemType.pin:
        return Icons.place_rounded;
    }
  }
}
