import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';
import '../../core/app_colors.dart';
import '../../core/app_router.dart';
import '../../core/session_manager.dart';
import '../../core/theme_controller.dart';

/// Splash / onboarding entry point.
/// BACKEND: Replace _onInit with real auth check:
///   if (await AuthService.isLoggedIn()) navigate to explore
///   else navigate to survey / onboarding
class SplashView extends StatefulWidget {
  const SplashView({super.key});
  @override State<SplashView> createState() => _SplashViewState();
}

class _SplashViewState extends State<SplashView>
    with SingleTickerProviderStateMixin {
  late final AnimationController _ctrl;
  late final Animation<double> _fade;
  late final Animation<double> _scale;

  @override
  void initState() {
    super.initState();
    _ctrl  = AnimationController(vsync: this, duration: const Duration(milliseconds: 900));
    _fade  = CurvedAnimation(parent: _ctrl, curve: Curves.easeOut);
    _scale = Tween<double>(begin: 0.82, end: 1.0)
        .animate(CurvedAnimation(parent: _ctrl, curve: Curves.easeOutBack));
    _ctrl.forward();
    _navigate();
  }

  Future<void> _navigate() async {
    await Future.delayed(const Duration(milliseconds: 2200));
    if (!mounted) return;
    // Decide where to go based on stored session + inactivity.
    final session = SessionManager.instance;
    final loggedIn = await session.isLoggedIn();
    final hasActiveRoute = await session.hasActiveRoute();
    final inactiveFor = await session.timeSinceLastActive();
    const longTimeout = Duration(minutes: 45);

    String next;

    if (!loggedIn) {
      // Never logged in → go to login
      next = AppRouter.login;
    } else if (hasActiveRoute) {
      // User is currently navigating a route → always resume explore shell
      next = AppRouter.explore;
    } else if (inactiveFor > longTimeout) {
      // Logged in but inactive for a long time (no active route) → reset to explore
      next = AppRouter.explore;
    } else {
      // Logged in, recently active → resume last route or explore by default
      final saved = await session.getLastRoute() ?? AppRouter.explore;
      // /community and /profile are tab-only views that live inside RootShell.
      // Navigating to them directly skips the Scaffold + bottom nav.
      // Always enter through /explore — RootShell will restore the correct tab.
      next = (saved == AppRouter.community || saved == AppRouter.profile)
          ? AppRouter.explore
          : saved;
    }

    await session.updateLastActive();
    if (!mounted) return;
    Navigator.pushReplacementNamed(context, next);
  }

  @override
  void dispose() { _ctrl.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    final isDark = context.watch<ThemeController>().isDark;
    return Scaffold(
      backgroundColor: isDark ? AppColors.bgDark : AppColors.bgLight,
      body: Center(
        child: FadeTransition(
          opacity: _fade,
          child: ScaleTransition(
            scale: _scale,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                // Logo mark
                Container(
                  width: 80, height: 80,
                  decoration: BoxDecoration(
                    color: AppColors.teal,
                    borderRadius: BorderRadius.circular(22),
                    boxShadow: [BoxShadow(
                      color: AppColors.tealGlow,
                      blurRadius: 32, spreadRadius: 4)],
                  ),
                  child: const Icon(Icons.shield_rounded,
                    color: Colors.white, size: 44),
                ),
                const SizedBox(height: 20),
                Text('LIGTAS',
                  style: GoogleFonts.plusJakartaSans(
                    fontSize: 32, fontWeight: FontWeight.w900,
                    color: AppColors.textLight, letterSpacing: 4)),
                const SizedBox(height: 6),
                Text('Safe Commute Planner',
                  style: GoogleFonts.dmSans(
                    fontSize: 14, color: AppColors.text2Light)),
                const SizedBox(height: 48),
                // Loading dot
                SizedBox(
                  width: 24, height: 24,
                  child: CircularProgressIndicator(
                    strokeWidth: 2.5,
                    color: AppColors.teal.withValues(alpha: 0.6)),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}