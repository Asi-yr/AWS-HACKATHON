import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../core/app_colors.dart';
import '../../core/app_router.dart';
import '../../core/session_manager.dart';
import '../../core/api_client.dart';

// ════════════════════════════════════════════════════════════════
// LOGIN / REGISTRATION SCREEN  —  Production Integration
// ════════════════════════════════════════════════════════════════
// Wired to backend API:
//
//   Sign In  →  BACKEND: POST /api/auth/login  { username, password }
//                200 → save token → AppRouter.explore
//                401 → show error
//
//   Register →  BACKEND: POST /api/auth/register  { username, email, password }
//                201 → AppRouter.survey  (first-time onboarding)
//                409 → email already in use
//
//   Google   →  Firebase / OAuth
//                new user  → AppRouter.survey
//                returning → AppRouter.explore
// ════════════════════════════════════════════════════════════════

class LoginView extends StatefulWidget {
  const LoginView({super.key});
  @override State<LoginView> createState() => _LoginViewState();
}

class _LoginViewState extends State<LoginView> {
  bool _isLogin = true;
  bool _isLoading = false;
  String? _errorMessage;

  final _usernameCtrl = TextEditingController();
  final _emailCtrl = TextEditingController();
  final _passwordCtrl = TextEditingController();

  @override
  void dispose() {
    _usernameCtrl.dispose();
    _emailCtrl.dispose();
    _passwordCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bgLight,
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(28, 48, 28, 32),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // ── Logo ─────────────────────────────────────────
              Container(
                width: 52, height: 52,
                decoration: BoxDecoration(
                  color: AppColors.teal,
                  borderRadius: BorderRadius.circular(14),
                  boxShadow: [BoxShadow(
                    color: AppColors.tealGlow,
                    blurRadius: 20, spreadRadius: 2)],
                ),
                child: const Icon(Icons.shield_rounded,
                  color: Colors.white, size: 28),
              ),
              const SizedBox(height: 24),
              Text(
                _isLogin ? 'Welcome back.' : 'Create account.',
                style: GoogleFonts.plusJakartaSans(
                  fontSize: 30, fontWeight: FontWeight.w900,
                  color: AppColors.textLight, height: 1.1),
              ),
              const SizedBox(height: 6),
              Text(
                _isLogin
                  ? 'Sign in to your Ligtas account.'
                  : 'Join Ligtas and commute safer.',
                style: GoogleFonts.dmSans(
                  fontSize: 14, color: AppColors.text2Light),
              ),
              const SizedBox(height: 36),

              // ── Sign In / Register tab toggle ─────────────────
              Container(
                decoration: BoxDecoration(
                  color: AppColors.cardLight,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: AppColors.borderLight)),
                padding: const EdgeInsets.all(4),
                child: Row(children: [
                  _tab('Sign In',  _isLogin,  () => setState(() { _isLogin = true; _errorMessage = null; })),
                  _tab('Register', !_isLogin, () => setState(() { _isLogin = false; _errorMessage = null; })),
                ]),
              ),
              const SizedBox(height: 28),

