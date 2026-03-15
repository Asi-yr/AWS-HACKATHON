import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';

import '../../core/app_colors.dart';
import '../../core/theme_controller.dart';
import '../../data/mock_data.dart';
import '../../models/explore_models.dart';
import 'explore_controller.dart';

// ═══════════════════════════════════════════════════════════════
// MiniScreen — Animated landing screen (State 1)
// ═══════════════════════════════════════════════════════════════
class MiniScreen extends StatefulWidget {
  final VoidCallback? onSearchTap;
  const MiniScreen({super.key, this.onSearchTap});
  static const routeName = '/explore/search';

  @override
  State<MiniScreen> createState() => _MiniScreenState();
}

class _MiniScreenState extends State<MiniScreen> {
  @override
  Widget build(BuildContext context) {
    if (widget.onSearchTap == null) return const _SearchOverlay();
    return _LandingScreen(onSearchTap: widget.onSearchTap!);
  }
}

// ═══════════════════════════════════════════════════════════════
// LANDING SCREEN
// ═══════════════════════════════════════════════════════════════
class _LandingScreen extends StatefulWidget {
  final VoidCallback onSearchTap;
  const _LandingScreen({required this.onSearchTap});

  @override
  State<_LandingScreen> createState() => _LandingScreenState();
}

