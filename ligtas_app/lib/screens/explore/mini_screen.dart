import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';

import '../../core/app_colors.dart';
import '../../core/theme_controller.dart';
import '../../data/search_history.dart';
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
//   1. Calls GPS → reverse-geocodes via /api/reverse → fills the origin field
//   2. Then opens the search overlay so the user just needs to type a dest.
// The hint text shows the most recent destination from SearchHistoryService.
class _LandingSearchPill extends StatefulWidget {
  final VoidCallback onSearchTap;
  const _LandingSearchPill({required this.onSearchTap});

  @override
  State<_LandingSearchPill> createState() => _LandingSearchPillState();
}

class _LandingSearchPillState extends State<_LandingSearchPill> {
  String? _lastDest;
  bool _gpsLoading = false;

  @override
  void initState() {
    super.initState();
    _loadLastDest();
  }

  Future<void> _loadLastDest() async {
    final recents = await SearchHistoryService.instance.loadRecents();
    if (!mounted) return;
    setState(() {
      _lastDest = recents.isNotEmpty ? recents.first.name : null;
    });
  }

  Future<void> _openSearch() async {
    // Transition to state2 first so the map renders behind the search overlay.
    // Both this call and the Navigator push happen in the same frame, so the
    // context is still valid. The landing widget will be disposed on the next
    // frame — that's fine since _loadLastDest() checks mounted.
    context.read<ExploreController>().setState(AppState.state2);
    await Navigator.of(context).pushNamed(MiniScreen.routeName);
    await _loadLastDest();
  }

