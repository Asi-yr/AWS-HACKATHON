import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../models/explore_models.dart';
import '../../data/mock_data.dart';
import 'explore_controller.dart';
import 'mini_screen.dart';
import '../../core/app_colors.dart';
//import '../../core/ligtas_theme.dart';
import '../../core/theme_controller.dart';

// ── Route Preference Filter Options ────────────────────────────────────────
// These options let users prioritize routes by different criteria
final preferenceOptions = [
  FilterOption(key: 'safest', label: 'Safest', icon: Icons.shield_rounded),
  FilterOption(key: 'fastest', label: 'Fastest', icon: Icons.speed_rounded),
  FilterOption(key: 'cheapest', label: 'Cheapest', icon: Icons.savings_rounded),
  FilterOption(key: 'balanced', label: 'Balanced', icon: Icons.balance_rounded),
  FilterOption(key: 'moderate', label: 'Moderate', icon: Icons.adjust_rounded),
];

class ExploreView extends StatelessWidget {
  const ExploreView({super.key});

  @override
  Widget build(BuildContext context) {
    return const _ExploreScaffold(); 
  }
}

class _ExploreScaffold extends StatefulWidget {
  const _ExploreScaffold();
  @override
  State<_ExploreScaffold> createState() => _ExploreScaffoldState();
}

class _ExploreScaffoldState extends State<_ExploreScaffold> {
  final MapController _mapCtrl = MapController();

  // Panel drag state for the suggestion drawer
  // We track panel height directly in pixels — simple and predictable.
  static const double _panelMin  = 0.30; // default height when drawer opens (30% of screen) 
  static const double _panelMax  = 0.58;  // max — stops well below the search header (which is ~top 20%)
  double _panelHeight = -1; // -1 = uninitialised, set on first build

  void _onPanelDragStart(DragStartDetails d, double screenH) {}

  void _onPanelDragUpdate(DragUpdateDetails d, double screenH) {
    // Dragging UP (negative delta) should INCREASE panel height
    setState(() {
      _panelHeight = (_panelHeight - d.primaryDelta!)
          .clamp(screenH * _panelMin, screenH * _panelMax);
    });
  }

  void _onPanelDragEnd(DragEndDetails d, double screenH) {
  final min  = screenH * _panelMin;
  final max  = screenH * _panelMax;
  final vel  = d.primaryVelocity ?? 0;
  double target;

  if (vel < -400) {
    target = max;               // fast fling up → full open
  } else if (vel > 400) {
    target = min;               // fast fling down → back to default
  } else {
    // Snap to nearest of two positions
    final snaps = [min, max];
    target = snaps.reduce((a, b) =>
      (a - _panelHeight).abs() < (b - _panelHeight).abs() ? a : b);
  }

  setState(() => _panelHeight = target);
}

  @override
  void dispose() {
    super.dispose();
  }

  void _openSearch(BuildContext context) {
    Navigator.of(context).pushNamed(MiniScreen.routeName);
  }

  @override
  Widget build(BuildContext context) {
    final appState = context.select<ExploreController, AppState>((c) => c.state);
    final screenHeight = MediaQuery.of(context).size.height;

    final isState2    = appState == AppState.state2;
    final isState3    = appState == AppState.state3;
    final isNavigating = appState == AppState.state4;

    // Initialise panel height on first build
    if (_panelHeight < 0) _panelHeight = screenHeight * _panelMin;

    // State3 fixed panel
    final detailPanelHeight  = screenHeight * 0.65;
    final detailPanelBottom  = isState3 ? 0.0 : -detailPanelHeight;

    // ── Button layout logic ────────────────────────────────────────
    // Panel top edge (from screen bottom) = 72 (nav) + _panelHeight
    final double panelTopEdge = 72 + _panelHeight;

    // The 3-button column is 3×38 + 2×8 = 130px tall.
    // Fix their bottom at exactly 12px above the panel at DEFAULT height.
    // When the panel rises, it naturally covers them (Stack order handles it).
    final double zoomBtnsBottom = 72 + screenHeight * _panelMin + 12;

    // Ligtas sits at the top of the 3-button column at default panel height.
    // Column top = zoomBtnsBottom + columnHeight + 8 gap
    const double zoomColHeight = 130.0; // 3×38 + 2×8
    final double ligtasDefaultBottom = zoomBtnsBottom + zoomColHeight + 8;

    // Once the panel top rises above ligtasDefaultBottom, Ligtas rides with it.
    // Cap at panelMax so it never goes above the highest the panel can reach.
    final double ligtasMaxBottom = 72 + screenHeight * _panelMax + 12;
    double ligtasBottom;
    if (isState2) {
      // Only start moving once the panel top passes the ligtas default position
      final double rideStart = ligtasDefaultBottom - 12; // panel top that triggers movement
      if (panelTopEdge > rideStart) {
        ligtasBottom = (panelTopEdge + 12).clamp(ligtasDefaultBottom, ligtasMaxBottom);
      } else {
        ligtasBottom = ligtasDefaultBottom;
      }
    } else if (isNavigating) {
      ligtasBottom = 160;
    } else {
      ligtasBottom = 96;
    }

    final isDark = context.watch<ThemeController>().isDark;

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: isDark ? SystemUiOverlayStyle.light : SystemUiOverlayStyle.dark,
      child: Scaffold(
        backgroundColor: AppColors.bg(isDark),
        body: Stack(
          children: [
            if (appState != AppState.state1)
              RepaintBoundary(child: _MapLayer(mapCtrl: _mapCtrl)),

            if (appState == AppState.state1)
              MiniScreen(onSearchTap: () => _openSearch(context)),

            if (isState2 || isState3)
              _SearchHeader(onTap: () => _openSearch(context)),

            if (isNavigating) const _NavHeader(),
            if (isNavigating) const _StopBar(),

            // ── Zoom/center: rendered BEFORE the panel so panel covers them ──
            if (isState2)
              _MapZoomControls(
                mapCtrl: _mapCtrl,
                bottomPadding: zoomBtnsBottom,
              ),

            // ── Suggestion panel — pinned above nav bar (72px) ──────────
            // Rendered AFTER zoom buttons so it naturally covers them on drag.
            if (isState2)
              Positioned(
                left: 0, right: 0, bottom: 72, // sits on top of the nav bar
                height: _panelHeight,
                child: Container(
                  decoration: BoxDecoration(
                    color: AppColors.card(isDark),
                    borderRadius: const BorderRadius.vertical(top: Radius.circular(32)),
                    border: Border(top: BorderSide(color: AppColors.border(isDark))),
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withValues(alpha: 0.3),
                        blurRadius: 20, offset: const Offset(0, -4),
                      ),
                    ],
                  ),
                  child: ClipRRect(
                    borderRadius: const BorderRadius.vertical(top: Radius.circular(32)),
                    child: _SuggestionDrawer(
                      onDragStart:  (d) => _onPanelDragStart(d, screenHeight),
                      onDragUpdate: (d) => _onPanelDragUpdate(d, screenHeight),
                      onDragEnd:    (d) => _onPanelDragEnd(d, screenHeight),
                    ),
                  ),
                ),
              ),

            // ── Detail panel (state3) ────────────────────────────────────
            AnimatedPositioned(
              duration: const Duration(milliseconds: 400),
              curve: Curves.easeOutCubic,
              left: 0, right: 0,
              bottom: detailPanelBottom,
              height: detailPanelHeight,
              child: isState3
                  ? Container(
                      decoration: BoxDecoration(
                        color: AppColors.card(isDark),
                        borderRadius: const BorderRadius.vertical(top: Radius.circular(32)),
                        border: Border(top: BorderSide(color: AppColors.border(isDark))),
                        boxShadow: [
                          BoxShadow(
                            color: Colors.black.withValues(alpha: 0.3),
                            blurRadius: 20, offset: const Offset(0, -4),
                          ),
                        ],
                      ),
                      child: ClipRRect(
                        borderRadius: const BorderRadius.vertical(top: Radius.circular(32)),
                        child: const _DetailsPanel(key: ValueKey('details')),
                      ),
                    )
                  : const SizedBox.shrink(),
            ),

            // ── Ligtas toggle: floats above panel, rendered after panel ──────
            // Always on top of everything including the panel.
            if (isState2)
              _LigtasToggle(bottom: ligtasBottom),
            if (isNavigating)
              _MapControls(
                mapCtrl: _mapCtrl,
                bottomPadding: 80, // Positioned just above the stop bar (which is ~70px tall)
                showLigtasToggle: false,
              ),

            if (context.select<ExploreController, bool>((c) => c.locationPopupVisible))
              const _LocationPopup(),
            // ── Advisory banner — floats at very top of map ──────────────
            // BACKEND: call ctrl.setAdvisory(AdvisoryModel(...)) to show,
            // ctrl.setAdvisory(null) to dismiss.
            // Hidden by default until backend sends an active advisory.
            const _AdvisoryBanner(),
            const _Toast(),
          ],
        ),
      ),
    );
  }
}

