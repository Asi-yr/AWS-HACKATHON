import 'package:flutter/material.dart';
import '../core/app_colors.dart';

// ── App State ────────────────────────────────────────────────────
enum AppState { state1, mini, state2, state3, state4 }

// ── Route Model ──────────────────────────────────────────────────
class RouteStep {
  final String title;
  final String description;
  final String vehicleName;
  const RouteStep({
    required this.title,
    this.description = '',
    this.vehicleName = '',
  });
}

class RouteModel {
  final String id;
  final String modes;
  final int minutes;
  final int fare;
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

  const RouteModel({
    required this.id,
    required this.modes,
    required this.minutes,
    required this.fare,
    required this.safetyScore,
    required this.tag,
    required this.safetyNote,
    required this.steps,
    required this.polyline,
    // Default to empty lists so existing RouteModel usages don't break.
    // Fill these in mock_data.dart (and eventually your API layer) for
    // filtering to actually work.
    this.commuterTags = const [],
    this.ligtasTags   = const [],
  });

  SafetyMeta get safetyMeta {
    if (safetyScore >= 85) return SafetyMeta(color: AppColors.safeGreen, label: 'Safe');
    if (safetyScore >= 70) return SafetyMeta(color: AppColors.safeAmber, label: 'Moderate');
    return SafetyMeta(color: AppColors.safeRed, label: 'Caution');
  }

  TagMeta get tagMeta {
    const map = {
      'fastest':   TagMeta(bg: AppColors.tagFastest,  fg: Colors.white,       label: 'Fastest'),
      'balanced':  TagMeta(bg: AppColors.tagBalanced,  fg: Colors.white,       label: 'Balanced'),
      'cheapest':  TagMeta(bg: AppColors.tagCheapest,  fg: Color(0xFF0F1F35), label: 'Cheapest'),
      'safest':    TagMeta(bg: AppColors.tagSafest,    fg: Color(0xFF0F1F35), label: 'Safest'),
      'moderate':  TagMeta(bg: AppColors.tagModerate,  fg: Colors.white,       label: 'Moderate'),
      'dangerous': TagMeta(bg: AppColors.tagDanger,    fg: Colors.white,       label: 'Dangerous'),
    };
    return map[tag] ?? TagMeta(bg: AppColors.teal, fg: Colors.white, label: tag);
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
  const FilterOption({required this.key, required this.label, required this.icon});
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
      case MiniItemType.clock: return Icons.history_rounded;
      case MiniItemType.home:  return Icons.home_rounded;
      case MiniItemType.heart: return Icons.favorite_rounded;
      case MiniItemType.pin:   return Icons.place_rounded;
    }
  }
}