  Future<void> _onGpsTap() async {
    if (_gpsLoading) return;
    setState(() => _gpsLoading = true);
    try {
      await context.read<ExploreController>().useCurrentLocationAsOrigin();
    } finally {
      if (mounted) setState(() => _gpsLoading = false);
    }
    await _openSearch();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = context.watch<ThemeController>().isDark;

    final hasRecent = _lastDest != null;

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
              onTap: _openSearch,
              behavior: HitTestBehavior.opaque,
              child: Row(
                children: [
                  Icon(
                    hasRecent ? Icons.history_rounded : Icons.search_rounded,
                    color: AppColors.teal,
                    size: 20,
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        if (hasRecent)
                          Text(
                            'Last: $_lastDest',
                            style: GoogleFonts.plusJakartaSans(
                              fontSize: 14,
                              color: AppColors.text(isDark),
                              fontWeight: FontWeight.w600,
                            ),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          )
                        else
                          Text(
                            'Search destination…',
                            style: GoogleFonts.plusJakartaSans(
                              fontSize: 15,
                              color: AppColors.text2(isDark),
                              fontWeight: FontWeight.w500,
                            ),
                          ),
                        if (hasRecent)
                          Text(
                            'Tap to search again',
                            style: GoogleFonts.plusJakartaSans(
                              fontSize: 11,
                              color: AppColors.text3(isDark),
                            ),
                          ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
          // ── GPS icon — reverse-geocodes origin via backend, then opens search ──
          GestureDetector(
            onTap: _onGpsTap,
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
              child: _gpsLoading
                  ? const Padding(
                      padding: EdgeInsets.all(10),
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: Colors.white,
                      ),
                    )
                  : const Icon(
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
  // Two separate suggestion lists: persistent history + live API results.
  List<MiniItem> _recents = [];
  List<MiniItem> _saved = [];
  List<MiniItem> _filteredStatic = [];
  List<Map<String, dynamic>> _apiSuggestions = []; // from /api/suggest
  String _lastQuery = '___INIT___';
  Timer? _debounce;
  bool _isLoadingApi = false;
  // Set true by tap handlers so _search() doesn't double-save to recents.
  bool _destRecentSaved = false;

  @override
  void initState() {
    super.initState();

    final ctrl = context.read<ExploreController>();
    _currentCtrl.text = ctrl.originText;
    _destCtrl.text = ctrl.destText;
    // History loads asynchronously; list starts empty until ready.
    _loadHistory();

    // If origin is empty but GPS coordinates are already available,
    // silently re-fill origin from the device location (mirrors web behaviour
    // where "My Location" sticks as the default origin).
    if (_currentCtrl.text.isEmpty && ctrl.hasLocation && ctrl.lat != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) async {
        if (!mounted) return;
        await _useCurrentLocation();
      });
    }

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

  Future<void> _loadHistory() async {
    final recents = await SearchHistoryService.instance.loadRecents();
    final saved = await SearchHistoryService.instance.loadSaved();
    if (!mounted) return;
    setState(() {
      _recents = recents;
      _saved = saved;
      // Saved first, then recent — same order as display sections.
      _filteredStatic = [..._saved, ..._recents];
    });
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

    // Always update local results instantly
    setState(() {
      _filteredStatic = query.isEmpty
          ? [..._saved, ..._recents]
          : _searchStatic(query);
      _apiSuggestions = [];
      // Show spinner immediately once the user has typed enough
      if (query.length >= 3) _isLoadingApi = true;
    });

    // Debounce: wait 380ms after the user stops typing before hitting the API.
    // This avoids flooding /api/suggest on every keystroke.
    _debounce?.cancel();
    if (query.length >= 3) {
      _debounce = Timer(
        const Duration(milliseconds: 380),
        () => _fetchApiSuggestions(query),
      );
    } else {
      // Query too short — clear the spinner if it was set
      if (_isLoadingApi) setState(() => _isLoadingApi = false);
    }
  }

  Future<void> _fetchApiSuggestions(String query) async {
    if (!mounted) return;
    try {
      final ctrl = context.read<ExploreController>();
      final results = await ctrl.suggestLocations(query);
      if (!mounted) return;
      // Guard: only apply if the active field still matches this query
      final currentQuery = _isOriginFocused
          ? _currentCtrl.text
          : _destCtrl.text;
      if (currentQuery == query) {
        setState(() {
          _apiSuggestions = results;
          _isLoadingApi = false;
        });
      } else {
        // A newer query is already in flight — just kill the spinner
        setState(() => _isLoadingApi = false);
      }
    } catch (_) {
      if (mounted) setState(() => _isLoadingApi = false);
    }
  }

  List<MiniItem> _searchStatic(String query) {
    final lowerQuery = query.toLowerCase().trim();
    final allLocal = [..._saved, ..._recents];
    final scored = allLocal
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

    // Persist destination to recents — but only for manually typed text.
    // Tap handlers (_onApiItemTap / _onStaticItemTap) already saved with
    // proper sub + coordinates; don't overwrite with an empty-sub duplicate.
    if (_destCtrl.text.isNotEmpty && !_destRecentSaved) {
      SearchHistoryService.instance.addRecent(_destCtrl.text, '');
    }
    _destRecentSaved = false;

    // searchRoutes() sets state → state2 synchronously on its first line,
    // so the map is already showing the moment we pop back to ExploreView.
    // The async geocoding + route fetching completes in the background and
    // notifyListeners() triggers map repaints as each step finishes.
    ctrl.searchRoutes(); // intentionally not awaited — fire and pop
    if (mounted) Navigator.of(context).pop();
  }

  void _back() {
    FocusScope.of(context).unfocus();
    final ctrl = context.read<ExploreController>();
    // If user opened search from the landing and backed out without searching,
    // return to the landing screen (state1). Keep state2 if a prior search
    // exists or GPS origin was already set.
    if (ctrl.routes.isEmpty &&
        ctrl.destText.isEmpty &&
        ctrl.originText.isEmpty) {
      ctrl.setState(AppState.state1);
    }
    Navigator.of(context).pop();
  }

  void _onStaticItemTap(MiniItem item) {
    final ctrl = context.read<ExploreController>();
    if (_isOriginFocused) {
      // Pre-seed origin pin on map immediately if coordinates are cached.
      if (item.lat != null && item.lon != null) {
        ctrl.previewLocation(
          isOrigin: true,
          lat: item.lat!,
          lon: item.lon!,
          label: item.name,
        );
      }
      _currentCtrl.text = item.name;
      _destFocus.requestFocus();
    } else {
      // Pre-seed dest pin on map immediately if coordinates are cached.
      if (item.lat != null && item.lon != null) {
        ctrl.previewLocation(
          isOrigin: false,
          lat: item.lat!,
          lon: item.lon!,
          label: item.name,
        );
      }
      _destCtrl.text = item.name;
      // Bump to top of recents with coords preserved.
      _destRecentSaved = true;
      SearchHistoryService.instance.addRecent(
        item.name, item.sub,
        lat: item.lat, lon: item.lon,
      );
    }
    if (_currentCtrl.text.isNotEmpty && _destCtrl.text.isNotEmpty) {
      _search();
    }
  }

  void _onApiItemTap(String placeName, String sub, double lat, double lon) {
    final ctrl = context.read<ExploreController>();
    // Pre-seed resolved coordinates and pan the map immediately (web parity).
    ctrl.previewLocation(
      isOrigin: _isOriginFocused,
      lat: lat,
      lon: lon,
      label: placeName,
    );
    if (_isOriginFocused) {
      _currentCtrl.text = placeName;
      _destFocus.requestFocus();
    } else {
      _destCtrl.text = placeName;
      // Save destination to recents with full coordinates.
      _destRecentSaved = true;
      SearchHistoryService.instance.addRecent(placeName, sub, lat: lat, lon: lon);
    }
    setState(() {
      _apiSuggestions = [];
    });
    if (_currentCtrl.text.isNotEmpty && _destCtrl.text.isNotEmpty) {
      _search();
    }
  }

  Future<void> _toggleSave(MiniItem item) async {
    await SearchHistoryService.instance.toggleSaved(
      item.name, item.sub,
      lat: item.lat, lon: item.lon,
    );
    await _loadHistory();
  }

  Future<void> _removeRecent(String name) async {
    await SearchHistoryService.instance.removeRecent(name);
    await _loadHistory();
  }

  /// Mirrors Flask's locate-dest-btn → startPinPick('dest').
  /// Pops the search overlay and activates pinpoint-destination mode so
  /// the next map tap sets the destination (exactly as the web does).
  void _pinpointDest() {
    FocusScope.of(context).unfocus();
    final ctrl = context.read<ExploreController>();
    // Ensure the map state is active before popping.
    if (ctrl.state == AppState.state1) ctrl.setState(AppState.state2);
    // Enable pinpoint mode BEFORE popping so the banner appears immediately.
    if (!ctrl.pinpointDestMode) ctrl.togglePinpointDestMode();
    Navigator.of(context).pop();
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
        // Always transparent — the map is always rendered behind this overlay
        // (we transition to state2 before pushing this route from landing).
        backgroundColor: Colors.transparent,
        body: SafeArea(
          bottom: false,
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
                onPinDestTap: _pinpointDest,
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
                  onToggleSave: _toggleSave,
                  onRemoveRecent: _removeRecent,
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
    _ModeOption(key: 'transit', label: 'Transit', icon: Icons.directions_bus_rounded),
    _ModeOption(key: 'walk', label: 'Walk', icon: Icons.directions_walk_rounded),
    _ModeOption(key: 'car', label: 'Car', icon: Icons.directions_car_rounded),
    _ModeOption(key: 'motorcycle', label: 'Motorcycle', icon: Icons.two_wheeler_rounded),
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
                    Icon(m.icon, size: 16, color: isActive ? Colors.white : AppColors.text2(isDark)),
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
  final String key, label;
  final IconData icon;
  const _ModeOption({
    required this.key,
    required this.label,
    required this.icon,
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
    required this.onPinDestTap,
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
  final VoidCallback onUseCurrentLocation; // GPS: use device location as origin
  final VoidCallback onPinDestTap;         // Pin: tap map to set destination

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
                    Row(
                      children: [
                        Expanded(
                          child: _InputField(
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
                        ),
                        const SizedBox(width: 6),
                        // ── Pin-destination button — tap map to set dest ──
                        // Mirrors Flask's locate-dest-btn → startPinPick('dest')
                        Builder(builder: (context) {
                          final active = context
                              .watch<ExploreController>()
                              .pinpointDestMode;
                          return GestureDetector(
                            onTap: onPinDestTap,
                            child: AnimatedContainer(
                              duration: const Duration(milliseconds: 180),
                              width: 32,
                              height: 32,
                              decoration: BoxDecoration(
                                color: active
                                    ? const Color(0xFF6C5CE7)
                                    : AppColors.card2(
                                        context
                                            .watch<ThemeController>()
                                            .isDark,
                                      ),
                                borderRadius: BorderRadius.circular(8),
                                border: Border.all(
                                  color: active
                                      ? const Color(0xFF6C5CE7)
                                      : AppColors.border(
                                          context
                                              .watch<ThemeController>()
                                              .isDark,
                                        ),
                                ),
                              ),
                              child: Icon(
                                Icons.push_pin_rounded,
                                color: active ? Colors.white : AppColors.teal,
                                size: 16,
                              ),
                            ),
                          );
                        }),
                      ],
                    ),
                  ],
                ),
              ),
              // ── [x] dismiss — go straight to map ──────────────────────────
              GestureDetector(
                onTap: onBack,
                child: Container(
                  width: 32,
                  height: 32,
                  margin: const EdgeInsets.only(top: 6, left: 8),
                  decoration: BoxDecoration(
                    color: AppColors.card2(isDark),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Icon(
                    Icons.close_rounded,
                    size: 18,
                    color: AppColors.text2(isDark),
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            'Tap 📡 for GPS location · Tap 📌 to pin dest on map',
            style: GoogleFonts.plusJakartaSans(
              fontSize: 11,
              color: AppColors.text3(isDark),
              fontWeight: FontWeight.w500,
            ),
          ),
          // ── Find Routes button — visible when both fields are filled ──
          ListenableBuilder(
            listenable: Listenable.merge([currentCtrl, destCtrl]),
            builder: (_, child) {
              final bothFilled =
                  currentCtrl.text.isNotEmpty && destCtrl.text.isNotEmpty;
              return AnimatedSize(
                duration: const Duration(milliseconds: 220),
                curve: Curves.easeOutCubic,
                child: bothFilled
                    ? Padding(
                        padding: const EdgeInsets.only(top: 10),
                        child: GestureDetector(
                          onTap: onSearch,
                          child: Container(
                            width: double.infinity,
                            padding: const EdgeInsets.symmetric(vertical: 13),
                            decoration: BoxDecoration(
                              color: AppColors.teal,
                              borderRadius: BorderRadius.circular(12),
                              boxShadow: [
                                BoxShadow(
                                  color: AppColors.teal.withValues(alpha: 0.40),
                                  blurRadius: 12,
                                  offset: const Offset(0, 4),
                                ),
                              ],
                            ),
                            child: Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                const Icon(
                                  Icons.route_rounded,
                                  color: Colors.white,
                                  size: 18,
                                ),
                                const SizedBox(width: 8),
                                Text(
                                  'Find Safe Routes',
                                  style: GoogleFonts.plusJakartaSans(
                                    fontSize: 14,
                                    fontWeight: FontWeight.w800,
                                    color: Colors.white,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      )
                    : const SizedBox.shrink(),
              );
            },
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
  final void Function(String name, String sub, double lat, double lon) onSelectApi;
  final void Function(MiniItem) onToggleSave;
  final void Function(String name) onRemoveRecent;

  const _SuggestionList({
    required this.staticItems,
    required this.apiSuggestions,
    required this.isLoadingApi,
    required this.query,
    required this.onSelectStatic,
    required this.onSelectApi,
    required this.onToggleSave,
    required this.onRemoveRecent,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = context.watch<ThemeController>().isDark;
    final hasApi = apiSuggestions.isNotEmpty;

    // Split persistent items into sections.
    final savedItems = staticItems.where((i) => i.type == MiniItemType.pin).toList();
    final recentItems = staticItems.where((i) => i.type == MiniItemType.clock).toList();
    final hasStatic = savedItems.isNotEmpty || recentItems.isNotEmpty;

    final isEmpty = !hasApi && !hasStatic && query.isNotEmpty && !isLoadingApi;
    final isEmptyAndNoQuery = !hasApi && !hasStatic && query.isEmpty && !isLoadingApi;

    if (isEmpty) {
      return ColoredBox(
        color: AppColors.bg(isDark),
        child: Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(Icons.search_off_rounded, size: 48, color: AppColors.text3(isDark)),
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
        ),
      );
    }

    if (isEmptyAndNoQuery) {
      return const SizedBox.shrink();
    }

    return ColoredBox(
      color: AppColors.bg(isDark),
      child: ListView(
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
                child: CircularProgressIndicator(strokeWidth: 2, color: AppColors.teal),
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
            final fullName = place['display_name'] as String? ?? '';
            final address = place['address'] as Map? ?? {};

            // Philippine Nominatim address fields, in preference order:
            //   road / amenity → what the place is called on the street
            //   suburb → barangay-level name
            //   city_district / city / municipality / town / village → urban area
            //   province → for the subtitle locality line
            final String? road = (address['road'] ?? address['amenity'])
                ?.toString().trim().isNotEmpty == true
                ? (address['road'] ?? address['amenity']).toString().trim()
                : null;
            final String? locality = (address['suburb'] ??
                    address['city_district'] ??
                    address['city'] ??
                    address['municipality'] ??
                    address['town'] ??
                    address['village'])
                ?.toString()
                .trim();
            final String? province =
                (address['province'] ?? address['state'])
                    ?.toString()
                    .trim();

            // Title: "Road, Locality" or just the first segment of display_name
            final titleParts = [road, locality]
                .where((s) => s != null && s.isNotEmpty)
                .cast<String>()
                .toList();
            final displayName = titleParts.isNotEmpty
                ? titleParts.join(', ')
                : fullName.split(',').first.trim();

            // Subtitle: province + rest of full address for context
            final subtitleParts = [
              if (locality != null && locality.isNotEmpty && road != null)
                locality,
              if (province != null && province.isNotEmpty) province,
            ];
            final sub = subtitleParts.isNotEmpty
                ? subtitleParts.join(', ')
                : (displayName != fullName ? fullName : '');

            return ListTile(
              leading: Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  color: AppColors.tealDim,
                  borderRadius: BorderRadius.circular(10),
                ),
                child: const Icon(Icons.location_on_rounded, size: 18, color: AppColors.teal),
              ),
              title: _HighlightedText(
                text: displayName,
                query: query,
                style: GoogleFonts.plusJakartaSans(
                  color: AppColors.text(isDark),
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                ),
              ),
              subtitle: sub.isNotEmpty
                  ? Text(
                      sub,
                      style: GoogleFonts.plusJakartaSans(
                        color: AppColors.text2(isDark),
                        fontSize: 10,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    )
                  : null,
              onTap: () {
                final lat = double.tryParse(place['lat']?.toString() ?? '') ?? 0;
                final lon = double.tryParse(place['lon']?.toString() ?? '') ?? 0;
                onSelectApi(displayName, sub, lat, lon);
              },
            );
          }),
        ],

        // ── Saved places ───────────────────────────────────────
        if (savedItems.isNotEmpty) ...[
          _SectionHeader(
            label: hasApi ? 'Saved' : 'Saved',
            isDark: isDark,
          ),
          ...savedItems.map(
            (item) => _SuggestionTile(
              item: item,
              query: query,
              onTap: () => onSelectStatic(item),
              onToggleSave: () => onToggleSave(item),
            ),
          ),
        ],

        // ── Recent searches ────────────────────────────────────
        if (recentItems.isNotEmpty) ...[
          _SectionHeader(
            label: hasApi ? 'Recent' : 'Recent',
            isDark: isDark,
          ),
          ...recentItems.map(
            (item) => _SuggestionTile(
              item: item,
              query: query,
              onTap: () => onSelectStatic(item),
              onToggleSave: () => onToggleSave(item),
              onRemove: () => onRemoveRecent(item.name),
            ),
          ),
        ],
      ],
    ),
    ); // ColoredBox
  }
}

// ── Section header ─────────────────────────────────────────────
class _SectionHeader extends StatelessWidget {
  final String label;
  final bool isDark;
  const _SectionHeader({required this.label, required this.isDark});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
      child: Text(
        label.toUpperCase(),
        style: GoogleFonts.plusJakartaSans(
          fontSize: 10,
          fontWeight: FontWeight.w800,
          color: AppColors.text3(isDark),
          letterSpacing: 0.8,
        ),
      ),
    );
  }
}

class _SuggestionTile extends StatelessWidget {
  final MiniItem item;
  final String query;
  final VoidCallback onTap;
  final VoidCallback onToggleSave;
  final VoidCallback? onRemove;

  const _SuggestionTile({
    required this.item,
    required this.query,
    required this.onTap,
    required this.onToggleSave,
    this.onRemove,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = context.watch<ThemeController>().isDark;
    final isSaved = item.type == MiniItemType.pin;

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
      subtitle: item.sub.isNotEmpty
          ? Text(
              item.sub,
              style: GoogleFonts.plusJakartaSans(
                color: AppColors.text2(isDark),
                fontSize: 11,
              ),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            )
          : null,
      onTap: onTap,
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Save / unsave bookmark button
          GestureDetector(
            onTap: onToggleSave,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 6),
              child: Icon(
                isSaved ? Icons.bookmark_rounded : Icons.bookmark_border_rounded,
                size: 18,
                color: isSaved ? AppColors.teal : AppColors.text3(isDark),
              ),
            ),
          ),
          // Remove button — only on recents (clock items)
          if (onRemove != null)
            GestureDetector(
              onTap: onRemove,
              child: Padding(
                padding: const EdgeInsets.only(left: 2),
                child: Icon(
                  Icons.close_rounded,
                  size: 16,
                  color: AppColors.text3(isDark),
                ),
              ),
            ),
        ],
      ),
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