class _SearchHeader extends StatelessWidget {
  final VoidCallback onTap;
  const _SearchHeader({required this.onTap});

  @override
  Widget build(BuildContext context) {
    final ctrl = context.read<ExploreController>();
    final currentLoc = context.select<ExploreController, String>((c) => c.originText);
    final dest = context.select<ExploreController, String>((c) => c.destText);
    final topPad = MediaQuery.of(context).padding.top;
    final isDark = context.watch<ThemeController>().isDark;

    return Positioned(
      top: 0, left: 0, right: 0,
      child: Padding(
        padding: EdgeInsets.fromLTRB(12, topPad + 8, 12, 0),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            GestureDetector(
              onTap: () => ctrl.setState(AppState.state1),
              child: Container(
                width: 36, height: 36,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: AppColors.card(isDark),
                  border: Border.all(color: AppColors.border(isDark)),
                  boxShadow: const [BoxShadow(color: Colors.black38, blurRadius: 8)],
                ),
                child: Icon(Icons.arrow_back_rounded,
                    color: AppColors.text(isDark), size: 18),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: GestureDetector(
                onTap: onTap,
                behavior: HitTestBehavior.opaque,
                child: Container(
                  padding: const EdgeInsets.fromLTRB(12, 7, 6, 7),
                  decoration: BoxDecoration(
                    color: AppColors.card(isDark),
                    borderRadius: BorderRadius.circular(50),
                    border: Border.all(color: AppColors.border(isDark)),
                    boxShadow: const [BoxShadow(color: Colors.black38, blurRadius: 8)],
                  ),
                  child: Row(
                    children: [
                      const Icon(Icons.search_rounded, color: AppColors.teal, size: 15),
                      const SizedBox(width: 6),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text(
                              currentLoc.isEmpty ? 'Current location' : currentLoc,
                              style: GoogleFonts.plusJakartaSans(
                                  color: AppColors.text2(isDark), fontSize: 10),
                              maxLines: 1, overflow: TextOverflow.ellipsis,
                            ),
                            Text(
                              dest.isEmpty ? 'Where to?' : dest,
                              style: GoogleFonts.plusJakartaSans(
                                  color: AppColors.text(isDark),
                                  fontSize: 12,
                                  fontWeight: FontWeight.w700),
                              maxLines: 1, overflow: TextOverflow.ellipsis,
                            ),
                          ],
                        ),
                      ),
                      GestureDetector(
                        onTap: ctrl.clearSearch,
                        child: Padding(
                          padding: const EdgeInsets.all(4),
                          child: Icon(Icons.close_rounded,
                              color: AppColors.text2(isDark), size: 16),
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

class _SuggestionDrawer extends StatelessWidget {
  final GestureDragStartCallback onDragStart;
  final GestureDragUpdateCallback onDragUpdate;
  final GestureDragEndCallback onDragEnd;

  const _SuggestionDrawer({
    required this.onDragStart,
    required this.onDragUpdate,
    required this.onDragEnd,
  });

  @override
  Widget build(BuildContext context) {
    final ctrl = context.watch<ExploreController>();
    final isDark = context.watch<ThemeController>().isDark;
    return Column(
      children: [
        // ── Drag handle ──────────────────────────────────────────────
        GestureDetector(
          behavior: HitTestBehavior.opaque,
          onVerticalDragStart:  onDragStart,
          onVerticalDragUpdate: onDragUpdate,
          onVerticalDragEnd:    onDragEnd,
          child: Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(vertical: 12),
            color: Colors.transparent,
            child: Center(
              child: Container(
                width: 36, height: 4,
                decoration: BoxDecoration(
                  color: AppColors.border(isDark),
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),
          ),
        ),
        _FilterChipsRow(ctrl: ctrl),
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
          child: Align(
            alignment: Alignment.centerLeft,
            child: Text('Suggested Routes',
              style: GoogleFonts.plusJakartaSans(
                fontSize: 18, fontWeight: FontWeight.w900, color: AppColors.text(isDark))),
          ),
        ),
        Expanded(
          child: ctrl.routes.isEmpty
              ? Center(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.search_off_rounded, size: 40, color: AppColors.text3(isDark)),
                        const SizedBox(height: 12),
                        Text('No routes match your filters',
                          style: GoogleFonts.plusJakartaSans(
                            fontSize: 13, color: AppColors.text2(isDark), fontWeight: FontWeight.w600),
                          textAlign: TextAlign.center),
                      ],
                    ),
                  ),
                )
              : ListView.builder(
                  padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                  itemCount: ctrl.routes.length,
                  itemBuilder: (_, i) => _RouteCard(route: ctrl.routes[i]),
                ),
        ),
      ],
    );
  }
}


class _DetailsPanel extends StatefulWidget {
  const _DetailsPanel({super.key});

  @override
  State<_DetailsPanel> createState() => _DetailsPanelState();
}

class _DetailsPanelState extends State<_DetailsPanel> {
  bool _safetyNoteExpanded = false;

  @override
  Widget build(BuildContext context) {
    final ctrl  = context.watch<ExploreController>();
    final route = ctrl.activeRoute;
    if (route == null) return const SizedBox.shrink();
    final meta = route.safetyMeta;
    final isDark = context.watch<ThemeController>().isDark;

    // Get active preference filter name for title (only show filter name)
    String routeTypeLabel = meta.label; // Default to safety label
    if (ctrl.preferenceFilters.isNotEmpty) {
      final pref = ctrl.preferenceFilters.first;
      routeTypeLabel = pref[0].toUpperCase() + pref.substring(1); // Capitalize
    }

    return Column(
      children: [
        Container(
          width: 36, height: 4, margin: const EdgeInsets.only(top: 10, bottom: 8),
          decoration: BoxDecoration(color: AppColors.border(isDark), borderRadius: BorderRadius.circular(2)),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 12),
          child: Row(
            children: [
              GestureDetector(
                onTap: ctrl.backToRoutes,
                child: Container(
                  width: 34, height: 34,
                  decoration: BoxDecoration(
                    color: AppColors.card2(isDark), borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: AppColors.border(isDark)),
                  ),
                  child: Icon(Icons.arrow_back_rounded, color: AppColors.text(isDark), size: 18),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text('Route Details', style: GoogleFonts.plusJakartaSans(
                  fontSize: 16, fontWeight: FontWeight.w800, color: AppColors.text(isDark))),
              ),
            ],
          ),
        ),
        Divider(height: 1, color: AppColors.border(isDark)),
        Expanded(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Safety score with expandable description
                GestureDetector(
                  onTap: () => setState(() => _safetyNoteExpanded = !_safetyNoteExpanded),
                  child: Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(color: meta.bgColor, borderRadius: BorderRadius.circular(12)),
                    child: Column(
                      children: [
                        Row(
                          children: [
                            Icon(Icons.shield_rounded, color: meta.color, size: 24),
                            const SizedBox(width: 10),
                            Expanded(
                              child: Text('$routeTypeLabel Route · ${route.safetyScore}% Safety',
                                style: GoogleFonts.plusJakartaSans(color: meta.color, fontSize: 13, fontWeight: FontWeight.w700)),
                            ),
                            Icon(
                              _safetyNoteExpanded ? Icons.keyboard_arrow_up_rounded : Icons.keyboard_arrow_down_rounded,
                              color: meta.color,
                              size: 20,
                            ),
                          ],
                        ),
                        if (_safetyNoteExpanded) ...[
                          const SizedBox(height: 8),
                          Text(
                            route.safetyNote,
                            style: GoogleFonts.plusJakartaSans(color: AppColors.text2(isDark), fontSize: 11),
                          ),
                        ] else ...[
                          const SizedBox(height: 4),
                          Text(
                            route.safetyNote,
                            style: GoogleFonts.plusJakartaSans(color: AppColors.text2(isDark), fontSize: 11),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ],
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                // Stat boxes - Duration, Fare, Distance
                Row(
                  children: [
                    _statBox('${route.minutes} min', 'Duration', isDark),
                    const SizedBox(width: 8),
                    _statBox('₱${route.fare}', 'Fare', isDark),
                    const SizedBox(width: 8),
                    _statBox('5.8 km', 'Distance', isDark),
                  ],
                ),
                const SizedBox(height: 16),
                // Route name/title
                Text(
                  route.modes,
                  style: GoogleFonts.plusJakartaSans(fontSize: 15, fontWeight: FontWeight.w800, color: AppColors.text(isDark)),
                ),
                const SizedBox(height: 12),
                // Steps
                ...route.steps.asMap().entries.map((e) => _stepRow(e.key, e.value, route.steps.length, isDark)),
              ],
            ),
          ),
        ),
        Divider(height: 1, color: AppColors.border(isDark)),
        Builder(
          builder: (context) {
            final bottomInset = MediaQuery.of(context).padding.bottom;
            final bottomPadding = bottomInset > 20 ? bottomInset : 12.0;
            return Padding(
              padding: EdgeInsets.fromLTRB(16, 12, 16, bottomPadding),
              child: SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppColors.teal,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  ),
                  onPressed: ctrl.startNavigation,
                  child: Text('Start Route', style: GoogleFonts.plusJakartaSans(fontWeight: FontWeight.w800, fontSize: 15)),
                ),
              ),
            );
          },
        ),
      ],
    );
  }

  Widget _statBox(String value, String label, bool isDark) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 10),
        decoration: BoxDecoration(
          color: AppColors.card2(isDark),
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: AppColors.border(isDark)),
        ),
        child: Column(
          children: [
            Text(value, style: GoogleFonts.plusJakartaSans(
              fontSize: 14, fontWeight: FontWeight.w800, color: AppColors.text(isDark))),
            const SizedBox(height: 2),
            Text(label, style: GoogleFonts.plusJakartaSans(
              fontSize: 9, color: AppColors.text2(isDark))),
          ],
        ),
      ),
    );
  }

  Widget _stepRow(int index, RouteStep step, int total, bool isDark) {
    IconData stepIcon;
    Color stepColor;
    
    // Determine icon based on step title
    final title = step.title.toLowerCase();
    if (title.contains('walk')) {
      stepIcon = Icons.directions_walk_rounded;
      stepColor = AppColors.text2(isDark);
    } else if (title.contains('transfer')) {
      stepIcon = Icons.sync_alt_rounded;
      stepColor = AppColors.text2(isDark);
    } else {
      stepIcon = Icons.directions_bus_rounded;
      stepColor = AppColors.teal;
    }

    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Column(
            children: [
              Container(
                width: 36, height: 36,
                decoration: BoxDecoration(
                  color: stepIcon == Icons.directions_bus_rounded ? AppColors.tealDim : AppColors.card2(isDark),
                  shape: BoxShape.circle,
                  border: Border.all(
                    color: AppColors.teal,
                    width: 2,
                  ),
                ),
                child: Icon(stepIcon, color: stepColor, size: 16),
              ),
              if (index < total - 1)
                Container(width: 2, height: 40, color: AppColors.border(isDark)),
            ],
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  step.title,
                  style: GoogleFonts.plusJakartaSans(
                    fontSize: 13,
                    fontWeight: FontWeight.w700,
                    color: AppColors.text(isDark),
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  step.description,
                  style: GoogleFonts.plusJakartaSans(
                    fontSize: 12,
                    fontWeight: FontWeight.w500,
                    color: AppColors.text2(isDark),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _FilterChipsRow extends StatelessWidget {
  final ExploreController ctrl;
  const _FilterChipsRow({required this.ctrl});

  @override
  Widget build(BuildContext context) {
    final activeChips = <_ActiveChip>[];
    for (final k in ctrl.commuterFilters) {
      final opt = commuterOptions.where((o) => o.key == k).firstOrNull;
      if (opt != null) activeChips.add(_ActiveChip(opt: opt, group: 'commuter', ctrl: ctrl));
    }
    for (final k in ctrl.transportFilters) {
      final opt = transportOptions.where((o) => o.key == k).firstOrNull;
      if (opt != null) activeChips.add(_ActiveChip(opt: opt, group: 'transport', ctrl: ctrl));
    }
    for (final k in ctrl.ligtasFilters) {
      final opt = ligtasFeatures.where((o) => o.key == k).firstOrNull;
      if (opt != null) activeChips.add(_ActiveChip(opt: opt, group: 'ligtas', ctrl: ctrl));
    }
    for (final k in ctrl.preferenceFilters) {
      final opt = preferenceOptions.where((o) => o.key == k).firstOrNull;
      if (opt != null) activeChips.add(_ActiveChip(opt: opt, group: 'preference', ctrl: ctrl));
    }

    final isDark = context.watch<ThemeController>().isDark;

    void openFilters() => showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => ChangeNotifierProvider.value(
          value: ctrl, child: const _FilterModal()),
    );

    return Container(
      height: 54,
      decoration: BoxDecoration(
        border: Border(bottom: BorderSide(color: AppColors.border(isDark))),
      ),
      child: Row(
        children: [
          const SizedBox(width: 12),
          GestureDetector(
            onTap: openFilters,
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 200),
              width: 36, height: 36,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(10),
                color: ctrl.hasFilters
                    ? const Color(0xFF0A6A6A)
                    : AppColors.card2(isDark),
                border: Border.all(
                  color: ctrl.hasFilters
                      ? const Color(0xFF0D9E9E)
                      : AppColors.border(isDark),
                  width: 1.5,
                ),
                boxShadow: [
                  BoxShadow(color: Colors.black.withValues(alpha: 0.2), blurRadius: 4),
                ],
              ),
              child: Icon(
                Icons.tune_rounded,
                size: 16,
                color: ctrl.hasFilters ? Colors.white : AppColors.text2(isDark),
              ),
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: activeChips.isEmpty
                ? Text(
                    'Tap to filter routes',
                    style: GoogleFonts.plusJakartaSans(
                        color: AppColors.text3(isDark), fontSize: 12),
                  )
                : Stack(
                    children: [
                      ListView(
                        scrollDirection: Axis.horizontal,
                        padding: const EdgeInsets.only(right: 32),
                        children: activeChips,
                      ),
                      Positioned(
                        right: 0, top: 0, bottom: 0, width: 32,
                        child: IgnorePointer(
                          child: DecoratedBox(
                            decoration: BoxDecoration(
                              gradient: LinearGradient(
                                begin: Alignment.centerLeft,
                                end: Alignment.centerRight,
                                colors: [
                                  AppColors.card(isDark).withValues(alpha: 0.0),
                                  AppColors.card(isDark),
                                ],
                              ),
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
          ),
          if (ctrl.hasFilters) ...[
            const SizedBox(width: 8),
            GestureDetector(
              onTap: ctrl.clearAllFilters,
              child: Container(
                width: 24,
                height: 24,
                decoration: BoxDecoration(
                  color: AppColors.card2(isDark),
                  borderRadius: BorderRadius.circular(6),
                  border: Border.all(color: AppColors.border(isDark)),
                ),
                child: Icon(
                  Icons.close_rounded,
                  size: 14,
                  color: AppColors.text2(isDark),
                ),
              ),
            ),
          ],
          const SizedBox(width: 12),
        ],
      ),
    );
  }
}

class _ActiveChip extends StatelessWidget {
  final FilterOption opt;
  final String group;
  final ExploreController ctrl;
  const _ActiveChip({required this.opt, required this.group, required this.ctrl});

  @override
  Widget build(BuildContext context) {
    // Original teal pill design — bright, visible, white text.
    // Distinct from toggle: chips are bright AppColors.teal,
    // toggle is a darker teal (0xFF0A6A6A) when active.
    return Container(
      margin: const EdgeInsets.only(right: 8, top: 10, bottom: 10),
      padding: const EdgeInsets.symmetric(horizontal: 12),
      decoration: BoxDecoration(
        color: AppColors.teal,
        borderRadius: BorderRadius.circular(50),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(opt.icon, size: 12, color: Colors.white),
          const SizedBox(width: 6),
          Text(opt.label,
              style: GoogleFonts.plusJakartaSans(
                  fontSize: 11, fontWeight: FontWeight.w700, color: Colors.white)),
          const SizedBox(width: 6),
          GestureDetector(
            onTap: () => ctrl.removeFilter(group, opt.key),
            child: const Icon(Icons.close_rounded, size: 12, color: Colors.white70),
          ),
        ],
      ),
    );
  }
}

class _FilterModal extends StatelessWidget {
  const _FilterModal();

  @override
  Widget build(BuildContext context) {
    final ctrl = context.watch<ExploreController>();
    final isDark = context.watch<ThemeController>().isDark;
    return DraggableScrollableSheet(
      initialChildSize: 0.75,
      maxChildSize: 0.95,
      minChildSize: 0.5,
      builder: (_, scrollCtrl) => Container(
        decoration: BoxDecoration(
          color: AppColors.card(isDark),
          borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
          border: Border(top: BorderSide(color: AppColors.border(isDark))),
        ),
        child: ListView(
          controller: scrollCtrl,
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 32),
          children: [
            Center(
              child: Container(
                width: 36, height: 4, margin: const EdgeInsets.symmetric(vertical: 12),
                decoration: BoxDecoration(color: AppColors.border(isDark), borderRadius: BorderRadius.circular(2)),
              ),
            ),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text('Filters', style: GoogleFonts.plusJakartaSans(
                  fontSize: 18, fontWeight: FontWeight.w800, color: AppColors.text(isDark))),
                IconButton(
                  icon: Icon(Icons.close_rounded, color: AppColors.text2(isDark)),
                  onPressed: () => Navigator.pop(context),
                ),
              ],
            ),
            Divider(color: AppColors.border(isDark)),
            const SizedBox(height: 12),
            _sectionLabel('COMMUTER TYPE'),
            _optionGrid(context, ctrl, commuterOptions, 'commuter'),
            const SizedBox(height: 20),
            _sectionLabel('TRANSPORT MODE'),
            _optionGrid(context, ctrl, transportOptions, 'transport'),
            const SizedBox(height: 20),
            _sectionLabel('ROUTE PREFERENCE'),
            _optionGrid(context, ctrl, preferenceOptions, 'preference'),
            
            if (ctrl.ligtasModeOn) ...[
              const SizedBox(height: 20),
              _sectionLabel('LIGTAS FEATURES'),
              _optionGrid(context, ctrl, ligtasFeatures, 'ligtas'),
            ],
            
            const SizedBox(height: 24),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppColors.teal,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                ),
                onPressed: () => Navigator.pop(context),
                child: const Text('Apply Filters', style: TextStyle(fontWeight: FontWeight.bold)),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _sectionLabel(String title) => Padding(
    padding: const EdgeInsets.only(bottom: 10),
    child: Builder(builder: (context) {
      final isDark = context.watch<ThemeController>().isDark;
      return Text(title, style: GoogleFonts.plusJakartaSans(
        fontSize: 11, fontWeight: FontWeight.w800, color: AppColors.text2(isDark), letterSpacing: 1));
    }),
  );

  Widget _optionGrid(BuildContext context, ExploreController ctrl, List<FilterOption> options, String group) {
    final active = group == 'commuter' ? ctrl.commuterFilters
                 : group == 'transport' ? ctrl.transportFilters
                 : group == 'ligtas' ? ctrl.ligtasFilters
                 : ctrl.preferenceFilters;
    final isDark = context.watch<ThemeController>().isDark;
    return GridView.count(
      crossAxisCount: 3, shrinkWrap: true, physics: const NeverScrollableScrollPhysics(),
      mainAxisSpacing: 8, crossAxisSpacing: 8, childAspectRatio: 1.6,
      children: options.map((opt) {
        final isActive = active.contains(opt.key);
        return GestureDetector(
          onTap: () => ctrl.toggleFilter(group, opt.key),
          child: Container(
            decoration: BoxDecoration(
              color: isActive ? AppColors.teal : AppColors.card2(isDark),
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: isActive ? AppColors.teal : AppColors.border(isDark)),
            ),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(opt.icon, size: 18, color: isActive ? Colors.white : AppColors.text2(isDark)),
                const SizedBox(height: 4),
                Text(opt.label, style: GoogleFonts.plusJakartaSans(
                  fontSize: 10, fontWeight: FontWeight.w700, color: isActive ? Colors.white : AppColors.text2(isDark)),
                  textAlign: TextAlign.center),
              ],
            ),
          ),
        );
      }).toList(),
    );
  }
}

// ── Ligtas toggle: fixed position, never pushed by the suggestion panel ──
class _LigtasToggle extends StatelessWidget {
  final double bottom;
  const _LigtasToggle({required this.bottom});

  @override
  Widget build(BuildContext context) {
    final ctrl = context.watch<ExploreController>();
    return Positioned(
      right: 14,
      bottom: bottom,
      child: GestureDetector(
        onTap: ctrl.toggleLigtasMode,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 300),
          width: 38, height: 38,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: ctrl.ligtasModeOn ? AppColors.goldActive : AppColors.gold,
            boxShadow: [
              BoxShadow(
                color: AppColors.gold.withValues(
                    alpha: ctrl.ligtasModeOn ? 0.6 : 0.3),
                blurRadius: 15,
              ),
            ],
          ),
          child: const Icon(Icons.wb_sunny_rounded,
              color: Colors.white, size: 20),
        ),
      ),
    );
  }
}

// ── Zoom + center: follows the panel up, gets hidden behind it ────────────
class _MapZoomControls extends StatelessWidget {
  final MapController mapCtrl;
  final double bottomPadding;
  const _MapZoomControls({
    required this.mapCtrl,
    required this.bottomPadding,
  });

  @override
  Widget build(BuildContext context) {
    final ctrl = context.watch<ExploreController>();
    return Positioned(
      right: 14,
      bottom: bottomPadding,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          _mapBtn(context, Icons.add_rounded, () {
            mapCtrl.move(mapCtrl.camera.center, mapCtrl.camera.zoom + 1);
          }),
          const SizedBox(height: 8),
          _mapBtn(context, Icons.remove_rounded, () {
            mapCtrl.move(mapCtrl.camera.center, mapCtrl.camera.zoom - 1);
          }),
          const SizedBox(height: 8),
          _mapBtn(context, Icons.my_location_rounded, () {
            final route = ctrl.activeRoute;
            if (route != null && route.polyline.isNotEmpty) {
              final origin = LatLng(route.polyline.first[0], route.polyline.first[1]);
              mapCtrl.move(origin, 16);
            } else {
              mapCtrl.move(const LatLng(14.6530, 121.0580), 14);
            }
          }),
        ],
      ),
    );
  }

  Widget _mapBtn(BuildContext context, IconData icon, VoidCallback onTap) {
    final isDark = context.watch<ThemeController>().isDark;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 38, height: 38,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: AppColors.card(isDark),
          border: Border.all(color: AppColors.border(isDark)),
          boxShadow: const [BoxShadow(color: Colors.black26, blurRadius: 8)],
        ),
        child: Icon(icon, color: AppColors.text2(isDark), size: 24),
      ),
    );
  }
}

