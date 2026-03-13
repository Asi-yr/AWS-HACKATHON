import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Global theme state — mirrors main.js THEME_KEY logic.
/// Wrap the app root with ChangeNotifierProvider(create: (_) => ThemeController()).
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

  Future<void> setDark(bool value) async {
    _isDark = value;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_key, value ? 'dark' : 'light');
    notifyListeners();
  }

  Future<void> toggle() => setDark(!_isDark);
}
