import 'package:shared_preferences/shared_preferences.dart';

/// Centralized session + inactivity tracking for the app.
///
/// Responsibilities:
/// - Remember if the user is logged in.
/// - Store auth token for API requests.
/// - Track last-active timestamp.
/// - Track whether a route is actively being navigated.
/// - Remember the last logical route (e.g. explore / community / profile).
class SessionManager {
  SessionManager._();
  static final SessionManager instance = SessionManager._();

  static const _kLoggedIn = 'session_logged_in';
  static const _kAuthToken = 'session_auth_token';
  static const _kUsername = 'session_username';
  static const _kLastActiveMs = 'session_last_active_ms';
  static const _kHasActiveRoute = 'session_has_active_route';
  static const _kLastRoute = 'session_last_route';

  SharedPreferences? _prefs;

  Future<void> _ensurePrefs() async {
    _prefs ??= await SharedPreferences.getInstance();
  }

  /// Set login state and store auth token.
  Future<void> setLoggedIn(bool value, {String? token, String? username}) async {
    await _ensurePrefs();
    await _prefs!.setBool(_kLoggedIn, value);
    if (token != null) {
      await _prefs!.setString(_kAuthToken, token);
    }
    if (username != null) {
      await _prefs!.setString(_kUsername, username);
    }
    await updateLastActive();
  }

  Future<bool> isLoggedIn() async {
    await _ensurePrefs();
    return _prefs!.getBool(_kLoggedIn) ?? false;
  }

  /// Get the stored auth token for API requests.
  Future<String?> getAuthToken() async {
    await _ensurePrefs();
    return _prefs!.getString(_kAuthToken);
  }

  /// Get the stored username.
  Future<String?> getUsername() async {
    await _ensurePrefs();
    return _prefs!.getString(_kUsername);
  }

  /// Clear auth token on logout.
  Future<void> clearAuthToken() async {
    await _ensurePrefs();
    await _prefs!.remove(_kAuthToken);
    await _prefs!.remove(_kUsername);
    await _prefs!.setBool(_kLoggedIn, false);
  }

  Future<void> setHasActiveRoute(bool value) async {
    await _ensurePrefs();
    await _prefs!.setBool(_kHasActiveRoute, value);
    await updateLastActive();
  }

  Future<bool> hasActiveRoute() async {
    await _ensurePrefs();
    return _prefs!.getBool(_kHasActiveRoute) ?? false;
  }

  Future<void> setLastRoute(String routeName) async {
    await _ensurePrefs();
    await _prefs!.setString(_kLastRoute, routeName);
    await updateLastActive();
  }

  Future<String?> getLastRoute() async {
    await _ensurePrefs();
    return _prefs!.getString(_kLastRoute);
  }

  Future<void> updateLastActive() async {
    await _ensurePrefs();
    final nowMs = DateTime.now().millisecondsSinceEpoch;
    await _prefs!.setInt(_kLastActiveMs, nowMs);
  }

  Future<DateTime?> getLastActive() async {
    await _ensurePrefs();
    final ms = _prefs!.getInt(_kLastActiveMs);
    if (ms == null) return null;
    return DateTime.fromMillisecondsSinceEpoch(ms);
  }

  /// Returns how long it has been since the last recorded activity.
  /// If no timestamp is stored yet, returns Duration.zero.
  Future<Duration> timeSinceLastActive() async {
    final last = await getLastActive();
    if (last == null) return Duration.zero;
    return DateTime.now().difference(last);
  }
}

