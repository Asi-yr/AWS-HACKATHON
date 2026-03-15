import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';
import '../../core/app_colors.dart';
import '../../core/app_router.dart';
import '../../core/session_manager.dart';
import '../../core/api_client.dart';
import '../../screens/explore/explore_controller.dart';
import '../../widgets/shared_widgets.dart';

// Light-mode token shortcuts — survey is always shown before auth
// so it must never inherit the dark theme.
const _bg     = AppColors.bgLight;
const _card   = AppColors.cardLight;
const _border = AppColors.borderLight;
const _text   = AppColors.textLight;
const _text2  = AppColors.text2Light;
const _teal   = AppColors.teal;

// ════════════════════════════════════════════════════════════════
// SURVEY / ONBOARDING SCREEN
// ════════════════════════════════════════════════════════════════
// 3-step onboarding survey:
//   Step 1 — Who are you? (commuter type)
//   Step 2 — How do you usually commute? (transport modes)
//   Step 3 — What safety concerns matter most?
//
// BACKEND: POST /api/user/survey  { commuterType, transport, safetyPrefs }
//          On success → navigate to explore
// ════════════════════════════════════════════════════════════════

class SurveyView extends StatefulWidget {
  const SurveyView({super.key});
  @override State<SurveyView> createState() => _SurveyViewState();
}

class _SurveyViewState extends State<SurveyView> {
  int _step = 0;
  bool _isSubmitting = false;

  // Step 1 — commuter type (multi select)
  final Set<String> _commuterTypes = {};

  // Step 2 — transport (multi select)
  final Set<String> _transport = {};

  // Step 3 — safety concerns (multi select)
  final Set<String> _safety = {};

  static const _commuterOptions = [
    _Option('normal',    'Normal Commuter',          Icons.person_rounded),
    _Option('student',   'Student',                  Icons.school_rounded),
    _Option('women',     'Women',                    Icons.woman_rounded),
    _Option('lgbtq',     'LGBTQ+',                   Icons.diversity_3_rounded),
    _Option('disabled',  'Disabled / Elderly',       Icons.accessible_rounded),
    _Option('minor',     'Minor (under 18)',          Icons.child_care_rounded),
  ];

  static const _transportOptions = [
    _Option('jeep',       'Jeepney',    Icons.directions_bus_rounded),
    _Option('bus',        'Bus',        Icons.airport_shuttle_rounded),
    _Option('mrt',        'MRT / LRT',  Icons.train_rounded),
    _Option('uv',         'UV Express', Icons.directions_car_rounded),
    _Option('tricycle',   'Tricycle',   Icons.electric_rickshaw_rounded),
    _Option('walk',       'Walking',    Icons.directions_walk_rounded),
    _Option('motorcycle', 'Motorcycle', Icons.two_wheeler_rounded),
  ];

  static const _safetyOptions = [
    _Option('crime',    'Crime Hotspots',  Icons.gpp_bad_rounded),
    _Option('dark',     'Dark Areas',      Icons.nightlight_round),
    _Option('flooding', 'Flooding',        Icons.water_rounded),
    _Option('traffic',  'Heavy Traffic',   Icons.traffic_rounded),
    _Option('typhoon',  'Typhoon Risk',    Icons.thunderstorm_rounded),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: _bg,
      body: SafeArea(
        child: Column(children: [
          // Progress bar
          _ProgressBar(current: _step, total: 3),
          // Step content
          Expanded(child: AnimatedSwitcher(
            duration: const Duration(milliseconds: 320),
            transitionBuilder: (child, anim) => FadeTransition(
              opacity: anim,
              child: SlideTransition(
                position: Tween<Offset>(
                  begin: const Offset(0.08, 0), end: Offset.zero)
                  .animate(anim),
                child: child)),
            child: KeyedSubtree(
              key: ValueKey(_step),
              child: _step == 0 ? _StepCommuter(
                selected: _commuterTypes,
                options: _commuterOptions,
                onToggle: (v) => setState(() {
                  if (_commuterTypes.contains(v)) {
                    _commuterTypes.remove(v);
                  } else {
                    _commuterTypes.add(v);
                  }
                }),
              ) : _step == 1 ? _StepMulti(
                title: 'How do you\nusually commute?',
                subtitle: 'Select all that apply',
                options: _transportOptions,
                selected: _transport,
                onToggle: (v) => setState(() =>
                  _transport.contains(v) ? _transport.remove(v) : _transport.add(v)),
              ) : _StepMulti(
                title: 'What safety concerns\nmatter most to you?',
                subtitle: 'We\'ll prioritize these on your routes',
                options: _safetyOptions,
                selected: _safety,
                onToggle: (v) => setState(() =>
                  _safety.contains(v) ? _safety.remove(v) : _safety.add(v)),
              ),
            ),
          )),
          // Nav buttons
          Padding(
            padding: const EdgeInsets.fromLTRB(24, 8, 24, 24),
            child: Row(children: [
              if (_step > 0) ...[
                Expanded(child: OutlinedButton(
                  style: OutlinedButton.styleFrom(
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                    side: BorderSide(color: _border)),
                  onPressed: () => setState(() => _step--),
                  child: Text('Back',
                    style: GoogleFonts.plusJakartaSans(
                      fontWeight: FontWeight.w700, color: _text2)),
                )),
                const SizedBox(width: 12),
              ],
              Expanded(flex: 2, child: _isSubmitting
                ? const TealButton(label: 'Saving...', onTap: _noOp)
                : TealButton(
                    label: _step < 2 ? 'Continue' : 'Get Started',
                    onTap: _canContinue ? _next : _noOp,
                  )),

            ]),
          ),
        ]),
      ),
    );
  }

  bool get _canContinue {
    if (_step == 0) return _commuterTypes.isNotEmpty;
    if (_step == 1) return _transport.isNotEmpty;
    return true; // safety step optional
  }

  static void _noOp() {}

  void _next() {
    if (_step < 2) {
      setState(() => _step++);
    } else {
      _saveSurveyAndNavigate();
    }
  }

  /// Save survey responses to backend and navigate to explore screen.
  Future<void> _saveSurveyAndNavigate() async {
    setState(() => _isSubmitting = true);
    try {
      final token = await SessionManager.instance.getAuthToken();
      if (token == null || token.isEmpty) {
        debugPrint('[SurveyView] Not logged in, using local defaults only');
        _proceedToExplore();
        return;
      }

      await ApiClient.instance.saveSurvey(
        commuterTypes: _commuterTypes.toList(),
        transportModes: _transport.toList(),
        safetyConcerns: _safety.toList(),
        token: token,
      );
      _proceedToExplore();
    } catch (e) {
      debugPrint('[SurveyView] Error saving survey: $e');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Survey saved locally — server unreachable')),
        );
      }
      _proceedToExplore();
    } finally {
      if (mounted) setState(() => _isSubmitting = false);
    }
  }

  /// Navigate to explore screen with survey defaults.
  void _proceedToExplore() {
    if (!mounted) return;
    // Seed the explore filters with the user's answers so they
    // show up pre-selected when the explore screen loads for the first time.
    context.read<ExploreController>().setSurveyDefaults(
      commuterTypes: _commuterTypes.toList(),
      transport: _transport.toList(),
      safety: _safety.toList(),
    );
    // Mark last route as explore so short inactivity resumes into the shell.
    SessionManager.instance.setLastRoute(AppRouter.explore);
    Navigator.pushReplacementNamed(context, AppRouter.explore);
  }
}

