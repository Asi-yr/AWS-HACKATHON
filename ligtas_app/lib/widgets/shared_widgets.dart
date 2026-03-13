import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../core/app_colors.dart';
import '../core/custom_theme.dart';

// ─────────────────────────────────────────────────────────────────────────────
// APP HEADER
// ─────────────────────────────────────────────────────────────────────────────
class LigtasHeader extends StatelessWidget {
  final String title;
  final Widget? leading;
  final Widget? trailing;
  const LigtasHeader({super.key, required this.title, this.leading, this.trailing});

  @override
  Widget build(BuildContext context) {
    final t = context.lt;
    return Container(
      padding: EdgeInsets.fromLTRB(
          16, MediaQuery.of(context).padding.top + 8, 16, 12),
      decoration: BoxDecoration(
        color: t.card,
        border: Border(bottom: BorderSide(color: t.border))),
      child: Row(
        children: [
          SizedBox(width: 38, child: leading),
          Expanded(child: Center(
            child: Text(title, style: t.title(size: 17)),
          )),
          SizedBox(width: 38, child: trailing),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// SECTION LABEL
// ─────────────────────────────────────────────────────────────────────────────
class SectionLabel extends StatelessWidget {
  final String label;
  final EdgeInsets padding;
  const SectionLabel(this.label,
      {super.key, this.padding = const EdgeInsets.fromLTRB(16, 20, 16, 8)});

  @override
  Widget build(BuildContext context) => Padding(
    padding: padding,
    child: Text(label,
      style: GoogleFonts.plusJakartaSans(
        fontSize: 11, fontWeight: FontWeight.w700,
        color: AppColors.text3(context.isDark), letterSpacing: 0.1)),
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// SETTINGS CARD
// ─────────────────────────────────────────────────────────────────────────────
class SettingsCard extends StatelessWidget {
  final List<Widget> children;
  final EdgeInsets margin;
  const SettingsCard({super.key, required this.children,
    this.margin = const EdgeInsets.fromLTRB(16, 0, 16, 4)});

  @override
  Widget build(BuildContext context) {
    final t = context.lt;
    return Padding(
      padding: margin,
      child: Container(
        decoration: BoxDecoration(
          color: t.card,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: t.border)),
        child: Column(children: children),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// ROW DIVIDER
// ─────────────────────────────────────────────────────────────────────────────
class RowDivider extends StatelessWidget {
  const RowDivider({super.key});
  @override
  Widget build(BuildContext context) => Container(
    height: 1,
    margin: const EdgeInsets.only(left: 56),
    color: AppColors.divider(context.isDark),
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// ROW ICON
// ─────────────────────────────────────────────────────────────────────────────
class RowIcon extends StatelessWidget {
  final IconData icon;
  final bool danger;
  const RowIcon({super.key, required this.icon, this.danger = false});

  @override
  Widget build(BuildContext context) {
    final isDark = context.isDark;
    final bg = danger ? AppColors.redDim : AppColors.iconBg(isDark);
    final color = danger
        ? (isDark ? AppColors.redDark : AppColors.red)
        : AppColors.primaryTeal(isDark);
    return Container(
      width: 36, height: 36,
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(10)),
      child: Icon(icon, color: color, size: 18),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// TOGGLE ROW
// ─────────────────────────────────────────────────────────────────────────────
class ToggleRow extends StatelessWidget {
  final IconData icon;
  final String title, subtitle;
  final bool value;
  final ValueChanged<bool> onChanged;
  const ToggleRow({super.key,
    required this.icon, required this.title, required this.subtitle,
    required this.value, required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    final t = context.lt;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      child: Row(children: [
        RowIcon(icon: icon),
        const SizedBox(width: 12),
        Expanded(child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: t.title(size: 14)),
            if (subtitle.isNotEmpty)
              Text(subtitle, style: t.body(size: 12, color: t.text2)),
          ],
        )),
        Switch.adaptive(
          value: value,
          onChanged: onChanged,
          activeTrackColor: t.teal,
          inactiveThumbColor: Colors.white,
          inactiveTrackColor: t.toggleBg,
        ),
      ]),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// CHEVRON ROW
// ─────────────────────────────────────────────────────────────────────────────
class ChevronRow extends StatelessWidget {
  final IconData icon;
  final String title, subtitle;
  final String? trailing;
  final bool danger;
  final VoidCallback? onTap;
  const ChevronRow({super.key,
    required this.icon, required this.title, this.subtitle = '',
    this.trailing, this.danger = false, this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final t = context.lt;
    final titleColor = danger ? t.red : t.text;
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(16),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 13),
        child: Row(children: [
          RowIcon(icon: icon, danger: danger),
          const SizedBox(width: 12),
          Expanded(child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: t.title(size: 14, color: titleColor)),
              if (subtitle.isNotEmpty)
                Text(subtitle, style: t.body(size: 12, color: t.text2)),
            ],
          )),
          if (trailing != null) ...[
            Text(trailing!, style: t.body(size: 12, color: t.text2)),
            const SizedBox(width: 4),
          ],
          Icon(Icons.chevron_right_rounded, size: 18, color: t.text2),
        ]),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// TEAL BUTTON
// ─────────────────────────────────────────────────────────────────────────────
class TealButton extends StatelessWidget {
  final String label;
  final VoidCallback onTap;
  final bool fullWidth;
  final double vertPad;
  const TealButton({super.key,
    required this.label, required this.onTap,
    this.fullWidth = true, this.vertPad = 14,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = context.isDark;
    return SizedBox(
      width: fullWidth ? double.infinity : null,
      child: ElevatedButton(
        style: ElevatedButton.styleFrom(
          backgroundColor: AppColors.primaryTeal(isDark),
          foregroundColor: Colors.white,
          padding: EdgeInsets.symmetric(vertical: vertPad, horizontal: 20),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          shadowColor: AppColors.tealGlow,
          elevation: 4,
        ),
        onPressed: onTap,
        child: Text(label,
          style: GoogleFonts.plusJakartaSans(fontWeight: FontWeight.w800, fontSize: 14)),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// COMING SOON OVERLAY
// FIX: was hardcoded to dark colors (AppColors.cardDark, AppColors.borderDark,
// AppColors.textDark, AppColors.text2Dark). Now uses context.lt / context.isDark
// so it correctly responds to the Night Mode toggle.
// ─────────────────────────────────────────────────────────────────────────────
class ComingSoonOverlay extends StatelessWidget {
  final VoidCallback onDismiss;
  const ComingSoonOverlay({super.key, required this.onDismiss});

  @override
  Widget build(BuildContext context) {
    // FIX: Read live theme instead of hardcoding dark values
    final t = context.lt;

    return GestureDetector(
      onTap: onDismiss,
      child: Container(
        color: Colors.black54,
        child: Center(
          child: GestureDetector(
            onTap: () {},
            child: Container(
              margin: const EdgeInsets.all(32),
              padding: const EdgeInsets.all(24),
              decoration: BoxDecoration(
                // FIX: was AppColors.cardDark (always dark navy)
                color: t.card,
                borderRadius: BorderRadius.circular(20),
                // FIX: was AppColors.borderDark (always dark border)
                border: Border.all(color: t.border),
              ),
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                Container(
                  width: 52, height: 52,
                  decoration: BoxDecoration(
                    color: AppColors.tealDim,
                    borderRadius: BorderRadius.circular(14)),
                  child: const Icon(Icons.schedule_rounded, color: AppColors.teal, size: 26),
                ),
                const SizedBox(height: 12),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: AppColors.yellow.withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(50),
                    border: Border.all(color: AppColors.yellow.withValues(alpha: 0.4))),
                  child: Text('Beta Roadmap',
                    style: GoogleFonts.plusJakartaSans(
                      fontSize: 10, fontWeight: FontWeight.w700,
                      color: AppColors.yellow)),
                ),
                const SizedBox(height: 10),
                // FIX: was AppColors.textDark (always white)
                Text('Feature Coming Soon',
                  style: GoogleFonts.plusJakartaSans(
                    fontSize: 16, fontWeight: FontWeight.w800,
                    color: t.text)),
                const SizedBox(height: 8),
                // FIX: was AppColors.text2Dark (always dim white)
                Text(
                  'This feature is actively being built and will be available in an upcoming Beta release.',
                  style: GoogleFonts.dmSans(
                    fontSize: 13, color: t.text2, height: 1.5),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 20),
                TealButton(label: 'Got it!', onTap: onDismiss),
              ]),
            ),
          ),
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// TOAST  (inline — put inside a Stack)
// FIX: was hardcoded to AppColors.cardDark / AppColors.borderDark /
// AppColors.textDark. Now uses context.lt so it reflects the active theme.
// ─────────────────────────────────────────────────────────────────────────────
class LigtasToast extends StatelessWidget {
  final bool visible;
  final String message;
  final String type; // 'teal' | 'green' | 'red'
  const LigtasToast({super.key,
    required this.visible, required this.message, this.type = 'teal'});

  Color _dot(bool isDark) => type == 'green' ? AppColors.green
                           : type == 'red'   ? AppColors.redDark
                           : AppColors.teal;

  @override
  Widget build(BuildContext context) {
    // FIX: Read live theme
    final t = context.lt;

    return AnimatedPositioned(
      duration: const Duration(milliseconds: 280),
      curve: Curves.easeOutBack,
      top: visible ? 100 : 64,
      left: 0, right: 0,
      child: IgnorePointer(
        ignoring: !visible,
        child: AnimatedOpacity(
          duration: const Duration(milliseconds: 220),
          opacity: visible ? 1 : 0,
          child: Center(child: Material(
            color: Colors.transparent,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 10),
              decoration: BoxDecoration(
                // FIX: was AppColors.cardDark (always dark navy)
                color: t.card,
                borderRadius: BorderRadius.circular(50),
                // FIX: was AppColors.borderDark (always dark border)
                border: Border.all(color: t.border),
                boxShadow: const [BoxShadow(color: Colors.black26, blurRadius: 20)]),
              child: Row(mainAxisSize: MainAxisSize.min, children: [
                Container(width: 8, height: 8,
                  decoration: BoxDecoration(color: _dot(context.isDark), shape: BoxShape.circle)),
                const SizedBox(width: 8),
                // FIX: was AppColors.textDark (always white)
                Text(message,
                  style: GoogleFonts.plusJakartaSans(
                    color: t.text, fontSize: 13, fontWeight: FontWeight.w600)),
              ]),
            ),
          )),
        ),
      ),
    );
  }
}