class _MapControls extends StatelessWidget {
  final MapController mapCtrl;
  final double bottomPadding;
  /// true  → show Ligtas toggle (states 1, 2, 3)
  /// false → hide it (state 4, active navigation)
  final bool showLigtasToggle;
  const _MapControls({
    required this.mapCtrl,
    required this.bottomPadding,
    this.showLigtasToggle = true,
  });

  @override
  Widget build(BuildContext context) {
    final ctrl = context.watch<ExploreController>();

    return Positioned(
      right: 14,
      bottom: bottomPadding,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // ── Ligtas toggle — hidden only during active navigation ──
          AnimatedSize(
            duration: const Duration(milliseconds: 250),
            curve: Curves.easeInOut,
            child: showLigtasToggle
                ? Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      GestureDetector(
                        onTap: ctrl.toggleLigtasMode,
                        child: AnimatedContainer(
                          duration: const Duration(milliseconds: 300),
                          width: 38, height: 38,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            color: ctrl.ligtasModeOn ? AppColors.goldActive : AppColors.gold,
                            boxShadow: [
                              BoxShadow(
                                color: AppColors.gold.withValues(
                                    alpha: ctrl.ligtasModeOn ? 0.6 : 0.3),
                                blurRadius: 15,
                              )
                            ],
                          ),
                          child: const Icon(Icons.wb_sunny_rounded,
                              color: Colors.white, size: 20),
                        ),
                      ),
                      const SizedBox(height: 10),
                    ],
                  )
                : const SizedBox.shrink(),
          ),
          // Zoom in
          _mapBtn(Icons.add_rounded, () {
            mapCtrl.move(mapCtrl.camera.center, mapCtrl.camera.zoom + 1);
          }),
          const SizedBox(height: 8),
          // Zoom out
          _mapBtn(Icons.remove_rounded, () {
            mapCtrl.move(mapCtrl.camera.center, mapCtrl.camera.zoom - 1);
          }),
          const SizedBox(height: 8),
          // Recenter - follows current location marker (origin)
          _mapBtn(Icons.my_location_rounded, () {
            // BACKEND: Replace with real GPS location
            // For now, center on origin marker from active route
            final route = ctrl.activeRoute;
            if (route != null && route.polyline.isNotEmpty) {
              // Origin is the first point in the polyline
              final origin = LatLng(route.polyline.first[0], route.polyline.first[1]);
              mapCtrl.move(origin, 16); // Zoom in closer for navigation
            } else {
              // Fallback to default center
              mapCtrl.move(const LatLng(14.6530, 121.0580), 14);
            }
          }),
        ],
      ),
    );
  }

  Widget _mapBtn(IconData icon, VoidCallback onTap) => Builder(
    builder: (context) {
      final isDark = context.watch<ThemeController>().isDark;
      return GestureDetector(
        onTap: onTap,
        child: Container(
          width: 38, height: 38,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: AppColors.card(isDark),
            border: Border.all(color: AppColors.border(isDark)),
            boxShadow: const [BoxShadow(color: Colors.black26, blurRadius: 8)],
          ),
          child: Icon(icon, color: AppColors.text2(isDark), size: 24),
        ),
      );
    },
  );
}