              // ── Error message if present ──────────────────────
              if (_errorMessage != null) ...[
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: Colors.red.shade50,
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: Colors.red.shade200),
                  ),
                  child: Text(
                    _errorMessage!,
                    style: GoogleFonts.dmSans(
                      fontSize: 13,
                      color: Colors.red.shade700,
                    ),
                  ),
                ),
                const SizedBox(height: 16),
              ],

              // ── Fields ────────────────────────────────────────
              _field(
                'Username',
                Icons.person_outline_rounded,
                false,
                _usernameCtrl,
              ),
              const SizedBox(height: 14),
              if (!_isLogin) ...[
                _field(
                  'Email Address',
                  Icons.email_outlined,
                  false,
                  _emailCtrl,
                ),
                const SizedBox(height: 14),
              ],
              _field(
                'Password',
                Icons.lock_outline_rounded,
                true,
                _passwordCtrl,
              ),
              const SizedBox(height: 28),

              // ── Primary CTA ───────────────────────────────────
              _PrimaryButton(
                label: _isLoading
                  ? 'Loading...'
                  : (_isLogin ? 'Sign In' : 'Create Account'),
                isLoading: _isLoading,
                onTap: _isLoading ? null : _handleAuthSubmit,
              ),
              const SizedBox(height: 20),

              // ── Divider ───────────────────────────────────────
              Row(children: [
                Expanded(child: Divider(color: AppColors.borderLight)),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 12),
                  child: Text('or',
                    style: GoogleFonts.dmSans(
                      fontSize: 13, color: AppColors.text2Light)),
                ),
                Expanded(child: Divider(color: AppColors.borderLight)),
              ]),
              const SizedBox(height: 20),

              // ── Social / OAuth ────────────────────────────────
              // BACKEND: wire Google OAuth / Firebase here
              _SocialButton(
                label: 'Continue with Google',
                icon: Icons.g_mobiledata_rounded,
                onTap: () {
                  // TODO: wire Google OAuth / Firebase
                },
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _handleAuthSubmit() async {
    setState(() => _errorMessage = null);

    final username = _usernameCtrl.text.trim();
    final email = _emailCtrl.text.trim();
    final password = _passwordCtrl.text.trim();

    // Validate input
    if (username.isEmpty || password.isEmpty) {
      setState(() => _errorMessage = 'Please fill in all required fields');
      return;
    }

    if (!_isLogin && email.isEmpty) {
      setState(() => _errorMessage = 'Email is required for registration');
      return;
    }

    setState(() => _isLoading = true);

    try {
      if (_isLogin) {
        // Login
        final result = await ApiClient.instance.login(
          username: username,
          password: password,
        );

        if (result['ok'] == true) {
          final token = result['token'] as String;
          final user = result['user'] as String;

          // Save token and mark as logged in
          await SessionManager.instance.setLoggedIn(true, token: token, username: user);
          await SessionManager.instance.setLastRoute(AppRouter.explore);

          if (mounted) {
            Navigator.pushReplacementNamed(context, AppRouter.explore);
          }
        }
      } else {
        // Register
        final result = await ApiClient.instance.register(
          username: username,
          password: password,
          email: email,
        );

        if (result['ok'] == true) {
          final token = result['token'] as String;
          final user = result['user'] as String;

          // Save token and mark as logged in
          await SessionManager.instance.setLoggedIn(true, token: token, username: user);
          await SessionManager.instance.setLastRoute(AppRouter.survey);

          if (mounted) {
            Navigator.pushReplacementNamed(context, AppRouter.survey);
          }
        }
      }
    } catch (e) {
      setState(() {
        _errorMessage = e.toString().replaceAll('Exception: ', '');
      });
    } finally {
      if (mounted) {
        setState(() => _isLoading = false);
      }
    }
  }

  Widget _tab(String label, bool active, VoidCallback onTap) => Expanded(
    child: GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 180),
        padding: const EdgeInsets.symmetric(vertical: 10),
        decoration: BoxDecoration(
          color: active ? AppColors.teal : Colors.transparent,
          borderRadius: BorderRadius.circular(9)),
        child: Center(child: Text(label,
          style: GoogleFonts.plusJakartaSans(
            fontSize: 13, fontWeight: FontWeight.w700,
            color: active ? Colors.white : AppColors.text2Light))),
      ),
    ),
  );

  Widget _field(
    String hint,
    IconData icon,
    bool obscure,
    TextEditingController controller,
  ) => TextField(
    controller: controller,
    obscureText: obscure,
    enabled: !_isLoading,
    style: GoogleFonts.dmSans(fontSize: 14, color: AppColors.textLight),
    decoration: InputDecoration(
      hintText: hint,
      hintStyle: GoogleFonts.dmSans(fontSize: 14, color: AppColors.text2Light),
      prefixIcon: Icon(icon, size: 18, color: AppColors.text2Light),
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      filled: true,
      fillColor: AppColors.cardLight,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: AppColors.borderLight)),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: AppColors.borderLight)),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: AppColors.teal, width: 1.5)),
      disabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: AppColors.borderLight)),
    ),
  );
}

class _PrimaryButton extends StatelessWidget {
  final String label;
  final bool isLoading;
  final VoidCallback? onTap;
  const _PrimaryButton({
    required this.label,
    required this.isLoading,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) => SizedBox(
    width: double.infinity,
    child: ElevatedButton(
      style: ElevatedButton.styleFrom(
        backgroundColor: AppColors.teal,
        foregroundColor: Colors.white,
        padding: const EdgeInsets.symmetric(vertical: 15),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        elevation: 0,
        disabledBackgroundColor: AppColors.teal.withOpacity(0.5),
      ),
      onPressed: onTap,
      child: isLoading
        ? SizedBox(
            height: 20,
            width: 20,
            child: CircularProgressIndicator(
              strokeWidth: 2,
              valueColor: AlwaysStoppedAnimation<Color>(
                Colors.white.withOpacity(0.8),
              ),
            ),
          )
        : Text(
            label,
            style: GoogleFonts.plusJakartaSans(
              fontSize: 15,
              fontWeight: FontWeight.w800,
            ),
          ),
    ),
  );
}

class _SocialButton extends StatelessWidget {
  final String label;
  final IconData icon;
  final VoidCallback onTap;
  const _SocialButton({required this.label, required this.icon, required this.onTap});
  @override
  Widget build(BuildContext context) => SizedBox(
    width: double.infinity,
    child: OutlinedButton.icon(
      style: OutlinedButton.styleFrom(
        foregroundColor: AppColors.textLight,
        padding: const EdgeInsets.symmetric(vertical: 13),
        side: const BorderSide(color: AppColors.borderLight),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
      onPressed: onTap,
      icon: Icon(icon, size: 22, color: AppColors.text2Light),
      label: Text(label,
        style: GoogleFonts.plusJakartaSans(
          fontSize: 14, fontWeight: FontWeight.w700,
          color: AppColors.text2Light)),
    ),
  );
}