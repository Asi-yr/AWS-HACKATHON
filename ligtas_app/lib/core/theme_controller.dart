import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Global theme state.
///
/// Key fix: `notifyListeners()` is called BEFORE the async disk write so the
/// UI updates instantly — no 50-300 ms delay waiting for SharedPreferences.
class ThemeController extends ChangeNotifier {
  static const _key = 'ligtas_theme';

  bool _isDark = false;
  bool get isDark => _isDark;

  ThemeController() {
    _load();
  }

  Future<void> _load() async {
    final prefs = await SharedPreferences.getInstance();
    _isDark = (prefs.getString(_key) ?? 'light') == 'dark';
    notifyListeners();
  }

  /// Instantly updates the UI, then saves to disk in the background.
  Future<void> setDark(bool value) async {
    if (_isDark == value) return;
    _isDark = value;
    notifyListeners(); // ← paint NOW, before any async work
    _save();           // fire-and-forget disk write
  }

  Future<void> toggle() => setDark(!_isDark);

  Future<void> _save() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_key, _isDark ? 'dark' : 'light');
  }
}