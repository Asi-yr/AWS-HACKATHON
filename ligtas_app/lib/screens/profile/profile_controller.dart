import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../models/user_model.dart';
import '../../models/travel_history_model.dart';
import '../../core/theme_controller.dart';
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

  // ── Two-Factor Authentication state ──────────────────────────
  bool _twoFactorEnabled = false;
  bool get twoFactorEnabled => _twoFactorEnabled;

  TravelRoute? selectedRoute;

  ProfileController() {
    _loadPreferences();
  }

  Future<void> _loadPreferences() async {
    final prefs = await SharedPreferences.getInstance();
    final bool aiSafetyEnabled = prefs.getBool("ai_safety_enabled") ?? false;
    final bool tfa             = prefs.getBool("two_factor_enabled") ?? false;
    user = user.copyWith(
      preferences: user.preferences.copyWith(aiSafety: aiSafetyEnabled),
    );
    _twoFactorEnabled = tfa;
    notifyListeners();
  }

  Future<void> toggleAiSafety() async {
    final newValue = !user.preferences.aiSafety;
    user = user.copyWith(preferences: user.preferences.copyWith(aiSafety: newValue));
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool("ai_safety_enabled", newValue);
    showToast(newValue ? "AI Safety Assistant Enabled" : "AI Safety Assistant Disabled", "teal");
    notifyListeners();
  }

  Future<void> pickProfileImage() async {
    final ImagePicker picker = ImagePicker();
    try {
      final XFile? image = await picker.pickImage(source: ImageSource.gallery, imageQuality: 80);
      if (image != null) {
        user = user.copyWith(avatarUrl: image.path);
        showToast("Profile image updated!", "green");
        notifyListeners();
      }
    } catch (e) {
      showToast("Error picking image", "red");
    }
  }

  void logOut(BuildContext context) {
    showToast("Logging out...", "teal");
    final navigator = Navigator.of(context, rootNavigator: true);
    Future.delayed(const Duration(milliseconds: 600), () {
      // pushNamedAndRemoveUntil clears the entire back stack so the user
      // cannot press Back to return to the main shell after logging out.
      navigator.pushNamedAndRemoveUntil('/login', (route) => false);
    });
  }

  // ── Edit Profile (password handled separately in Security sheet) ──
  void saveProfile({
    required String name,
    required String username,
    required String commuterType,
  }) {
    user = user.copyWith(name: name, username: username, role: commuterType, commuterType: commuterType);
    showToast("Profile updated!", "green");
    notifyListeners();
  }

  // ── Change Password ───────────────────────────────────────────
  // BACKEND: POST /api/auth/change-password
  //   body: { current_password, new_password }
  //   200 → success | 401 → wrong current password
  //
  // Firebase: reauthenticateWithCredential() then updatePassword()
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
    // BACKEND HOOK: replace below with real API call
    // try {
    //   await authApi.changePassword(userId: user.id,
    //     currentPassword: currentPassword, newPassword: newPassword);
    // } on WrongPasswordException {
    //   showToast("Current password is incorrect", "red"); return;
    // } catch (_) {
    //   showToast("Something went wrong. Try again.", "red"); return;
    // }
    await Future.delayed(const Duration(milliseconds: 400)); // MOCK
    showToast("Password updated successfully", "green");
    onSuccess();
    notifyListeners();
  }

  // ── Change Email ──────────────────────────────────────────────
  // Requires current password to re-authenticate.
  // Sends a verification link — change only takes effect after user confirms.
  //
  // BACKEND: POST /api/auth/change-email
  //   body: { new_email, current_password }
  //   200 → verification sent | 401 → wrong pw | 409 → email in use
  //
  // Firebase: reauthenticateWithCredential() then verifyBeforeUpdateEmail()
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
    // BACKEND HOOK: replace below with real API / Firebase call
    // Firebase: 
    //   final cred = EmailAuthProvider.credential(email: fbUser.email!, password: currentPassword);
    //   await fbUser.reauthenticateWithCredential(cred);
    //   await fbUser.verifyBeforeUpdateEmail(newEmail);
    await Future.delayed(const Duration(milliseconds: 400)); // MOCK
    showToast("Verification sent to $newEmail", "green");
    onSuccess();
    notifyListeners();
  }

  // ── Two-Factor Authentication ─────────────────────────────────
  // BACKEND:
  //   POST /api/auth/2fa/enable   → { message, qr_code_url? }
  //   POST /api/auth/2fa/disable  → { message }
  //
  // TOTP flow: show qr_code_url in a dialog for Google Authenticator.
  // Email-OTP flow: backend emails a code on each login attempt.
  Future<void> toggle2FA(BuildContext context) async {
    final enabling = !_twoFactorEnabled;
    // BACKEND HOOK:
    // if (enabling) {
    //   final result = await authApi.enable2FA(userId: user.id);
    //   // TOTP: show result.qrCodeUrl to user before confirming
    // } else {
    //   await authApi.disable2FA(userId: user.id);
    // }
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
  void openTravelHistory()  { travelHistoryOpen = true;  notifyListeners(); }
  void closeTravelHistory() { travelHistoryOpen = false; notifyListeners(); }
  void openSecurity()  { securityOpen = true;  notifyListeners(); }
  void closeSecurity() { securityOpen = false; notifyListeners(); }
  void openPassword()  { passwordOpen = true;  notifyListeners(); }
  void closePassword() { passwordOpen = false; notifyListeners(); }
  void openEmail()     { emailOpen = true;     notifyListeners(); }
  void closeEmail()    { emailOpen = false;    notifyListeners(); }
  void openTwoFA()     { twoFAOpen = true;     notifyListeners(); }
  void closeTwoFA()    { twoFAOpen = false;    notifyListeners(); }

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