class _RouteCard extends StatelessWidget {
  final RouteModel route;
  const _RouteCard({required this.route});

  @override
  Widget build(BuildContext context) {
    final ctrl  = context.read<ExploreController>();
    final meta  = route.safetyMeta;
    final isDark = context.watch<ThemeController>().isDark;

    return GestureDetector(
      onTap: () => ctrl.selectRoute(route),
      child: Container(
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: AppColors.card2(isDark),
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: AppColors.border(isDark)),
        ),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(route.modes, style: GoogleFonts.plusJakartaSans(
                    color: AppColors.text(isDark), 
                    fontSize: 13, 
                    fontWeight: FontWeight.w700
                  )),
                  const SizedBox(height: 6),
                  Row(
                    children: [
                      Icon(Icons.schedule_rounded, size: 13, color: AppColors.text2(isDark)),
                      const SizedBox(width: 4),
                      Text('${route.minutes} min', style: GoogleFonts.plusJakartaSans(
                        color: AppColors.text2(isDark), 
                        fontSize: 11,
                        fontWeight: FontWeight.w600
                      )),
                      const SizedBox(width: 12),
                      Icon(Icons.payments_rounded, size: 13, color: AppColors.text2(isDark)),
                      const SizedBox(width: 4),
                      Text('₱${route.fare}', style: GoogleFonts.plusJakartaSans(
                        color: AppColors.text2(isDark), 
                        fontSize: 11,
                        fontWeight: FontWeight.w600
                      )),
                    ],
                  ),
                ],
              ),
            ),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(
                color: meta.bgColor, 
                borderRadius: BorderRadius.circular(8)
              ),
              child: Text('${route.safetyScore}%', style: GoogleFonts.plusJakartaSans(
                color: meta.color, 
                fontSize: 13, 
                fontWeight: FontWeight.w800
              )),
            ),
          ],
        ),
      ),
    );
  }
}

