import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'app_colors.dart';

ThemeData buildLightTheme() => ThemeData(
  brightness: Brightness.light,
  scaffoldBackgroundColor: AppColors.bgLight,
  colorScheme: const ColorScheme.light(
    primary: AppColors.teal, surface: AppColors.cardLight, error: AppColors.red),
  textTheme: _textTheme(AppColors.textLight),
  dividerColor: AppColors.dividerLight,
  useMaterial3: true,
);

ThemeData buildDarkTheme() => ThemeData(
  brightness: Brightness.dark,
  scaffoldBackgroundColor: AppColors.bgDark,
  colorScheme: const ColorScheme.dark(
    primary: AppColors.tealBright, surface: AppColors.cardDark, error: AppColors.redDark),
  textTheme: _textTheme(AppColors.textDark),
  dividerColor: AppColors.dividerDark,
  useMaterial3: true,
);

TextTheme _textTheme(Color base) => TextTheme(
  displayLarge: GoogleFonts.plusJakartaSans(fontWeight: FontWeight.w900, color: base),
  titleLarge:   GoogleFonts.plusJakartaSans(fontWeight: FontWeight.w800, color: base),
  titleMedium:  GoogleFonts.plusJakartaSans(fontWeight: FontWeight.w700, color: base),
  bodyLarge:    GoogleFonts.dmSans(fontWeight: FontWeight.w400, color: base),
  bodyMedium:   GoogleFonts.dmSans(fontWeight: FontWeight.w400, color: base),
  labelSmall:   GoogleFonts.plusJakartaSans(
      fontWeight: FontWeight.w700, letterSpacing: 0.1, color: base),
);
