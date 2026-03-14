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
import '../../core/theme_controller.dart';

// ── Route Preference Filter Options ────────────────────────────────────────
final preferenceOptions = [
  FilterOption(key: 'safest', label: 'Safest', icon: Icons.shield_rounded),
  FilterOption(key: 'fastest', label: 'Fastest', icon: Icons.speed_rounded),
  FilterOption(key: 'cheapest', label: 'Cheapest', icon: Icons.savings_rounded),
  FilterOption(key: 'balanced', label: 'Balanced', icon: Icons.balance_rounded),
  FilterOption(key: 'moderate', label: 'Moderate', icon: Icons.adjust_rounded),
];

// ── Vulnerable profile options ──────────────────────────────────────────────
final _profileOptions = [
  _ProfileOption(
    key: 'senior',
    label: 'Senior (60+)',
    icon: Icons.elderly_rounded,
  ),
  _ProfileOption(
    key: 'pwd',
    label: 'PWD / Wheelchair',
    icon: Icons.accessible_rounded,
  ),
  _ProfileOption(
    key: 'women',
    label: "Women's Safety",
    icon: Icons.woman_rounded,
  ),
  _ProfileOption(
    key: 'child',
    label: 'Child / Student',
    icon: Icons.school_rounded,
  ),
];

class _ProfileOption {
  final String key, label;
  final IconData icon;
  const _ProfileOption({
    required this.key,
    required this.label,
    required this.icon,
  });
}

class ExploreView extends StatelessWidget {
  const ExploreView({super.key});
  @override
  Widget build(BuildContext context) => const _ExploreScaffold();
}

class _ExploreScaffold extends StatefulWidget {
  const _ExploreScaffold();
  @override
  State<_ExploreScaffold> createState() => _ExploreScaffoldState();
}

class _ExploreScaffoldState extends State<_ExploreScaffold> {
  final MapController _mapCtrl = MapController();

  static const double _panelMin = 0.30;
  static const double _panelMax = 0.58;
  double _panelHeight = -1;

  void _onPanelDragUpdate(DragUpdateDetails d, double screenH) {
    setState(() {
      _panelHeight = (_panelHeight - d.primaryDelta!).clamp(
        screenH * _panelMin,
        screenH * _panelMax,
      );
    });
  }

  void _onPanelDragEnd(DragEndDetails d, double screenH) {
    final min = screenH * _panelMin;
    final max = screenH * _panelMax;
    final vel = d.primaryVelocity ?? 0;
    double target;
    if (vel < -400) {
      target = max;
    } else if (vel > 400) {
      target = min;
    } else {
      final snaps = [min, max];
      target = snaps.reduce(
        (a, b) => (a - _panelHeight).abs() < (b - _panelHeight).abs() ? a : b,
      );
    }
    setState(() => _panelHeight = target);
  }

  void _openSearch(BuildContext context) {
    Navigator.of(context).pushNamed(MiniScreen.routeName);
  }

  @override
  Widget build(BuildContext context) {
    final appState = context.select<ExploreController, AppState>(
      (c) => c.state,
    );
    final screenHeight = MediaQuery.of(context).size.height;

    final isState2 = appState == AppState.state2;
    final isState3 = appState == AppState.state3;
    final isNavigating = appState == AppState.state4;

    if (_panelHeight < 0) _panelHeight = screenHeight * _panelMin;

    final detailPanelHeight = screenHeight * 0.65;
    final detailPanelBottom = isState3 ? 0.0 : -detailPanelHeight;

    final double panelTopEdge = 72 + _panelHeight;
    final double zoomBtnsBottom = 72 + screenHeight * _panelMin + 12;
    const double zoomColHeight = 130.0;
    final double ligtasDefaultBottom = zoomBtnsBottom + zoomColHeight + 8;
    final double ligtasMaxBottom = 72 + screenHeight * _panelMax + 12;

    double ligtasBottom;
    if (isState2) {
      final double rideStart = ligtasDefaultBottom - 12;
      if (panelTopEdge > rideStart) {
        ligtasBottom = (panelTopEdge + 12).clamp(
          ligtasDefaultBottom,
          ligtasMaxBottom,
        );
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
            if (isNavigating) _StopBar(mapCtrl: _mapCtrl),

            if (isState2)
              _MapZoomControls(
                mapCtrl: _mapCtrl,
                bottomPadding: zoomBtnsBottom,
              ),

            if (isState2)
              Positioned(
                left: 0,
                right: 0,
                bottom: 72,
                height: _panelHeight,
                child: Container(
                  decoration: BoxDecoration(
                    color: AppColors.card(isDark),
                    borderRadius: const BorderRadius.vertical(
                      top: Radius.circular(32),
                    ),
                    border: Border(
                      top: BorderSide(color: AppColors.border(isDark)),
                    ),
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withValues(alpha: 0.3),
                        blurRadius: 20,
                        offset: const Offset(0, -4),
                      ),
                    ],
                  ),
                  child: ClipRRect(
                    borderRadius: const BorderRadius.vertical(
                      top: Radius.circular(32),
                    ),
                    child: _SuggestionDrawer(
                      onDragStart: (_) {},
                      onDragUpdate: (d) => _onPanelDragUpdate(d, screenHeight),
                      onDragEnd: (d) => _onPanelDragEnd(d, screenHeight),
                    ),
                  ),
                ),
              ),

            AnimatedPositioned(
              duration: const Duration(milliseconds: 400),
              curve: Curves.easeOutCubic,
              left: 0,
              right: 0,
              bottom: detailPanelBottom,
              height: detailPanelHeight,
              child: isState3
                  ? Container(
                      decoration: BoxDecoration(
                        color: AppColors.card(isDark),
                        borderRadius: const BorderRadius.vertical(
                          top: Radius.circular(32),
                        ),
                        border: Border(
                          top: BorderSide(color: AppColors.border(isDark)),
                        ),
                        boxShadow: [
                          BoxShadow(
                            color: Colors.black.withValues(alpha: 0.3),
                            blurRadius: 20,
                            offset: const Offset(0, -4),
                          ),
                        ],
                      ),
                      child: ClipRRect(
                        borderRadius: const BorderRadius.vertical(
                          top: Radius.circular(32),
                        ),
                        child: const _DetailsPanel(key: ValueKey('details')),
                      ),
                    )
                  : const SizedBox.shrink(),
            ),

            if (isState2) _LigtasToggle(bottom: ligtasBottom),
            if (isNavigating)
              _MapControls(
                mapCtrl: _mapCtrl,
                bottomPadding: 80,
                showLigtasToggle: false,
              ),

            if (context.select<ExploreController, bool>(
              (c) => c.locationPopupVisible,
            ))
              const _LocationPopup(),

            // ── MMDA banner (shown when road closures / coding active) ──
            const _MmdaBanner(),

            // ── Advisory banner (weather / seismic / crime) ─────────────
            const _AdvisoryBanner(),
            const _Toast(),
          ],
        ),
      ),
    );
  }
}

