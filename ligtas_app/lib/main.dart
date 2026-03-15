import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'core/theme_controller.dart';
import 'core/app_router.dart';
import 'core/app_colors.dart';
import 'core/app_tab_controller.dart';
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
        ChangeNotifierProvider(create: (_) => AppTabController()),
      ],
      child: const LigtasApp(),
    ),
  );
}

class LigtasApp extends StatelessWidget {
  const LigtasApp({super.key});

  @override
  Widget build(BuildContext context) {
    // ── FIX 1: Selector instead of context.watch ──────────────────────────────
    // Selector<T, S> only rebuilds when the selected value (isDark) changes.
    // Unlike context.watch, it won't rebuild if ThemeController ever notifies
    // for reasons other than isDark changing. It also makes the rebuild scope
    // explicit and readable.
    return Selector<ThemeController, bool>(
      selector: (_, tc) => tc.isDark,
      builder: (context, isDark, _) => MaterialApp(
        title: 'Ligtas',
        debugShowCheckedModeBanner: false,
        themeMode: isDark ? ThemeMode.dark : ThemeMode.light,
        theme: ThemeData(
          brightness: Brightness.light,
          useMaterial3: false,
        ),
        darkTheme: ThemeData(
          brightness: Brightness.dark,
          useMaterial3: false,
        ),
        initialRoute: AppRouter.splash,
        onGenerateRoute: AppRouter.onGenerateRoute,
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// RootShell — bottom nav host
// ─────────────────────────────────────────────────────────────────────────────
class RootShell extends StatefulWidget {
  const RootShell({super.key});
  @override
  State<RootShell> createState() => _RootShellState();
}

class _RootShellState extends State<RootShell> {
  int _currentIndex = 0;
  late final PageController _pageController;

  @override
  void initState() {
    super.initState();
    _pageController = PageController(initialPage: _currentIndex);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      // Listen for tab switches triggered externally via AppTabController
      context.read<AppTabController>().addListener(_onTabControllerChanged);
      // Restore the tab the user was on when the app was last closed
      SessionManager.instance.getLastRoute().then((route) {
        if (!mounted) return;
        if (route == AppRouter.community && _currentIndex != 1) {
          _pageController.jumpToPage(1);
          setState(() => _currentIndex = 1);
        } else if (route == AppRouter.profile && _currentIndex != 2) {
          _pageController.jumpToPage(2);
          setState(() => _currentIndex = 2);
        }
      });
    });
  }

  @override
  void dispose() {
    context.read<AppTabController>().removeListener(_onTabControllerChanged);
    _pageController.dispose();
    super.dispose();
  }

  void _onTabControllerChanged() {
    final requested = context.read<AppTabController>().index;
    if (requested != _currentIndex) {
      _onNavTap(requested);
    }
  }

  void _onNavTap(int index) {
    if (index == 0) {
      context.read<ExploreController>().clearSearch();
      SessionManager.instance.setLastRoute(AppRouter.explore);
    } else if (index == 1) {
      SessionManager.instance.setLastRoute(AppRouter.community);
    } else if (index == 2) {
      SessionManager.instance.setLastRoute(AppRouter.profile);
    }
    SessionManager.instance.updateLastActive();
    context.read<AppTabController>().switchTo(index);
    _pageController.jumpToPage(index);
    setState(() => _currentIndex = index);
  }

  @override
  Widget build(BuildContext context) {
    // ── FIX 2: RootShell has NO ThemeController dependency ───────────────────
    // RootShell only rebuilds when _currentIndex changes (setState in
    // _onNavTap). Theme changes propagate through the MaterialApp →
    // Theme InheritedWidget cascade, not through RootShell rebuilds.
    return Scaffold(
      resizeToAvoidBottomInset: false,
      extendBody: true,
      body: PageView(
        // ── FIX 3: PageView + keepAlive instead of IndexedStack ───────────────
        // IndexedStack keeps all 3 pages in the RENDER tree at all times.
        // On theme change, Flutter repaints all 3 simultaneously, and they
        // finish at different times depending on subtree depth — that's the
        // staggered update you see.
        //
        // PageView only renders the ACTIVE page. Inactive pages are kept
        // alive in memory (not destroyed) by AutomaticKeepAliveClientMixin
        // in _KeepAlivePage, so all state, controllers, and scroll positions
        // are preserved. But they are NOT in the repaint tree, so theme
        // changes only repaint the one visible page. No more race condition.
        controller: _pageController,
        physics: const NeverScrollableScrollPhysics(), // no swipe between tabs
        children: const [
          _KeepAlivePage(child: ExploreView()),
          _KeepAlivePage(child: CommunityView()),
          _KeepAlivePage(child: ProfileView()),
        ],
      ),
      bottomNavigationBar: _LigtasBottomNav(
        currentIndex: _currentIndex,
        onTap: _onNavTap,
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// _KeepAlivePage — keeps page state alive when PageView deactivates it
// ─────────────────────────────────────────────────────────────────────────────
class _KeepAlivePage extends StatefulWidget {
  final Widget child;
  const _KeepAlivePage({required this.child});

  @override
  State<_KeepAlivePage> createState() => _KeepAlivePageState();
}

class _KeepAlivePageState extends State<_KeepAlivePage>
    with AutomaticKeepAliveClientMixin {
  // wantKeepAlive = true tells PageView: keep this element alive in memory
  // even when it is not the active page. State, controllers, scroll positions,
  // and Provider subtrees are all preserved. The page simply stops receiving
  // build calls and repaints — it does not get destroyed and recreated.
  @override
  bool get wantKeepAlive => true;

  @override
  Widget build(BuildContext context) {
    super.build(context); // required call for AutomaticKeepAliveClientMixin
    return widget.child;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Bottom nav bar
// ─────────────────────────────────────────────────────────────────────────────
class _LigtasBottomNav extends StatelessWidget {
  const _LigtasBottomNav({
    required this.currentIndex,
    required this.onTap,
  });

  final int currentIndex;
  final ValueChanged<int> onTap;

  static const _teal = AppColors.tealBright;
  static const _items = [
    _NavItem(label: 'HOME',      icon: Icons.home_outlined,           iconActive: Icons.home_rounded),
    _NavItem(label: 'COMMUNITY', icon: Icons.group_outlined,          iconActive: Icons.group_rounded),
    _NavItem(label: 'PROFILE',   icon: Icons.account_circle_outlined, iconActive: Icons.account_circle_rounded),
  ];

  @override
  Widget build(BuildContext context) {
    // ── FIX 4: Theme.of(context) instead of ThemeController watch ────────────
    // Theme.of(context) is a zero-cost InheritedWidget lookup — it does NOT
    // add this widget as a ThemeController listener. Instead it reads the
    // Theme that MaterialApp already propagated down the tree.
    //
    // When isDark changes, MaterialApp (via Selector in LigtasApp) rebuilds
    // and pushes a new Theme InheritedWidget. Flutter then marks every widget
    // that called Theme.of(context) as dirty and rebuilds them all in the
    // SAME FRAME — including this nav bar and the active page. They always
    // update together, no lag, no race.
    final isDark      = Theme.of(context).brightness == Brightness.dark;
    final bgColor     = isDark ? AppColors.cardDark  : AppColors.cardLight;
    final borderColor = isDark ? AppColors.borderDark : AppColors.borderLight;
    final mutedColor  = isDark ? AppColors.text2Dark  : AppColors.text2Light;

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
  const _NavItem({
    required this.label,
    required this.icon,
    required this.iconActive,
  });
}