class _LandingScreenState extends State<_LandingScreen>
    with TickerProviderStateMixin {
  late final AnimationController _entryCtrl;
  late final Animation<double> _logoFade, _logoScale;
  late final Animation<Offset> _logoSlide;
  late final Animation<double> _subtitleFade;
  late final Animation<Offset> _subtitleSlide;
  late final Animation<double> _pillFade;
  late final Animation<Offset> _pillSlide;

  late final AnimationController _pulseCtrl;
  late final Animation<double> _pulseOpacity, _pulseScale;

  @override
  void initState() {
    super.initState();

    _entryCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 800),
    );

    _logoFade = CurvedAnimation(
      parent: _entryCtrl,
      curve: const Interval(0.00, 0.55, curve: Curves.easeOut),
    );
    _logoScale = Tween<double>(begin: 0.72, end: 1.0).animate(
      CurvedAnimation(
        parent: _entryCtrl,
        curve: const Interval(0.00, 0.60, curve: Curves.easeOutBack),
      ),
    );
    _logoSlide = Tween<Offset>(begin: const Offset(0, 0.22), end: Offset.zero)
        .animate(
          CurvedAnimation(
            parent: _entryCtrl,
            curve: const Interval(0.00, 0.58, curve: Curves.easeOutCubic),
          ),
        );

    _subtitleFade = CurvedAnimation(
      parent: _entryCtrl,
      curve: const Interval(0.28, 0.72, curve: Curves.easeOut),
    );
    _subtitleSlide =
        Tween<Offset>(begin: const Offset(0, 0.28), end: Offset.zero).animate(
          CurvedAnimation(
            parent: _entryCtrl,
            curve: const Interval(0.28, 0.72, curve: Curves.easeOutCubic),
          ),
        );

    _pillFade = CurvedAnimation(
      parent: _entryCtrl,
      curve: const Interval(0.50, 0.92, curve: Curves.easeOut),
    );
    _pillSlide = Tween<Offset>(begin: const Offset(0, 0.35), end: Offset.zero)
        .animate(
          CurvedAnimation(
            parent: _entryCtrl,
            curve: const Interval(0.50, 0.92, curve: Curves.easeOutCubic),
          ),
        );

    _pulseCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2400),
    )..repeat(reverse: true);
    _pulseOpacity = Tween<double>(
      begin: 0.18,
      end: 0.52,
    ).animate(CurvedAnimation(parent: _pulseCtrl, curve: Curves.easeInOut));
    _pulseScale = Tween<double>(
      begin: 1.0,
      end: 1.15,
    ).animate(CurvedAnimation(parent: _pulseCtrl, curve: Curves.easeInOut));

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
            Positioned.fill(child: _RadialGlow(isDark: isDark)),
            Positioned.fill(
              child: CustomPaint(painter: _DotGridPainter(isDark: isDark)),
            ),
            SafeArea(
              child: Center(
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 32),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.center,
                    children: [
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
                                  animation: Listenable.merge([
                                    _pulseScale,
                                    _pulseOpacity,
                                  ]),
                                  builder: (_, _) => SizedBox(
                                    width: 120,
                                    height: 120,
                                    child: Stack(
                                      alignment: Alignment.center,
                                      children: [
                                        Transform.scale(
                                          scale: _pulseScale.value,
                                          child: Container(
                                            width: 110,
                                            height: 110,
                                            decoration: BoxDecoration(
                                              shape: BoxShape.circle,
                                              color: AppColors.teal.withValues(
                                                alpha:
                                                    _pulseOpacity.value * 0.28,
                                              ),
                                            ),
                                          ),
                                        ),
                                        Transform.scale(
                                          scale:
                                              (_pulseScale.value - 1) * 0.55 +
                                              1,
                                          child: Container(
                                            width: 84,
                                            height: 84,
                                            decoration: BoxDecoration(
                                              shape: BoxShape.circle,
                                              color: AppColors.teal.withValues(
                                                alpha:
                                                    _pulseOpacity.value * 0.45,
                                              ),
                                            ),
                                          ),
                                        ),
                                        Container(
                                          width: 64,
                                          height: 64,
                                          decoration: BoxDecoration(
                                            color: AppColors.teal,
                                            borderRadius: BorderRadius.circular(
                                              18,
                                            ),
                                            boxShadow: [
                                              BoxShadow(
                                                color: AppColors.teal
                                                    .withValues(alpha: 0.55),
                                                blurRadius: 30,
                                                spreadRadius: 2,
                                                offset: const Offset(0, 8),
                                              ),
                                            ],
                                          ),
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
                                  color: AppColors.text(
                                    isDark,
                                  ).withValues(alpha: 0.92),
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
                      FadeTransition(
                        opacity: _pillFade,
                        child: SlideTransition(
                          position: _pillSlide,
                          child: _LandingSearchPill(
                            onSearchTap: widget.onSearchTap,
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
      ..style = PaintingStyle.fill;
    const spacing = 26.0;
    const r = 1.3;
    for (double x = spacing / 2; x < size.width; x += spacing) {
      for (double y = spacing / 2; y < size.height; y += spacing) {
        canvas.drawCircle(Offset(x, y), r, p);
      }
    }
  }

  @override
  bool shouldRepaint(_DotGridPainter old) => old.isDark != isDark;
}

// ── Landing search pill ──────────────────────────────────────────
// The pill itself opens the search overlay.
// The teal GPS icon button inside it independently:
//   1. Calls GPS → reverse-geocodes → fills the origin field
//   2. Then opens the search overlay so the user just needs to type a dest.
class _LandingSearchPill extends StatelessWidget {
  final VoidCallback onSearchTap;
  const _LandingSearchPill({required this.onSearchTap});

  @override
  Widget build(BuildContext context) {
    final isDark = context.watch<ThemeController>().isDark;
    final ctrl = context.read<ExploreController>();

    return Container(
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
            blurRadius: 20,
            offset: const Offset(0, 6),
          ),
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.12),
            blurRadius: 10,
            offset: const Offset(0, 3),
          ),
        ],
      ),
      child: Row(
        children: [
          // ── Search text area — opens search overlay ──
          Expanded(
            child: GestureDetector(
              onTap: onSearchTap,
              behavior: HitTestBehavior.opaque,
              child: Row(
                children: [
                  const Icon(
                    Icons.search_rounded,
                    color: AppColors.teal,
                    size: 20,
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      'Search destination…',
                      style: GoogleFonts.plusJakartaSans(
                        fontSize: 15,
                        color: AppColors.text2(isDark),
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
          // ── GPS icon — gets current location then opens search ──
          GestureDetector(
            onTap: () async {
              await ctrl.useCurrentLocationAsOrigin();
              onSearchTap();
            },
            child: Container(
              width: 38,
              height: 38,
              decoration: BoxDecoration(
                color: AppColors.teal,
                shape: BoxShape.circle,
                boxShadow: [
                  BoxShadow(
                    color: AppColors.teal.withValues(alpha: 0.40),
                    blurRadius: 12,
                    offset: const Offset(0, 3),
                  ),
                ],
              ),
              child: const Icon(
                Icons.my_location_rounded,
                color: Colors.white,
                size: 17,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════
// SEARCH OVERLAY
// ═══════════════════════════════════════════════════════════════
class _SearchOverlay extends StatefulWidget {
  const _SearchOverlay();

  @override
  State<_SearchOverlay> createState() => _SearchOverlayState();
}

class _SearchOverlayState extends State<_SearchOverlay> {
  final _currentCtrl = TextEditingController();
  final _destCtrl = TextEditingController();
  final _currentFocus = FocusNode();
  final _destFocus = FocusNode();

  bool _isOriginFocused = true;
  bool _currentActive = true;

  // ── Autocomplete ──────────────────────────────────────────────
  // Two separate suggestion lists: static miniItems + live API results.
  List<MiniItem> _filteredStatic = []; // from mock_data.dart
  List<Map<String, dynamic>> _apiSuggestions = []; // from /api/suggest
  String _lastQuery = '___INIT___';
  Timer? _debounce;
  bool _isLoadingApi = false;

  @override
  void initState() {
    super.initState();

    final ctrl = context.read<ExploreController>();
    _currentCtrl.text = ctrl.originText;
    _destCtrl.text = ctrl.destText;
    _filteredStatic = List.from(miniItems);

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
      _currentActive = isOrigin;
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

    // Always update static results instantly
    setState(() {
      _filteredStatic = query.isEmpty
          ? List.from(miniItems)
          : _searchStatic(query);
      _apiSuggestions = [];
    });

    // Fetch live API suggestions for queries ≥ 3 characters
    if (query.length >= 3) {
      _fetchApiSuggestions(query);
    }
  }

  Future<void> _fetchApiSuggestions(String query) async {
    if (!mounted) return;
    setState(() => _isLoadingApi = true);
    try {
      final ctrl = context.read<ExploreController>();
      final results = await ctrl.suggestLocations(query);
      if (!mounted) return;
      // Guard: only update if the query is still current
      final currentQuery = _isOriginFocused
          ? _currentCtrl.text
          : _destCtrl.text;
      if (currentQuery == query) {
        setState(() {
          _apiSuggestions = results;
          _isLoadingApi = false;
        });
      } else {
        setState(() => _isLoadingApi = false);
      }
    } catch (_) {
      if (mounted) setState(() => _isLoadingApi = false);
    }
  }

  List<MiniItem> _searchStatic(String query) {
    final lowerQuery = query.toLowerCase().trim();
    final scored = miniItems
        .map((item) {
          final nameLower = item.name.toLowerCase();
          final subLower = item.sub.toLowerCase();
          int score = 0;
          if (nameLower == lowerQuery) {
            score = 1000;
          } else if (nameLower.startsWith(lowerQuery)) {
            score = 500;
          } else if (nameLower.contains(' $lowerQuery') ||
              nameLower.contains('$lowerQuery ')) {
            score = 300;
          } else if (nameLower.contains(lowerQuery)) {
            score = 100;
          } else if (subLower.contains(lowerQuery)) {
            score = 50;
          }
          return MapEntry(item, score);
        })
        .where((e) => e.value > 0)
        .toList();
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
    // Always sync text fields to controller before searching
    if (_currentCtrl.text.isNotEmpty) ctrl.setOriginText(_currentCtrl.text);
    if (_destCtrl.text.isNotEmpty) ctrl.setDestText(_destCtrl.text);
    // searchRoutes() sets state → state2 synchronously on its first line,
    // so the map is already showing the moment we pop back to ExploreView.
    // The async geocoding + route fetching completes in the background and
    // notifyListeners() triggers map repaints as each step finishes.
    ctrl.searchRoutes(); // intentionally not awaited — fire and pop
    if (mounted) Navigator.of(context).pop();
  }

  void _back() {
    FocusScope.of(context).unfocus();
    Navigator.of(context).pop();
  }

  void _onStaticItemTap(MiniItem item) {
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

  void _onApiItemTap(String placeName) {
    if (_isOriginFocused) {
      _currentCtrl.text = placeName;
      _destFocus.requestFocus();
    } else {
      _destCtrl.text = placeName;
    }
    setState(() {
      _apiSuggestions = [];
    });
    if (_currentCtrl.text.isNotEmpty && _destCtrl.text.isNotEmpty) {
      _search();
    }
  }

  /// Called by the GPS icon in the search header.
  /// Gets position, fills origin field, then shifts focus to destination.
  Future<void> _useCurrentLocation() async {
    final ctrl = context.read<ExploreController>();
    await ctrl.useCurrentLocationAsOrigin();
    if (!mounted) return;
    // After GPS fills the field, sync the controller text
    _currentCtrl.text = ctrl.originText;
    _destFocus.requestFocus();
    _setFocusState(false);
  }

  @override
  Widget build(BuildContext context) {
    final isDark = context.watch<ThemeController>().isDark;
    final query = _isOriginFocused ? _currentCtrl.text : _destCtrl.text;

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: isDark ? SystemUiOverlayStyle.light : SystemUiOverlayStyle.dark,
      child: Scaffold(
        backgroundColor: AppColors.bg(isDark),
        body: SafeArea(
          child: Column(
            children: [
              _InputHeader(
                currentCtrl: _currentCtrl,
                destCtrl: _destCtrl,
                currentFocus: _currentFocus,
                destFocus: _destFocus,
                currentActive: _currentActive,
                onCurrentTap: () => _currentFocus.requestFocus(),
                onDestTap: () => _destFocus.requestFocus(),
                onSearch: _search,
                onBack: _back,
                onUseCurrentLocation: _useCurrentLocation,
              ),
              const _ModeSelectorRow(),
              Expanded(
                child: _SuggestionList(
                  staticItems: _filteredStatic,
                  apiSuggestions: _apiSuggestions,
                  isLoadingApi: _isLoadingApi,
                  query: query,
                  onSelectStatic: _onStaticItemTap,
                  onSelectApi: _onApiItemTap,
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
// MODE SELECTOR ROW — Transit / Walk / Car / Motorcycle
// ═══════════════════════════════════════════════════════════════

class _ModeSelectorRow extends StatelessWidget {
  const _ModeSelectorRow();

  static const _modes = [
    _ModeOption(key: 'transit', label: 'Transit', emoji: '🚌'),
    _ModeOption(key: 'walk', label: 'Walk', emoji: '🚶'),
    _ModeOption(key: 'car', label: 'Car', emoji: '🚗'),
    _ModeOption(key: 'motorcycle', label: 'Motorcycle', emoji: '🏍️'),
  ];

  @override
  Widget build(BuildContext context) {
    final ctrl = context.watch<ExploreController>();
    final isDark = context.watch<ThemeController>().isDark;

    return Container(
      height: 56,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      decoration: BoxDecoration(
        color: AppColors.bg(isDark),
        border: Border(bottom: BorderSide(color: AppColors.border(isDark))),
      ),
      child: Row(
        children: _modes.map((m) {
          final isActive = ctrl.activeMode == m.key;
          return Expanded(
            child: GestureDetector(
              onTap: () => ctrl.setMode(m.key),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                margin: const EdgeInsets.symmetric(horizontal: 4),
                decoration: BoxDecoration(
                  color: isActive ? AppColors.teal : AppColors.card2(isDark),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(
                    color: isActive ? AppColors.teal : AppColors.border(isDark),
                  ),
                ),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(m.emoji, style: const TextStyle(fontSize: 14)),
                    const SizedBox(height: 1),
                    Text(
                      m.label,
                      style: GoogleFonts.plusJakartaSans(
                        fontSize: 9,
                        fontWeight: FontWeight.w700,
                        color: isActive
                            ? Colors.white
                            : AppColors.text2(isDark),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          );
        }).toList(),
      ),
    );
  }
}

class _ModeOption {
  final String key, label, emoji;
  const _ModeOption({
    required this.key,
    required this.label,
    required this.emoji,
  });
}

// ═══════════════════════════════════════════════════════════════
// SEARCH OVERLAY COMPONENTS
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
    required this.onUseCurrentLocation,
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
  final VoidCallback onUseCurrentLocation; // ← NEW: GPS tap handler

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
                  width: 32,
                  height: 32,
                  margin: const EdgeInsets.only(top: 6),
                  decoration: BoxDecoration(
                    color: AppColors.card2(isDark),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Icon(
                    Icons.arrow_back_rounded,
                    size: 18,
                    color: AppColors.text2(isDark),
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Column(
                children: [
                  const SizedBox(height: 14),
                  _Dot(
                    color: currentActive
                        ? AppColors.teal
                        : AppColors.text3(isDark),
                  ),
                  Container(
                    width: 2,
                    height: 32,
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.topCenter,
                        end: Alignment.bottomCenter,
                        colors: [
                          currentActive
                              ? AppColors.teal
                              : AppColors.text3(isDark),
                          !currentActive
                              ? AppColors.teal
                              : AppColors.text3(isDark),
                        ],
                      ),
                    ),
                  ),
                  _Dot(
                    color: !currentActive
                        ? AppColors.teal
                        : AppColors.text3(isDark),
                  ),
                ],
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  children: [
                    // ── Current location field with GPS icon ──────────────────
                    Row(
                      children: [
                        Expanded(
                          child: _InputField(
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
                        ),
                        const SizedBox(width: 6),
                        // ── GPS button — fills origin from device location ──
                        GestureDetector(
                          onTap: onUseCurrentLocation,
                          child: Container(
                            width: 32,
                            height: 32,
                            decoration: BoxDecoration(
                              color: AppColors.teal,
                              borderRadius: BorderRadius.circular(8),
                              boxShadow: [
                                BoxShadow(
                                  color: AppColors.teal.withValues(alpha: 0.35),
                                  blurRadius: 8,
                                ),
                              ],
                            ),
                            child: const Icon(
                              Icons.my_location_rounded,
                              color: Colors.white,
                              size: 16,
                            ),
                          ),
                        ),
                      ],
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
            'Tap the 📍 icon to use your current location',
            style: GoogleFonts.plusJakartaSans(
              fontSize: 11,
              color: AppColors.text3(isDark),
              fontWeight: FontWeight.w500,
            ),
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
      width: 10,
      height: 10,
      decoration: BoxDecoration(
        color: color,
        shape: BoxShape.circle,
        border: Border.all(
          color: AppColors.card2(context.watch<ThemeController>().isDark),
          width: 2,
        ),
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
          color: isActive ? AppColors.teal : Colors.transparent,
        ),
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
                color: AppColors.text(isDark),
                fontSize: 13,
              ),
              decoration: InputDecoration(
                hintText: hint,
                hintStyle: GoogleFonts.plusJakartaSans(
                  color: AppColors.text2(isDark),
                  fontSize: 13,
                ),
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
                      child: Icon(
                        Icons.close_rounded,
                        size: 14,
                        color: AppColors.text2(isDark),
                      ),
                    ),
            ),
        ],
      ),
    );
  }
}

// ── Unified suggestion list ────────────────────────────────────
// Shows live API results first, then static favourites below.
class _SuggestionList extends StatelessWidget {
  final List<MiniItem> staticItems;
  final List<Map<String, dynamic>> apiSuggestions;
  final bool isLoadingApi;
  final String query;
  final void Function(MiniItem) onSelectStatic;
  final void Function(String) onSelectApi;

  const _SuggestionList({
    required this.staticItems,
    required this.apiSuggestions,
    required this.isLoadingApi,
    required this.query,
    required this.onSelectStatic,
    required this.onSelectApi,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = context.watch<ThemeController>().isDark;
    final hasApi = apiSuggestions.isNotEmpty;
    final hasStatic = staticItems.isNotEmpty;
    final isEmpty = !hasApi && !hasStatic && query.isNotEmpty && !isLoadingApi;

    if (isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.search_off_rounded,
              size: 48,
              color: AppColors.text3(isDark),
            ),
            const SizedBox(height: 16),
            Text(
              'No results for "$query"',
              style: GoogleFonts.plusJakartaSans(
                fontSize: 14,
                color: AppColors.text2(isDark),
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
      );
    }

    return ListView(
      keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
      children: [
        // ── Loading indicator while API call is in-flight ──────
        if (isLoadingApi)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 12),
            child: Center(
              child: SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  color: AppColors.teal,
                ),
              ),
            ),
          ),

        // ── Live API results (Nominatim) ───────────────────────
        if (hasApi) ...[
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
            child: Text(
              'Places',
              style: GoogleFonts.plusJakartaSans(
                fontSize: 10,
                fontWeight: FontWeight.w800,
                color: AppColors.text3(isDark),
                letterSpacing: 0.8,
              ),
            ),
          ),
          ...apiSuggestions.map((place) {
            final name = place['display_name'] as String? ?? '';
            final address = place['address'] as Map? ?? {};
            // Build a short readable label from the address parts
            final shortName = [
              address['road'] as String?,
              address['suburb'] as String? ?? address['city'] as String?,
            ].where((s) => s != null && s.isNotEmpty).join(', ');

            return ListTile(
              leading: Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  color: AppColors.tealDim,
                  borderRadius: BorderRadius.circular(10),
                ),
                child: const Icon(
                  Icons.location_on_rounded,
                  size: 18,
                  color: AppColors.teal,
                ),
              ),
              title: _HighlightedText(
                text: shortName.isNotEmpty ? shortName : name,
                query: query,
                style: GoogleFonts.plusJakartaSans(
                  color: AppColors.text(isDark),
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                ),
              ),
              subtitle: shortName.isNotEmpty
                  ? Text(
                      name,
                      style: GoogleFonts.plusJakartaSans(
                        color: AppColors.text2(isDark),
                        fontSize: 10,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    )
                  : null,
              onTap: () => onSelectApi(shortName.isNotEmpty ? shortName : name),
            );
          }),
        ],

        // ── Static favourites / recent places ─────────────────
        if (hasStatic) ...[
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
            child: Text(
              hasApi ? 'Suggestions' : 'Recent & Saved',
              style: GoogleFonts.plusJakartaSans(
                fontSize: 10,
                fontWeight: FontWeight.w800,
                color: AppColors.text3(isDark),
                letterSpacing: 0.8,
              ),
            ),
          ),
          ...staticItems.map(
            (item) => _SuggestionTile(
              item: item,
              query: query,
              onTap: () => onSelectStatic(item),
            ),
          ),
        ],
      ],
    );
  }
}

class _SuggestionTile extends StatelessWidget {
  final MiniItem item;
  final String query;
  final VoidCallback onTap;
  const _SuggestionTile({
    required this.item,
    required this.query,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = context.watch<ThemeController>().isDark;
    return ListTile(
      leading: Container(
        width: 36,
        height: 36,
        decoration: BoxDecoration(
          color: AppColors.card2(isDark),
          borderRadius: BorderRadius.circular(10),
        ),
        child: Icon(
          item.icon,
          size: 18,
          color: item.type == MiniItemType.heart
              ? AppColors.safeRed
              : AppColors.text2(isDark),
        ),
      ),
      title: _HighlightedText(
        text: item.name,
        query: query,
        style: GoogleFonts.plusJakartaSans(
          color: AppColors.text(isDark),
          fontSize: 13,
          fontWeight: FontWeight.w600,
        ),
      ),
      subtitle: Text(
        item.sub,
        style: GoogleFonts.plusJakartaSans(
          color: AppColors.text2(isDark),
          fontSize: 11,
        ),
      ),
      onTap: onTap,
    );
  }
}

class _HighlightedText extends StatelessWidget {
  final String text;
  final String query;
  final TextStyle style;
  const _HighlightedText({
    required this.text,
    required this.query,
    required this.style,
  });

  @override
  Widget build(BuildContext context) {
    final lowerText = text.toLowerCase();
    final lowerQuery = query.toLowerCase();
    final index = lowerText.indexOf(lowerQuery);

    if (query.isEmpty || index == -1) {
      return Text(
        text,
        style: style,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
      );
    }
    return Text.rich(
      TextSpan(
        children: [
          TextSpan(text: text.substring(0, index)),
          TextSpan(
            text: text.substring(index, index + query.length),
            style: const TextStyle(
              fontWeight: FontWeight.w800,
              color: AppColors.teal,
            ),
          ),
          TextSpan(text: text.substring(index + query.length)),
        ],
        style: style,
      ),
      maxLines: 1,
      overflow: TextOverflow.ellipsis,
    );
  }
}
