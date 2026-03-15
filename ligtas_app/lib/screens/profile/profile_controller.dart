import 'dart:typed_data';

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../models/user_model.dart';
import '../../models/travel_history_model.dart';
import '../../core/theme_controller.dart';
import '../../core/session_manager.dart';
import '../../core/api_client.dart';
import 'package:provider/provider.dart';

class ProfileController extends ChangeNotifier {
  UserModel user = UserModel.mock();
  TravelHistory history = TravelHistory.mock();

  bool toastVis = false;
  String toastMsg = '';
  String toastType = 'teal';
  bool travelHistoryOpen = false;
  bool securityOpen  = false;
  bool passwordOpen  = false;
  bool emailOpen     = false;
  bool twoFAOpen     = false;
  bool comingSoon = false;

  // ── Travel history loading state ──────────────────────────────
  bool isLoadingHistory = false;

  // ── Two-Factor Authentication state ──────────────────────────
  bool _twoFactorEnabled = false;
  bool get twoFactorEnabled => _twoFactorEnabled;

  // ── Locally picked avatar (web-safe) ─────────────────────────
  // Image.file() crashes on Flutter Web — we always read raw bytes so
  // both web and native can display via Image.memory(avatarBytes).
  Uint8List? avatarBytes;

  ProfileController() {
    _loadLocalPreferences();
    _loadUserFromBackend();
    _loadTravelHistoryFromBackend();
    loadSosContacts();
    _loadSettingsFromBackend();
  }

  Future<void> _loadLocalPreferences() async {
    final prefs = await SharedPreferences.getInstance();
    final bool aiSafetyEnabled = prefs.getBool("ai_safety_enabled") ?? false;
    final bool tfa             = prefs.getBool("two_factor_enabled") ?? false;
    user = user.copyWith(
      preferences: user.preferences.copyWith(aiSafety: aiSafetyEnabled),
    );
    _twoFactorEnabled = tfa;
    notifyListeners();
  }

  /// Load user settings from backend API.
  Future<void> _loadSettingsFromBackend() async {
    try {
      final token = await SessionManager.instance.getAuthToken();
      if (token == null || token.isEmpty) return;

      final settingsData = await ApiClient.instance.getSettings(token: token);
      if (settingsData['ok'] == true) {
        final settings = settingsData['settings'] ?? {};
        user = user.copyWith(
          commuterType: settings['default_commuter_type'] ?? user.commuterType,
          preferences: user.preferences.copyWith(
            aiSafety: settings['show_weather_banner'] ?? true,
            transport: List<String>.from(settings['transport_preference'] ?? ['jeep', 'walk']),
          ),
        );
        notifyListeners();
      }
    } catch (e) {
      debugPrint('[ProfileController] Error loading settings: $e');
    }
  }

  /// Load user profile from backend API.
  Future<void> _loadUserFromBackend() async {
    try {
      final token = await SessionManager.instance.getAuthToken();
      if (token == null || token.isEmpty) return;

      final userData = await ApiClient.instance.getCurrentUser(token: token);
      if (userData['ok'] == true) {
        user = UserModel(
          id: userData['id'] ?? user.id,
          name: userData['name'] ?? user.name,
          username: userData['username'] ?? user.username,
          role: userData['role'] ?? user.role,
          avatarUrl: userData['avatarUrl'],
          stats: UserStats(
            trips: (userData['stats']?['trips'] ?? 0) as int,
            reports: (userData['stats']?['reports'] ?? 0) as int,
            upvotedReports: (userData['stats']?['upvotedReports'] ?? 0) as int,
          ),
          commuterType: userData['commuterType'],
          preferences: UserPreferences(
            aiSafety: userData['preferences']?['aiSafety'] ?? true,
            nightMode: userData['preferences']?['nightMode'] ?? false,
            transport: List<String>.from(userData['preferences']?['transport'] ?? ['jeep', 'walk']),
          ),
        );
        // Backend gave us a fresh user — clear any locally picked bytes
        // so the backend avatar is shown instead.
        avatarBytes = null;
        notifyListeners();
      }
    } catch (e) {
      debugPrint('[ProfileController] Error loading user: $e');
    }
  }

