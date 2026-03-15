import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';
import '../../core/app_colors.dart';
import '../../core/theme_controller.dart';
import '../../core/app_router.dart';
import '../../core/session_manager.dart';
import '../../core/api_client.dart';
import '../explore/explore_controller.dart';

// ════════════════════════════════════════════════════════════════
// LOGIN / REGISTRATION SCREEN
// ════════════════════════════════════════════════════════════════
//
//   Sign In  →  BACKEND: POST /api/auth/login  { username, password }
//                200 → save token → AppRouter.explore
//                401 → show error
//
//   Register →  BACKEND: POST /api/auth/register  { username, password, email }
//                201 → AppRouter.survey  (first-time onboarding)
//                409 → username already in use
//
//   Google   →  Firebase / OAuth  (not yet implemented)
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

  late final TextEditingController _nameController;
  late final TextEditingController _emailController;
  late final TextEditingController _passwordController;

  @override
  void initState() {
    super.initState();
    _nameController = TextEditingController();
    _emailController = TextEditingController();
    _passwordController = TextEditingController();
  }

  @override
  void dispose() {
    _nameController.dispose();
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _handleLogin() async {
    final username = _emailController.text.trim();
    final password = _passwordController.text;

    if (username.isEmpty || password.isEmpty) {
      _showError('Please enter username and password');
      return;
    }

    setState(() => _isLoading = true);
    try {
      final response = await ApiClient.instance.login(
        username: username,
        password: password,
      );

      if (!mounted) return;

      if (response['ok'] == true && response['token'] != null) {
        // Save token and user info
        await SessionManager.instance.setLoggedIn(
          true,
          token: response['token'],
          username: response['user'],
        );
        await SessionManager.instance.setLastRoute(AppRouter.explore);

        if (!mounted) return;
        context.read<ExploreController>().loadUserPreferences();
        Navigator.pushReplacementNamed(context, AppRouter.explore);
      } else {
        _showError(response['message'] ?? 'Login failed');
      }
    } catch (e) {
      if (!mounted) return;
      final msg = e.toString();
      if (msg.contains('SocketException') || msg.contains('Connection refused') || msg.contains('Failed host lookup')) {
        _showError('Cannot reach server. Check your connection.');
      } else {
        _showError(msg.replaceFirst('Exception: ', ''));
      }
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  Future<void> _handleRegister() async {
    final name = _nameController.text.trim();
    final email = _emailController.text.trim();
    final password = _passwordController.text;

    if (name.isEmpty || email.isEmpty || password.isEmpty) {
      _showError('Please fill all fields');
      return;
    }

    if (password.length < 6) {
      _showError('Password must be at least 6 characters');
      return;
    }

    setState(() => _isLoading = true);
    try {
      final response = await ApiClient.instance.register(
        username: name,
        password: password,
        email: email,
      );

      if (!mounted) return;

      if (response['ok'] == true && response['token'] != null) {
        // Auto-login after successful registration
        await SessionManager.instance.setLoggedIn(
          true,
          token: response['token'],
          username: response['user'],
        );
        await SessionManager.instance.setLastRoute(AppRouter.survey);

        if (!mounted) return;
        Navigator.pushReplacementNamed(context, AppRouter.survey);
      } else {
        _showError(response['message'] ?? 'Registration failed');
      }
    } catch (e) {
      if (!mounted) return;
      final msg = e.toString();
      if (msg.contains('SocketException') || msg.contains('Connection refused') || msg.contains('Failed host lookup')) {
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
                  color: AppColors.text(isDark), height: 1.1),
              ),
              const SizedBox(height: 6),
              Text(
                _isLogin
                  ? 'Sign in to your Ligtas account.'
                  : 'Join Ligtas and commute safer.',
                style: GoogleFonts.dmSans(
                  fontSize: 14, color: AppColors.text2(isDark)),
              ),
              const SizedBox(height: 36),

              // ── Sign In / Register tab toggle ─────────────────
              Container(
                decoration: BoxDecoration(
                  color: AppColors.card(isDark),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: AppColors.border(isDark))),
                padding: const EdgeInsets.all(4),
                child: Row(children: [
                  _tab('Sign In',  _isLogin,  () => setState(() => _isLogin = true),  isDark),
                  _tab('Register', !_isLogin, () => setState(() => _isLogin = false), isDark),
                ]),
              ),
              const SizedBox(height: 28),

              // ── Fields ────────────────────────────────────────
              if (!_isLogin) ...[
                _field('Full Name', Icons.person_outline_rounded, false, _nameController, isDark),
                const SizedBox(height: 14),
              ],
              _field(
                _isLogin ? 'Username' : 'Email Address',
                _isLogin ? Icons.person_outline_rounded : Icons.email_outlined,
                false,
                _emailController,
                isDark,
              ),
              const SizedBox(height: 14),
              _field('Password', Icons.lock_outline_rounded, true, _passwordController, isDark),
              const SizedBox(height: 28),

              // ── Primary CTA ───────────────────────────────────
              // BACKEND: Connected to /api/auth/login and /api/auth/register
              _PrimaryButton(
                label: _isLogin ? 'Sign In' : 'Create Account',
                isLoading: _isLoading,
                onTap: _isLoading ? null : (_isLogin ? _handleLogin : _handleRegister),
              ),
              const SizedBox(height: 20),

              // ── Divider ───────────────────────────────────────
              Row(children: [
                Expanded(child: Divider(color: AppColors.border(isDark))),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 12),
                  child: Text('or',
                    style: GoogleFonts.dmSans(
                      fontSize: 13, color: AppColors.text2(isDark))),
                ),
                Expanded(child: Divider(color: AppColors.border(isDark))),
              ]),
              const SizedBox(height: 20),

              // ── Social / OAuth ────────────────────────────────
              // BACKEND: wire Google OAuth / Firebase here
              _SocialButton(
                label: 'Continue with Google',
                icon: Icons.g_mobiledata_rounded,
                onTap: () {
                  // new user  → AppRouter.survey
                  // returning → AppRouter.explore
                },
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _tab(String label, bool active, VoidCallback onTap, bool isDark) => Expanded(
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
            color: active ? Colors.white : AppColors.text2(isDark)))),
      ),
    ),
  );

  Widget _field(String hint, IconData icon, bool obscure, TextEditingController controller, bool isDark) => TextField(
    controller: controller,
    obscureText: obscure,
    style: GoogleFonts.dmSans(fontSize: 14, color: AppColors.text(isDark)),
    decoration: InputDecoration(
      hintText: hint,
      hintStyle: GoogleFonts.dmSans(fontSize: 14, color: AppColors.text2(isDark)),
      prefixIcon: Icon(icon, size: 18, color: AppColors.text2(isDark)),
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      filled: true,
      fillColor: AppColors.card(isDark),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide(color: AppColors.border(isDark))),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide(color: AppColors.border(isDark))),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: AppColors.teal, width: 1.5)),
    ),
  );
}

