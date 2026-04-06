import 'package:shared_preferences/shared_preferences.dart';

import '../models/explore_models.dart';

/// Persists recent searches and saved places using SharedPreferences.
///
/// Recents  — last 10 destinations the user navigated to (MiniItemType.clock).
/// Saved    — places the user explicitly bookmarked (MiniItemType.pin).
class SearchHistoryService {
  static const _recentKey = 'search_recents_v1';
  static const _savedKey = 'search_saved_v1';
  static const _maxRecents = 10;

  // Unit-separator character as field delimiter (safe inside normal place names).
  static const _sep = '\x1f';

  SearchHistoryService._();
  static final SearchHistoryService instance = SearchHistoryService._();

  // ── Read ─────────────────────────────────────────────────────

  Future<List<MiniItem>> loadRecents() async {
    final prefs = await SharedPreferences.getInstance();
    return (prefs.getStringList(_recentKey) ?? [])
        .map(_decode)
        .whereType<MiniItem>()
        .toList();
  }

  Future<List<MiniItem>> loadSaved() async {
    final prefs = await SharedPreferences.getInstance();
    return (prefs.getStringList(_savedKey) ?? [])
        .map(_decode)
        .whereType<MiniItem>()
        .toList();
  }

  // ── Write ────────────────────────────────────────────────────

  Future<void> addRecent(String name, String sub, {double? lat, double? lon}) async {
    if (name.trim().isEmpty) return;
    final prefs = await SharedPreferences.getInstance();
    var raw = prefs.getStringList(_recentKey) ?? [];
    // Deduplicate — keep the latest position
    raw.removeWhere((e) => _decodeName(e) == name);
    raw.insert(0, _encode(MiniItemType.clock, name, sub, lat: lat, lon: lon));
    if (raw.length > _maxRecents) raw = raw.sublist(0, _maxRecents);
    await prefs.setStringList(_recentKey, raw);
  }

  /// Removes [name] from recents. No-op if not present.
  Future<void> removeRecent(String name) async {
    final prefs = await SharedPreferences.getInstance();
    var raw = prefs.getStringList(_recentKey) ?? [];
    raw.removeWhere((e) => _decodeName(e) == name);
    await prefs.setStringList(_recentKey, raw);
  }

  /// Adds or removes [name] from saved places.
  /// Returns `true` if the item is now saved, `false` if it was removed.
  Future<bool> toggleSaved(String name, String sub, {double? lat, double? lon}) async {
    final prefs = await SharedPreferences.getInstance();
    var raw = prefs.getStringList(_savedKey) ?? [];
    final idx = raw.indexWhere((e) => _decodeName(e) == name);
    if (idx >= 0) {
      raw.removeAt(idx);
      await prefs.setStringList(_savedKey, raw);
      return false;
    } else {
      raw.insert(0, _encode(MiniItemType.pin, name, sub, lat: lat, lon: lon));
      await prefs.setStringList(_savedKey, raw);
      return true;
    }
  }

  Future<bool> isSaved(String name) async {
    final prefs = await SharedPreferences.getInstance();
    return (prefs.getStringList(_savedKey) ?? [])
        .any((e) => _decodeName(e) == name);
  }

  // ── Encoding ─────────────────────────────────────────────────
  // Format: type\x1fname\x1fsub[\x1flat\x1flon]
  // Lat/lon fields are optional — old 3-field entries are still decoded.

  String _encode(MiniItemType type, String name, String sub, {double? lat, double? lon}) {
    final base = '${type == MiniItemType.pin ? 'pin' : 'clock'}$_sep$name$_sep$sub';
    if (lat != null && lon != null) {
      return '$base$_sep$lat$_sep$lon';
    }
    return base;
  }

  MiniItem? _decode(String raw) {
    final parts = raw.split(_sep);
    if (parts.length < 3) return null;
    final type = parts[0] == 'pin' ? MiniItemType.pin : MiniItemType.clock;
    final lat = parts.length >= 5 ? double.tryParse(parts[3]) : null;
    final lon = parts.length >= 5 ? double.tryParse(parts[4]) : null;
    return MiniItem(type: type, name: parts[1], sub: parts[2], lat: lat, lon: lon);
  }

  String _decodeName(String raw) {
    final firstSep = raw.indexOf(_sep);
    if (firstSep < 0) return '';
    final rest = raw.substring(firstSep + 1);
    final secondSep = rest.indexOf(_sep);
    return secondSep < 0 ? rest : rest.substring(0, secondSep);
  }
}