  /// Load travel history from backend API.
  Future<void> _loadTravelHistoryFromBackend() async {
    isLoadingHistory = true;
    notifyListeners();

    try {
      final token = await SessionManager.instance.getAuthToken();
      if (token == null || token.isEmpty) {
        isLoadingHistory = false;
        notifyListeners();
        return;
      }

      final historyData = await ApiClient.instance.getRouteHistory(token: token);

      final routes = historyData.asMap().entries.map((entry) {
        final index = entry.key;
        final item = entry.value;
        return TravelRoute(
          id: 'history_$index',
          origin: item['origin']?.toString() ?? 'Unknown',
          destination: item['destination']?.toString() ?? 'Unknown',
          modes: item['commuterType']?.toString() ?? 'commute',
          minutes: 0,
          fare: 0,
          safetyScore: 75,
          safetyNote: 'Previous route search',
          date: item['searchedAt']?.toString() ?? 'Unknown',
          saved: false,
          steps: const [],
        );
      }).toList();

      history = TravelHistory(saved: const [], history: routes);
    } catch (e) {
      debugPrint('[ProfileController] Error loading travel history: $e');
      showToast('Could not load travel history', 'red');
    } finally {
      isLoadingHistory = false;
      notifyListeners();
    }
  }

  /// Public refresh — called when the user opens the Travel History panel.
  Future<void> refreshTravelHistory() => _loadTravelHistoryFromBackend();

  Future<void> toggleAiSafety() async {
    final newValue = !user.preferences.aiSafety;
    user = user.copyWith(preferences: user.preferences.copyWith(aiSafety: newValue));
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool("ai_safety_enabled", newValue);
    try {
      final token = await SessionManager.instance.getAuthToken();
      if (token != null && token.isNotEmpty) {
        await ApiClient.instance.saveSettings(
          defaultCommuterType: user.commuterType ?? 'commute',
          transportPreference: user.preferences.transport,
          showWeatherBanner: newValue,
          token: token,
        );
      }
    } catch (e) {
      debugPrint('[ProfileController] Error saving settings to backend: $e');
    }
    showToast(newValue ? "AI Safety Assistant Enabled" : "AI Safety Assistant Disabled", "teal");
    notifyListeners();
  }

  Future<void> pickProfileImage() async {
    final ImagePicker picker = ImagePicker();
    try {
      final XFile? image = await picker.pickImage(
        source: ImageSource.gallery,
        imageQuality: 80,
      );
      if (image == null) return;

      // Always read raw bytes — works on web AND native.
      // Image.file() crashes on Flutter Web so we never use it for preview.
      final bytes = await image.readAsBytes();
      avatarBytes = bytes;

      if (!kIsWeb) {
        // On native, also store the file path for potential backend upload.
        user = user.copyWith(avatarUrl: image.path);
      }
      // On web: avatarBytes is sufficient — image.path is a blob URL
      // that Image.file() cannot load, so we don't touch avatarUrl.

      showToast("Profile image updated!", "green");
      notifyListeners();
    } catch (e) {
      showToast("Error picking image", "red");
    }
  }

  void logOut(BuildContext context) {
    showToast("Logging out...", "teal");
    _performLogout();
    final navigator = Navigator.of(context, rootNavigator: true);
    Future.delayed(const Duration(milliseconds: 600), () {
      navigator.pushNamedAndRemoveUntil('/login', (route) => false);
    });
  }

  Future<void> _performLogout() async {
    try {
      final token = await SessionManager.instance.getAuthToken();
      await ApiClient.instance.logout(token: token);
    } catch (_) {
      // Backend logout is best-effort
    }
    await SessionManager.instance.clearAuthToken();
  }

