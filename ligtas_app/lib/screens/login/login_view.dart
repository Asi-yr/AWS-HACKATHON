import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../core/app_colors.dart';
import '../../core/app_router.dart';
import '../../core/session_manager.dart';

// ════════════════════════════════════════════════════════════════
// LOGIN / REGISTRATION SCREEN  —  PLACEHOLDER
// ════════════════════════════════════════════════════════════════
// Wire the actual auth logic here:
//
//   Sign In  →  BACKEND: POST /api/auth/login  { email, password }
//                200 → save token → AppRouter.explore
//                401 → show error
//
//   Register →  BACKEND: POST /api/auth/register  { name, email, password }
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
                  _tab('Sign In',  _isLogin,  () => setState(() => _isLogin = true)),
                  _tab('Register', !_isLogin, () => setState(() => _isLogin = false)),
                ]),
              ),
              const SizedBox(height: 28),

              // ── Fields ────────────────────────────────────────
              if (!_isLogin) ...[
                _field('Full Name', Icons.person_outline_rounded, false),
                const SizedBox(height: 14),
              ],
              _field('Email Address', Icons.email_outlined, false),
              const SizedBox(height: 14),
              _field('Password', Icons.lock_outline_rounded, true),
              const SizedBox(height: 28),

              // ── Primary CTA ───────────────────────────────────
              // BACKEND: replace with real auth call (see header comment)
              _PrimaryButton(
                label: _isLogin ? 'Sign In' : 'Create Account',
                onTap: () {
                  if (_isLogin) {
                    // Returning user → mark logged in and go to main shell
                    SessionManager.instance.setLoggedIn(true);
                    SessionManager.instance.setLastRoute(AppRouter.explore);
                    Navigator.pushReplacementNamed(context, AppRouter.explore);
                  } else {
                    // New user → mark logged in and go to onboarding survey
                    SessionManager.instance.setLoggedIn(true);
                    SessionManager.instance.setLastRoute(AppRouter.survey);
                    Navigator.pushReplacementNamed(context, AppRouter.survey);
                  }
                },
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

  Widget _field(String hint, IconData icon, bool obscure) => TextField(
    obscureText: obscure,
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
    ),
  );
}

class _PrimaryButton extends StatelessWidget {
  final String label;
  final VoidCallback onTap;
  const _PrimaryButton({required this.label, required this.onTap});
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
      onPressed: onTap,
      child: Text(label,
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