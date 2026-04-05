import 'package:flutter/material.dart';
import '../main.dart' show RootShell;
import '../screens/splash/splash_view.dart';
import '../screens/login/login_view.dart';
import '../screens/explore/mini_screen.dart';
import '../screens/profile/profile_view.dart';
import '../screens/community/community_view.dart';
import '../screens/survey/survey_view.dart';

/// Named routes for the entire app.
/// Add new screens here as you build them.
class AppRouter {
  static const splash      = '/';
  static const login       = '/login';
  static const survey      = '/survey';
  static const explore     = '/explore';
  static const profile     = '/profile';
  static const community   = '/community';
  static const miniSearch  = '/explore/search';

  static Route<dynamic> onGenerateRoute(RouteSettings s) {
    switch (s.name) {
      case splash:     return _fade(const SplashView());
      case login:      return _fade(const LoginView());
      case survey:     return _fade(const SurveyView());
      case explore:    return _fade(const RootShell());
      case profile:    return _fade(const ProfileView());
      case community:  return _fade(const CommunityView());
      case miniSearch: return _fadeTransparent(const MiniScreen());
      default:         return _fade(const SplashView());
    }
  }

  static PageRoute _fade(Widget page) => PageRouteBuilder(
    pageBuilder: (_, _, _) => page,
    transitionsBuilder: (_, anim, _, child) => FadeTransition(
      opacity: CurvedAnimation(parent: anim, curve: Curves.easeOut),
      child: child),
    transitionDuration: const Duration(milliseconds: 220),
  );

  /// Same as [_fade] but keeps the route non-opaque so backgrounds beneath
  /// (e.g. the map in ExploreView) remain visible.
  static PageRoute _fadeTransparent(Widget page) => PageRouteBuilder(
    opaque: false,
    pageBuilder: (_, _, _) => page,
    transitionsBuilder: (_, anim, _, child) => FadeTransition(
      opacity: CurvedAnimation(parent: anim, curve: Curves.easeOut),
      child: child),
    transitionDuration: const Duration(milliseconds: 220),
  );
}