  // ── Edit Profile ──────────────────────────────────────────────
  Future<void> saveProfile({
    required String name,
    required String username,
    required String commuterType,
  }) async {
    user = user.copyWith(name: name, username: username, role: commuterType, commuterType: commuterType);
    notifyListeners();
    try {
      final token = await SessionManager.instance.getAuthToken();
      if (token != null && token.isNotEmpty) {
        await ApiClient.instance.saveSettings(
          defaultCommuterType: commuterType,
          transportPreference: user.preferences.transport,
          displayName: name,
          token: token,
        );
      }
    } catch (e) {
      debugPrint('[ProfileController] Error saving profile to backend: $e');
    }
    showToast("Profile updated!", "green");
  }

  // ── Change Password ───────────────────────────────────────────
  Future<void> changePassword({
    required BuildContext context,
    required String currentPassword,
    required String newPassword,
    required String confirmPassword,
    required VoidCallback onSuccess,
  }) async {
    if (currentPassword.isEmpty || newPassword.isEmpty || confirmPassword.isEmpty) {
      showToast("Please fill in all fields", "red"); return;
    }
    if (newPassword.length < 8) {
      showToast("Password must be at least 8 characters", "red"); return;
    }
    if (newPassword != confirmPassword) {
      showToast("New passwords do not match", "red"); return;
    }
    if (currentPassword == newPassword) {
      showToast("New password must be different from current", "red"); return;
    }
    try {
      final token = await SessionManager.instance.getAuthToken();
      if (token == null || token.isEmpty) {
        showToast("Not logged in. Please try again.", "red"); return;
      }
      await ApiClient.instance.changePassword(
        currentPassword: currentPassword,
        newPassword: newPassword,
        token: token,
      );
      showToast("Password updated successfully", "green");
      onSuccess();
      notifyListeners();
    } catch (e) {
      final errorMsg = e.toString();
      if (errorMsg.contains('401') || errorMsg.contains('wrong')) {
        showToast("Current password is incorrect", "red");
      } else {
        showToast("Error: ${e.toString()}", "red");
      }
    }
  }

  // ── Change Email ──────────────────────────────────────────────
  Future<void> changeEmail({
    required BuildContext context,
    required String newEmail,
    required String currentPassword,
    required VoidCallback onSuccess,
  }) async {
    if (newEmail.isEmpty || currentPassword.isEmpty) {
      showToast("Please fill in all fields", "red"); return;
    }
    final emailRe = RegExp(r'^[\w\.\-]+@[\w\-]+\.[a-zA-Z]{2,}$');
    if (!emailRe.hasMatch(newEmail)) {
      showToast("Enter a valid email address", "red"); return;
    }
    try {
      final token = await SessionManager.instance.getAuthToken();
      if (token == null || token.isEmpty) {
        showToast("Not logged in. Please try again.", "red"); return;
      }
      await ApiClient.instance.changeEmail(
        currentPassword: currentPassword,
        newEmail: newEmail,
        token: token,
      );
      showToast("Email updated successfully", "green");
      onSuccess();
      notifyListeners();
    } catch (e) {
      final errorMsg = e.toString();
      if (errorMsg.contains('401') || errorMsg.contains('incorrect')) {
        showToast("Current password is incorrect", "red");
      } else {
        showToast("Error: ${e.toString()}", "red");
      }
    }
  }

  // ── Two-Factor Authentication ─────────────────────────────────
  Future<void> toggle2FA(BuildContext context) async {
    final enabling = !_twoFactorEnabled;
    await Future.delayed(const Duration(milliseconds: 300)); // MOCK
    _twoFactorEnabled = enabling;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool("two_factor_enabled", enabling);
    showToast(
      enabling ? "2FA enabled successfully" : "2FA disabled successfully",
      enabling ? "green" : "teal",
    );
    notifyListeners();
  }

  void showComingSoon() { comingSoon = true; notifyListeners(); }
  void hideComingSoon()  { comingSoon = false; notifyListeners(); }