class _PrimaryButton extends StatelessWidget {
  final String label;
  final VoidCallback? onTap;
  final bool isLoading;
  const _PrimaryButton({
    required this.label,
    required this.onTap,
    this.isLoading = false,
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
      ),
      onPressed: isLoading ? null : onTap,
      child: isLoading
        ? const SizedBox(
            width: 20,
            height: 20,
            child: CircularProgressIndicator(
              strokeWidth: 2,
              valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
            ),
          )
        : Text(label,
            style: GoogleFonts.plusJakartaSans(fontSize: 15, fontWeight: FontWeight.w800)),
    ),
  );
}

class _SocialButton extends StatelessWidget {
  final String label;
  final IconData icon;
  final VoidCallback onTap;
  const _SocialButton({required this.label, required this.icon, required this.onTap});
  @override
  Widget build(BuildContext context) {
    final isDark = context.watch<ThemeController>().isDark;
    return SizedBox(
      width: double.infinity,
      child: OutlinedButton.icon(
        style: OutlinedButton.styleFrom(
          foregroundColor: AppColors.text(isDark),
          padding: const EdgeInsets.symmetric(vertical: 13),
          side: BorderSide(color: AppColors.border(isDark)),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        ),
        onPressed: onTap,
        icon: Icon(icon, size: 22, color: AppColors.text2(isDark)),
        label: Text(label,
          style: GoogleFonts.plusJakartaSans(
            fontSize: 14, fontWeight: FontWeight.w700,
            color: AppColors.text2(isDark))),
      ),
    );
  }
}