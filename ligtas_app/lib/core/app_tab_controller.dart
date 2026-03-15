import 'package:flutter/material.dart';

/// Minimal tab-switch notifier so any screen can request the root shell
/// to switch to a specific bottom-nav tab.
///
/// Usage (from any widget with Provider in scope):
///   context.read[AppTabController]().switchTo(0); // go to Home/Explore
class AppTabController extends ChangeNotifier {
  int _index = 0;
  int get index => _index;

  void switchTo(int i) {
    if (_index == i) return;
    _index = i;
    notifyListeners();
  }
}