  void openTravelHistory() {
    travelHistoryOpen = true;
    // Always refresh when the panel opens so data is current
    refreshTravelHistory();
    notifyListeners();
  }
  void closeTravelHistory() { travelHistoryOpen = false; notifyListeners(); }

  /// Clear travel history on the backend then wipe local state.
  Future<void> clearTravelHistory() async {
    try {
      final token = await SessionManager.instance.getAuthToken();
      if (token == null || token.isEmpty) {
        showToast("Not logged in", "red");
        return;
      }
      await ApiClient.instance.clearRouteHistory(token: token);
      history = const TravelHistory(saved: [], history: []);
      showToast("Travel history cleared", "teal");
      notifyListeners();
    } catch (e) {
      showToast("Error clearing history: ${e.toString()}", "red");
    }
  }

  // ── SOS Contacts ──────────────────────────────────────────────
  List<Map<String, dynamic>> _sosContacts = [];
  List<Map<String, dynamic>> get sosContacts => _sosContacts;

  Future<void> loadSosContacts() async {
    try {
      final token = await SessionManager.instance.getAuthToken();
      if (token == null || token.isEmpty) {
        showToast('Not logged in', 'red');
        return;
      }
      _sosContacts = await ApiClient.instance.getSosContacts(token: token);
      notifyListeners();
    } catch (e) {
      debugPrint('[ProfileController] Error loading SOS contacts: $e');
      showToast('Could not load SOS contacts', 'red');
    }
  }

  Future<void> addSosContact({
    required String name,
    required String contactType,
    required String contactValue,
  }) async {
    try {
      final token = await SessionManager.instance.getAuthToken();
      if (token == null || token.isEmpty) {
        showToast("Not logged in", "red");
        return;
      }
      final result = await ApiClient.instance.addSosContact(
        name: name,
        contactType: contactType,
        contactValue: contactValue,
        token: token,
      );
      if (result['ok'] == true) {
        await loadSosContacts();
        showToast("Contact added successfully", "green");
      } else {
        showToast(result['message']?.toString() ?? "Failed to add contact", "red");
      }
    } catch (e) {
      showToast("Error: ${e.toString()}", "red");
    }
  }

  Future<void> removeSosContact({required int contactId}) async {
    try {
      final token = await SessionManager.instance.getAuthToken();
      if (token == null || token.isEmpty) {
        showToast("Not logged in", "red");
        return;
      }
      final result = await ApiClient.instance.removeSosContact(
        contactId: contactId,
        token: token,
      );
      if (result['ok'] == true) {
        await loadSosContacts();
        showToast("Contact removed", "teal");
      } else {
        showToast(result['message']?.toString() ?? "Failed to remove contact", "red");
      }
    } catch (e) {
      showToast("Error: ${e.toString()}", "red");
    }
  }

  void openSecurity()  { securityOpen = true;  notifyListeners(); }
  void closeSecurity() { securityOpen = false; notifyListeners(); }
  void openPassword()  { passwordOpen = true;  notifyListeners(); }
  void closePassword() { passwordOpen = false; notifyListeners(); }
  void openEmail()     { emailOpen = true;     notifyListeners(); }
  void closeEmail()    { emailOpen = false;    notifyListeners(); }
  void openTwoFA()     { twoFAOpen = true;     notifyListeners(); }
  void closeTwoFA()    { twoFAOpen = false;    notifyListeners(); }

  // ── SOS Contacts Panel state ──────────────────────────────────
  bool sosContactsOpen = false;
  void openSosContacts()  { sosContactsOpen = true;  loadSosContacts(); notifyListeners(); }
  void closeSosContacts() { sosContactsOpen = false; notifyListeners(); }

  void toggleTheme(BuildContext context) {
    context.read<ThemeController>().toggle();
  }

  void showToast(String msg, String type) {
    toastMsg = msg; toastType = type; toastVis = true;
    notifyListeners();
    Future.delayed(const Duration(seconds: 3), () {
      toastVis = false;
      notifyListeners();
    });
  }
}