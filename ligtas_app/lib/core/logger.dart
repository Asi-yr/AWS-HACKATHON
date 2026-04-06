import 'package:flutter/foundation.dart';

/// Simple logger utility for the app.
/// Centralizes all debug, info, warning, and error logging.
/// Uses debugPrint which is automatically stripped from release builds.
class Logger {
  static const String _prefix = '[LIGTAS]';

  /// Log debug message (only in debug mode)
  static void debug(String message) {
    debugPrint('$_prefix [DEBUG] $message');
  }

  /// Log info message (only in debug mode)
  static void info(String message) {
    debugPrint('$_prefix [INFO] $message');
  }

  /// Log warning message (only in debug mode)
  static void warning(String message) {
    debugPrint('$_prefix [WARN] $message');
  }

  /// Log error message (only in debug mode)
  static void error(String message, [Object? error, StackTrace? stackTrace]) {
    debugPrint('$_prefix [ERROR] $message');
    if (error != null) {
      debugPrint('$_prefix [ERROR] Exception: $error');
    }
    if (stackTrace != null) {
      debugPrint('$_prefix [ERROR] Stack: $stackTrace');
    }
  }
}
