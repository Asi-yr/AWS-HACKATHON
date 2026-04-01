import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';
import '../../core/app_colors.dart';
import '../../core/theme_controller.dart';
import '../../core/app_router.dart';
import '../../core/session_manager.dart';
import '../../core/api_client.dart';
import '../explore/explore_controller.dart';

// ════════════════════════════════════════════════════════════════
// TWO-FACTOR AUTHENTICATION SCREEN
// ════════════════════════════════════════════════════════════════
//
//   Pushed from LoginView when the backend returns:
//     { ok: true, requires_2fa: true, temp_token: "..." }
//
//   Verify → BACKEND: POST /api/auth/verify-2fa
//              { temp_token, otp_code }
//              200 + ok → save real token → AppRouter.explore
//              401       → show "Invalid code" error
// ════════════════════════════════════════════════════════════════

class TwoFactorView extends StatefulWidget {
  final String tempToken;
  const TwoFactorView({super.key, required this.tempToken});

  @override
  State<TwoFactorView> createState() => _TwoFactorViewState();
}

class _TwoFactorViewState extends State<TwoFactorView> {
  final _codeController = TextEditingController();
  bool _isLoading = false;

  @override
  void dispose() {
    _codeController.dispose();
    super.dispose();
  }

  Future<void> _verify() async {
    final code = _codeController.text.trim();
    if (code.length != 6) {
      _showError('Enter the 6-digit code sent to your email');
      return;
    }

    setState(() => _isLoading = true);
    try {
      final response = await ApiClient.instance.verify2FA(
        tempToken: widget.tempToken,
        otpCode: code,
      );

      if (!mounted) return;

      if (response['ok'] == true && response['token'] != null) {
        // Temp token fulfilled — clear it and promote to a real session.
        await SessionManager.instance.clearTempToken();
        await SessionManager.instance.setLoggedIn(
          true,
          token: response['token'] as String,
          username: response['user'] as String?,
        );
        await SessionManager.instance.setLastRoute(AppRouter.explore);

        if (!mounted) return;
        context.read<ExploreController>().loadUserPreferences();
        // Remove all previous routes so the user cannot back-navigate to login.
        Navigator.pushNamedAndRemoveUntil(
          context,
          AppRouter.explore,
          (_) => false,
        );
      } else {
        _showError(response['message'] as String? ?? 'Invalid code. Try again.');
        _codeController.clear();
      }
    } catch (e) {
      if (!mounted) return;
      final msg = e.toString();
      if (msg.contains('SocketException') ||
          msg.contains('Connection refused') ||
          msg.contains('Failed host lookup')) {
        _showError('Cannot reach server. Check your connection.');
      } else {
        _showError(msg.replaceFirst('Exception: ', ''));
      }
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  void _showError(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: AppColors.safeRed,
        duration: const Duration(seconds: 3),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = context.watch<ThemeController>().isDark;

    return Scaffold(
      backgroundColor: AppColors.bg(isDark),
      appBar: AppBar(
        backgroundColor: AppColors.bg(isDark),
        elevation: 0,
        leading: BackButton(color: AppColors.text(isDark)),
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(28, 16, 28, 32),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // ── Icon ─────────────────────────────────────────
              Container(
                width: 52,
                height: 52,
                decoration: BoxDecoration(
                  color: AppColors.teal,
                  borderRadius: BorderRadius.circular(14),
                  boxShadow: [
                    BoxShadow(
                      color: AppColors.tealGlow,
                      blurRadius: 20,
                      spreadRadius: 2,
                    ),
                  ],
                ),
                child: const Icon(
                  Icons.lock_clock_rounded,
                  color: Colors.white,
                  size: 26,
                ),
              ),
              const SizedBox(height: 24),

              // ── Heading ──────────────────────────────────────
              Text(
                'Two-factor\nauthentication',
                style: GoogleFonts.plusJakartaSans(
                  fontSize: 28,
                  fontWeight: FontWeight.w900,
                  color: AppColors.text(isDark),
                  height: 1.15,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                'Enter the 6-digit code sent to your email to continue.',
                style: GoogleFonts.dmSans(
                  fontSize: 14,
                  color: AppColors.text2(isDark),
                ),
              ),
              const SizedBox(height: 36),

              // ── OTP input ────────────────────────────────────
              TextField(
                controller: _codeController,
                keyboardType: TextInputType.number,
                maxLength: 6,
                textAlign: TextAlign.center,
                autofocus: true,
                inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                style: GoogleFonts.dmSans(
                  fontSize: 30,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 14,
                  color: AppColors.text(isDark),
                ),
                decoration: InputDecoration(
                  counterText: '',
                  hintText: '000000',
                  hintStyle: GoogleFonts.dmSans(
                    fontSize: 30,
                    letterSpacing: 14,
                    color: AppColors.text2(isDark).withOpacity(0.25),
                  ),
                  filled: true,
                  fillColor: AppColors.card(isDark),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: BorderSide(color: AppColors.border(isDark)),
                  ),
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: BorderSide(color: AppColors.border(isDark)),
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide:
                        const BorderSide(color: AppColors.teal, width: 1.5),
                  ),
                ),
                onSubmitted: (_) => _verify(),
              ),
              const SizedBox(height: 24),

              // ── Verify button ─────────────────────────────────
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppColors.teal,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 15),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                    elevation: 0,
                  ),
                  onPressed: _isLoading ? null : _verify,
                  child: _isLoading
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            valueColor:
                                AlwaysStoppedAnimation<Color>(Colors.white),
                          ),
                        )
                      : Text(
                          'Verify',
                          style: GoogleFonts.plusJakartaSans(
                            fontSize: 15,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                ),
              ),
              const SizedBox(height: 20),

              // ── Helper text ───────────────────────────────────
              Center(
                child: Text(
                  'Check your email inbox for the\n6-digit verification code.',
                  textAlign: TextAlign.center,
                  style: GoogleFonts.dmSans(
                    fontSize: 12,
                    color: AppColors.text2(isDark),
                    height: 1.5,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