class _LocationPopup extends StatelessWidget {
  const _LocationPopup();
  @override
  Widget build(BuildContext context) {
    final ctrl = context.read<ExploreController>();
    final isDark = context.watch<ThemeController>().isDark;
    return Container(
      decoration: BoxDecoration(color: Colors.black.withValues(alpha: 0.6)),
      child: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Container(
            padding: const EdgeInsets.all(24),
            decoration: BoxDecoration(
              color: AppColors.card(isDark),
              borderRadius: BorderRadius.circular(20),
              border: Border.all(color: AppColors.border(isDark)),
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 56, height: 56,
                  decoration: const BoxDecoration(color: AppColors.tealDim, shape: BoxShape.circle),
                  child: const Icon(Icons.my_location_rounded, color: AppColors.teal, size: 28),
                ),
                const SizedBox(height: 16),
                Text('Enable Location', style: GoogleFonts.plusJakartaSans(
                  fontSize: 18, fontWeight: FontWeight.w800, color: AppColors.text(isDark))),
                const SizedBox(height: 8),
                Text(
                  'Allow Ligtas to access your location to find safe routes near you.',
                  style: GoogleFonts.plusJakartaSans(color: AppColors.text2(isDark), fontSize: 13),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 20),
                Row(
                  children: [
                    Expanded(
                      child: ElevatedButton(
                        style: ElevatedButton.styleFrom(
                          backgroundColor: AppColors.teal,
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(vertical: 12),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                        ),
                        onPressed: ctrl.requestLocation,
                        child: Text('Enable', style: GoogleFonts.plusJakartaSans(fontWeight: FontWeight.w700)),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: OutlinedButton(
                        style: OutlinedButton.styleFrom(
                          foregroundColor: AppColors.text2(isDark),
                          side: BorderSide(color: AppColors.border(isDark)),
                          padding: const EdgeInsets.symmetric(vertical: 12),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                        ),
                        onPressed: ctrl.skipLocation,
                        child: Text('Skip', style: GoogleFonts.plusJakartaSans(fontWeight: FontWeight.w700)),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _MapLayer extends StatelessWidget {
  final MapController mapCtrl;
  const _MapLayer({required this.mapCtrl});

  @override
  Widget build(BuildContext context) {
    final ctrl = context.watch<ExploreController>();
    final route = ctrl.activeRoute;
    final List<Polyline> polylines = [];
    final List<Marker> markers = [];

    if (route != null) {
      final pts = route.polyline.map((p) => LatLng(p[0], p[1])).toList();
      polylines.add(Polyline(
        points: pts, 
        color: route.safetyMeta.color, 
        strokeWidth: 5,
      ));
      
      if (pts.isNotEmpty) {
        // Origin marker - dark blue (current location)
        markers.add(Marker(
          point: pts.first, 
          width: 40, height: 40,
          child: _mapPin(AppColors.teal, Icons.person_pin_circle_rounded)
        ));
        // Destination marker - safety color
        markers.add(Marker(
          point: pts.last, 
          width: 40, height: 40,
          child: _mapPin(route.safetyMeta.color, Icons.location_pin)
        ));
      }
    }

    // ── POI markers (hospitals, police, fire stations) ──────────
    // BACKEND: populated via ctrl.setPois([...]) once API is ready.
    // Empty by default — nothing renders until the backend feeds data.
    final poiMarkers = ctrl.pois.map((poi) => Marker(
      point: LatLng(poi.lat, poi.lng),
      width: 36, height: 36,
      child: _poiPin(poi.color, poi.icon, poi.label),
    )).toList();

    // ── Hotspot circles (crime, flood-prone, dark areas) ────────
    // BACKEND: populated via ctrl.setHotspots([...]) once API ready.
    // Empty by default — circles only appear when backend sends data.
    final circles = ctrl.hotspots.map((h) => CircleMarker(
      point: LatLng(h.lat, h.lng),
      radius: h.radiusMeters,
      useRadiusInMeter: true,
      color: h.color,
      borderColor: h.color.withValues(alpha: 1.0),
      borderStrokeWidth: 1.5,
    )).toList();

    return FlutterMap(
      mapController: mapCtrl,
      options: const MapOptions(
        initialCenter: LatLng(14.6530, 121.0580), 
        initialZoom: 14,
        interactionOptions: InteractionOptions(flags: InteractiveFlag.all),
      ),
      children: [
        TileLayer(
          urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
          userAgentPackageName: 'com.ligtas.explore',
        ),
        // Hotspot circles rendered under routes so routes stay visible on top
        if (circles.isNotEmpty) CircleLayer(circles: circles),
        if (polylines.isNotEmpty) PolylineLayer(polylines: polylines),
        // Route markers on top of polylines
        if (markers.isNotEmpty) MarkerLayer(markers: markers),
        // POI markers on top of everything
        if (poiMarkers.isNotEmpty) MarkerLayer(markers: poiMarkers),
      ],
    );
  }

  Widget _poiPin(Color color, IconData icon, String label) => Tooltip(
    message: label,
    child: Container(
      width: 32, height: 32,
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        shape: BoxShape.circle,
        border: Border.all(color: color, width: 1.5),
      ),
      child: Icon(icon, color: color, size: 16),
    ),
  );

  Widget _mapPin(Color color, IconData icon) => Container(
    decoration: BoxDecoration(
      color: color, shape: BoxShape.circle,
      border: Border.all(color: Colors.white, width: 2.5),
      boxShadow: [BoxShadow(color: color.withValues(alpha: 0.4), blurRadius: 8, offset: const Offset(0,2))],
    ),
    child: Icon(icon, color: Colors.white, size: 20),
  );
}


class _NavHeader extends StatelessWidget {
  const _NavHeader();
  
  @override
  Widget build(BuildContext context) {
    final route = context.watch<ExploreController>().activeRoute;
    final isDark = context.watch<ThemeController>().isDark;
    
    // BACKEND: Replace with real-time calculation
    final estimatedTime = route != null ? '${route.minutes} min' : '—';
    
    return Positioned(
      top: 0, left: 0, right: 0,
      child: Container(
        color: Colors.transparent,
        padding: EdgeInsets.fromLTRB(16, MediaQuery.of(context).padding.top + 8, 16, 12),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          decoration: BoxDecoration(
            color: AppColors.card(isDark),
            borderRadius: BorderRadius.circular(50),
            border: Border.all(color: AppColors.border(isDark)),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.2),
                blurRadius: 10,
                offset: const Offset(0, 2),
              ),
            ],
          ),
          child: Row(
            children: [
              Container(
                width: 32, height: 32,
                decoration: const BoxDecoration(color: AppColors.teal, shape: BoxShape.circle),
                child: const Icon(Icons.my_location_rounded, color: Colors.white, size: 16),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'NAVIGATING',
                      style: GoogleFonts.plusJakartaSans(
                        fontSize: 9, fontWeight: FontWeight.w800,
                        color: AppColors.text3(isDark), letterSpacing: 0.5,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      route?.modes ?? '—',
                      style: GoogleFonts.plusJakartaSans(
                        fontSize: 13, fontWeight: FontWeight.w700,
                        color: AppColors.text(isDark),
                      ),
                      maxLines: 1, overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(color: AppColors.tealDim, borderRadius: BorderRadius.circular(20)),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.schedule_rounded, color: AppColors.teal, size: 14),
                    const SizedBox(width: 4),
                    Text(estimatedTime,
                      style: GoogleFonts.plusJakartaSans(
                        fontSize: 12, fontWeight: FontWeight.w700, color: AppColors.teal)),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _StopBar extends StatelessWidget {
  const _StopBar();
  
  @override
  Widget build(BuildContext context) {
    final ctrl = context.read<ExploreController>();
    final isDark = context.watch<ThemeController>().isDark;
    final bottomPadding = MediaQuery.of(context).padding.bottom;
    
    return Positioned(
      bottom: 0, // Changed from 72 to 0 to cover the bottom nav
      left: 0, right: 0,
      child: Container(
        padding: EdgeInsets.fromLTRB(16, 12, 16, bottomPadding + 12),
        decoration: BoxDecoration(
          color: AppColors.card(isDark),
          border: Border(top: BorderSide(color: AppColors.border(isDark))),
          boxShadow: [
            BoxShadow(color: Colors.black.withValues(alpha: 0.2), blurRadius: 10, offset: const Offset(0, -2)),
          ],
        ),
        child: Row(
          children: [
            // Report button on the left - filled background
            ElevatedButton(
              style: ElevatedButton.styleFrom(
                backgroundColor: AppColors.teal,
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
                elevation: 0,
              ),
              onPressed: () {
                // BACKEND: Open report incident modal
                ctrl.showToast('Report incident feature', 'teal');
              },
              child: Text(
                'Report',
                style: GoogleFonts.plusJakartaSans(
                  fontWeight: FontWeight.w700,
                  fontSize: 14,
                ),
              ),
            ),
            const SizedBox(width: 12),
            // Stop button on the right (expanded)
            Expanded(
              child: ElevatedButton(
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFFDC2626),
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                  elevation: 0,
                ),
                onPressed: () => ctrl.confirmStopNavigation(context),
                child: Text(
                  'Stop Route',
                  style: GoogleFonts.plusJakartaSans(
                    fontWeight: FontWeight.w700,
                    fontSize: 14,
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

// ── Advisory banner ───────────────────────────────────────────────────────────
// Sits at the top of the map stack. Hidden when ctrl.advisory is null.
// BACKEND: ctrl.setAdvisory(AdvisoryModel(message: '...', type: 'warning'))
//   type 'info'    → teal background
//   type 'warning' → amber background
//   type 'danger'  → red background
class _AdvisoryBanner extends StatelessWidget {
  const _AdvisoryBanner();

  @override
  Widget build(BuildContext context) {
    final advisory = context.select<ExploreController, AdvisoryModel?>(
        (c) => c.advisory);

    // Nothing to show — backend hasn't sent any advisory
    if (advisory == null) return const SizedBox.shrink();

    final Color bg;
    final Color textColor;
    final IconData icon;
    switch (advisory.type) {
      case 'danger':
        bg        = const Color(0xFFDC2626);
        textColor = Colors.white;
        icon      = Icons.warning_rounded;
        break;
      case 'info':
        bg        = AppColors.teal;
        textColor = Colors.white;
        icon      = Icons.info_outline_rounded;
        break;
      case 'warning':
      default:
        bg        = const Color(0xFFF59E0B);
        textColor = const Color(0xFF1C1A00);
        icon      = Icons.warning_amber_rounded;
    }

    return Positioned(
      top: 0, left: 0, right: 0,
      child: Material(
        color: bg,
        child: SafeArea(
          bottom: false,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
            child: Row(children: [
              Icon(icon, color: textColor, size: 16),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  advisory.message,
                  style: GoogleFonts.plusJakartaSans(
                    fontSize: 12, fontWeight: FontWeight.w700,
                    color: textColor, height: 1.3),
                ),
              ),
              // Dismiss button
              GestureDetector(
                onTap: () => context.read<ExploreController>().setAdvisory(null),
                child: Padding(
                  padding: const EdgeInsets.only(left: 8),
                  child: Icon(Icons.close_rounded, color: textColor, size: 16),
                ),
              ),
            ]),
          ),
        ),
      ),
    );
  }
}

class _Toast extends StatelessWidget {
  const _Toast();
  @override
  Widget build(BuildContext context) {
    final msg = context.select<ExploreController, String>((c) => c.toastMsg);
    final visible = context.select<ExploreController, bool>((c) => c.toastVisible);
    final isDark = context.watch<ThemeController>().isDark;
    return AnimatedPositioned(
      duration: const Duration(milliseconds: 300),
      top: visible ? 100 : 60, left: 0, right: 0,
      child: IgnorePointer(
        ignoring: !visible,
        child: AnimatedOpacity(
          duration: const Duration(milliseconds: 250),
          opacity: visible ? 1.0 : 0.0,
          child: Center(
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 10),
              decoration: BoxDecoration(
                color: AppColors.card(isDark),
                borderRadius: BorderRadius.circular(50),
                border: Border.all(color: AppColors.border(isDark)),
              ),
              child: Text(msg, style: TextStyle(color: AppColors.text(isDark), fontSize: 13)),
            ),
          ),
        ),
      ),
    );
  }
}