// ── Search header (state 2 & 3) ──────────────────────────────────────────────
class _SearchHeader extends StatelessWidget {
  final VoidCallback onTap;
  const _SearchHeader({required this.onTap});

  @override
  Widget build(BuildContext context) {
    final ctrl = context.read<ExploreController>();
    final currentLoc = context.select<ExploreController, String>(
      (c) => c.originText,
    );
    final dest = context.select<ExploreController, String>((c) => c.destText);
    final topPad = MediaQuery.of(context).padding.top;
    final isDark = context.watch<ThemeController>().isDark;

    return Positioned(
      top: 0,
      left: 0,
      right: 0,
      child: Padding(
        padding: EdgeInsets.fromLTRB(12, topPad + 8, 12, 0),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            GestureDetector(
              onTap: () => ctrl.setState(AppState.state1),
              child: Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: AppColors.card(isDark),
                  border: Border.all(color: AppColors.border(isDark)),
                  boxShadow: const [
                    BoxShadow(color: Colors.black38, blurRadius: 8),
                  ],
                ),
                child: Icon(
                  Icons.arrow_back_rounded,
                  color: AppColors.text(isDark),
                  size: 18,
                ),
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
                    boxShadow: const [
                      BoxShadow(color: Colors.black38, blurRadius: 8),
                    ],
                  ),
                  child: Row(
                    children: [
                      const Icon(
                        Icons.search_rounded,
                        color: AppColors.teal,
                        size: 15,
                      ),
                      const SizedBox(width: 6),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text(
                              currentLoc.isEmpty
                                  ? 'Current location'
                                  : currentLoc,
                              style: GoogleFonts.plusJakartaSans(
                                color: AppColors.text2(isDark),
                                fontSize: 10,
                              ),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                            Text(
                              dest.isEmpty ? 'Where to?' : dest,
                              style: GoogleFonts.plusJakartaSans(
                                color: AppColors.text(isDark),
                                fontSize: 12,
                                fontWeight: FontWeight.w700,
                              ),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ],
                        ),
                      ),
                      GestureDetector(
                        onTap: ctrl.clearSearch,
                        child: Padding(
                          padding: const EdgeInsets.all(4),
                          child: Icon(
                            Icons.close_rounded,
                            color: AppColors.text2(isDark),
                            size: 16,
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

// ── Suggestion drawer (state 2) ──────────────────────────────────────────────
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
        GestureDetector(
          behavior: HitTestBehavior.opaque,
          onVerticalDragStart: onDragStart,
          onVerticalDragUpdate: onDragUpdate,
          onVerticalDragEnd: onDragEnd,
          child: Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(vertical: 12),
            color: Colors.transparent,
            child: Center(
              child: Container(
                width: 36,
                height: 4,
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
            child: Text(
              'Suggested Routes',
              style: GoogleFonts.plusJakartaSans(
                fontSize: 18,
                fontWeight: FontWeight.w900,
                color: AppColors.text(isDark),
              ),
            ),
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
                        Icon(
                          Icons.search_off_rounded,
                          size: 40,
                          color: AppColors.text3(isDark),
                        ),
                        const SizedBox(height: 12),
                        Text(
                          'No routes match your filters',
                          style: GoogleFonts.plusJakartaSans(
                            fontSize: 13,
                            color: AppColors.text2(isDark),
                            fontWeight: FontWeight.w600,
                          ),
                          textAlign: TextAlign.center,
                        ),
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

// ── Details panel (state 3) ──────────────────────────────────────────────────
class _DetailsPanel extends StatefulWidget {
  const _DetailsPanel({super.key});
  @override
  State<_DetailsPanel> createState() => _DetailsPanelState();
}

class _DetailsPanelState extends State<_DetailsPanel> {
  bool _safetyNoteExpanded = false;

  @override
  Widget build(BuildContext context) {
    final ctrl = context.watch<ExploreController>();
    final route = ctrl.activeRoute;
    if (route == null) return const SizedBox.shrink();
    final meta = route.safetyMeta;
    final isDark = context.watch<ThemeController>().isDark;

    String routeTypeLabel = meta.label;
    if (ctrl.preferenceFilters.isNotEmpty) {
      final pref = ctrl.preferenceFilters.first;
      routeTypeLabel = pref[0].toUpperCase() + pref.substring(1);
    }

    return Column(
      children: [
        Container(
          width: 36,
          height: 4,
          margin: const EdgeInsets.only(top: 10, bottom: 8),
          decoration: BoxDecoration(
            color: AppColors.border(isDark),
            borderRadius: BorderRadius.circular(2),
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 12),
          child: Row(
            children: [
              GestureDetector(
                onTap: ctrl.backToRoutes,
                child: Container(
                  width: 34,
                  height: 34,
                  decoration: BoxDecoration(
                    color: AppColors.card2(isDark),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: AppColors.border(isDark)),
                  ),
                  child: Icon(
                    Icons.arrow_back_rounded,
                    color: AppColors.text(isDark),
                    size: 18,
                  ),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  'Route Details',
                  style: GoogleFonts.plusJakartaSans(
                    fontSize: 16,
                    fontWeight: FontWeight.w800,
                    color: AppColors.text(isDark),
                  ),
                ),
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
                GestureDetector(
                  onTap: () => setState(
                    () => _safetyNoteExpanded = !_safetyNoteExpanded,
                  ),
                  child: Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: meta.bgColor,
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Column(
                      children: [
                        Row(
                          children: [
                            Icon(
                              Icons.shield_rounded,
                              color: meta.color,
                              size: 24,
                            ),
                            const SizedBox(width: 10),
                            Expanded(
                              child: Text(
                                '$routeTypeLabel Route · ${route.safetyScore}% Safety',
                                style: GoogleFonts.plusJakartaSans(
                                  color: meta.color,
                                  fontSize: 13,
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                            ),
                            Icon(
                              _safetyNoteExpanded
                                  ? Icons.keyboard_arrow_up_rounded
                                  : Icons.keyboard_arrow_down_rounded,
                              color: meta.color,
                              size: 20,
                            ),
                          ],
                        ),
                        if (_safetyNoteExpanded) ...[
                          const SizedBox(height: 8),
                          Text(
                            route.safetyNote,
                            style: GoogleFonts.plusJakartaSans(
                              color: AppColors.text2(isDark),
                              fontSize: 11,
                            ),
                          ),
                        ] else ...[
                          const SizedBox(height: 4),
                          Text(
                            route.safetyNote,
                            style: GoogleFonts.plusJakartaSans(
                              color: AppColors.text2(isDark),
                              fontSize: 11,
                            ),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ],
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                Row(
                  children: [
                    _statBox('${route.minutes} min', 'Duration', isDark),
                    const SizedBox(width: 8),
                    _statBox('₱${route.fare}', 'Fare', isDark),
                    const SizedBox(width: 8),
                    _statBox('5.8 km', 'Distance', isDark),
                  ],
                ),
                // ── Live risk warnings from backend ─────────────────────
                ..._buildRouteWarnings(route, isDark),
                const SizedBox(height: 16),
                Text(
                  route.modes,
                  style: GoogleFonts.plusJakartaSans(
                    fontSize: 15,
                    fontWeight: FontWeight.w800,
                    color: AppColors.text(isDark),
                  ),
                ),
                const SizedBox(height: 12),
                ...route.steps.asMap().entries.map(
                  (e) => _stepRow(e.key, e.value, route.steps.length, isDark),
                ),
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
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                  ),
                  onPressed: ctrl.startNavigation,
                  child: Text(
                    'Start Route',
                    style: GoogleFonts.plusJakartaSans(
                      fontWeight: FontWeight.w800,
                      fontSize: 15,
                    ),
                  ),
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
            Text(
              value,
              style: GoogleFonts.plusJakartaSans(
                fontSize: 14,
                fontWeight: FontWeight.w800,
                color: AppColors.text(isDark),
              ),
            ),
            const SizedBox(height: 2),
            Text(
              label,
              style: GoogleFonts.plusJakartaSans(
                fontSize: 9,
                color: AppColors.text2(isDark),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _stepRow(int index, RouteStep step, int total, bool isDark) {
    final title = step.title.toLowerCase();
    late IconData stepIcon;
    late Color stepColor;
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
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  color: stepIcon == Icons.directions_bus_rounded
                      ? AppColors.tealDim
                      : AppColors.card2(isDark),
                  shape: BoxShape.circle,
                  border: Border.all(color: AppColors.teal, width: 2),
                ),
                child: Icon(stepIcon, color: stepColor, size: 16),
              ),
              if (index < total - 1)
                Container(
                  width: 2,
                  height: 40,
                  color: AppColors.border(isDark),
                ),
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

  List<Widget> _buildRouteWarnings(RouteModel route, bool isDark) {
    final entries = <_RiskWarning>[];

    final seismic = route.seismicWarning;
    if (seismic != null && seismic.isNotEmpty) {
      entries.add(
        _RiskWarning(
          icon: Icons.vibration_rounded,
          color: const Color(0xFFE74C3C),
          bg: const Color(0x22E74C3C),
          text: seismic,
        ),
      );
    }
    final flood = route.floodWarning;
    if (flood != null && flood.isNotEmpty) {
      entries.add(
        _RiskWarning(
          icon: Icons.water_rounded,
          color: const Color(0xFF3B82F6),
          bg: const Color(0x223B82F6),
          text: flood,
        ),
      );
    }
    final crime = route.crimeWarning;
    if (crime != null && crime.isNotEmpty) {
      entries.add(
        _RiskWarning(
          icon: Icons.warning_amber_rounded,
          color: const Color(0xFFF59E0B),
          bg: const Color(0x22F59E0B),
          text: crime,
        ),
      );
    }
    final profile = route.profileWarnings;
    if (profile != null) {
      for (final w in profile) {
        final text = w?.toString() ?? '';
        if (text.isNotEmpty) {
          entries.add(
            _RiskWarning(
              icon: Icons.person_rounded,
              color: const Color(0xFF8E44AD),
              bg: const Color(0x228E44AD),
              text: text,
            ),
          );
        }
      }
    }

    if (entries.isEmpty) return [];

    return [
      const SizedBox(height: 14),
      ...entries.map(
        (e) => Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
            decoration: BoxDecoration(
              color: e.bg,
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: e.color.withValues(alpha: 0.35)),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(e.icon, color: e.color, size: 15),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    e.text,
                    style: GoogleFonts.plusJakartaSans(
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                      color: e.color,
                      height: 1.4,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    ];
  }
}

class _RiskWarning {
  final IconData icon;
  final Color color, bg;
  final String text;
  const _RiskWarning({
    required this.icon,
    required this.color,
    required this.bg,
    required this.text,
  });
}

// ── Filter chips row ─────────────────────────────────────────────────────────
class _FilterChipsRow extends StatelessWidget {
  final ExploreController ctrl;
  const _FilterChipsRow({required this.ctrl});

  @override
  Widget build(BuildContext context) {
    final activeChips = <_ActiveChip>[];
    for (final k in ctrl.commuterFilters) {
      final opt = commuterOptions.where((o) => o.key == k).firstOrNull;
      if (opt != null)
        activeChips.add(_ActiveChip(opt: opt, group: 'commuter', ctrl: ctrl));
    }
    for (final k in ctrl.transportFilters) {
      final opt = transportOptions.where((o) => o.key == k).firstOrNull;
      if (opt != null)
        activeChips.add(_ActiveChip(opt: opt, group: 'transport', ctrl: ctrl));
    }
    for (final k in ctrl.ligtasFilters) {
      final opt = ligtasFeatures.where((o) => o.key == k).firstOrNull;
      if (opt != null)
        activeChips.add(_ActiveChip(opt: opt, group: 'ligtas', ctrl: ctrl));
    }
    for (final k in ctrl.preferenceFilters) {
      final opt = preferenceOptions.where((o) => o.key == k).firstOrNull;
      if (opt != null)
        activeChips.add(_ActiveChip(opt: opt, group: 'preference', ctrl: ctrl));
    }
    // Active vulnerable profile chip
    if (ctrl.activeVulnerableProfile != null) {
      final p = _profileOptions
          .where((o) => o.key == ctrl.activeVulnerableProfile)
          .firstOrNull;
      if (p != null) {
        activeChips.add(
          _ActiveChip(
            opt: FilterOption(key: p.key, label: p.label, icon: p.icon),
            group: 'profile',
            ctrl: ctrl,
          ),
        );
      }
    }

    final isDark = context.watch<ThemeController>().isDark;

    void openFilters() => showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => ChangeNotifierProvider.value(
        value: ctrl,
        child: const _FilterModal(),
      ),
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
              width: 36,
              height: 36,
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
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.2),
                    blurRadius: 4,
                  ),
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
                      color: AppColors.text3(isDark),
                      fontSize: 12,
                    ),
                  )
                : Stack(
                    children: [
                      ListView(
                        scrollDirection: Axis.horizontal,
                        padding: const EdgeInsets.only(right: 32),
                        children: activeChips,
                      ),
                      Positioned(
                        right: 0,
                        top: 0,
                        bottom: 0,
                        width: 32,
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
          if (ctrl.hasFilters || ctrl.activeVulnerableProfile != null) ...[
            const SizedBox(width: 8),
            GestureDetector(
              onTap: () {
                ctrl.clearAllFilters();
                ctrl.setVulnerableProfile(null);
              },
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
  const _ActiveChip({
    required this.opt,
    required this.group,
    required this.ctrl,
  });

  @override
  Widget build(BuildContext context) {
    final isProfile = group == 'profile';
    return Container(
      margin: const EdgeInsets.only(right: 8, top: 10, bottom: 10),
      padding: const EdgeInsets.symmetric(horizontal: 12),
      decoration: BoxDecoration(
        color: isProfile ? const Color(0xFF8E44AD) : AppColors.teal,
        borderRadius: BorderRadius.circular(50),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(opt.icon, size: 12, color: Colors.white),
          const SizedBox(width: 6),
          Text(
            opt.label,
            style: GoogleFonts.plusJakartaSans(
              fontSize: 11,
              fontWeight: FontWeight.w700,
              color: Colors.white,
            ),
          ),
          const SizedBox(width: 6),
          GestureDetector(
            onTap: () {
              if (isProfile) {
                ctrl.setVulnerableProfile(null);
              } else {
                ctrl.removeFilter(group, opt.key);
              }
            },
            child: const Icon(
              Icons.close_rounded,
              size: 12,
              color: Colors.white70,
            ),
          ),
        ],
      ),
    );
  }
}

// ── Filter modal ─────────────────────────────────────────────────────────────
class _FilterModal extends StatelessWidget {
  const _FilterModal();

  @override
  Widget build(BuildContext context) {
    final ctrl = context.watch<ExploreController>();
    final isDark = context.watch<ThemeController>().isDark;
    return DraggableScrollableSheet(
      initialChildSize: 0.85,
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
                width: 36,
                height: 4,
                margin: const EdgeInsets.symmetric(vertical: 12),
                decoration: BoxDecoration(
                  color: AppColors.border(isDark),
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  'Filters',
                  style: GoogleFonts.plusJakartaSans(
                    fontSize: 18,
                    fontWeight: FontWeight.w800,
                    color: AppColors.text(isDark),
                  ),
                ),
                IconButton(
                  icon: Icon(
                    Icons.close_rounded,
                    color: AppColors.text2(isDark),
                  ),
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

            // ── Vulnerable commuter profile ─────────────────────────────
            const SizedBox(height: 20),
            _sectionLabel('COMMUTER PROFILE'),
            Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Builder(
                builder: (context) {
                  final isDark = context.watch<ThemeController>().isDark;
                  return Text(
                    'Applies safety adjustments for vulnerable commuters',
                    style: GoogleFonts.plusJakartaSans(
                      fontSize: 11,
                      color: AppColors.text3(isDark),
                    ),
                  );
                },
              ),
            ),
            _profileGrid(context, ctrl),

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
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
                onPressed: () => Navigator.pop(context),
                child: const Text(
                  'Apply Filters',
                  style: TextStyle(fontWeight: FontWeight.bold),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _sectionLabel(String title) => Padding(
    padding: const EdgeInsets.only(bottom: 10),
    child: Builder(
      builder: (context) {
        final isDark = context.watch<ThemeController>().isDark;
        return Text(
          title,
          style: GoogleFonts.plusJakartaSans(
            fontSize: 11,
            fontWeight: FontWeight.w800,
            color: AppColors.text2(isDark),
            letterSpacing: 1,
          ),
        );
      },
    ),
  );

  Widget _optionGrid(
    BuildContext context,
    ExploreController ctrl,
    List<FilterOption> options,
    String group,
  ) {
    final active = group == 'commuter'
        ? ctrl.commuterFilters
        : group == 'transport'
        ? ctrl.transportFilters
        : group == 'ligtas'
        ? ctrl.ligtasFilters
        : ctrl.preferenceFilters;
    final isDark = context.watch<ThemeController>().isDark;
    return GridView.count(
      crossAxisCount: 3,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      mainAxisSpacing: 8,
      crossAxisSpacing: 8,
      childAspectRatio: 1.6,
      children: options.map((opt) {
        final isActive = active.contains(opt.key);
        return GestureDetector(
          onTap: () => ctrl.toggleFilter(group, opt.key),
          child: Container(
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
                Icon(
                  opt.icon,
                  size: 18,
                  color: isActive ? Colors.white : AppColors.text2(isDark),
                ),
                const SizedBox(height: 4),
                Text(
                  opt.label,
                  style: GoogleFonts.plusJakartaSans(
                    fontSize: 10,
                    fontWeight: FontWeight.w700,
                    color: isActive ? Colors.white : AppColors.text2(isDark),
                  ),
                  textAlign: TextAlign.center,
                ),
              ],
            ),
          ),
        );
      }).toList(),
    );
  }

  /// Vulnerable profile selector — radio style (one at a time).
  Widget _profileGrid(BuildContext context, ExploreController ctrl) {
    final isDark = context.watch<ThemeController>().isDark;
    return GridView.count(
      crossAxisCount: 2,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      mainAxisSpacing: 8,
      crossAxisSpacing: 8,
      childAspectRatio: 2.4,
      children: _profileOptions.map((p) {
        final isActive = ctrl.activeVulnerableProfile == p.key;
        return GestureDetector(
          onTap: () => ctrl.setVulnerableProfile(isActive ? null : p.key),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 10),
            decoration: BoxDecoration(
              color: isActive
                  ? const Color(0xFF8E44AD)
                  : AppColors.card2(isDark),
              borderRadius: BorderRadius.circular(10),
              border: Border.all(
                color: isActive
                    ? const Color(0xFF8E44AD)
                    : AppColors.border(isDark),
              ),
            ),
            child: Row(
              children: [
                Icon(
                  p.icon,
                  size: 16,
                  color: isActive ? Colors.white : AppColors.text2(isDark),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    p.label,
                    style: GoogleFonts.plusJakartaSans(
                      fontSize: 10,
                      fontWeight: FontWeight.w700,
                      color: isActive ? Colors.white : AppColors.text2(isDark),
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
          ),
        );
      }).toList(),
    );
  }
}

// ── Ligtas toggle ─────────────────────────────────────────────────────────────
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
          width: 38,
          height: 38,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: ctrl.ligtasModeOn ? AppColors.goldActive : AppColors.gold,
            boxShadow: [
              BoxShadow(
                color: AppColors.gold.withValues(
                  alpha: ctrl.ligtasModeOn ? 0.6 : 0.3,
                ),
                blurRadius: 15,
              ),
            ],
          ),
          child: const Icon(
            Icons.wb_sunny_rounded,
            color: Colors.white,
            size: 20,
          ),
        ),
      ),
    );
  }
}

// ── Zoom controls (state 2) ──────────────────────────────────────────────────
class _MapZoomControls extends StatelessWidget {
  final MapController mapCtrl;
  final double bottomPadding;
  const _MapZoomControls({required this.mapCtrl, required this.bottomPadding});

  @override
  Widget build(BuildContext context) {
    final ctrl = context.watch<ExploreController>();
    final isDark = context.watch<ThemeController>().isDark;
    return Positioned(
      right: 14,
      bottom: bottomPadding,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          _btn(
            isDark,
            Icons.add_rounded,
            () => mapCtrl.move(mapCtrl.camera.center, mapCtrl.camera.zoom + 1),
          ),
          const SizedBox(height: 8),
          _btn(
            isDark,
            Icons.remove_rounded,
            () => mapCtrl.move(mapCtrl.camera.center, mapCtrl.camera.zoom - 1),
          ),
          const SizedBox(height: 8),
          // Recenter: use real GPS if available, else route origin
          _btn(isDark, Icons.my_location_rounded, () {
            if (ctrl.hasLocation && ctrl.lat != null && ctrl.lng != null) {
              mapCtrl.move(LatLng(ctrl.lat!, ctrl.lng!), 16);
            } else {
              final route = ctrl.activeRoute;
              if (route != null && route.polyline.isNotEmpty) {
                mapCtrl.move(
                  LatLng(route.polyline.first[0], route.polyline.first[1]),
                  15,
                );
              } else {
                mapCtrl.move(const LatLng(14.6530, 121.0580), 14);
              }
            }
          }),
        ],
      ),
    );
  }

  Widget _btn(bool isDark, IconData icon, VoidCallback onTap) =>
      GestureDetector(
        onTap: onTap,
        child: Container(
          width: 38,
          height: 38,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: isDark ? const Color(0xFF1E2530) : Colors.white,
            border: Border.all(
              color: isDark ? const Color(0xFF2A3340) : const Color(0xFFE2E8F0),
            ),
            boxShadow: const [BoxShadow(color: Colors.black26, blurRadius: 8)],
          ),
          child: Icon(
            icon,
            color: isDark ? const Color(0xFFCBD5E1) : const Color(0xFF475569),
            size: 24,
          ),
        ),
      );
}

// ── Map controls (state 4 — navigation) ─────────────────────────────────────
class _MapControls extends StatelessWidget {
  final MapController mapCtrl;
  final double bottomPadding;
  final bool showLigtasToggle;
  const _MapControls({
    required this.mapCtrl,
    required this.bottomPadding,
    this.showLigtasToggle = true,
  });

  @override
  Widget build(BuildContext context) {
    final ctrl = context.watch<ExploreController>();
    final isDark = context.watch<ThemeController>().isDark;
    return Positioned(
      right: 14,
      bottom: bottomPadding,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
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
                          width: 38,
                          height: 38,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            color: ctrl.ligtasModeOn
                                ? AppColors.goldActive
                                : AppColors.gold,
                            boxShadow: [
                              BoxShadow(
                                color: AppColors.gold.withValues(
                                  alpha: ctrl.ligtasModeOn ? 0.6 : 0.3,
                                ),
                                blurRadius: 15,
                              ),
                            ],
                          ),
                          child: const Icon(
                            Icons.wb_sunny_rounded,
                            color: Colors.white,
                            size: 20,
                          ),
                        ),
                      ),
                      const SizedBox(height: 10),
                    ],
                  )
                : const SizedBox.shrink(),
          ),
          _btn(
            isDark,
            Icons.add_rounded,
            () => mapCtrl.move(mapCtrl.camera.center, mapCtrl.camera.zoom + 1),
          ),
          const SizedBox(height: 8),
          _btn(
            isDark,
            Icons.remove_rounded,
            () => mapCtrl.move(mapCtrl.camera.center, mapCtrl.camera.zoom - 1),
          ),
          const SizedBox(height: 8),
          // Recenter to real GPS position during navigation
          _btn(isDark, Icons.my_location_rounded, () {
            if (ctrl.hasLocation && ctrl.lat != null && ctrl.lng != null) {
              mapCtrl.move(LatLng(ctrl.lat!, ctrl.lng!), 17);
            } else {
              final route = ctrl.activeRoute;
              if (route != null && route.polyline.isNotEmpty) {
                mapCtrl.move(
                  LatLng(route.polyline.first[0], route.polyline.first[1]),
                  16,
                );
              } else {
                mapCtrl.move(const LatLng(14.6530, 121.0580), 14);
              }
            }
          }),
        ],
      ),
    );
  }

  Widget _btn(bool isDark, IconData icon, VoidCallback onTap) =>
      GestureDetector(
        onTap: onTap,
        child: Container(
          width: 38,
          height: 38,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: isDark ? const Color(0xFF1E2530) : Colors.white,
            border: Border.all(
              color: isDark ? const Color(0xFF2A3340) : const Color(0xFFE2E8F0),
            ),
            boxShadow: const [BoxShadow(color: Colors.black26, blurRadius: 8)],
          ),
          child: Icon(
            icon,
            color: isDark ? const Color(0xFFCBD5E1) : const Color(0xFF475569),
            size: 24,
          ),
        ),
      );
}

// ── Route card ───────────────────────────────────────────────────────────────
class _RouteCard extends StatelessWidget {
  final RouteModel route;
  const _RouteCard({required this.route});

  @override
  Widget build(BuildContext context) {
    final ctrl = context.read<ExploreController>();
    final meta = route.safetyMeta;
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
                  Text(
                    route.modes,
                    style: GoogleFonts.plusJakartaSans(
                      color: AppColors.text(isDark),
                      fontSize: 13,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Row(
                    children: [
                      Icon(
                        Icons.schedule_rounded,
                        size: 13,
                        color: AppColors.text2(isDark),
                      ),
                      const SizedBox(width: 4),
                      Text(
                        '${route.minutes} min',
                        style: GoogleFonts.plusJakartaSans(
                          color: AppColors.text2(isDark),
                          fontSize: 11,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const SizedBox(width: 12),
                      Icon(
                        Icons.payments_rounded,
                        size: 13,
                        color: AppColors.text2(isDark),
                      ),
                      const SizedBox(width: 4),
                      Text(
                        '₱${route.fare}',
                        style: GoogleFonts.plusJakartaSans(
                          color: AppColors.text2(isDark),
                          fontSize: 11,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(
                color: meta.bgColor,
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text(
                '${route.safetyScore}%',
                style: GoogleFonts.plusJakartaSans(
                  color: meta.color,
                  fontSize: 13,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ── Location permission popup ─────────────────────────────────────────────────
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
                  width: 56,
                  height: 56,
                  decoration: const BoxDecoration(
                    color: AppColors.tealDim,
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(
                    Icons.my_location_rounded,
                    color: AppColors.teal,
                    size: 28,
                  ),
                ),
                const SizedBox(height: 16),
                Text(
                  'Enable Location',
                  style: GoogleFonts.plusJakartaSans(
                    fontSize: 18,
                    fontWeight: FontWeight.w800,
                    color: AppColors.text(isDark),
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  'Allow Ligtas to access your location to find safe routes near you.',
                  style: GoogleFonts.plusJakartaSans(
                    color: AppColors.text2(isDark),
                    fontSize: 13,
                  ),
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
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(10),
                          ),
                        ),
                        onPressed: ctrl.requestLocation,
                        child: Text(
                          'Enable',
                          style: GoogleFonts.plusJakartaSans(
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: OutlinedButton(
                        style: OutlinedButton.styleFrom(
                          foregroundColor: AppColors.text2(isDark),
                          side: BorderSide(color: AppColors.border(isDark)),
                          padding: const EdgeInsets.symmetric(vertical: 12),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(10),
                          ),
                        ),
                        onPressed: ctrl.skipLocation,
                        child: Text(
                          'Skip',
                          style: GoogleFonts.plusJakartaSans(
                            fontWeight: FontWeight.w700,
                          ),
                        ),
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

// ── Map layer ─────────────────────────────────────────────────────────────────
class _MapLayer extends StatelessWidget {
  final MapController mapCtrl;
  const _MapLayer({required this.mapCtrl});

  @override
  Widget build(BuildContext context) {
    final ctrl = context.watch<ExploreController>();
    final route = ctrl.activeRoute;
    final polylines = <Polyline>[];
    final markers = <Marker>[];

    if (route != null) {
      final pts = route.polyline.map((p) => LatLng(p[0], p[1])).toList();
      polylines.add(
        Polyline(points: pts, color: route.safetyMeta.color, strokeWidth: 5),
      );
      if (pts.isNotEmpty) {
        markers.add(
          Marker(
            point: pts.first,
            width: 40,
            height: 40,
            child: _mapPin(AppColors.teal, Icons.person_pin_circle_rounded),
          ),
        );
        markers.add(
          Marker(
            point: pts.last,
            width: 40,
            height: 40,
            child: _mapPin(route.safetyMeta.color, Icons.location_pin),
          ),
        );
      }
    }

    // Real GPS position marker (shown when location is enabled)
    if (ctrl.hasLocation && ctrl.lat != null && ctrl.lng != null) {
      markers.add(
        Marker(
          point: LatLng(ctrl.lat!, ctrl.lng!),
          width: 44,
          height: 44,
          child: _gpsPin(),
        ),
      );
    }

    final poiMarkers = ctrl.pois
        .map(
          (poi) => Marker(
            point: LatLng(poi.lat, poi.lng),
            width: 36,
            height: 36,
            child: _poiPin(poi.color, poi.icon, poi.label),
          ),
        )
        .toList();

    final circles = ctrl.hotspots
        .map(
          (h) => CircleMarker(
            point: LatLng(h.lat, h.lng),
            radius: h.radiusMeters,
            useRadiusInMeter: true,
            color: h.color,
            borderColor: h.color.withValues(alpha: 1.0),
            borderStrokeWidth: 1.5,
          ),
        )
        .toList();

    return FlutterMap(
      mapController: mapCtrl,
      options: MapOptions(
        initialCenter: ctrl.hasLocation && ctrl.lat != null
            ? LatLng(ctrl.lat!, ctrl.lng!)
            : const LatLng(14.6530, 121.0580),
        initialZoom: 14,
        interactionOptions: const InteractionOptions(
          flags: InteractiveFlag.all,
        ),
      ),
      children: [
        TileLayer(
          urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
          userAgentPackageName: 'com.ligtas.explore',
        ),
        if (circles.isNotEmpty) CircleLayer(circles: circles),
        if (polylines.isNotEmpty) PolylineLayer(polylines: polylines),
        if (markers.isNotEmpty) MarkerLayer(markers: markers),
        if (poiMarkers.isNotEmpty) MarkerLayer(markers: poiMarkers),
      ],
    );
  }

  Widget _gpsPin() => Container(
    width: 20,
    height: 20,
    decoration: BoxDecoration(
      color: AppColors.teal,
      shape: BoxShape.circle,
      border: Border.all(color: Colors.white, width: 3),
      boxShadow: [
        BoxShadow(
          color: AppColors.teal.withValues(alpha: 0.5),
          blurRadius: 12,
          spreadRadius: 2,
        ),
      ],
    ),
  );

  Widget _poiPin(Color color, IconData icon, String label) => Tooltip(
    message: label,
    child: Container(
      width: 32,
      height: 32,
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
      color: color,
      shape: BoxShape.circle,
      border: Border.all(color: Colors.white, width: 2.5),
      boxShadow: [
        BoxShadow(
          color: color.withValues(alpha: 0.4),
          blurRadius: 8,
          offset: const Offset(0, 2),
        ),
      ],
    ),
    child: Icon(icon, color: Colors.white, size: 20),
  );
}

// ── Nav header (state 4) ─────────────────────────────────────────────────────
class _NavHeader extends StatelessWidget {
  const _NavHeader();

  @override
  Widget build(BuildContext context) {
    final route = context.watch<ExploreController>().activeRoute;
    final isDark = context.watch<ThemeController>().isDark;
    final estimatedTime = route != null ? '${route.minutes} min' : '—';

    return Positioned(
      top: 0,
      left: 0,
      right: 0,
      child: Container(
        color: Colors.transparent,
        padding: EdgeInsets.fromLTRB(
          16,
          MediaQuery.of(context).padding.top + 8,
          16,
          12,
        ),
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
                width: 32,
                height: 32,
                decoration: const BoxDecoration(
                  color: AppColors.teal,
                  shape: BoxShape.circle,
                ),
                child: const Icon(
                  Icons.my_location_rounded,
                  color: Colors.white,
                  size: 16,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'NAVIGATING',
                      style: GoogleFonts.plusJakartaSans(
                        fontSize: 9,
                        fontWeight: FontWeight.w800,
                        color: AppColors.text3(isDark),
                        letterSpacing: 0.5,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      route?.modes ?? '—',
                      style: GoogleFonts.plusJakartaSans(
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                        color: AppColors.text(isDark),
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 12,
                  vertical: 6,
                ),
                decoration: BoxDecoration(
                  color: AppColors.tealDim,
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(
                      Icons.schedule_rounded,
                      color: AppColors.teal,
                      size: 14,
                    ),
                    const SizedBox(width: 4),
                    Text(
                      estimatedTime,
                      style: GoogleFonts.plusJakartaSans(
                        fontSize: 12,
                        fontWeight: FontWeight.w700,
                        color: AppColors.teal,
                      ),
                    ),
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

// ── Stop bar (state 4) ───────────────────────────────────────────────────────
// Now has a working Report button and an SOS button.
class _StopBar extends StatelessWidget {
  final MapController mapCtrl;
  const _StopBar({required this.mapCtrl});

  @override
  Widget build(BuildContext context) {
    final ctrl = context.read<ExploreController>();
    final isDark = context.watch<ThemeController>().isDark;
    final bottomPadding = MediaQuery.of(context).padding.bottom;

    return Positioned(
      bottom: 0,
      left: 0,
      right: 0,
      child: Container(
        padding: EdgeInsets.fromLTRB(16, 12, 16, bottomPadding + 12),
        decoration: BoxDecoration(
          color: AppColors.card(isDark),
          border: Border(top: BorderSide(color: AppColors.border(isDark))),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.2),
              blurRadius: 10,
              offset: const Offset(0, -2),
            ),
          ],
        ),
        child: Row(
          children: [
            // ── Report incident button ────────────────────────────
            ElevatedButton(
              style: ElevatedButton.styleFrom(
                backgroundColor: AppColors.teal,
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 14,
                ),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
                elevation: 0,
              ),
              onPressed: () => _showReportModal(context, ctrl),
              child: Text(
                'Report',
                style: GoogleFonts.plusJakartaSans(
                  fontWeight: FontWeight.w700,
                  fontSize: 14,
                ),
              ),
            ),
            const SizedBox(width: 8),
            // ── SOS button ───────────────────────────────────────
            ElevatedButton(
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFFDC2626),
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 14,
                ),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
                elevation: 0,
              ),
              onPressed: () => ctrl.triggerSos(context),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.emergency_rounded, size: 16),
                  const SizedBox(width: 6),
                  Text(
                    'SOS',
                    style: GoogleFonts.plusJakartaSans(
                      fontWeight: FontWeight.w800,
                      fontSize: 14,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 8),
            // ── Stop route button ────────────────────────────────
            Expanded(
              child: ElevatedButton(
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF1E293B),
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

  /// Shows the report incident bottom sheet.
  /// Fetches available report types from backend on first open.
  void _showReportModal(BuildContext context, ExploreController ctrl) {
    // Ensure types are loaded (cached after first call)
    ctrl.loadReportTypes();

    final isDark = context.read<ThemeController>().isDark;
    final latCtrl = ctrl.lat ?? 14.5995;
    final lonCtrl = ctrl.lng ?? 120.9842;

    String? selectedType;
    final descCtrl = TextEditingController();

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => Padding(
        padding: EdgeInsets.only(bottom: MediaQuery.of(ctx).viewInsets.bottom),
        child: ChangeNotifierProvider.value(
          value: ctrl,
          child: StatefulBuilder(
            builder: (ctx, setModalState) {
              final types = ctrl.reportTypes;
              return Container(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 28),
                decoration: BoxDecoration(
                  color: AppColors.card(isDark),
                  borderRadius: const BorderRadius.vertical(
                    top: Radius.circular(20),
                  ),
                ),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Center(
                      child: Container(
                        width: 36,
                        height: 4,
                        margin: const EdgeInsets.only(bottom: 16),
                        decoration: BoxDecoration(
                          color: AppColors.border(isDark),
                          borderRadius: BorderRadius.circular(2),
                        ),
                      ),
                    ),
                    Text(
                      'Report an Incident',
                      style: GoogleFonts.plusJakartaSans(
                        fontSize: 17,
                        fontWeight: FontWeight.w800,
                        color: AppColors.text(isDark),
                      ),
                    ),
                    const SizedBox(height: 14),
                    // Type selector chips
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: types.map((t) {
                        final isSelected = selectedType == t.key;
                        return GestureDetector(
                          onTap: () =>
                              setModalState(() => selectedType = t.key),
                          child: Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 14,
                              vertical: 8,
                            ),
                            decoration: BoxDecoration(
                              color: isSelected
                                  ? AppColors.teal
                                  : AppColors.card2(isDark),
                              borderRadius: BorderRadius.circular(50),
                              border: Border.all(
                                color: isSelected
                                    ? AppColors.teal
                                    : AppColors.border(isDark),
                              ),
                            ),
                            child: Text(
                              '${t.icon} ${t.label}',
                              style: GoogleFonts.plusJakartaSans(
                                fontSize: 12,
                                fontWeight: FontWeight.w600,
                                color: isSelected
                                    ? Colors.white
                                    : AppColors.text(isDark),
                              ),
                            ),
                          ),
                        );
                      }).toList(),
                    ),
                    const SizedBox(height: 14),
                    // Description field
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 14,
                        vertical: 10,
                      ),
                      decoration: BoxDecoration(
                        color: AppColors.card2(isDark),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: AppColors.border(isDark)),
                      ),
                      child: TextField(
                        controller: descCtrl,
                        maxLines: 3,
                        minLines: 2,
                        style: GoogleFonts.plusJakartaSans(
                          color: AppColors.text(isDark),
                          fontSize: 13,
                        ),
                        decoration: InputDecoration(
                          hintText: 'Describe what you saw… (optional)',
                          hintStyle: GoogleFonts.plusJakartaSans(
                            color: AppColors.text3(isDark),
                            fontSize: 13,
                          ),
                          isDense: true,
                          border: InputBorder.none,
                          contentPadding: EdgeInsets.zero,
                        ),
                      ),
                    ),
                    const SizedBox(height: 16),
                    SizedBox(
                      width: double.infinity,
                      child: ElevatedButton(
                        style: ElevatedButton.styleFrom(
                          backgroundColor: selectedType != null
                              ? AppColors.teal
                              : AppColors.border(isDark),
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(vertical: 14),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(12),
                          ),
                          elevation: 0,
                        ),
                        onPressed: selectedType == null
                            ? null
                            : () async {
                                Navigator.pop(ctx);
                                await ctrl.submitReport(
                                  reportType: selectedType!,
                                  lat: latCtrl,
                                  lon: lonCtrl,
                                  description: descCtrl.text,
                                );
                              },
                        child: Text(
                          'Submit Report',
                          style: GoogleFonts.plusJakartaSans(
                            fontWeight: FontWeight.w700,
                            fontSize: 15,
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              );
            },
          ),
        ),
      ),
    );
  }
}

// ── MMDA banner ──────────────────────────────────────────────────────────────
// Shown when MMDA data is active (number coding / road closures).
// Sits just below any advisory banner, or at the top when advisory is null.
class _MmdaBanner extends StatelessWidget {
  const _MmdaBanner();

  @override
  Widget build(BuildContext context) {
    final ctrl = context.watch<ExploreController>();
    final status = ctrl.mmdaStatus;

    // Only show when there are active closures or number coding
    if (!status.isCoded && status.closuresCount == 0) {
      return const SizedBox.shrink();
    }

    final msg = status.isCoded && status.codingMessage != null
        ? '🚦 ${status.codingMessage}'
        : '🚧 ${status.closuresCount} MMDA road closure${status.closuresCount > 1 ? 's' : ''} active — check route';

    return Positioned(
      top: 0,
      left: 0,
      right: 0,
      child: Material(
        color: const Color(
          0xFF1D4ED8,
        ), // deep blue — distinct from advisory amber
        child: SafeArea(
          bottom: false,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
            child: Row(
              children: [
                const Icon(
                  Icons.traffic_rounded,
                  color: Colors.white,
                  size: 16,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    msg,
                    style: GoogleFonts.plusJakartaSans(
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                      color: Colors.white,
                      height: 1.3,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// ── Advisory banner ──────────────────────────────────────────────────────────
class _AdvisoryBanner extends StatelessWidget {
  const _AdvisoryBanner();

  @override
  Widget build(BuildContext context) {
    final advisory = context.select<ExploreController, AdvisoryModel?>(
      (c) => c.advisory,
    );
    if (advisory == null) return const SizedBox.shrink();

    final Color bg;
    final Color textColor;
    final IconData icon;
    switch (advisory.type) {
      case 'danger':
        bg = const Color(0xFFDC2626);
        textColor = Colors.white;
        icon = Icons.warning_rounded;
        break;
      case 'info':
        bg = AppColors.teal;
        textColor = Colors.white;
        icon = Icons.info_outline_rounded;
        break;
      case 'warning':
      default:
        bg = const Color(0xFFF59E0B);
        textColor = const Color(0xFF1C1A00);
        icon = Icons.warning_amber_rounded;
    }

    // Offset below the MMDA banner if both are visible
    final ctrl = context.read<ExploreController>();
    final hasMmda =
        ctrl.mmdaStatus.isCoded || ctrl.mmdaStatus.closuresCount > 0;

    return Positioned(
      top: hasMmda ? 44.0 : 0.0,
      left: 0,
      right: 0,
      child: Material(
        color: bg,
        child: SafeArea(
          bottom: false,
          top: !hasMmda,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
            child: Row(
              children: [
                Icon(icon, color: textColor, size: 16),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    advisory.message,
                    style: GoogleFonts.plusJakartaSans(
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                      color: textColor,
                      height: 1.3,
                    ),
                  ),
                ),
                GestureDetector(
                  onTap: () =>
                      context.read<ExploreController>().setAdvisory(null),
                  child: Padding(
                    padding: const EdgeInsets.only(left: 8),
                    child: Icon(
                      Icons.close_rounded,
                      color: textColor,
                      size: 16,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// ── Toast ─────────────────────────────────────────────────────────────────────
class _Toast extends StatelessWidget {
  const _Toast();
  @override
  Widget build(BuildContext context) {
    final msg = context.select<ExploreController, String>((c) => c.toastMsg);
    final visible = context.select<ExploreController, bool>(
      (c) => c.toastVisible,
    );
    final isDark = context.watch<ThemeController>().isDark;
    return AnimatedPositioned(
      duration: const Duration(milliseconds: 300),
      top: visible ? 100 : 60,
      left: 0,
      right: 0,
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
              child: Text(
                msg,
                style: TextStyle(color: AppColors.text(isDark), fontSize: 13),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
