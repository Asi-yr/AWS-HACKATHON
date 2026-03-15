import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../core/app_colors.dart';
import '../core/custom_theme.dart';

/// Global overlay toast — mirrors Design.showToast() from main.js.
/// Call: ToastService.show(context, 'Message', ToastType.teal)
enum ToastType { teal, green, red }

class ToastService {
  static OverlayEntry? _entry;
  static bool _visible = false;

  static void show(BuildContext context, String message, ToastType type) {
    _entry?.remove();
    _visible = true;
    _entry = OverlayEntry(builder: (_) => _ToastWidget(message: message, type: type));
    Overlay.of(context).insert(_entry!);
    Future.delayed(const Duration(milliseconds: 2200), () {
      if (_visible) {
        _entry?.remove();
        _visible = false;
      }
    });
  }
}

class _ToastWidget extends StatefulWidget {
  final String message;
  final ToastType type;
  const _ToastWidget({required this.message, required this.type});
  @override State<_ToastWidget> createState() => _ToastWidgetState();
}

class _ToastWidgetState extends State<_ToastWidget>
    with SingleTickerProviderStateMixin {
  late final AnimationController _ctrl;
  late final Animation<double> _opacity;
  late final Animation<Offset> _slide;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 280));
    _opacity = CurvedAnimation(parent: _ctrl, curve: Curves.easeOut);
    _slide   = Tween<Offset>(begin: const Offset(0, -0.3), end: Offset.zero)
        .animate(CurvedAnimation(parent: _ctrl, curve: Curves.easeOutBack));
    _ctrl.forward();
  }

  @override void dispose() { _ctrl.dispose(); super.dispose(); }

  Color get _dotColor {
    switch (widget.type) {
      case ToastType.green: return AppColors.green;
      case ToastType.red:   return AppColors.red;
      case ToastType.teal:  return AppColors.teal;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Positioned(
      top: 100, left: 0, right: 0,
      child: SlideTransition(
        position: _slide,
        child: FadeTransition(
          opacity: _opacity,
          child: Center(
            child: Material(
              color: Colors.transparent,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 10),
                decoration: BoxDecoration(
                  color: AppColors.card(context.isDark),
                  borderRadius: BorderRadius.circular(50),
                  border: Border.all(color: AppColors.border(context.isDark)),
                  boxShadow: const [BoxShadow(color: Colors.black26, blurRadius: 20)],
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 8, height: 8,
                      decoration: BoxDecoration(color: _dotColor, shape: BoxShape.circle),
                    ),
                    const SizedBox(width: 8),
                    Text(widget.message,
                      style: GoogleFonts.plusJakartaSans(
                        color: AppColors.text(context.isDark), fontSize: 13, fontWeight: FontWeight.w600)),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}