// ── Progress bar ──────────────────────────────────────────────
class _ProgressBar extends StatelessWidget {
  final int current, total;
  const _ProgressBar({required this.current, required this.total});
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 20, 24, 0),
      child: Row(children: List.generate(total, (i) => Expanded(
        child: Container(
          height: 4, margin: const EdgeInsets.symmetric(horizontal: 3),
          decoration: BoxDecoration(
            color: i <= current
              ? _teal
              : _border,
            borderRadius: BorderRadius.circular(2)),
        ),
      ))),
    );
  }
}

// ── Step 1: single select commuter type ─────────────────────
class _StepCommuter extends StatelessWidget {
  final Set<String> selected;
  final List<_Option> options;
  final ValueChanged<String> onToggle;
  const _StepCommuter({
    required this.selected,
    required this.options,
    required this.onToggle,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 32, 24, 16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('Who are you as\na commuter?',
          style: GoogleFonts.plusJakartaSans(
            fontSize: 26, fontWeight: FontWeight.w900, color: _text, height: 1.2)),
        const SizedBox(height: 8),
        Text('This helps us tailor routes to your specific safety needs.',
          style: GoogleFonts.dmSans(fontSize: 14, color: _text2)),
        const SizedBox(height: 28),
        Expanded(child: GridView.count(
          crossAxisCount: 2, mainAxisSpacing: 10, crossAxisSpacing: 10,
          childAspectRatio: 2.2,
          children: options.map((o) {
            final isSelected = selected.contains(o.key);
            return _OptionChip(
              option: o,
              selected: isSelected,
              onTap: () => onToggle(o.key),
            );
          }).toList(),
        )),
      ]),
    );
  }
}

// ── Step 2 & 3: multi select ─────────────────────────────────
class _StepMulti extends StatelessWidget {
  final String title, subtitle;
  final List<_Option> options;
  final Set<String> selected;
  final ValueChanged<String> onToggle;
  const _StepMulti({required this.title, required this.subtitle,
    required this.options, required this.selected, required this.onToggle});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 32, 24, 16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(title,
          style: GoogleFonts.plusJakartaSans(
            fontSize: 26, fontWeight: FontWeight.w900, color: _text, height: 1.2)),
        const SizedBox(height: 8),
        Text(subtitle,
          style: GoogleFonts.dmSans(fontSize: 14, color: _text2)),
        const SizedBox(height: 28),
        Expanded(child: GridView.count(
          crossAxisCount: 2, mainAxisSpacing: 10, crossAxisSpacing: 10,
          childAspectRatio: 2.2,
          children: options.map((o) {
            final isSel = selected.contains(o.key);
            return _OptionChip(
              option: o, selected: isSel,
              onTap: () => onToggle(o.key));
          }).toList(),
        )),
      ]),
    );
  }
}

// ── Option chip ───────────────────────────────────────────────
class _OptionChip extends StatelessWidget {
  final _Option option;
  final bool selected;
  final VoidCallback onTap;
  const _OptionChip({required this.option, required this.selected,
    required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 180),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        decoration: BoxDecoration(
          color: selected ? _teal.withValues(alpha: 0.12) : _card,
          borderRadius: BorderRadius.circular(13),
          border: Border.all(
            color: selected ? _teal : _border,
            width: selected ? 1.5 : 1)),
        child: Row(children: [
          Icon(option.icon,
            size: 18,
            color: selected ? _teal : _text2),
          const SizedBox(width: 8),
          Expanded(child: Text(option.label,
            style: GoogleFonts.plusJakartaSans(
              fontSize: 12, fontWeight: FontWeight.w700,
              color: selected ? _teal : _text),
            maxLines: 2, overflow: TextOverflow.ellipsis)),
        ]),
      ),
    );
  }
}

class _Option {
  final String key, label;
  final IconData icon;
  const _Option(this.key, this.label, this.icon);
}