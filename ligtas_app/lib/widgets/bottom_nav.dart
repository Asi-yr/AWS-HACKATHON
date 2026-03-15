import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../core/app_colors.dart';
import '../core/app_router.dart';
import '../core/custom_theme.dart';

enum NavTab { home, community, profile }

/// Shared bottom nav — mirrors main.js NAV_ITEMS.
/// Usage: BottomNav(active: NavTab.profile)
class BottomNav extends StatelessWidget {
  final NavTab active;
  const BottomNav({super.key, required this.active});

  @override
  Widget build(BuildContext context) {
    final t = context.lt;
    return Container(
      height: 64 + MediaQuery.of(context).padding.bottom,
      padding: EdgeInsets.only(bottom: MediaQuery.of(context).padding.bottom),
      decoration: BoxDecoration(
        color: t.card,
        border: Border(top: BorderSide(color: t.border, width: 1)),
        boxShadow: [BoxShadow(color: Colors.black.withValues(alpha: 0.06), blurRadius: 12)],
      ),
      child: Row(
        children: [
          _NavBtn(tab: NavTab.home,      icon: Icons.home_rounded,         label: 'HOME',      route: AppRouter.explore,   active: active),
          _NavBtn(tab: NavTab.community, icon: Icons.people_alt_rounded,   label: 'COMMUNITY', route: AppRouter.community, active: active),
          _NavBtn(tab: NavTab.profile,   icon: Icons.person_rounded,       label: 'PROFILE',   route: AppRouter.profile,   active: active),
        ],
      ),
    );
  }
}

class _NavBtn extends StatelessWidget {
  final NavTab tab, active;
  final IconData icon;
  final String label, route;
  const _NavBtn({
    required this.tab, required this.active,
    required this.icon, required this.label, required this.route,
  });

  @override
  Widget build(BuildContext context) {
    final isActive = tab == active;
    final color    = isActive ? AppColors.primaryTeal(context.isDark) : AppColors.text2(context.isDark);

    return Expanded(
      child: GestureDetector(
        onTap: () {
          if (!isActive) Navigator.pushReplacementNamed(context, route);
        },
        behavior: HitTestBehavior.opaque,
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, color: color, size: 22),
            const SizedBox(height: 3),
            Text(label,
              style: GoogleFonts.plusJakartaSans(
                fontSize: 9, fontWeight: FontWeight.w700,
                color: color, letterSpacing: 0.08)),
            const SizedBox(height: 4),
            AnimatedContainer(
              duration: const Duration(milliseconds: 220),
              width:  isActive ? 18 : 0,
              height: isActive ? 2  : 0,
              decoration: BoxDecoration(
                color: AppColors.primaryTeal(context.isDark),
                borderRadius: BorderRadius.circular(1)),
            ),
          ],
        ),
      ),
    );
  }
}
