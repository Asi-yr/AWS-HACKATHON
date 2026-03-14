import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/app_colors.dart';
import '../../core/theme_controller.dart';
import '../../data/mock_data.dart';
import '../../models/explore_models.dart';
import 'explore_controller.dart';

// ═══════════════════════════════════════════════════════════════
// MiniScreen — Animated landing screen (State 1)
//
// Used in explore_view.dart as:
//   MiniScreen(onSearchTap: () => _openSearch(context))
//
// Used in main.dart routes as:
//   MiniScreen.routeName  →  '/explore/search'
//   routes: { MiniScreen.routeName: (_) => const MiniScreen() }
//   (when used as a route, it shows the search overlay instead)
// ═══════════════════════════════════════════════════════════════
class MiniScreen extends StatefulWidget {
  /// Provide [onSearchTap] when embedding as the landing screen in explore_view.
  /// Omit it (leave null) when pushed as a named route — it will show the
  /// search overlay automatically.
  final VoidCallback? onSearchTap;

  const MiniScreen({super.key, this.onSearchTap});

  static const routeName = '/explore/search';

  @override
  State<MiniScreen> createState() => _MiniScreenState();
}

class _MiniScreenState extends State<MiniScreen> {
  @override
  Widget build(BuildContext context) {
    // When pushed as a named route (onSearchTap == null), show search overlay.
    // When embedded in explore_view with onSearchTap, show the landing screen.
    if (widget.onSearchTap == null) {
      return const _SearchOverlay();
    }
    return _LandingScreen(onSearchTap: widget.onSearchTap!);
  }
}

// ═══════════════════════════════════════════════════════════════
// LANDING SCREEN  (animated)
// ═══════════════════════════════════════════════════════════════
class _LandingScreen extends StatefulWidget {
  final VoidCallback onSearchTap;
  const _LandingScreen({required this.onSearchTap});

  @override
  State<_LandingScreen> createState() => _LandingScreenState();
}

