import 'package:flutter/material.dart';

/// Color tokens — mirrors :root and [data-theme="dark"] in main.css.
class AppColors {
  AppColors._();

  static const teal       = Color(0xFF0D9E9E);
  static const tealLight  = Color(0xFF0FB9B9);
  static const tealBright = Color(0xFF12D9C0);
  static const tealDim    = Color(0x1A0D9E9E);
  static const tealGlow   = Color(0x4D0D9E9E);

  static const green      = Color(0xFF34D399);
  static const greenDim   = Color(0x1F34D399);
  static const red        = Color(0xFFF43F5E);
  static const redDark    = Color(0xFFFB7185);
  static const redDim     = Color(0x1AF43F5E);
  static const yellow     = Color(0xFFFACC15);
  static const yellowDark = Color(0xFFFDE047);
  static const yellowDim  = Color(0x1FFACC15);
  static const blue       = Color(0xFF3B9EFF);
  static const blueDark   = Color(0xFF60AEFF);
  static const blueDim    = Color(0x1F3B9EFF);

  static const safeGreen  = Color(0xFF059669);
  static const safeAmber  = Color(0xFFD97706);
  static const safeRed    = Color(0xFFDC2626);

  static const gold       = Color(0xFFD4A017);
  static const goldActive = Color(0xFFF5C518);

  // Light
  static const bgLight      = Color(0xFFF0F4F8);
  static const cardLight    = Color(0xFFFFFFFF);
  static const card2Light   = Color(0xFFF5F8FB);
  static const borderLight  = Color(0xFFE0E8F0);
  static const border2Light = Color(0xFFC8D8E8);
  static const dividerLight = Color(0xFFEEF2F7);
  static const textLight    = Color(0xFF0F1F35);
  static const text2Light   = Color(0xFF7A94AD);
  static const text3Light   = Color(0xFFA0B4C8);
  static const iconBgLight  = Color(0xFFEEF4FB);
  static const toggleOff    = Color(0xFFD0DCE8);

  // Dark
  static const bgDark       = Color(0xFF0B1120);
  static const cardDark     = Color(0xFF111C2E);
  static const card2Dark    = Color(0xFF162030);
  static const borderDark   = Color(0xFF1E3A5F);
  static const border2Dark  = Color(0xFF1A2D47);
  static const dividerDark  = Color(0xFF1A2D47);
  static const textDark     = Color(0xFFE8F0F8);
  static const text2Dark    = Color(0xFF6B8AAD);
  static const text3Dark    = Color(0xFF4A6080);
  static const iconBgDark   = Color(0xFF1A2D47);
  static const toggleOffDk  = Color(0xFF2A3D56);

  static const rankCandle     = Color(0xFF34D399);
  static const rankLantern    = Color(0xFF3B9EFF);
  static const rankLighthouse = Color(0xFFFACC15);

  static const tagFastest  = Color(0xFF0D9E9E);
  static const tagBalanced = Color(0xFF3B82F6);
  static const tagCheapest = Color(0xFF34D399);
  static const tagSafest   = Color(0xFF12D9C0);
  static const tagModerate = Color(0xFFD97706);
  static const tagDanger   = Color(0xFFFB7185);

  static Color get chipBg => const Color(0xFFF5F5F5); // Example light grey
static Color get chipCommuter => const Color(0xFF008080); // Example teal

  // Helpers
  static Color bg(bool d)      => d ? bgDark     : bgLight;
  static Color card(bool d)    => d ? cardDark    : cardLight;
  static Color card2(bool d)   => d ? card2Dark   : card2Light;
  static Color border(bool d)  => d ? borderDark  : borderLight;
  static Color divider(bool d) => d ? dividerDark : dividerLight;
  static Color text(bool d)    => d ? textDark    : textLight;
  static Color text2(bool d)   => d ? text2Dark   : text2Light;
  static Color text3(bool d)   => d ? text3Dark   : text3Light;
  static Color iconBg(bool d)  => d ? iconBgDark  : iconBgLight;
  static Color toggleBg(bool d) => d ? toggleOffDk : toggleOff;
  static Color primaryTeal(bool d) => d ? tealBright : teal;
}
