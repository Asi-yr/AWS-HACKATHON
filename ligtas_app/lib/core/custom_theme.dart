import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'app_colors.dart';

/// Convenience extension — use in any widget:
///   final t = context.lt;
///   Container(color: t.card, child: Text('Hi', style: t.title))
extension LigtasThemeX on BuildContext {
  bool get isDark => Theme.of(this).brightness == Brightness.dark;
  // Add this 'ignore' line here:
  // ignore: library_private_types_in_public_api
  _LT get lt => _LT(isDark);
}

class _LT {
  final bool dark;
  const _LT(this.dark);

  Color get bg       => AppColors.bg(dark);
  Color get card     => AppColors.card(dark);
  Color get card2    => AppColors.card2(dark);
  Color get border   => AppColors.border(dark);
  Color get divider  => AppColors.divider(dark);
  Color get text     => AppColors.text(dark);
  Color get text2    => AppColors.text2(dark);
  Color get text3    => AppColors.text3(dark);
  Color get iconBg   => AppColors.iconBg(dark);
  Color get teal     => AppColors.primaryTeal(dark);
  Color get tealDim  => AppColors.tealDim;
  Color get red      => dark ? AppColors.redDark   : AppColors.red;
  Color get yellow   => dark ? AppColors.yellowDark: AppColors.yellow;
  Color get blue     => dark ? AppColors.blueDark  : AppColors.blue;
  Color get toggleBg => AppColors.toggleBg(dark);

  TextStyle title({double size = 17, FontWeight w = FontWeight.w800, Color? color}) =>
      GoogleFonts.plusJakartaSans(fontSize: size, fontWeight: w, color: color ?? text);

  TextStyle body({double size = 14, FontWeight w = FontWeight.w400, Color? color}) =>
      GoogleFonts.dmSans(fontSize: size, fontWeight: w, color: color ?? text);

  TextStyle label({double size = 11, Color? color}) =>
      GoogleFonts.plusJakartaSans(
          fontSize: size, fontWeight: FontWeight.w700,
          letterSpacing: 0.08, color: color ?? text3);
}