class _LandingScreenState extends State<_LandingScreen>
    with TickerProviderStateMixin {

  // ── Entry: plays once on mount ─────────────────────────────────
  late final AnimationController _entryCtrl;
  late final Animation<double> _logoFade, _logoScale;
  late final Animation<Offset>  _logoSlide;
  late final Animation<double>  _subtitleFade;
  late final Animation<Offset>  _subtitleSlide;
  late final Animation<double>  _pillFade;
  late final Animation<Offset>  _pillSlide;

  // ── Idle loop: only pulse (keeps RAM low) ─────────────────────
  late final AnimationController _pulseCtrl;

  late final Animation<double> _pulseOpacity, _pulseScale;

  @override
  void initState() {
    super.initState();

    _entryCtrl = AnimationController(
        vsync: this, duration: const Duration(milliseconds: 800));

    _logoFade = CurvedAnimation(parent: _entryCtrl,
        curve: const Interval(0.00, 0.55, curve: Curves.easeOut));
    _logoScale = Tween<double>(begin: 0.72, end: 1.0).animate(
        CurvedAnimation(parent: _entryCtrl,
            curve: const Interval(0.00, 0.60, curve: Curves.easeOutBack)));
    _logoSlide = Tween<Offset>(
        begin: const Offset(0, 0.22), end: Offset.zero).animate(
        CurvedAnimation(parent: _entryCtrl,
            curve: const Interval(0.00, 0.58, curve: Curves.easeOutCubic)));

    _subtitleFade = CurvedAnimation(parent: _entryCtrl,
        curve: const Interval(0.28, 0.72, curve: Curves.easeOut));
    _subtitleSlide = Tween<Offset>(
        begin: const Offset(0, 0.28), end: Offset.zero).animate(
        CurvedAnimation(parent: _entryCtrl,
            curve: const Interval(0.28, 0.72, curve: Curves.easeOutCubic)));

    _pillFade = CurvedAnimation(parent: _entryCtrl,
        curve: const Interval(0.50, 0.92, curve: Curves.easeOut));
    _pillSlide = Tween<Offset>(
        begin: const Offset(0, 0.35), end: Offset.zero).animate(
        CurvedAnimation(parent: _entryCtrl,
            curve: const Interval(0.50, 0.92, curve: Curves.easeOutCubic)));

    _pulseCtrl = AnimationController(
        vsync: this, duration: const Duration(milliseconds: 2400))
      ..repeat(reverse: true);
    _pulseOpacity = Tween<double>(begin: 0.18, end: 0.52).animate(
        CurvedAnimation(parent: _pulseCtrl, curve: Curves.easeInOut));
    _pulseScale = Tween<double>(begin: 1.0, end: 1.15).animate(
        CurvedAnimation(parent: _pulseCtrl, curve: Curves.easeInOut));

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _entryCtrl.forward();
    });
  }

  @override
  void dispose() {
    _entryCtrl.dispose();
    _pulseCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = context.watch<ThemeController>().isDark;

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: isDark ? SystemUiOverlayStyle.light : SystemUiOverlayStyle.dark,
      child: Container(
        width: double.infinity,
        height: double.infinity,
        color: AppColors.bg(isDark),
        child: Stack(
          children: [

            // ── Radial teal glow backdrop ──────────────────────
            Positioned.fill(child: _RadialGlow(isDark: isDark)),

            // ── Dot-grid texture ───────────────────────────────
            Positioned.fill(child: CustomPaint(painter: _DotGridPainter(isDark: isDark))),

            // ── All content: centered ──────────────────────────
            SafeArea(
              child: Center(
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 32),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.center,
                    children: [

                      // ── Logo + app name ──────────────────────
                      FadeTransition(
                        opacity: _logoFade,
                        child: SlideTransition(
                          position: _logoSlide,
                          child: ScaleTransition(
                            scale: _logoScale,
                            child: Column(
                              mainAxisSize: MainAxisSize.min,
                              children: [

                                AnimatedBuilder(
                                  animation: Listenable.merge(
                                      [_pulseScale, _pulseOpacity]),
                                  builder: (_, _) => SizedBox(
                                    width: 120, height: 120,
                                    child: Stack(
                                      alignment: Alignment.center,
                                      children: [
                                        // Outer glow ring
                                        Transform.scale(
                                          scale: _pulseScale.value,
                                          child: Container(
                                            width: 110, height: 110,
                                            decoration: BoxDecoration(
                                              shape: BoxShape.circle,
                                              color: AppColors.teal.withValues(
                                                  alpha: _pulseOpacity.value * 0.28),
                                            ),
                                          ),
                                        ),
                                        // Middle glow ring
                                        Transform.scale(
                                          scale: (_pulseScale.value - 1) * 0.55 + 1,
                                          child: Container(
                                            width: 84, height: 84,
                                            decoration: BoxDecoration(
                                              shape: BoxShape.circle,
                                              color: AppColors.teal.withValues(
                                                  alpha: _pulseOpacity.value * 0.45),
                                            ),
                                          ),
                                        ),

                                        // ┌────────────────────────────────┐
                                        // │   LOGO IMAGE PLACEHOLDER       │
                                        // │   Replace this Container with: │
                                        // │                                │
                                        // │   SvgPicture.asset(            │
                                        // │     'assets/logo.svg',         │
                                        // │     width: 64, height: 64,     │
                                        // │   )                            │
                                        // └────────────────────────────────┘
                                        Container(
                                          width: 64, height: 64,
                                          decoration: BoxDecoration(
                                            color: AppColors.teal,
                                            borderRadius: BorderRadius.circular(18),
                                            boxShadow: [
                                              BoxShadow(
                                                color: AppColors.teal.withValues(alpha: 0.55),
                                                blurRadius: 30,
                                                spreadRadius: 2,
                                                offset: const Offset(0, 8),
                                              ),
                                            ],
                                          ),
                                          // ↓ Remove this Icon once SVG logo is ready
                                          child: const Icon(
                                            Icons.image_outlined,
                                            color: Colors.white54,
                                            size: 26,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                ),

                                const SizedBox(height: 20),

                                Text(
                                  'LIGTAS',
                                  textAlign: TextAlign.center,
                                  style: GoogleFonts.plusJakartaSans(
                                    fontSize: 36,
                                    fontWeight: FontWeight.w900,
                                    color: AppColors.text(isDark),
                                    letterSpacing: 7,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),

                      const SizedBox(height: 18),

                      // ── Headline + subtitle ──────────────────
                      FadeTransition(
                        opacity: _subtitleFade,
                        child: SlideTransition(
                          position: _subtitleSlide,
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Text(
                                'Where do you want\nto go safely?',
                                textAlign: TextAlign.center,
                                style: GoogleFonts.plusJakartaSans(
                                  fontSize: 22,
                                  fontWeight: FontWeight.w700,
                                  color: AppColors.text(isDark).withValues(alpha: 0.92),
                                  height: 1.38,
                                  letterSpacing: -0.3,
                                ),
                              ),
                              const SizedBox(height: 10),
                              Text(
                                'Safe routes for every commuter',
                                textAlign: TextAlign.center,
                                style: GoogleFonts.dmSans(
                                  fontSize: 14,
                                  color: AppColors.text2(isDark),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),

                      const SizedBox(height: 44),

                      // ── Search pill ──────────────────────────
                      FadeTransition(
                        opacity: _pillFade,
                        child: SlideTransition(
                          position: _pillSlide,
                          child: _LandingSearchPill(
                            onTap: widget.onSearchTap,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════
// BACKGROUND HELPERS
// ═══════════════════════════════════════════════════════════════

class _RadialGlow extends StatelessWidget {
  final bool isDark;
  const _RadialGlow({required this.isDark});
  @override
  Widget build(BuildContext context) => Container(
    decoration: BoxDecoration(
      gradient: RadialGradient(
        center: const Alignment(0, -0.22),
        radius: 0.90,
        colors: [
          AppColors.teal.withValues(alpha: isDark ? 0.14 : 0.08),
          AppColors.teal.withValues(alpha: isDark ? 0.05 : 0.02),
          Colors.transparent,
        ],
        stops: const [0.0, 0.46, 1.0],
      ),
    ),
  );
}

class _DotGridPainter extends CustomPainter {
  final bool isDark;
  const _DotGridPainter({required this.isDark});
  @override
  void paint(Canvas canvas, Size size) {
    final p = Paint()
      ..color = AppColors.teal.withValues(alpha: isDark ? 0.045 : 0.06)
      ..style  = PaintingStyle.fill;
    const spacing = 26.0;
    const r = 1.3;
    for (double x = spacing / 2; x < size.width;  x += spacing) {
    for (double y = spacing / 2; y < size.height; y += spacing) {
      canvas.drawCircle(Offset(x, y), r, p);
  }}}
  @override bool shouldRepaint(_DotGridPainter old) => old.isDark != isDark;
}

class _LandingSearchPill extends StatelessWidget {
  final VoidCallback onTap;
  const _LandingSearchPill({required this.onTap});

  @override
  Widget build(BuildContext context) {
    final isDark = context.watch<ThemeController>().isDark;
    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
        decoration: BoxDecoration(
          color: AppColors.card(isDark),
          borderRadius: BorderRadius.circular(50),
          border: Border.all(
            color: AppColors.teal.withValues(alpha: 0.35),
            width: 1.4,
          ),
          boxShadow: [
            BoxShadow(
              color: AppColors.teal.withValues(alpha: 0.12),
              blurRadius: 20, offset: const Offset(0, 6),
            ),
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.12),
              blurRadius: 10, offset: const Offset(0, 3),
            ),
          ],
        ),
        child: Row(children: [
          const Icon(Icons.search_rounded, color: AppColors.teal, size: 20),
          const SizedBox(width: 12),
          Expanded(
            child: Text('Search destination…',
              style: GoogleFonts.plusJakartaSans(
                fontSize: 15,
                color: AppColors.text2(isDark),
                fontWeight: FontWeight.w500,
              ),
            ),
          ),
          Container(
            width: 38, height: 38,
            decoration: BoxDecoration(
              color: AppColors.teal, shape: BoxShape.circle,
              boxShadow: [BoxShadow(
                color: AppColors.teal.withValues(alpha: 0.40),
                blurRadius: 12, offset: const Offset(0, 3),
              )],
            ),
            child: const Icon(Icons.my_location_rounded,
                color: Colors.white, size: 17),
          ),
        ]),
      ),
    );
  }
}


// ═══════════════════════════════════════════════════════════════
// SEARCH OVERLAY  (original MiniScreen logic — unchanged)
// Shown when MiniScreen is pushed as a named route with no onSearchTap
// ═══════════════════════════════════════════════════════════════
class _SearchOverlay extends StatefulWidget {
  const _SearchOverlay();

  @override
  State<_SearchOverlay> createState() => _SearchOverlayState();
}

class _SearchOverlayState extends State<_SearchOverlay> {
  final _currentCtrl  = TextEditingController();
  final _destCtrl     = TextEditingController();
  final _currentFocus = FocusNode();
  final _destFocus    = FocusNode();

  bool _isOriginFocused = true;
  bool _currentActive   = true;

  List<MiniItem> _filteredItems = [];
  String _lastQuery = '___INIT___';
  Timer? _debounce;

  @override
  void initState() {
    super.initState();

    final ctrl = context.read<ExploreController>();
    _currentCtrl.text = ctrl.originText;
    _destCtrl.text    = ctrl.destText;
    _filteredItems    = List.from(miniItems);

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_currentCtrl.text.isEmpty) {
        _currentFocus.requestFocus();
        _setFocusState(true);
      } else {
        _destFocus.requestFocus();
        _setFocusState(false);
      }
    });

    _currentFocus.addListener(_syncFocus);
    _destFocus.addListener(_syncFocus);
    _currentCtrl.addListener(_onSearchChanged);
    _destCtrl.addListener(_onSearchChanged);
  }

  void _setFocusState(bool isOrigin) {
    if (!mounted) return;
    setState(() {
      _currentActive   = isOrigin;
      _isOriginFocused = isOrigin;
      _lastQuery = '___REFRESH___';
      _onSearchChanged();
    });
  }

  void _syncFocus() {
    if (!mounted) return;
    if (_currentFocus.hasFocus && !_currentActive) {
      _setFocusState(true);
    } else if (_destFocus.hasFocus && _currentActive) {
      _setFocusState(false);
    }
  }

  void _onSearchChanged() {
    if (!mounted) return;
    final query = _isOriginFocused ? _currentCtrl.text : _destCtrl.text;
    if (query == _lastQuery) return;
    _lastQuery = query;

    if (query.isEmpty) {
      setState(() => _filteredItems = List.from(miniItems));
      return;
    }

    // Show immediate local results while API call is in-flight
    setState(() => _filteredItems = _localSearch(query));

    // Debounce API call — wait 400ms after user stops typing
    if (query.length >= 3) {
      _debounce?.cancel();
      _debounce = Timer(const Duration(milliseconds: 400), () {
        _fetchApiSuggestions(query);
      });
    }
  }

  Future<void> _fetchApiSuggestions(String query) async {
    final results = await ApiClient.instance.getSuggestions(query);
    if (!mounted) return;
    // Only apply if the query hasn't changed since the call was made
    final current = _isOriginFocused ? _currentCtrl.text : _destCtrl.text;
    if (current != query) return;
    if (results.isNotEmpty) {
      setState(() => _filteredItems = results);
    }
  }

  List<MiniItem> _localSearch(String query) {
    final lowerQuery = query.toLowerCase().trim();
    final scored = miniItems.map((item) {
      final nameLower = item.name.toLowerCase();
      final subLower  = item.sub.toLowerCase();
      int score = 0;
      if (nameLower == lowerQuery)                                              { score = 1000; }
      else if (nameLower.startsWith(lowerQuery))                                { score = 500;  }
      else if (nameLower.contains(' $lowerQuery') ||
               nameLower.contains('$lowerQuery '))                              { score = 300;  }
      else if (nameLower.contains(lowerQuery))                                  { score = 100;  }
      else if (subLower.contains(lowerQuery))                                   { score = 50;   }
      return MapEntry(item, score);
    }).where((e) => e.value > 0).toList();
    scored.sort((a, b) => b.value.compareTo(a.value));
    return scored.map((e) => e.key).toList();
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _currentFocus.removeListener(_syncFocus);
    _destFocus.removeListener(_syncFocus);
    _currentCtrl.removeListener(_onSearchChanged);
    _destCtrl.removeListener(_onSearchChanged);
    _currentCtrl.dispose();
    _destCtrl.dispose();
    _currentFocus.dispose();
    _destFocus.dispose();
    super.dispose();
  }

  void _search() {
    FocusScope.of(context).unfocus();
    final ctrl = context.read<ExploreController>();
    if (_currentCtrl.text.isNotEmpty) ctrl.setOriginText(_currentCtrl.text);
    if (_destCtrl.text.isNotEmpty)    ctrl.setDestText(_destCtrl.text);
    ctrl.searchRoutes();
    if (mounted) Navigator.of(context).pop();
  }

  void _back() {
    FocusScope.of(context).unfocus();
    Navigator.of(context).pop();
  }

  void _onItemTap(MiniItem item) {
    if (_isOriginFocused) {
      _currentCtrl.text = item.name;
      _destFocus.requestFocus();
    } else {
      _destCtrl.text = item.name;
    }
    if (_currentCtrl.text.isNotEmpty && _destCtrl.text.isNotEmpty) {
      _search();
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = context.watch<ThemeController>().isDark;
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: isDark ? SystemUiOverlayStyle.light : SystemUiOverlayStyle.dark,
      child: Scaffold(
        backgroundColor: AppColors.bg(isDark),
        body: SafeArea(
          child: Column(
            children: [
              _InputHeader(
                currentCtrl:   _currentCtrl,
                destCtrl:      _destCtrl,
                currentFocus:  _currentFocus,
                destFocus:     _destFocus,
                currentActive: _currentActive,
                onCurrentTap:  () => _currentFocus.requestFocus(),
                onDestTap:     () => _destFocus.requestFocus(),
                onSearch:      _search,
                onBack:        _back,
              ),
              Expanded(
                child: _SuggestionList(
                  items: _filteredItems,
                  query: _currentActive ? _currentCtrl.text : _destCtrl.text,
                  onSelect: _onItemTap,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════
// SEARCH OVERLAY COMPONENTS  (original — unchanged)
// ═══════════════════════════════════════════════════════════════

class _InputHeader extends StatelessWidget {
  const _InputHeader({
    required this.currentCtrl,
    required this.destCtrl,
    required this.currentFocus,
    required this.destFocus,
    required this.currentActive,
    required this.onCurrentTap,
    required this.onDestTap,
    required this.onSearch,
    required this.onBack,
  });

  final TextEditingController currentCtrl;
  final TextEditingController destCtrl;
  final FocusNode currentFocus;
  final FocusNode destFocus;
  final bool currentActive;
  final VoidCallback onCurrentTap;
  final VoidCallback onDestTap;
  final VoidCallback onSearch;
  final VoidCallback onBack;

  @override
  Widget build(BuildContext context) {
    final isDark = context.watch<ThemeController>().isDark;
    return Container(
      color: AppColors.bg(isDark),
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              GestureDetector(
                onTap: onBack,
                child: Container(
                  width: 32, height: 32,
                  margin: const EdgeInsets.only(top: 6),
                  decoration: BoxDecoration(
                    color: AppColors.card2(isDark),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Icon(Icons.arrow_back_rounded, size: 18,
                      color: AppColors.text2(isDark)),
                ),
              ),
              const SizedBox(width: 12),
              Column(
                children: [
                  const SizedBox(height: 14),
                  _Dot(color: currentActive
                      ? AppColors.teal : AppColors.text3(isDark)),
                  Container(
                    width: 2, height: 32,
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.topCenter,
                        end: Alignment.bottomCenter,
                        colors: [
                          currentActive
                              ? AppColors.teal : AppColors.text3(isDark),
                          !currentActive
                              ? AppColors.teal : AppColors.text3(isDark),
                        ],
                      ),
                    ),
                  ),
                  _Dot(color: !currentActive
                      ? AppColors.teal : AppColors.text3(isDark)),
                ],
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  children: [
                    _InputField(
                      controller: currentCtrl,
                      focusNode: currentFocus,
                      onTap: onCurrentTap,
                      hint: 'Current location',
                      isActive: currentActive,
                      dotIcon: Icons.my_location_rounded,
                      dotColor: AppColors.teal,
                      textInputAction: TextInputAction.next,
                      onSubmitted: (_) => destFocus.requestFocus(),
                    ),
                    const SizedBox(height: 8),
                    _InputField(
                      controller: destCtrl,
                      focusNode: destFocus,
                      onTap: onDestTap,
                      hint: 'Where to?',
                      isActive: !currentActive,
                      dotIcon: Icons.location_on_rounded,
                      dotColor: AppColors.teal,
                      textInputAction: TextInputAction.search,
                      onSubmitted: (_) => onSearch(),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            'Tap a suggestion or press Enter to search',
            style: GoogleFonts.plusJakartaSans(
                fontSize: 11,
                color: AppColors.text3(isDark),
                fontWeight: FontWeight.w500),
          ),
        ],
      ),
    );
  }
}

class _Dot extends StatelessWidget {
  final Color color;
  const _Dot({required this.color});
  @override
  Widget build(BuildContext context) {
    return Container(
      width: 10, height: 10,
      decoration: BoxDecoration(
        color: color,
        shape: BoxShape.circle,
        border: Border.all(
            color: AppColors.card2(context.watch<ThemeController>().isDark),
            width: 2),
      ),
    );
  }
}

class _InputField extends StatelessWidget {
  const _InputField({
    required this.controller,
    required this.focusNode,
    required this.onTap,
    required this.hint,
    required this.isActive,
    required this.dotIcon,
    required this.dotColor,
    required this.textInputAction,
    required this.onSubmitted,
  });

  final TextEditingController controller;
  final FocusNode focusNode;
  final VoidCallback onTap;
  final String hint;
  final bool isActive;
  final IconData dotIcon;
  final Color dotColor;
  final TextInputAction textInputAction;
  final ValueChanged<String>? onSubmitted;

  @override
  Widget build(BuildContext context) {
    final isDark = context.watch<ThemeController>().isDark;
    return AnimatedContainer(
      duration: const Duration(milliseconds: 140),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: isActive ? AppColors.tealDim : AppColors.card2(isDark),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
            color: isActive ? AppColors.teal : Colors.transparent),
      ),
      child: Row(
        children: [
          Icon(dotIcon, color: dotColor, size: 16),
          const SizedBox(width: 8),
          Expanded(
            child: TextField(
              controller: controller,
              focusNode: focusNode,
              onTap: onTap,
              textInputAction: textInputAction,
              onSubmitted: onSubmitted,
              autocorrect: false,
              enableSuggestions: false,
              style: GoogleFonts.plusJakartaSans(
                  color: AppColors.text(isDark), fontSize: 13),
              decoration: InputDecoration(
                hintText: hint,
                hintStyle: GoogleFonts.plusJakartaSans(
                    color: AppColors.text2(isDark), fontSize: 13),
                isDense: true,
                contentPadding: EdgeInsets.zero,
                border: InputBorder.none,
              ),
            ),
          ),
          if (isActive)
            ListenableBuilder(
              listenable: controller,
              builder: (_, _) => controller.text.isEmpty
                  ? const SizedBox.shrink()
                  : GestureDetector(
                      onTap: () => controller.clear(),
                      child: Icon(Icons.close_rounded,
                          size: 14, color: AppColors.text2(isDark)),
                    ),
            ),
        ],
      ),
    );
  }
}

class _SuggestionList extends StatelessWidget {
  final List<MiniItem> items;
  final String query;
  final void Function(MiniItem) onSelect;
  const _SuggestionList(
      {required this.items, required this.query, required this.onSelect});

  @override
  Widget build(BuildContext context) {
    final isDark = context.watch<ThemeController>().isDark;
    if (items.isEmpty && query.isNotEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.search_off_rounded,
                size: 48, color: AppColors.text3(isDark)),
            const SizedBox(height: 16),
            Text('No results for "$query"',
                style: GoogleFonts.plusJakartaSans(
                    fontSize: 14,
                    color: AppColors.text2(isDark),
                    fontWeight: FontWeight.w600)),
          ],
        ),
      );
    }
    return ListView.builder(
      keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
      itemCount: items.length,
      itemBuilder: (_, i) => _SuggestionTile(
          item: items[i], query: query, onTap: () => onSelect(items[i])),
    );
  }
}

class _SuggestionTile extends StatelessWidget {
  final MiniItem item;
  final String query;
  final VoidCallback onTap;
  const _SuggestionTile(
      {required this.item, required this.query, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final isDark = context.watch<ThemeController>().isDark;
    return ListTile(
      leading: Container(
        width: 36, height: 36,
        decoration: BoxDecoration(
            color: AppColors.card2(isDark),
            borderRadius: BorderRadius.circular(10)),
        child: Icon(item.icon,
            size: 18,
            color: item.type == MiniItemType.heart
                ? AppColors.safeRed
                : AppColors.text2(isDark)),
      ),
      title: _HighlightedText(
        text: item.name,
        query: query,
        style: GoogleFonts.plusJakartaSans(
            color: AppColors.text(isDark),
            fontSize: 13,
            fontWeight: FontWeight.w600),
      ),
      subtitle: Text(item.sub,
          style: GoogleFonts.plusJakartaSans(
              color: AppColors.text2(isDark), fontSize: 11)),
      onTap: onTap,
    );
  }
}

class _HighlightedText extends StatelessWidget {
  final String text;
  final String query;
  final TextStyle style;
  const _HighlightedText(
      {required this.text, required this.query, required this.style});

  @override
  Widget build(BuildContext context) {
    final lowerText  = text.toLowerCase();
    final lowerQuery = query.toLowerCase();
    final index      = lowerText.indexOf(lowerQuery);

    if (query.isEmpty || index == -1) {
      return Text(text, style: style, maxLines: 1,
          overflow: TextOverflow.ellipsis);
    }

    return Text.rich(
      TextSpan(children: [
        TextSpan(text: text.substring(0, index)),
        TextSpan(
            text: text.substring(index, index + query.length),
            style: const TextStyle(
                fontWeight: FontWeight.w800, color: AppColors.teal)),
        TextSpan(text: text.substring(index + query.length)),
      ], style: style),
      maxLines: 1, overflow: TextOverflow.ellipsis,
    );
  }
}