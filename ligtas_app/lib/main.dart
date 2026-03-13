import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'core/theme_controller.dart';
import 'core/app_router.dart';
import 'core/app_colors.dart';
import 'core/session_manager.dart';
import 'screens/explore/explore_view.dart';
import 'screens/explore/explore_controller.dart';
import 'screens/community/community_view.dart';
import 'screens/profile/profile_view.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);
  
  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => ThemeController()),
        ChangeNotifierProvider(create: (_) => ExploreController()), 
      ],
      child: const LigtasApp(),
    ),
  );
}

class LigtasApp extends StatelessWidget {
  const LigtasApp({super.key});

  @override
  Widget build(BuildContext context) {
    final themeController = context.watch<ThemeController>();

    return MaterialApp(
      title: 'Ligtas',
      debugShowCheckedModeBanner: false,
      themeMode: themeController.isDark ? ThemeMode.dark : ThemeMode.light,
      theme: ThemeData(
        brightness: Brightness.light,
        // Add your light theme properties here
      ),
      darkTheme: ThemeData(
        brightness: Brightness.dark,
        // Add your dark theme properties here
      ),
      initialRoute: AppRouter.splash,
      onGenerateRoute: AppRouter.onGenerateRoute,
    );
  }
}

class RootShell extends StatefulWidget {
  const RootShell({super.key});
  @override
  State<RootShell> createState() => _RootShellState();
}

class _RootShellState extends State<RootShell> {
  int _currentIndex = 0;

  final List<Widget> _pages = [
    const ExploreView(),
    const CommunityView(),
    const ProfileView(),
  ];

  @override
  Widget build(BuildContext context) {
    // FIX: Watch ThemeController HERE at the shell level, not inside
    // _LigtasBottomNav. This means the entire Scaffold (nav bar + body)
    // is rebuilt in the same frame when the theme changes, eliminating
    // the visual delay where the nav updates before the page content.
    // ignore: unused_local_variable
    final _ = context.watch<ThemeController>();

    return Scaffold(
      resizeToAvoidBottomInset: false,
      extendBody: true, 
      body: IndexedStack(
        index: _currentIndex,
        children: _pages,
      ),
      bottomNavigationBar: _LigtasBottomNav(
          currentIndex: _currentIndex,
          onTap: (index) {
            if (index == 0) {
              context.read<ExploreController>().clearSearch();
              SessionManager.instance.setLastRoute(AppRouter.explore);
            } else if (index == 1) {
              SessionManager.instance.setLastRoute(AppRouter.community);
            } else if (index == 2) {
              SessionManager.instance.setLastRoute(AppRouter.profile);
            }
            SessionManager.instance.updateLastActive();
            setState(() => _currentIndex = index);
          },
        ),
    );
  }
}

class _LigtasBottomNav extends StatelessWidget {
  const _LigtasBottomNav({
    required this.currentIndex,
    required this.onTap,
  });

  final int currentIndex;
  final ValueChanged<int> onTap;

  // FIX: Colors are now defined as getters that read from ThemeController,
  // not hardcoded constants. This makes the nav bar respond to dark/light mode.
  static const _teal = AppColors.tealBright;
  static const _items = [
    _NavItem(label: 'HOME',      icon: Icons.home_outlined,           iconActive: Icons.home_rounded),
    _NavItem(label: 'COMMUNITY', icon: Icons.group_outlined,          iconActive: Icons.group_rounded),
    _NavItem(label: 'PROFILE',   icon: Icons.account_circle_outlined, iconActive: Icons.account_circle_rounded),
  ];

  @override
  Widget build(BuildContext context) {
    // ThemeController is already watched by RootShell, so this widget
    // rebuilds in the same frame. Use read here to avoid double-watching.
    final isDark = context.read<ThemeController>().isDark;

    // FIX: Choose colors based on current theme instead of hardcoding dark values.
    final bgColor    = isDark ? AppColors.cardDark : AppColors.cardLight;
    final borderColor = isDark ? AppColors.borderDark : AppColors.borderLight;
    final mutedColor  = isDark ? AppColors.text2Dark : AppColors.text2Light;

    return Container(
      height: 72,
      decoration: BoxDecoration(
        color: bgColor,
        border: Border(top: BorderSide(color: borderColor)),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceAround,
        children: List.generate(_items.length, (i) {
          final item   = _items[i];
          final active = i == currentIndex;
          return GestureDetector(
            onTap: () => onTap(i),
            behavior: HitTestBehavior.opaque,
            child: SizedBox(
              width: MediaQuery.of(context).size.width / 3,
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(
                    active ? item.iconActive : item.icon,
                    color: active ? _teal : mutedColor,
                    size: 24,
                  ),
                  const SizedBox(height: 4),
                  Text(
                    item.label,
                    style: TextStyle(
                      fontSize: 10,
                      fontWeight: FontWeight.w700,
                      color: active ? _teal : mutedColor,
                    ),
                  ),
                ],
              ),
            ),
          );
        }),
      ),
    );
  }
}

class _NavItem {
  final String   label;
  final IconData icon;
  final IconData iconActive;
  const _NavItem({required this.label, required this.icon, required this.iconActive});
}